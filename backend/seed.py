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
    have = catalog.known_urls(models)
    return [e for e in entries() if e["url"] not in have]


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
        if i % 10 == 0:
            print(f"[seed] {i}/{len(todo)} processed · catalog {catalog.count()}", file=sys.stderr)
        time.sleep(batch_pause)
    return done


def warm() -> None:
    """Background import of whatever seed entries the catalog is missing."""
    global _running
    if _running:
        return
    todo = missing(False)
    if not todo:
        return
    _running = True
    print(f"[seed] importing {len(todo)} bundled listings in the background…", file=sys.stderr)

    def run():
        global _running
        try:
            n = load(False)
            print(f"[seed] done — {n} listings ready (catalog {catalog.count()})", file=sys.stderr)
        finally:
            _running = False

    threading.Thread(target=run, daemon=True).start()
