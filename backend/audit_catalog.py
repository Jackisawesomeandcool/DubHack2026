"""Find catalog items whose cutout still shows a person, and (optionally) crop them to just the clothes.

    python3 audit_catalog.py                 # list suspects (read-only)
    python3 audit_catalog.py --fix           # re-download the original photo and keep ONLY the garment
    python3 audit_catalog.py --fix --remove  # ...and delete the ones that can't be cropped cleanly
    python3 audit_catalog.py --remove        # just delete every flagged item

Detection: quality.py (local person detector + skin check). Cropping: garment.py (local cloth
segmentation; tops, outerwear and bottoms). Neither needs an API key. Bags/shoes/headwear that
show a person can't be cropped; they stay in the list (or are deleted with --remove).
The first --fix run downloads a 170 MB model. Stop the server first. Safe to re-run.
"""

import argparse
import sys
from pathlib import Path

import catalog
import config
import cutouts
import garment
import quality


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true", help="crop flagged clothing down to just the garment")
    ap.add_argument("--remove", action="store_true", help="delete flagged items (with --fix: only those that could not be fixed)")
    ap.add_argument("--limit", type=int, default=0, help="stop after fixing N items (testing)")
    args = ap.parse_args()
    if not quality.available():
        sys.exit("Needs: pip install onnxruntime numpy (and internet once to fetch the 20 MB model).")
    if args.fix and not garment.available():
        sys.exit("Cropping needs: pip install onnxruntime numpy scipy (and internet once for the 170 MB model).")

    cache = cutouts._load_cache()
    source_of = {v["file"]: k for k, v in cache.items() if isinstance(v, dict) and v.get("file") and not k.startswith(("pick:", "garment:"))}
    with catalog._lock:
        rows = catalog._db().execute("SELECT url, name, brand, category, cutout_p FROM products").fetchall()

    flagged = []
    for url, name, brand, cat, cp in rows:
        if cp and not quality.check_cutout(Path(config.DATA_DIR) / "cutouts" / Path(cp).name, cat)[0]:
            flagged.append((url, name, brand, cat, cp))
            if not args.fix:
                print(f"  person: {brand:8s} {cat:9s} {name[:60]}")
    print(f"{len(flagged)} of {len(rows)} items show a person.")
    if not args.fix:
        if args.remove and flagged:
            _delete([f[0] for f in flagged])
        return

    fixed, failed = 0, []
    for n, (url, name, brand, cat, cp) in enumerate(flagged, 1):
        if args.limit and fixed >= args.limit:
            break
        src = source_of.get(Path(cp).name)
        out, why = None, "original photo unknown"
        if src and garment.can_handle(cat):
            try:
                raw = cutouts._download(src)
                out, why = cutouts.garment_from_photos([raw], src, cat, name)
            except Exception as err:  # noqa: BLE001
                why = f"download failed: {err}"
        elif src:
            why = "can't crop this kind of item"
        if out:
            with catalog._lock:
                db = catalog._db()
                db.execute("UPDATE products SET cutout_p=? WHERE url=?", (out, url))
                db.commit()
            fixed += 1
            print(f"[{n}/{len(flagged)}] cropped  {cat:9s} {name[:55]}")
        else:
            failed.append(url)
            print(f"[{n}/{len(flagged)}] could not ({why})  {cat:9s} {name[:50]}")
    print(f"cropped {fixed}; {len(failed)} could not be fixed.")
    if args.remove and failed:
        _delete(failed)


def _delete(urls: list[str]) -> None:
    with catalog._lock:
        db = catalog._db()
        db.executemany("DELETE FROM products WHERE url=?", [(u,) for u in urls])
        db.commit()
    print(f"Removed {len(urls)} from the catalog; {catalog.count()} remain.")


if __name__ == "__main__":
    main()
