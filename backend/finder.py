"""Search orchestration, fastest source first, streamed as NDJSON events:

    {"items": [...]}                 catalog hits — finished, with cutouts (instant)
    {"append": [...]}                live products found (no images yet)
    {"index": i, "image": "..."}     cutout ready for item i (index into the full list)
    {"index": i, "drop": true}       no suitable photo; drop item i
    {"done": true}

Sources: local catalog → nike.com search API → Grok web search.
Everything that finishes with a cutout is added to the catalog.
"""

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import catalog
import cutouts
import grok
import nike
from products import normalize_list

LIVE_COUNT = 6


def _same(a: dict, b: dict) -> bool:
    return a.get("name", "").lower() == b.get("name", "").lower()


def _live(prompt: str, category: str | None, exclude: list[str], count: int) -> tuple[list[dict], str]:
    """Products from the fastest live source that answers."""
    t0 = time.time()
    items = nike.search(prompt, count=max(12, count * 2))
    if items:
        items = normalize_list(items)
        if category:
            items = [i for i in items if i["category"] == category] or items
        ex = {n.lower() for n in exclude}
        items = [i for i in items if i["name"].lower() not in ex][:count]
        if items:
            print(f"[finder] nike.com search {time.time() - t0:.1f}s → {len(items)}", file=sys.stderr)
            return items, "nike"
    items = grok.search_products(prompt, category, exclude, count)
    print(f"[finder] grok search {time.time() - t0:.1f}s → {len(items)}", file=sys.stderr)
    return items, "grok"


def stream(prompt: str, category: str | None = None, exclude: list[str] | None = None,
           models: bool = False, count: int = LIVE_COUNT, local_first: bool = True):
    exclude = exclude or []
    have: list[dict] = []

    if local_first:
        hits = catalog.search(prompt, category, models, exclude, limit=count)
        for h in hits:
            h.pop("tags", None); h.pop("seen", None); h.pop("models", None)
        if hits:
            have.extend(hits)
            yield {"items": hits}

    want = count - len(have) + (2 if have else 0)
    if want <= 0 and have:
        yield {"done": True}
        return

    try:
        live, source = _live(prompt, category, exclude + [h["name"] for h in have], want)
    except grok.GrokError as err:
        if have:
            yield {"done": True}
            return
        raise
    live = [i for i in live if not any(_same(i, h) for h in have)]
    if not live:
        yield {"done": True}
        return

    base = len(have)
    yield {"append": [{**i, "image": "", "image_product": None, "image_model": None} for i in live]}

    t1 = time.time()
    kept = []
    with ThreadPoolExecutor(max_workers=min(4, len(live))) as pool:
        futures = {pool.submit(cutouts.resolve, it, models): i for i, it in enumerate(live)}
        for fut in as_completed(futures):
            i = futures[fut]
            try:
                fut.result()
            except Exception as err:  # noqa: BLE001
                print(f"[cutouts] {err}", file=sys.stderr)
                live[i]["image"] = ""
            if live[i]["image"]:
                kept.append(live[i])
                yield {"index": base + i, "image": live[i]["image"]}
            else:
                yield {"index": base + i, "drop": True}
    print(f"[finder] {source}: photos {time.time() - t1:.1f}s · {len(kept)}/{len(live)} cutouts", file=sys.stderr)
    catalog.add(kept, models, prompt)
    yield {"done": True}


def find(prompt: str, models: bool = False, category: str | None = None, exclude: list[str] | None = None,
         count: int = LIVE_COUNT, local_first: bool = True) -> list[dict]:
    """Non-streaming: finished products with cutouts."""
    items: list[dict] = []
    for ev in stream(prompt, category, exclude, models, count, local_first):
        if "items" in ev:
            items.extend(ev["items"])
        elif "append" in ev:
            items.extend(ev["append"])
        elif "image" in ev:
            items[ev["index"]]["image"] = ev["image"]
        elif ev.get("drop"):
            items[ev["index"]]["image"] = ""
    return [i for i in items if i.get("image")]
