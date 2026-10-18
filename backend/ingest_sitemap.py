"""Seed the catalog from Nike's public product sitemap. No API key needed.

    python3 ingest_sitemap.py --dry-run          # count URLs per category, fetch nothing else
    python3 ingest_sitemap.py --limit 10         # try 10 products
    python3 ingest_sitemap.py --per-category 20  # ~20 per category (default)
    python3 ingest_sitemap.py --models           # also build on-model cutouts

For each sampled /t/ product page it reads the JSON-LD (name, price), picks a
product-only photo with the free skin-tone check, cuts out the background and
writes the result into backend/data/catalog.sqlite through catalog.upsert().
Resumable: URLs already in the catalog are skipped. Polite: one page at a time
with a delay. AI keys are ignored by default (--ai to use them).
"""

import argparse
import json
import os
import random
import re
import sys
import time
import urllib.error

if "--ai" not in sys.argv:
    # Force the free path (skin-tone check) even if a key is configured.
    for _k in ("XAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        os.environ[_k] = ""

import catalog
import cutouts
import images
from products import CATEGORIES

SITEMAP = "https://www.nike.com/sitemap-v2-pdp-en-us.xml"
_LOC = re.compile(r"<loc>\s*(https://www\.nike\.com/t/[^<\s]+)\s*</loc>")

# slug keyword -> category; first match wins, so order matters.
_CAT_RULES = [
    ("bag", ("backpack", "duffel", "tote", "crossbody", "waistpack", "hip-pack", "gym-sack")),
    ("headwear", ("beanie", "bucket-hat", "cap", "hat", "visor", "headband")),
    ("accessory", ("socks", "belt", "sunglasses", "gloves", "scarf", "water-bottle", "bottle", "wristband")),
    ("shoes", ("shoes", "sneakers", "boots", "slides", "sandals", "cleats", "flip-flops")),
    ("outerwear", ("jacket", "windbreaker", "puffer", "vest", "parka", "coat", "anorak")),
    ("bottom", ("pants", "joggers", "shorts", "leggings", "tights", "sweatpants", "skirt", "trousers")),
    ("top", ("hoodie", "tee", "t-shirt", "shirt", "crew", "sweatshirt", "tank", "top", "polo", "jersey", "bra", "half-zip", "long-sleeve")),
    ("bag", ("bag",)),  # last: "shoe bag" tees etc. match earlier rules first
]


def infer_category(slug: str) -> str | None:
    words = set(slug.lower().split("-"))
    for cat, keys in _CAT_RULES:
        for k in keys:
            if (k in words) if "-" not in k else (k in slug.lower()):
                return cat
    return None


def sitemap_urls() -> list[str]:
    # images._fetch_html caps pages at 2 MB, which truncates this sitemap.
    with images._get(SITEMAP, 60) as resp:
        raw = resp.read(60_000_000)
        if resp.headers.get("Content-Encoding") == "gzip":
            import gzip
            raw = gzip.decompress(raw)
    return list(dict.fromkeys(_LOC.findall(raw.decode("utf-8", "replace"))))


_KIDS = ("kids", "baby", "toddler", "little-kids", "big-kids", "infant")


def sample(urls: list[str], per_category: int, seed: int = 7, kids: bool = False) -> list[tuple[str, str]]:
    """Round-robin across categories so a small --limit still gives variety."""
    rng = random.Random(seed)
    buckets: dict[str, list[str]] = {c: [] for c in CATEGORIES}
    for u in urls:
        slug = u.rsplit("/t/", 1)[1].split("/")[0]
        if not kids and any(k in slug.lower().split("-") for k in _KIDS):
            continue
        cat = infer_category(slug)
        if cat:
            buckets[cat].append(u)
    for b in buckets.values():
        rng.shuffle(b)
    out: list[tuple[str, str]] = []
    for i in range(per_category):
        for cat in CATEGORIES:
            if i < len(buckets[cat]):
                out.append((cat, buckets[cat][i]))
    return out


def parse_product(html: str) -> dict | None:
    """name, price and photos from the page's JSON-LD Product/ProductGroup."""
    parser = images._MetaParser()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001
        pass
    found: dict = {"name": None, "price": None, "images": []}

    def walk(node):
        if isinstance(node, dict):
            t = node.get("@type")
            types = t if isinstance(t, list) else [t]
            if any(str(x).lower() in ("product", "productgroup") for x in types if x):
                found["name"] = found["name"] or node.get("name")
                img = node.get("image")
                if isinstance(img, str):
                    found["images"].append(img)
                elif isinstance(img, list):
                    found["images"] += [i if isinstance(i, str) else i.get("url", "") for i in img]
            if found["price"] is None and node.get("price") not in (None, ""):
                try:
                    found["price"] = float(str(node["price"]).replace(",", ""))
                except ValueError:
                    pass
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for block in parser.jsonld:
        try:
            walk(json.loads(block))
        except (json.JSONDecodeError, TypeError):
            continue
    if not found["name"] or not found["price"]:
        return None
    found["images"] = [i for i in found["images"] if i]
    return found


def already_have(url: str) -> bool:
    with catalog._lock:
        return catalog._db().execute("SELECT 1 FROM products WHERE url=?", (url,)).fetchone() is not None


def ingest_one(cat: str, url: str, models: bool) -> bool:
    try:
        html, final_url = images._fetch_html(url)
    except urllib.error.HTTPError as err:
        print(f"  skip ({err.code}) {url}", file=sys.stderr)
        return False
    except Exception as err:  # noqa: BLE001
        print(f"  skip (fetch failed: {err}) {url}", file=sys.stderr)
        return False
    if "/t/" not in final_url:
        print(f"  skip (redirected off product page) {url}", file=sys.stderr)
        return False
    info = parse_product(html)
    if not info:
        print(f"  skip (no name/price in JSON-LD) {url}", file=sys.stderr)
        return False
    item = {
        "name": str(info["name"]).strip(), "brand": "Nike", "price": info["price"],
        "url": final_url.split("?")[0], "image": info["images"][0] if info["images"] else "",
        "stock": "in_stock", "category": cat,
    }
    ok = False
    for mode in ([False, True] if models else [False]):
        it = dict(item)
        cutouts.resolve(it, mode)
        if it.get("image"):
            catalog.upsert([it], mode, query=item["name"], source="sitemap")
            ok = True
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--per-category", type=int, default=20)
    ap.add_argument("--limit", type=int, default=0, help="stop after N products tried")
    ap.add_argument("--delay", type=float, default=1.5, help="seconds between products")
    ap.add_argument("--models", action="store_true", help="also build on-model cutouts")
    ap.add_argument("--kids", action="store_true", help="include kids' / baby items")
    ap.add_argument("--ai", action="store_true", help="use configured AI keys for photo choice")
    args = ap.parse_args()

    urls = sitemap_urls()
    plan = sample(urls, args.per_category, kids=args.kids)
    counts = {c: sum(1 for k, _ in plan if k == c) for c in CATEGORIES}
    print(f"sitemap: {len(urls)} product URLs; planned {len(plan)}: {counts}")
    if args.dry_run:
        return
    if not cutouts.available():
        sys.exit("Cutouts unavailable: pip install -r requirements.txt (needs Pillow) and retry.")
    cutouts.warm()

    done = tried = 0
    for cat, url in plan:
        if args.limit and tried >= args.limit:
            break
        if already_have(url.split("?")[0]):
            continue
        tried += 1
        t0 = time.time()
        ok = ingest_one(cat, url, args.models)
        done += ok
        print(f"[{tried}] {cat:9s} {'ok  ' if ok else 'skip'} {time.time() - t0:4.1f}s · catalog {catalog.count()} · {url.rsplit('/t/', 1)[1][:60]}")
        time.sleep(args.delay)
    print(f"done — {done}/{tried} added, catalog now {catalog.count()} items")


if __name__ == "__main__":
    main()
