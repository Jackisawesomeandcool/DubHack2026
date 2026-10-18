"""Seed the catalog ahead of time.

NOTE: search is catalog-only now (finder.py no longer calls live sources), so this
script only exercises the search pipeline over products already in the catalog.
To add products use ingest_sites.py / ingest_sitemap.py / seed.py.

    python3 ingest.py                # product-only cutouts, every style x category
    python3 ingest.py --models       # also on-model cutouts
    python3 ingest.py --limit 20     # stop after N searches

Runs each search through the normal pipeline (nike.com API or Grok, cutouts,
tags) and writes the results into backend/data/catalog.sqlite. Safe to re-run;
products already present are refreshed, not duplicated. Rate-limited.
"""

import argparse
import itertools
import sys
import time

import catalog
import cutouts
import finder
import fits
from products import CATEGORIES

CATEGORY_TERMS = {
    "outerwear": ["jacket", "windbreaker", "puffer", "fleece jacket"],
    "top": ["hoodie", "tee", "crewneck", "long sleeve", "half-zip"],
    "bottom": ["joggers", "cargo pants", "shorts", "sweatpants", "track pants"],
    "shoes": ["sneakers", "running shoes", "basketball shoes", "retro sneakers", "trail shoes"],
    "bag": ["backpack", "crossbody bag", "tote", "duffel"],
    "headwear": ["cap", "beanie", "bucket hat"],
    "accessory": ["socks", "belt", "sunglasses"],
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", action="store_true", help="also build on-model cutouts")
    ap.add_argument("--limit", type=int, default=0, help="max searches to run")
    ap.add_argument("--gap", type=float, default=2.0, help="seconds between searches")
    args = ap.parse_args()

    if not cutouts.available():
        sys.exit("Cutouts unavailable: install Pillow (pip install -r requirements.txt) and retry.")
    cutouts.warm()
    modes = [False, True] if args.models else [False]
    searches = list(catalog.POPULAR)
    for cat in CATEGORIES:
        searches += [f"{t}" for t in CATEGORY_TERMS.get(cat, [])]
    for style in fits.STYLES:
        searches.append(style)
    if args.limit:
        searches = searches[: args.limit]

    total = 0
    for n, (term, models) in enumerate(itertools.product(searches, modes), 1):
        t0 = time.time()
        try:
            items = finder.find(term, models, count=8, local_first=False)
            total += len(items)
            print(f"[{n}/{len(searches) * len(modes)}] '{term}' ({'models' if models else 'product'}) → {len(items)} in {time.time() - t0:.1f}s · catalog {catalog.count()}")
        except Exception as err:  # noqa: BLE001
            print(f"[{n}] '{term}' failed: {err}", file=sys.stderr)
        time.sleep(args.gap)
    print(f"done — {total} products processed, catalog now {catalog.count()} items")


if __name__ == "__main__":
    main()
