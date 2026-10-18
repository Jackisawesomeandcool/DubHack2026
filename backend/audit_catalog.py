"""Find catalog items whose cutout still shows a person wearing the product.

    python3 audit_catalog.py              # list suspects
    python3 audit_catalog.py --remove     # also delete them from the catalog (cutout files stay)

Uses quality.py (local YOLOX detector + skin check, no API key). ~65 ms per item.
Stop the server first if you use --remove. Re-run your scrapers afterwards to refill:
they now try other photos of a product and skip it only if every photo shows a person.
"""

import argparse
import sys
from pathlib import Path

import catalog
import config
import quality


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--remove", action="store_true")
    args = ap.parse_args()
    if not quality.available():
        sys.exit("Needs: pip install onnxruntime numpy (and internet once to fetch the 20 MB model).")
    with catalog._lock:
        rows = catalog._db().execute("SELECT url, name, brand, category, cutout_p FROM products").fetchall()
    bad = []
    for url, name, brand, cat, cp in rows:
        if not cp:
            continue
        ok, why = quality.check_cutout(Path(config.DATA_DIR) / "cutouts" / Path(cp).name)
        if not ok:
            bad.append(url)
            print(f"  person: {brand:8s} {cat:9s} {name[:60]}")
    print(f"{len(bad)} of {len(rows)} items show a person.")
    if args.remove and bad:
        with catalog._lock:
            db = catalog._db()
            db.executemany("DELETE FROM products WHERE url=?", [(u,) for u in bad])
            db.commit()
        print(f"Removed {len(bad)} from the catalog; {catalog.count()} remain.")


if __name__ == "__main__":
    main()
