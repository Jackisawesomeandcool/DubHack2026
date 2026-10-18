"""Bundled seed listings (backend/seed/*.json) → catalog.

Each seed entry is a real listing: name, brand, price, url, category, stock,
and the listing's photo URLs. On startup, any entry not yet in the catalog is
run through the cutout pipeline (local, free) in the background and stored,
so the app is fully populated without any search API.
"""

import json
import sys
import threading
import time

import catalog
import config
import cutouts
from products import normalize

SEED_DIR = config.BACKEND_DIR / "seed"
_running = False


def entries() -> list[dict]:
    out = []
    for path in sorted(SEED_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as err:
            print(f"[seed] cannot read {path.name}: {err}", file=sys.stderr)
            continue
        for raw in data.get("items", []):
            item = normalize(raw)
            if item and raw.get("candidates"):
                item["candidates"] = [c for c in raw["candidates"] if isinstance(c, str) and c.startswith("http")]
                out.append(item)
    return out


def missing(models: bool = False) -> list[dict]:
    """Seed entries with no cutout for this mode yet (absent, or still raw photo)."""
    have = catalog.known_urls(models) - catalog.raw_urls(models)
    return [e for e in entries() if e["url"] not in have]


def preload() -> int:
    """Instantly register every seed listing with the retailer's own photo.

    Nothing is downloaded: the browser loads the photo straight from the
    retailer, so the board works the moment the server is up (even offline
    from nike.com). The background pass later swaps in transparent cutouts.
    """
    known = catalog.known_urls(None)
    todo = [e for e in entries() if e["url"] not in known and e.get("candidates")]
    for e in todo:
        photo = cutouts._fullres(e["candidates"][0])
        it = dict(e, image=photo)
        it.pop("candidates", None)
        catalog.upsert([it], False, query=it["name"], source="seed")
        catalog.upsert([it], True, query=it["name"], source="seed")
    return len(todo)


def load(models: bool = False, batch_pause: float = 0.2) -> int:
    """Synchronously import missing seed entries; returns how many got a cutout."""
    todo = missing(models)
    done = 0
    for i, item in enumerate(todo, 1):
        it = dict(item)
        try:
            cutouts.resolve(it, models)
        except Exception as err:  # noqa: BLE001
            print(f"[seed] {it['name']}: {err}", file=sys.stderr)
            it["image"] = ""
        if it["image"]:
            catalog.upsert([it], models, query=it["name"], source="seed")
            done += 1
        else:
            cutout_fail(it["url"])
        if i % 10 == 0:
            print(f"[seed] {i}/{len(todo)} processed · catalog {catalog.count()}", file=sys.stderr)
        time.sleep(batch_pause)
    return done


_failed: dict[str, int] = {}


def cutout_fail(url: str) -> None:
    _failed[url] = _failed.get(url, 0) + 1


def warm() -> None:
    """Background import of whatever seed entries the catalog is missing."""
    global _running
    if _running:
        return
    n = preload()
    if n:
        print(f"[seed] {n} bundled listings ready (catalog {catalog.count()})", file=sys.stderr)
    todo = [e for e in missing(False) if _failed.get(e["url"], 0) < 2]
    if not todo:
        return
    _running = True
    print(f"[seed] building transparent cutouts for {len(todo)} listings in the background…", file=sys.stderr)

    def run():
        global _running
        try:
            n = load(False)
            print(f"[seed] cutouts done — {n} built (catalog {catalog.count()})", file=sys.stderr)
        finally:
            _running = False

    threading.Thread(target=run, daemon=True).start()
