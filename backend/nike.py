"""Fast product search straight from nike.com's own product search API.

This is the same JSON endpoint nike.com's search page calls. It returns in
well under a second with title, price, stock, listing URL and two photos:
`squarishURL` (product on plain background) and `portraitURL` (usually on a
model). If the endpoint changes or fails, callers fall back to Grok.
"""

import json
import random
import sys
import urllib.parse
import urllib.request

import config
import time

_failures = 0
_disabled_until = 0.0

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
CHANNEL = "d9a5bc42-4b9c-4976-858a-f159cf99c647"
_anon = "".join(random.choice("0123456789abcdef") for _ in range(32))

_CATEGORY_WORDS = [
    ("shoes", ["shoe", "sneaker", "boot", "sandal", "slide", "cleat", "dunk", "air force", "jordan", "pegasus", "vomero", "air max", "footwear"]),
    ("outerwear", ["jacket", "coat", "parka", "windrunner", "windbreaker", "anorak", "puffer", "vest", "shell", "gilet"]),
    ("bottom", ["pant", "jogger", "short", "trouser", "legging", "tight", "skirt", "cargo", "sweatpant"]),
    ("headwear", ["cap", "hat", "beanie", "visor", "headband", "bucket"]),
    ("bag", ["bag", "backpack", "tote", "duffel", "crossbody", "hip pack", "fanny", "sling"]),
    ("accessory", ["sock", "belt", "glove", "scarf", "sunglass", "watch", "wristband", "sleeve", "bottle", "lanyard"]),
    ("top", ["hoodie", "sweatshirt", "crew", "tee", "t-shirt", "shirt", "top", "tank", "jersey", "polo", "sweater", "pullover", "half-zip", "long-sleeve", "fleece"]),
]


def _category(title: str, subtitle: str, product_type: str) -> str:
    text = f"{title} {subtitle}".lower()
    if "FOOTWEAR" in (product_type or "").upper():
        return "shoes"
    for cat, words in _CATEGORY_WORDS:
        if any(w in text for w in words):
            return cat
    return "accessory" if "EQUIPMENT" in (product_type or "").upper() else "top"


def _walk_products(node, out: list):
    if isinstance(node, dict):
        if "title" in node and ("images" in node or "squarishURL" in node):
            out.append(node)
        for v in node.values():
            _walk_products(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_products(v, out)


def search(term: str, count: int = 12) -> list[dict]:
    """Products for a search term, in our product shape (image fields raw)."""
    global _failures, _disabled_until
    if "nike.com" not in ",".join(config.ALLOWED_DOMAINS) and config.ALLOWED_DOMAINS:
        return []
    if time.time() < _disabled_until:
        return []
    endpoint = (
        "/product_feed/rollup_threads/v2?filter=marketplace(US)&filter=language(en)"
        f"&filter=employeePrice(true)&searchTerms={urllib.parse.quote(term)}&anchor=0"
        f"&consumerChannelId={CHANNEL}&count={count}"
    )
    url = (
        "https://api.nike.com/cic/browse/v2?queryid=products&anonymousId=" + _anon
        + "&country=us&language=en&localizedRangeStr=%7BlowestPrice%7D%20%E2%80%94%20%7BhighestPrice%7D"
        + "&endpoint=" + urllib.parse.quote(endpoint, safe="")
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json", "Accept-Language": "en-US,en;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as err:  # noqa: BLE001
        _failures += 1
        if _failures >= 2:
            _disabled_until = time.time() + 600
            print(f"[nike] search endpoint unavailable ({err}); using AI search for the next 10 min", file=sys.stderr)
        else:
            print(f"[nike] search failed ({err}); falling back to AI search", file=sys.stderr)
        return []
    _failures = 0

    raw: list = []
    _walk_products(data, raw)
    items, seen = [], set()
    for p in raw:
        title = str(p.get("title") or "").strip()
        if not title or title in seen:
            continue
        seen.add(title)
        images = p.get("images") or {}
        squarish = images.get("squarishURL") or p.get("squarishURL") or ""
        portrait = images.get("portraitURL") or p.get("portraitURL") or ""
        price = (p.get("price") or {}).get("currentPrice") or (p.get("price") or {}).get("fullPrice") or 0
        link = str(p.get("url") or "").replace("{countryLang}", "https://www.nike.com")
        if link and not link.startswith("http"):
            link = "https://www.nike.com" + link
        in_stock = p.get("inStock", True)
        items.append({
            "name": title,
            "brand": "Nike",
            "price": price,
            "url": link,
            "image": squarish or portrait,
            "image_product": squarish,
            "image_model": portrait,
            "stock": "in_stock" if in_stock else "out_of_stock",
            "category": _category(title, str(p.get("subtitle") or ""), str(p.get("productType") or "")),
        })
    return items
