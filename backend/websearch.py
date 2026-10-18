"""Free, keyless product search: DuckDuckGo's HTML endpoint restricted to the
allowed store(s), then each product page's own JSON-LD for the facts.

No AI involved. Rate-limited and polite; falls back silently to the AI
provider (if configured) when it finds nothing.
"""

import html
import json
import re
import sys
import threading
import time
import urllib.parse
import urllib.request

import config
import images

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_gap = threading.Lock()
_last = 0.0
MIN_GAP = 1.5  # seconds between search requests

_RESULT = re.compile(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_TAG = re.compile(r"<[^>]+>")

# Product-page URL shapes per store (so category/search pages are skipped).
_PRODUCT_PATHS = {
    "nike.com": re.compile(r"https?://(www\.)?nike\.com(/[a-z]{2}(/[a-z]{2})?)?/t/[^\s?#]+", re.I),
}


def _polite():
    global _last
    with _gap:
        wait = MIN_GAP - (time.time() - _last)
        if wait > 0:
            time.sleep(wait)
        _last = time.time()


def _decode_result_url(href: str) -> str:
    href = html.unescape(href)
    if href.startswith("//"):
        href = "https:" + href
    m = re.search(r"[?&]uddg=([^&]+)", href)
    return urllib.parse.unquote(m.group(1)) if m else href


def search_links(query: str, limit: int = 10) -> list[tuple[str, str]]:
    """(url, title) results for a query across the allowed stores."""
    sites = " OR ".join(f"site:{d}" for d in config.ALLOWED_DOMAINS) if config.ALLOWED_DOMAINS else ""
    q = f"{query} {sites}".strip()
    url = config.SEARCH_BASE_URL + "/html/?" + urllib.parse.urlencode({"q": q})
    _polite()
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html", "Accept-Language": "en-US,en;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            page = resp.read(2_000_000).decode("utf-8", "replace")
    except Exception as err:  # noqa: BLE001
        print(f"[websearch] failed ({err})", file=sys.stderr)
        return []
    out, seen = [], set()
    for href, title in _RESULT.findall(page):
        link = _decode_result_url(href).split("#")[0]
        if link in seen:
            continue
        seen.add(link)
        out.append((link, html.unescape(_TAG.sub("", title)).strip()))
        if len(out) >= limit:
            break
    return out


def is_product_url(url: str) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower()
    for domain, pat in _PRODUCT_PATHS.items():
        if domain in host:
            return bool(pat.match(url))
    return "/product" in url or "/p/" in url or "/t/" in url


def _walk_products(node, out: list):
    if isinstance(node, dict):
        t = node.get("@type")
        types = t if isinstance(t, list) else [t]
        if any(str(x).lower() in ("product", "productgroup") for x in types if x):
            out.append(node)
        for v in node.values():
            _walk_products(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_products(v, out)


def product_from_page(url: str) -> dict | None:
    """A product dict from the page's JSON-LD (name, brand, price, stock, photos)."""
    blocks = images.jsonld_blocks(url)
    found: list = []
    for b in blocks:
        try:
            _walk_products(json.loads(b), found)
        except (json.JSONDecodeError, TypeError):
            continue
    if not found:
        return None
    p = found[0]
    name = str(p.get("name") or "").strip()
    brand = p.get("brand")
    brand = (brand.get("name") if isinstance(brand, dict) else brand) or ""
    offers = p.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    price = offers.get("price") or offers.get("lowPrice") or 0
    avail = str(offers.get("availability") or "").lower()
    stock = "out_of_stock" if any(k in avail for k in ("outofstock", "soldout", "discontinued")) else "in_stock"
    img = p.get("image")
    photos = [img] if isinstance(img, str) else [i if isinstance(i, str) else i.get("url", "") for i in (img or [])] if isinstance(img, list) else []
    if not name:
        return None
    return {
        "name": name, "brand": str(brand).strip() or (config.ALLOWED_DOMAINS[0].split(".")[0].title() if config.ALLOWED_DOMAINS else "Unknown"),
        "price": price, "url": url, "image": photos[0] if photos else "", "stock": stock,
        "category": "",  # filled by caller from name/title
    }


_CATEGORY_WORDS = [
    ("shoes", ["shoe", "sneaker", "boot", "sandal", "slide", "cleat", "dunk", "air force", "jordan", "pegasus", "vomero", "air max", "footwear", "p-6000", "cortez", "blazer"]),
    ("outerwear", ["jacket", "coat", "parka", "windrunner", "windbreaker", "anorak", "puffer", "vest", "shell", "gilet"]),
    ("bottom", ["pant", "jogger", "short", "trouser", "legging", "tight", "skirt", "cargo", "sweatpant"]),
    ("headwear", ["cap", "hat", "beanie", "visor", "headband", "bucket"]),
    ("bag", ["bag", "backpack", "tote", "duffel", "crossbody", "hip pack", "fanny", "sling"]),
    ("accessory", ["sock", "belt", "glove", "scarf", "sunglass", "watch", "wristband", "sleeve", "bottle", "lanyard"]),
    ("top", ["hoodie", "sweatshirt", "crew", "tee", "t-shirt", "shirt", "top", "tank", "jersey", "polo", "sweater", "pullover", "half-zip", "long-sleeve", "fleece"]),
]


def category_for(text: str) -> str:
    t = text.lower()
    if "hoodie" in t or "sweatshirt" in t or "crew" in t:
        return "top"
    for cat, words in _CATEGORY_WORDS:
        if any(w in t for w in words):
            return cat
    return "top"


def search(prompt: str, category: str | None, exclude: list[str], count: int) -> list[dict]:
    """Products for a prompt: web search → product pages → JSON-LD."""
    from concurrent.futures import ThreadPoolExecutor
    hint = {"shoes": "shoes", "outerwear": "jacket", "bottom": "pants", "headwear": "hat", "bag": "bag", "accessory": "accessories", "top": "top"}.get(category or "", "")
    links = [l for l in search_links(f"{prompt} {hint}".strip(), limit=14) if is_product_url(l[0])]
    if not links:
        return []
    ex = {n.lower() for n in exclude}
    with ThreadPoolExecutor(max_workers=4) as pool:
        pages = list(pool.map(lambda l: product_from_page(l[0]), links[: count * 2]))
    items = []
    for (link, title), p in zip(links, pages):
        if not p or p["name"].lower() in ex:
            continue
        p["category"] = category_for(f"{p['name']} {title}")
        if category and p["category"] != category:
            continue
        items.append(p)
        if len(items) >= count:
            break
    return items
