"""Seed the catalog from more fashion sites. No API key needed.

    python3 ingest_sites.py --dry-run                 # fetch the feeds, count per category, no images
    python3 ingest_sites.py --limit 8                 # smoke test
    python3 ingest_sites.py --per-category 12         # ~12 products per category per site (default)
    python3 ingest_sites.py --sites stussy            # one site only

Sites
  stussy  Shopify store: https://www.stussy.com/products.json (paged). Real per-size
          availability, so only products with at least one size in stock are kept.
  brandy  Brandy Melville US, also a Shopify store (https://us.brandymelville.com/products.json). Women's
          tops, tanks, bottoms, skirts and sweats; dresses/rompers are skipped (no category for them yet).
  uniqlo  Uniqlo US search feed (unofficial JSON the website itself uses). Pulled
          per search term; kids/baby skipped unless --kids.

Each product: classify -> pick a product-only photo with the free skin-tone check ->
remove the background -> catalog.upsert(). Resumable (URLs already stored are skipped).
Rate limited. Hackathon-scale use only: these sites' terms likely restrict automated
access, so keep the volumes small and do not redistribute their images.
"""

import argparse
import json
import os
import random
import re
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

if "--ai" not in sys.argv:
    # Force the free path (skin-tone check) even if a key is configured.
    for _k in ("XAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        os.environ[_k] = ""

import catalog
import cutouts
import images
from products import CATEGORIES

STUSSY_FEED = "https://www.stussy.com/products.json?limit=250&page={page}"
BRANDY_FEED = "https://us.brandymelville.com/products.json?limit=250&page={page}"
UNIQLO_FEED = "https://www.uniqlo.com/us/api/commerce/v5/en/products?path=&q={q}&limit=36&offset={offset}"
UNIQLO_TERMS = [
    "hoodie", "sweatshirt", "t-shirt", "long sleeve t-shirt", "shirt", "overshirt", "sweater", "cardigan",
    "jacket", "coat", "parka", "vest", "jeans", "chinos", "cargo pants", "sweatpants", "shorts", "pants",
    "cap", "beanie", "tote bag", "backpack", "socks", "belt", "scarf",
]

# First matching rule wins, so order matters. Tokens are matched as whole words.
RULES = [
    ("accessory", ["socks", "sock"]),
    ("shoes", ["shoes", "shoe", "sneakers", "sneaker", "boots", "boot", "sandals", "slides", "loafers", "clogs", "trainers"]),
    ("headwear", ["cap", "caps", "hat", "hats", "beanie", "beanies", "bucket", "visor", "balaclava", "headband"]),
    ("bag", ["bag", "bags", "backpack", "tote", "duffel", "pouch", "crossbody", "wallet", "satchel"]),
    ("outerwear", ["jacket", "jackets", "coat", "coats", "parka", "parkas", "anorak", "windbreaker", "puffer", "vest", "vests",
                   "blazer", "gilet", "poncho", "shell", "bomber", "overcoat", "trench"]),
    ("bottom", ["pants", "pant", "jeans", "jean", "trousers", "trouser", "shorts", "chinos", "chino", "cargo", "cargos",
                "joggers", "sweatpants", "leggings", "skirt", "skirts", "skort", "sweats", "denim", "overalls"]),
    ("top", ["t shirt", "tee", "tees", "shirt", "shirts", "hoodie", "hoodies", "sweatshirt", "sweatshirts", "crewneck", "crew",
             "sweater", "sweaters", "cardigan", "knit", "polo", "tank", "henley", "longsleeve", "long sleeve", "pullover",
             "top", "turtleneck", "zip", "cami", "camisole", "bodysuit", "blouse", "halter", "corset", "tube", "babydoll"]),
    ("bottom", ["short"]),  # singular only after "top" so "Short Sleeve Tee" stays a top
    ("accessory", ["belt", "scarf", "gloves", "glove", "sunglasses", "keychain", "bandana", "jewelry"]),
]
TYPE_MAP = {
    "outerwear": "outerwear", "tops": "top", "bottoms": "bottom", "bags": "bag", "headwear": "headwear", "hats": "headwear",
    "footwear": "shoes", "knits": "top", "shirts": "top", "tees": "top", "t-shirts": "top", "sweatshirts": "top",
    "fleece": "top", "denim": "bottom", "tanks": "top", "sweatpants": "bottom", "skirts": "bottom", "sweaters": "top",
    "cardigans": "top", "jackets": "outerwear", "coats": "outerwear", "jeans": "bottom", "pants": "bottom", "shorts": "bottom", "socks": "accessory",
}


def classify(text: str) -> str | None:
    t = " " + re.sub(r"[^a-z0-9]+", " ", (text or "").lower()) + " "
    for cat, keys in RULES:
        if any(f" {k} " in t for k in keys):
            return cat
    return None


def http_json(url: str):
    with images._get(url, 30) as resp:
        return json.loads(resp.read(40_000_000).decode("utf-8", "replace"))


# ---------------------------------------------------------------- Stüssy
def stussy_item(p: dict) -> dict | None:
    title = str(p.get("title") or "").strip()
    variants = p.get("variants") or []
    if not title or not p.get("handle") or not any(v.get("available") for v in variants):
        return None
    prices = []
    for v in variants:
        try:
            prices.append(float(v.get("price")))
        except (TypeError, ValueError):
            pass
    if not prices or min(prices) <= 0:
        return None
    ptype = str(p.get("product_type") or "")
    cat = classify(title) or TYPE_MAP.get(ptype.strip().lower())
    if not cat:
        return None
    first_variant = str((variants[0] or {}).get("title") or "")
    color = first_variant.split(" / ")[0].lower() if " / " in first_variant else ""
    imgs = [i.get("src") for i in (p.get("images") or []) if isinstance(i, dict) and i.get("src")]
    if not imgs:
        return None
    return {
        "name": title.title() if title.isupper() else title, "brand": "Stüssy", "price": min(prices),  # feed "vendor" is often a fulfilment name ("Radial"), so brand is fixed
        "url": "https://www.stussy.com/products/" + str(p["handle"]), "category": cat,
        "candidates": imgs[:8], "tags": f"{ptype} {color}".lower(),
    }


def stussy_all(max_pages: int = 8) -> list[dict]:
    out = []
    for page in range(1, max_pages + 1):
        try:
            data = http_json(STUSSY_FEED.format(page=page))
        except Exception as err:  # noqa: BLE001
            print(f"[stussy] feed page {page} failed: {err}", file=sys.stderr)
            break
        prods = data.get("products") or []
        if not prods:
            break
        out += [it for it in (stussy_item(p) for p in prods) if it]
        time.sleep(0.5)
    return out


# ---------------------------------------------------------------- Uniqlo
# ---------------------------------------------------------------- Brandy Melville
def brandy_item(p: dict) -> dict | None:
    title = str(p.get("title") or "").strip()
    variants = p.get("variants") or []
    if not title or not p.get("handle") or not any(v.get("available") for v in variants):
        return None
    prices = []
    for v in variants:
        try:
            prices.append(float(v.get("price")))
        except (TypeError, ValueError):
            pass
    if not prices or min(prices) <= 0:
        return None
    ptype = str(p.get("product_type") or "")
    cat = classify(title) or classify(ptype) or TYPE_MAP.get(ptype.strip().lower())
    if not cat or cat in ("shoes", "bag", "headwear", "accessory"):
        return None                       # Brandy's jewelry/hair accessories aren't wanted; clothes only
    imgs = [i.get("src") for i in (p.get("images") or []) if isinstance(i, dict) and i.get("src")]
    if not imgs:
        return None
    return {
        "name": title, "brand": "Brandy Melville", "price": min(prices),
        "url": "https://us.brandymelville.com/products/" + str(p["handle"]), "category": cat,
        "candidates": imgs[:6], "tags": f"women womens {ptype}".lower(),
    }


def brandy_all(max_pages: int = 8) -> list[dict]:
    out = []
    for page in range(1, max_pages + 1):
        try:
            data = http_json(BRANDY_FEED.format(page=page))
        except Exception as err:  # noqa: BLE001
            print(f"[brandy] feed page {page} failed: {err}", file=sys.stderr)
            break
        prods = data.get("products") or []
        if not prods:
            break
        out += [it for it in (brandy_item(p) for p in prods) if it]
        time.sleep(0.5)
    return out


def uniqlo_item(it: dict, term: str, kids: bool = False) -> dict | None:
    pid = it.get("productId")
    name = str(it.get("name") or "").strip()
    gender = str(it.get("genderCategory") or it.get("genderName") or "").upper()
    if not pid or not name or (not kids and gender in ("KIDS", "BABY")):
        return None
    prices = it.get("prices") or {}
    price = ((prices.get("promo") or prices.get("base") or {}) or {}).get("value")
    try:
        price = float(price)
    except (TypeError, ValueError):
        return None
    cat = classify(name) or classify(term)
    if not cat or price <= 0:
        return None
    imgs = it.get("images") or {}
    main = [v for v in (imgs.get("main") or {}).values() if isinstance(v, dict) and v.get("image")]
    sub = [v for v in (imgs.get("sub") or []) if isinstance(v, dict) and v.get("image")]
    cands: list[str] = []
    cands += [v["image"] for v in sub if not v.get("model")]                              # plain product views
    cands += [v["image"].replace("_3x4", "") for v in main if "_3x4" in v["image"]]       # unsuffixed = often flat
    cands += [v["image"] for v in sub if v.get("model")] + [v["image"] for v in main]    # model shots last
    cands = list(dict.fromkeys(cands))[:8]
    if not cands:
        return None
    colors = " ".join(str(c.get("name") or "") for c in (it.get("colors") or []) if isinstance(c, dict)).lower()
    return {
        "name": name, "brand": "Uniqlo", "price": price,
        "url": f"https://www.uniqlo.com/us/en/products/{pid}/{it.get('priceGroup') or '00'}",
        "category": cat, "candidates": cands, "tags": colors,
    }


def uniqlo_all(pages: int = 2, kids: bool = False) -> list[dict]:
    seen, out = set(), []
    for term in UNIQLO_TERMS:
        for page in range(pages):
            try:
                data = http_json(UNIQLO_FEED.format(q=urllib.parse.quote(term), offset=page * 36))
            except Exception as err:  # noqa: BLE001
                print(f"[uniqlo] '{term}' page {page} failed: {err}", file=sys.stderr)
                break
            items = ((data.get("result") or {}).get("items")) or []
            if not items:
                break
            for it in items:
                row = uniqlo_item(it, term, kids)
                if row and row["url"] not in seen:
                    seen.add(row["url"])
                    out.append(row)
            time.sleep(0.5)
    return out


# ---------------------------------------------------------------- shared
def sample(items: list[dict], per_category: int, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    rng.shuffle(items)
    buckets: dict[str, list[dict]] = {c: [] for c in CATEGORIES}
    for it in items:
        if len(buckets[it["category"]]) < per_category:
            buckets[it["category"]].append(it)
    out = []
    for i in range(per_category):  # round-robin so --limit still gives variety
        for cat in CATEGORIES:
            if i < len(buckets[cat]):
                out.append(buckets[cat][i])
    return out


def already_have(url: str) -> bool:
    with catalog._lock:
        return (catalog._db().execute("SELECT 1 FROM products WHERE url=?", (url,)).fetchone() is not None
                or catalog._db().execute("SELECT 1 FROM blocked WHERE url=?", (url,)).fetchone() is not None)


def _download(u: str):
    try:
        return cutouts._download(u)
    except Exception:  # noqa: BLE001
        return None


def process(item: dict) -> bool:
    cands = item["candidates"]
    with ThreadPoolExecutor(max_workers=6) as pool:
        blobs = list(pool.map(_download, cands))
    # Best-first: the skin-tone check picks the order; best_cutout() then makes sure no person shows,
    # trying the other photos and finally cutting just the garment out of a model shot.
    first = cutouts.pick(blobs, False)
    order = ([first] if first >= 0 else []) + [i for i, b in enumerate(blobs) if b and i != first]
    path, how = cutouts.best_cutout(cands, blobs, item["category"], item["name"], order)
    if not path:
        print(f"  skipped {item['name']}: {how}", file=sys.stderr)
        return False
    if how != "product photo":
        print(f"  {item['name']}: {how}")
    row = {"name": item["name"], "brand": item["brand"], "price": item["price"], "url": item["url"],
           "image": path, "stock": "in_stock", "category": item["category"]}
    catalog.upsert([row], False, query=f"{item['name']} {item['tags']}", source=item["brand"].lower())
    return True


def apply_shard(plan: list, spec: str) -> list:
    """'2/3' -> every third entry starting at the second. Same flags on every machine = disjoint slices."""
    if not spec:
        return plan
    try:
        i, n = (int(x) for x in spec.split("/"))
        assert 1 <= i <= n
    except (ValueError, AssertionError):
        sys.exit("--shard must look like 2/3 (slice 2 of 3)")
    return plan[i - 1::n]


SKIPPED_FILE = catalog.config.DATA_DIR / "ingest_skipped.txt"


def _load_skipped() -> set[str]:
    try:
        return set(SKIPPED_FILE.read_text(encoding="utf-8").split())
    except OSError:
        return set()


def _remember_skipped(url: str) -> None:
    """Products with no usable photo are not retried on every run (--retry-skipped overrides)."""
    SKIPPED_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SKIPPED_FILE, "a", encoding="utf-8") as f:
        f.write(url + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", default="stussy,uniqlo")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--per-category", type=int, default=12)
    ap.add_argument("--limit", type=int, default=0, help="stop after N products tried")
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--kids", action="store_true", help="include kids'/baby items (Uniqlo)")
    ap.add_argument("--categories", default="", help="only these, comma separated: top,bottom,outerwear,shoes,bag,headwear,accessory (default: all)")
    ap.add_argument("--uniqlo-pages", type=int, default=2, help="result pages per Uniqlo search term (36 items each); raise it for a bigger pool")
    ap.add_argument("--retry-skipped", action="store_true", help="try again products an earlier run gave up on")
    ap.add_argument("--shard", default="", help="i/n: do only slice i of n (1-based) so teammates scrape different products; everyone must use the same other flags")
    ap.add_argument("--ai", action="store_true", help="use configured AI keys for photo choice")
    args = ap.parse_args()
    sites = [s.strip() for s in args.sites.split(",") if s.strip()]

    cats = {c.strip() for c in args.categories.split(",") if c.strip()}
    bad = cats - set(CATEGORIES)
    if bad:
        sys.exit(f"Unknown categories {sorted(bad)}; choose from {list(CATEGORIES)}")
    unknown = [x for x in sites if x not in ("stussy", "uniqlo", "brandy")]
    if unknown:
        sys.exit(f"Unknown site(s) {unknown}. This script does stussy, uniqlo and brandy; Nike is ingest_sitemap.py "
                 "(same --categories / --per-category flags).")
    skipped = _load_skipped()
    plan: list[dict] = []
    for site in sites:
        rows = stussy_all() if site == "stussy" else brandy_all() if site == "brandy" else uniqlo_all(pages=args.uniqlo_pages, kids=args.kids) if site == "uniqlo" else []
        feed = len(rows)
        if cats:
            rows = [r for r in rows if r["category"] in cats]
        rows = [r for r in rows if not already_have(r["url"]) and (args.retry_skipped or r["url"] not in skipped)]
        picked = sample(rows, args.per_category)     # --per-category counts NEW products only
        counts = {c: sum(1 for r in picked if r["category"] == c) for c in CATEGORIES if any(r["category"] == c for r in picked)}
        print(f"{site}: {feed} usable products in feed, {len(rows)} new{' in ' + ','.join(sorted(cats)) if cats else ''}; planned {len(picked)}: {counts}")
        plan += picked
    plan = apply_shard(plan, args.shard)
    if args.dry_run:
        return
    if not cutouts.available():
        sys.exit("Cutouts unavailable: pip install -r requirements-local.txt (needs Pillow) and retry.")
    cutouts.warm()

    done = tried = 0
    for item in plan:
        if args.limit and tried >= args.limit:
            break
        if already_have(item["url"]):
            continue
        tried += 1
        t0 = time.time()
        ok = process(item)
        if not ok:
            _remember_skipped(item["url"])
        done += ok
        print(f"[{tried}] {item['brand'][:7]:7s} {item['category']:9s} {'ok  ' if ok else 'skip'} {time.time() - t0:4.1f}s · catalog {catalog.count()} · {item['name'][:50]}")
        time.sleep(args.delay)
    print(f"done — {done}/{tried} added, catalog now {catalog.count()} items")


if __name__ == "__main__":
    main()
