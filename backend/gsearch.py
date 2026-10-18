"""Google Custom Search JSON API as the listings source (official API, free
100 queries/day, no billing required).

The engine is restricted to the store's site, so every hit is a real product
page, and Google returns the page's structured data already parsed
(pagemap.product / offer / metatags), so no page fetching is needed.
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request

import config

_blocked_until = 0.0
_CATEGORY_WORDS = [
    ("shoes", ["shoe", "sneaker", "boot", "sandal", "slide", "cleat", "dunk", "air force", "jordan", "pegasus", "vomero", "air max", "footwear", "p-6000", "cortez", "blazer"]),
    ("outerwear", ["jacket", "coat", "parka", "windrunner", "windbreaker", "anorak", "puffer", "vest", "shell", "gilet"]),
    ("bottom", ["pant", "jogger", "short", "trouser", "legging", "tight", "skirt", "cargo", "sweatpant"]),
    ("headwear", ["cap", "hat", "beanie", "visor", "headband", "bucket"]),
    ("bag", ["bag", "backpack", "tote", "duffel", "crossbody", "hip pack", "fanny", "sling"]),
    ("accessory", ["sock", "belt", "glove", "scarf", "sunglass", "watch", "wristband", "sleeve", "bottle", "lanyard"]),
    ("top", ["hoodie", "sweatshirt", "crew", "tee", "t-shirt", "shirt", "top", "tank", "jersey", "polo", "sweater", "pullover", "half-zip", "long-sleeve", "fleece"]),
]
_PRODUCT_URL = re.compile(r"https?://(www\.)?nike\.com(/[a-z]{2}(/[a-z]{2})?)?/t/", re.I)


def configured() -> bool:
    return bool(config.GOOGLE_CSE_KEY and config.GOOGLE_CSE_CX)


def category_for(text: str) -> str:
    t = text.lower()
    if "hoodie" in t or "sweatshirt" in t or "crew" in t:
        return "top"
    for cat, words in _CATEGORY_WORDS:
        if any(w in t for w in words):
            return cat
    return "top"


def _first(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None


def _item_from_result(r: dict) -> dict | None:
    link = r.get("link") or ""
    if not link or (config.ALLOWED_DOMAINS and "nike.com" in config.ALLOWED_DOMAINS[0] and not _PRODUCT_URL.match(link)):
        return None
    pm = r.get("pagemap") or {}
    product = (pm.get("product") or [{}])[0]
    offer = (pm.get("offer") or [{}])[0]
    meta = (pm.get("metatags") or [{}])[0]
    name = _first(product, "name") or _first(meta, "og:title", "twitter:title") or r.get("title", "")
    name = re.sub(r"\s*[.|–-]\s*Nike(\.com)?\s*$", "", str(name)).strip()
    price = _first(offer, "price", "lowprice") or _first(meta, "product:price:amount", "og:price:amount") or 0
    avail = str(_first(offer, "availability") or _first(meta, "product:availability", "og:availability") or "").lower()
    stock = "out_of_stock" if any(k in avail for k in ("outofstock", "soldout", "discontinued")) else "in_stock"
    image = _first(meta, "og:image", "twitter:image") or (pm.get("cse_image") or [{}])[0].get("src") or _first(product, "image") or ""
    brand = _first(product, "brand") or "Nike"
    if isinstance(brand, dict):
        brand = brand.get("name", "Nike")
    if not name:
        return None
    return {
        "name": name, "brand": str(brand), "price": price, "url": link.split("#")[0],
        "image": image, "stock": stock, "category": category_for(f"{name} {r.get('title','')}"),
    }


def search(prompt: str, category: str | None, exclude: list[str], count: int) -> list[dict]:
    global _blocked_until
    if not configured() or time.time() < _blocked_until:
        return []
    hint = {"shoes": "shoes", "outerwear": "jacket", "bottom": "pants", "headwear": "hat", "bag": "bag", "accessory": "accessories", "top": "top"}.get(category or "", "")
    params = {"key": config.GOOGLE_CSE_KEY, "cx": config.GOOGLE_CSE_CX, "q": f"{prompt} {hint}".strip(), "num": 10, "safe": "active"}
    url = "https://www.googleapis.com/customsearch/v1?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")
        try:
            msg = json.loads(detail)["error"]["message"]
        except Exception:  # noqa: BLE001
            msg = detail[:200]
        if err.code in (403, 429):
            _blocked_until = time.time() + 3600
            print(f"[gsearch] quota/permission problem ({err.code}: {msg[:120]}); pausing for 1 h", file=sys.stderr)
        else:
            print(f"[gsearch] failed ({err.code}: {msg[:120]})", file=sys.stderr)
        return []
    except Exception as err:  # noqa: BLE001
        print(f"[gsearch] failed ({err})", file=sys.stderr)
        return []

    ex = {n.lower() for n in exclude}
    items, seen = [], set()
    for r in data.get("items", []):
        it = _item_from_result(r)
        if not it or it["name"].lower() in ex or it["url"] in seen:
            continue
        if category and it["category"] != category:
            continue
        seen.add(it["url"])
        items.append(it)
        if len(items) >= count:
            break
    return items
