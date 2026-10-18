"""Search orchestration — catalog only, streamed as NDJSON events:

    {"items": [...]}       finished products (every catalog product already has its cutout)
    {"reason": "..."}      only when items is empty: why, e.g. "No shoes under $50 — cheapest is $55"
    {"done": true}

The `append` / `image` / `drop` events of the old live-search flow are no
longer emitted; the frontend still understands them, so nothing breaks there.
The `reason` event is new and additive — today's frontend ignores it and shows
its own "no alternatives found" line; a later UI can display the sentence.

    prompt ──intent.parse──▶ hard constraints (price, category, brand, color)
           ──catalog.candidates──▶ every product within them
           ──ranker.rank──▶ the AI picks the best `count` for the request
                            (keyword ranking when no AI key is configured)

`results()` raises NoMatch with the human-readable reason; `stream()` turns
that into the empty-items + reason events (HTTP 200). Results are cached for
an hour per *parsed* intent, so phrasing variants share the cache.
"""

import sys
import time

import catalog
import intent as intent_mod
import ranker

COUNT = 6


class NoMatch(Exception):
    """Nothing in the catalog satisfies the request; str(err) is the reason to show."""


def _reason(it: intent_mod.Intent) -> str:
    what = "/".join(it.categories) if it.categories else "items"
    if it.brands:
        what = f"{'/'.join(it.brands)} {what}"
    if it.colors:
        what = f"{'/'.join(it.colors)} {what}"
    if it.price_max is not None:
        floor = catalog.floor_price(it)
        tail = f" — cheapest is ${floor:,.0f}" if floor else ""
        return f"No {what} under ${it.price_max:,.0f}{tail}"
    if it.price_min is not None:
        return f"No {what} over ${it.price_min:,.0f}"
    if it.brands or it.colors or it.categories:
        return f"No {what} in the catalog"
    return f"Nothing in the catalog matches \"{it.raw.strip()}\""


def _dedupe(items: list[dict]) -> list[dict]:
    """One entry per product name (the dataset has several colorways of some products)."""
    seen, out = set(), []
    for i in items:
        k = i["name"].lower()
        if k not in seen:
            seen.add(k)
            out.append(i)
    return out


def results(prompt: str, category: str | None = None, exclude: list[str] | None = None,
            models: bool = False, count: int = COUNT) -> list[dict]:
    """Finished products for a request (all from the catalog). Raises NoMatch."""
    exclude = exclude or []
    t0 = time.time()
    it = intent_mod.parse(prompt, category)

    cached = catalog.cached_results(it, models, exclude)
    if cached:
        print(f"[finder] {it.describe()} · cache hit {1000 * (time.time() - t0):.0f}ms · {len(cached)} items", file=sys.stderr)
        return cached[:count]

    pool = _dedupe(catalog.candidates(it, models, exclude))
    if not pool:
        reason = _reason(it)
        print(f"[finder] {it.describe()} · 0 candidates · {reason}", file=sys.stderr)
        raise NoMatch(reason)

    picked, source = ranker.rank(prompt, it, pool, count, models, exclude)
    picked = _dedupe(picked)
    print(f"[finder] {it.describe()} · {len(pool)} candidates → {len(picked)} via {source} · {1000 * (time.time() - t0):.0f}ms",
          file=sys.stderr)
    if not picked:
        raise NoMatch(f"Nothing in the catalog matches \"{prompt.strip()}\"")
    catalog.cache_results(it, models, picked)
    return picked


def stream(prompt: str, category: str | None = None, exclude: list[str] | None = None,
           models: bool = False, count: int = COUNT, local_first: bool = True):
    """NDJSON event generator for /api/suggest. `local_first` is accepted for
    compatibility and ignored: everything is local now."""
    try:
        items = results(prompt, category, exclude, models, count)
    except NoMatch as err:
        yield {"items": []}
        yield {"reason": str(err)}
        yield {"done": True}
        return
    yield {"items": items}
    yield {"done": True}


def find(prompt: str, models: bool = False, category: str | None = None, exclude: list[str] | None = None,
         count: int = COUNT, local_first: bool = True) -> list[dict]:
    """Non-streaming variant (fits, warm-up). Empty list instead of NoMatch."""
    try:
        return results(prompt, category, exclude, models, count)
    except NoMatch:
        return []
