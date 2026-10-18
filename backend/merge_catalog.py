"""Merge a teammate's scraped data into yours.

    python3 merge_catalog.py ~/Downloads/data --dry-run     # see what would change
    python3 merge_catalog.py ~/Downloads/data               # do it

`other` is their backend/data folder (or the folder that contains it): it needs
catalog.sqlite and the cutouts/ images next to it. Safe to run repeatedly.

Rules
  - Products are matched by URL. New products are added with their cutout images.
  - Cutout file names are hashes of the source photo URL, so identical photos have
    identical names: existing files are never overwritten, duplicates collapse.
  - For a product you both have: missing cutouts are filled in, tags are unioned, and
    the stock/price/last_checked from whoever checked it most recently win.
  - Products whose cutout image is missing from their folder are skipped.
  - Cached searches (results table) and fits.json are NOT merged; they rebuild themselves.
Stop your backend server before merging.
"""

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path

import catalog
import config

COLS = ["url", "name", "brand", "price", "category", "tags", "cutout_p", "cutout_m", "stock", "source", "last_checked", "added_at"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("other", help="teammate's backend/data folder (or its parent)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = Path(args.other).expanduser().resolve()
    if not (src / "catalog.sqlite").exists() and (src / "data" / "catalog.sqlite").exists():
        src = src / "data"
    if not (src / "catalog.sqlite").exists():
        sys.exit(f"No catalog.sqlite in {src}")
    if src == config.DATA_DIR.resolve():
        sys.exit("That is your own data folder.")

    dst_cut = config.DATA_DIR / "cutouts"
    if not args.dry_run:
        dst_cut.mkdir(parents=True, exist_ok=True)

    other = sqlite3.connect(f"file:{src / 'catalog.sqlite'}?mode=ro", uri=True)
    other.row_factory = sqlite3.Row
    rows = other.execute("SELECT * FROM products").fetchall()

    def resolve(path: str | None) -> str | None:
        """Make sure the cutout behind `path` exists in our folder (copy it); None if it can't."""
        if not path or not path.startswith("/cutouts/"):
            return None
        name = Path(path).name
        if (dst_cut / name).exists():
            return path
        src_png = src / "cutouts" / name
        if not src_png.exists():
            return None
        if not args.dry_run:
            shutil.copy2(src_png, dst_cut / name)
        stats["files"] += 1
        return path

    stats = {"added": 0, "updated": 0, "same": 0, "skipped": 0, "files": 0}
    with catalog._lock:
        mine = catalog._db()
        mine.row_factory = sqlite3.Row
        for r in rows:
            cp, cm = resolve(r["cutout_p"]), resolve(r["cutout_m"])
            have = mine.execute("SELECT * FROM products WHERE url=?", (r["url"],)).fetchone()
            if not have:
                if not (cp or cm):
                    stats["skipped"] += 1
                    continue
                vals = [r[c] for c in COLS]
                vals[COLS.index("cutout_p")], vals[COLS.index("cutout_m")] = cp, cm
                if not args.dry_run:
                    mine.execute(f"INSERT INTO products ({', '.join(COLS)}) VALUES ({', '.join('?' * len(COLS))})", vals)
                stats["added"] += 1
                continue
            changes: dict = {}
            if not have["cutout_p"] and cp:
                changes["cutout_p"] = cp
            if not have["cutout_m"] and cm:
                changes["cutout_m"] = cm
            tags = set((have["tags"] or "").split()) | set((r["tags"] or "").split())
            if tags != set((have["tags"] or "").split()):
                changes["tags"] = " ".join(sorted(tags))
            if (r["last_checked"] or 0) > (have["last_checked"] or 0):
                for c in ("stock", "price", "last_checked"):
                    if r[c] != have[c]:
                        changes[c] = r[c]
            if changes:
                if not args.dry_run:
                    sets = ", ".join(f"{k}=?" for k in changes)
                    mine.execute(f"UPDATE products SET {sets} WHERE url=?", (*changes.values(), r["url"]))
                stats["updated"] += 1
            else:
                stats["same"] += 1
        if not args.dry_run:
            mine.commit()

    # Source-photo cache (source URL -> cutout file): lets later runs skip downloads.
    their_cache, my_cache = src / "cutouts.json", config.DATA_DIR / "cutouts.json"
    if their_cache.exists() and not args.dry_run:
        try:
            theirs = json.loads(their_cache.read_text(encoding="utf-8"))
            mine_c = json.loads(my_cache.read_text(encoding="utf-8")) if my_cache.exists() else {}
            for k, v in theirs.items():
                if k not in mine_c and (not isinstance(v, dict) or "file" not in v or (dst_cut / v["file"]).exists()):
                    mine_c[k] = v
            my_cache.write_text(json.dumps(mine_c), encoding="utf-8")
        except (OSError, json.JSONDecodeError) as err:
            print(f"(skipped cutouts.json merge: {err})", file=sys.stderr)

    verb = "would be" if args.dry_run else "were"
    print(f"{len(rows)} products in their catalog: {stats['added']} {verb} added, {stats['updated']} updated, "
          f"{stats['same']} already identical, {stats['skipped']} skipped (cutout image missing); "
          f"{stats['files']} cutout images {verb} copied.")
    if not args.dry_run:
        print(f"Your catalog now has {catalog.count()} products.")


if __name__ == "__main__":
    main()
