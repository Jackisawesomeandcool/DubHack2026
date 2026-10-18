"""The shared dataset: the catalog + its cutout images, committed to git so a teammate's
`git pull` is all it takes to get everything.

    python3 dataset.py export    # your local catalog -> backend/dataset/   (then commit + push)
    python3 dataset.py load      # backend/dataset/ -> your local catalog   (the server also does this on start)
    python3 dataset.py status    # how your local catalog and the dataset differ

backend/dataset/
    catalog.json     one product per line (so git diffs and merges are readable)
    removed.json     URLs removed by hand in view_catalog.py: they are deleted locally on load and
                     never re-added by scrapers
    cutouts/*.png    the product images, shrunk to <= 900 px and 256 colors (~70 KB each instead of ~400 KB)

Rules that keep teammates from clobbering each other
  - export MERGES into the dataset: it adds/updates your products and never drops one just because
    you do not have it locally. Only products you removed with the review tool are removed.
  - a product you restored locally is taken off the removed list.
  - load never deletes products that are not in the dataset, so your own scrapes survive a pull.
  - when both sides have a product, the dataset's cutout wins (it is the curated one); stock/price
    come from whichever was checked more recently.
Image files with the same name are never rewritten, so unchanged images add nothing to git history.
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
import time
from pathlib import Path

import catalog
import config

DIR = Path(config.BACKEND_DIR) / "dataset"
ITEMS = DIR / "catalog.json"
REMOVED = DIR / "removed.json"
IMG = DIR / "cutouts"
LOCAL_IMG = Path(config.DATA_DIR) / "cutouts"
MAX_SIDE = 900
FIELDS = ["url", "name", "brand", "price", "category", "tags", "cutout_p", "cutout_m", "stock", "source", "last_checked", "added_at"]


# ---------------------------------------------------------------- files
def _read_items() -> dict[str, dict]:
    try:
        data = json.loads(ITEMS.read_text(encoding="utf-8"))
        return {it["url"]: it for it in data.get("items", [])}
    except (OSError, json.JSONDecodeError, KeyError):
        return {}


def _read_removed() -> set[str]:
    try:
        return set(json.loads(REMOVED.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return set()


def _write_items(items: dict[str, dict]) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(items[u], ensure_ascii=False, separators=(",", ":")) for u in sorted(items)]
    ITEMS.write_text('{"version":1,"items":[\n' + ",\n".join(lines) + "\n]}\n", encoding="utf-8")


def _name(path: str | None) -> str | None:
    return path.rsplit("/", 1)[-1] if path else None


def _shrink(src: Path, dst: Path) -> bool:
    from PIL import Image
    try:
        im = Image.open(src).convert("RGBA")
        im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
        q = im.quantize(colors=256, method=Image.Quantize.FASTOCTREE)    # keeps transparency
        dst.parent.mkdir(parents=True, exist_ok=True)
        q.save(dst, "PNG", optimize=True)
        return True
    except Exception as err:  # noqa: BLE001
        print(f"  could not convert {src.name}: {err}", file=sys.stderr)
        return False


# ---------------------------------------------------------------- export
def export(quiet: bool = False) -> dict:
    with catalog._lock:
        db = catalog._db()
        local = [dict(r) for r in db.execute("SELECT * FROM products")]
        blocked = {r[0] for r in db.execute("SELECT url FROM blocked")}
    have = {r["url"] for r in local}
    items = _read_items()
    removed = (_read_removed() | blocked) - have          # restored locally -> no longer removed
    stats = {"added": 0, "updated": 0, "images": 0, "dropped": 0, "missing_image": 0}

    for r in local:
        cp, cm = _name(r["cutout_p"]), _name(r["cutout_m"])
        for n in (cp, cm):
            if n and not (IMG / n).exists():
                if (LOCAL_IMG / n).exists() and _shrink(LOCAL_IMG / n, IMG / n):
                    stats["images"] += 1
        cp = cp if cp and (IMG / cp).exists() else None
        cm = cm if cm and (IMG / cm).exists() else None
        if not (cp or cm):
            stats["missing_image"] += 1
            continue
        row = {k: r[k] for k in FIELDS}
        row["cutout_p"], row["cutout_m"] = cp, cm
        old = items.get(r["url"])
        if old is None:
            stats["added"] += 1
        elif (old.get("last_checked") or 0) > (r["last_checked"] or 0) and old.get("cutout_p") == cp:
            continue                                       # dataset copy is newer and identical image: keep it
        elif old != row:
            stats["updated"] += 1
        items[r["url"]] = row

    for u in list(items):
        if u in removed:
            del items[u]
            stats["dropped"] += 1
    _write_items(items)
    DIR.mkdir(parents=True, exist_ok=True)
    REMOVED.write_text(json.dumps(sorted(removed), indent=0) + "\n", encoding="utf-8")

    keep = {n for it in items.values() for n in (it.get("cutout_p"), it.get("cutout_m")) if n}
    if IMG.exists():
        for f in IMG.glob("*.png"):
            if f.name not in keep:
                f.unlink()                                 # image of a product that was removed
    size = sum(f.stat().st_size for f in IMG.glob("*.png")) / 1e6 if IMG.exists() else 0
    stats.update(total=len(items), removed=len(removed), megabytes=round(size, 1))
    if not quiet:
        print(f"dataset: {stats['total']} products ({stats['added']} new, {stats['updated']} updated, "
              f"{stats['dropped']} dropped), {stats['images']} images written, {stats['megabytes']} MB of images, "
              f"{stats['removed']} on the removed list.")
        if stats["missing_image"]:
            print(f"  ({stats['missing_image']} local products skipped: image file missing)")
    return stats


# ---------------------------------------------------------------- load
def load(quiet: bool = False) -> dict:
    """dataset/ -> local catalog. Cheap enough to run on every server start."""
    stats = {"added": 0, "updated": 0, "removed": 0, "images": 0}
    if not ITEMS.exists():
        return stats
    items, removed = _read_items(), _read_removed()
    LOCAL_IMG.mkdir(parents=True, exist_ok=True)
    changed = False
    with catalog._lock:
        db = catalog._db()
        for u in removed:
            if db.execute("SELECT 1 FROM products WHERE url=?", (u,)).fetchone():
                db.execute("DELETE FROM products WHERE url=?", (u,))
                stats["removed"] += 1
                changed = True
            db.execute("INSERT OR IGNORE INTO blocked (url, removed_at, snapshot) VALUES (?,?,NULL)", (u, time.time()))
        for u, it in items.items():
            if u in removed:
                continue
            paths = {}
            for k in ("cutout_p", "cutout_m"):
                n = it.get(k)
                if n and (IMG / n).exists():
                    if not (LOCAL_IMG / n).exists():
                        shutil.copy2(IMG / n, LOCAL_IMG / n)
                        stats["images"] += 1
                    paths[k] = "/cutouts/" + n
                else:
                    paths[k] = None
            if not (paths["cutout_p"] or paths["cutout_m"]):
                continue
            row = db.execute("SELECT * FROM products WHERE url=?", (u,)).fetchone()
            if row is None:
                vals = [it.get(c) for c in FIELDS]
                vals[FIELDS.index("cutout_p")], vals[FIELDS.index("cutout_m")] = paths["cutout_p"], paths["cutout_m"]
                db.execute(f"INSERT INTO products ({', '.join(FIELDS)}) VALUES ({', '.join('?' * len(FIELDS))})", vals)
                stats["added"] += 1
                changed = True
                continue
            upd: dict = {}
            if paths["cutout_p"] and row["cutout_p"] != paths["cutout_p"]:
                upd["cutout_p"] = paths["cutout_p"]          # the dataset's image is the curated one
            if paths["cutout_m"] and not row["cutout_m"]:
                upd["cutout_m"] = paths["cutout_m"]
            tags = set((row["tags"] or "").split()) | set((it.get("tags") or "").split())
            if tags != set((row["tags"] or "").split()):
                upd["tags"] = " ".join(sorted(tags))
            if (it.get("last_checked") or 0) > (row["last_checked"] or 0):
                for c in ("stock", "price", "last_checked"):
                    if it.get(c) is not None and it[c] != row[c]:
                        upd[c] = it[c]
            if upd:
                db.execute(f"UPDATE products SET {', '.join(f'{k}=?' for k in upd)} WHERE url=?", (*upd.values(), u))
                stats["updated"] += 1
                changed = True
        if changed:
            db.execute("DELETE FROM results")
        db.commit()
    if not quiet and (stats["added"] or stats["updated"] or stats["removed"]):
        print(f"[dataset] {stats['added']} products added, {stats['updated']} updated, {stats['removed']} removed, "
              f"{stats['images']} images copied (catalog {catalog.count()})", file=sys.stderr)
    return stats


def status() -> None:
    items, removed = _read_items(), _read_removed()
    with catalog._lock:
        local = {r[0] for r in catalog._db().execute("SELECT url FROM products")}
    print(f"dataset: {len(items)} products, {len(removed)} removed | local catalog: {len(local)} products")
    print(f"  only in the dataset (a load would add): {len([u for u in items if u not in local and u not in removed])}")
    print(f"  only local (an export would add):       {len([u for u in local if u not in items])}")
    print(f"  removed in the dataset but still local: {len([u for u in removed if u in local])}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["export", "load", "status"])
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    if a.cmd == "export":
        export(a.quiet)
    elif a.cmd == "load":
        s = load(a.quiet)
        if not a.quiet:
            print(f"loaded: {s['added']} added, {s['updated']} updated, {s['removed']} removed, {s['images']} images copied; catalog {catalog.count()}")
    else:
        status()


if __name__ == "__main__":
    main()
