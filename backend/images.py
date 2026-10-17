"""Resolve product images directly from retailer product pages.

For each product we open its listing URL and read the page's own product
image (Open Graph / Twitter card / JSON-LD Product image). Only URLs that
really serve an image are kept, so the collage never shows a broken photo.
"""

import gzip
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from html.parser import HTMLParser

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
PAGE_TIMEOUT = 6
IMAGE_TIMEOUT = 4
MAX_PAGE_BYTES = 2_000_000


def _get(url: str, timeout: int, byte_range: str | None = None):
    headers = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"}
    if byte_range:
        headers["Range"] = byte_range
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(req, timeout=timeout)


_IMG_URL = re.compile(r"https?://[^\s\"'<>\\]+?\.(?:jpe?g|png|webp)(?:\?[^\s\"'<>\\]*)?", re.I)


class _MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta: dict[str, str] = {}
        self.jsonld: list[str] = []
        self.imgs: list[str] = []
        self._in_jsonld = False
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "img":
            for key in ("src", "data-src", "data-srcset", "srcset"):
                if a.get(key):
                    self.imgs.append(a[key].split(",")[0].split(" ")[0])
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and a.get("content") and key not in self.meta:
                self.meta[key] = a["content"]
        elif tag == "script" and (a.get("type") or "").lower() == "application/ld+json":
            self._in_jsonld = True
            self._buf = []

    def handle_data(self, data):
        if self._in_jsonld:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._in_jsonld:
            self._in_jsonld = False
            self.jsonld.append("".join(self._buf))


def _jsonld_images(blocks: list[str]) -> list[str]:
    found: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            t = node.get("@type")
            types = t if isinstance(t, list) else [t]
            if any(str(x).lower() == "product" for x in types if x):
                img = node.get("image")
                if isinstance(img, str):
                    found.append(img)
                elif isinstance(img, list):
                    found.extend(i if isinstance(i, str) else i.get("url", "") for i in img)
                elif isinstance(img, dict):
                    found.append(img.get("url", ""))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for block in blocks:
        try:
            walk(json.loads(block))
        except (json.JSONDecodeError, TypeError):
            continue
    return [f for f in found if f]


def _fetch_html(url: str) -> tuple[str, str]:
    with _get(url, PAGE_TIMEOUT) as resp:
        raw = resp.read(MAX_PAGE_BYTES)
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return raw.decode("utf-8", "replace"), resp.geturl()


def jsonld_blocks(url: str) -> list[str]:
    """Raw JSON-LD script bodies from a page ([] on any failure)."""
    try:
        html, _ = _fetch_html(url)
    except Exception as err:  # noqa: BLE001
        print(f"[images] page fetch failed {url}: {err}", file=sys.stderr)
        return []
    parser = _MetaParser()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001
        pass
    return parser.jsonld


def candidates_from_page(url: str) -> list[str]:
    """Image URLs the product page itself declares, best first."""
    try:
        with _get(url, PAGE_TIMEOUT) as resp:
            raw = resp.read(MAX_PAGE_BYTES)
            if resp.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            final_url = resp.geturl()
    except Exception as err:  # noqa: BLE001 — any fetch failure just means no image
        print(f"[images] page fetch failed {url}: {err}", file=sys.stderr)
        return []

    html = raw.decode("utf-8", "replace")
    parser = _MetaParser()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001
        pass

    out: list[str] = []
    for key in ("og:image:secure_url", "og:image", "twitter:image", "twitter:image:src"):
        if parser.meta.get(key):
            out.append(parser.meta[key])
    out.extend(_jsonld_images(parser.jsonld))

    # Every product view the page carries (gallery images, embedded JSON), so a
    # product-only angle can be chosen even when the hero shot is on-model.
    host_hint = urllib.parse.urlparse(out[0]).netloc if out else ""
    extra = parser.imgs + _IMG_URL.findall(html)
    extra = [unescape(u).replace("\\/", "/") for u in extra]
    if host_hint:
        extra = [u for u in extra if host_hint in u] + [u for u in extra if host_hint not in u]
    skip = ("logo", "icon", "sprite", "favicon", "swatch", "badge", "avatar", "pixel", "1x1")
    for u in extra:
        if any(k in u.lower() for k in skip):
            continue
        out.append(u)
        if len(out) >= 14:
            break

    # Shopify-style stores expose the product JSON next to the page.
    if "/products/" in final_url and not out:
        try:
            pj = final_url.split("?")[0].rstrip("/") + ".json"
            with _get(pj, PAGE_TIMEOUT) as resp:
                data = json.loads(resp.read(MAX_PAGE_BYTES).decode("utf-8", "replace"))
            for im in data.get("product", {}).get("images", [])[:1]:
                out.append(im.get("src", ""))
        except Exception:  # noqa: BLE001
            pass

    cleaned = []
    for c in out:
        c = unescape(c).strip()
        if c.startswith("//"):
            c = "https:" + c
        elif c.startswith("/"):
            c = urllib.parse.urljoin(final_url, c)
        if c.startswith("http") and c not in cleaned:
            cleaned.append(c)
    return cleaned


def image_ok(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    try:
        with _get(url, IMAGE_TIMEOUT, "bytes=0-2047") as resp:
            ctype = resp.headers.get("Content-Type", "")
            return resp.status < 400 and ctype.startswith("image/")
    except Exception:  # noqa: BLE001
        return False


def resolve(item: dict) -> None:
    """Set item['image'] to a verified photo of the product.

    Fast path: the photo URL Grok saw on the listing (one small ranged GET).
    Slow path: open the product page and read the image it declares.
    """
    direct = item.get("image", "")
    if direct and image_ok(direct):
        item["image"] = direct
        return
    if item.get("url"):
        for cand in candidates_from_page(item["url"]):
            if image_ok(cand):
                item["image"] = cand
                return
    item["image"] = ""


def resolve_all(items: list[dict]) -> None:
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(items)))) as pool:
        list(pool.map(resolve, items))
