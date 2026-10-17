"""Product-only cutouts.

1. Gather candidate photos for a product (the listing page's og:image /
   JSON-LD images plus the one Grok saw).
2. Ask Grok (vision) which candidate shows ONLY the product — no model /
   person — and reject the product if none does.
3. Remove the background with rembg and save a trimmed transparent PNG under
   backend/data/cutouts/, served at /cutouts/<id>.png.

Results are cached by source URL so each photo is processed once.
"""

import hashlib
import io
import json
import sys
import threading
import urllib.request

import config
import images

try:  # optional, but needed for real cutouts
    from PIL import Image
    from rembg import new_session, remove as rembg_remove
    _HAVE_REMBG = True
except Exception:  # noqa: BLE001
    _HAVE_REMBG = False

CUTOUT_DIR = config.DATA_DIR / "cutouts"
MAX_CANDIDATES = 5
MAX_SIDE = 900

_lock = threading.Lock()
_session = None
_cache_path = config.DATA_DIR / "cutouts.json"
_cache: dict[str, dict] | None = None


def available() -> bool:
    return _HAVE_REMBG


def _load_cache() -> dict:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(_cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _cache = {}
    return _cache


def _save_cache() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path.write_text(json.dumps(_cache), encoding="utf-8")


def _get_session():
    global _session
    with _lock:
        if _session is None:
            _session = new_session("isnet-general-use")
        return _session


# ---------------------------------------------------------------- vision pick
def pick_product_only(candidates: list[str]) -> int:
    """Index of the candidate that shows only the product (no person), or -1."""
    if not candidates:
        return -1
    if not config.XAI_API_KEY:
        return 0
    content = [{
        "type": "text",
        "text": (
            "These are photos from one clothing listing. Which photo shows ONLY the product "
            "(flat lay / on a plain background / on an invisible mannequin) with NO person, model, "
            "face, hands or body visible? Prefer the clearest full view of the item. "
            'Reply with JSON only: {"index": <0-based index>} or {"index": -1} if every photo includes a person.'
        ),
    }]
    for url in candidates:
        content.append({"type": "image_url", "image_url": {"url": url, "detail": "low"}})
    payload = {
        "model": config.XAI_MODEL,
        "messages": [{"role": "user", "content": content}],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    req = urllib.request.Request(
        f"{config.XAI_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {config.XAI_API_KEY}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = data["choices"][0]["message"]["content"]
        idx = int(json.loads(text).get("index", -1))
        return idx if 0 <= idx < len(candidates) else -1
    except Exception as err:  # noqa: BLE001
        print(f"[cutouts] vision check failed ({err}); keeping first candidate", file=sys.stderr)
        return 0


# ---------------------------------------------------------------- cutout
def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": images.UA, "Accept": "image/*,*/*"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read(15_000_000)


def make_cutout(url: str) -> str | None:
    """Return the served path of a transparent PNG for this photo, or None."""
    cache = _load_cache()
    hit = cache.get(url)
    if hit and (CUTOUT_DIR / hit["file"]).exists():
        return f"/cutouts/{hit['file']}"
    if not _HAVE_REMBG:
        return None
    try:
        raw = _download(url)
        im = Image.open(io.BytesIO(raw)).convert("RGBA")
        im.thumbnail((MAX_SIDE, MAX_SIDE))
        out = rembg_remove(im, session=_get_session(), post_process_mask=True)
        bbox = out.getchannel("A").getbbox()
        if not bbox:
            return None
        out = out.crop(bbox)
        name = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ".png"
        CUTOUT_DIR.mkdir(parents=True, exist_ok=True)
        out.save(CUTOUT_DIR / name, "PNG", optimize=True)
        with _lock:
            cache[url] = {"file": name}
            _save_cache()
        return f"/cutouts/{name}"
    except Exception as err:  # noqa: BLE001
        print(f"[cutouts] failed for {url}: {err}", file=sys.stderr)
        return None


# ---------------------------------------------------------------- pipeline
def resolve(item: dict) -> None:
    """Fill item['image'] with a product-only cutout, or '' to drop the item."""
    cache = _load_cache()
    source_key = f"pick:{item.get('url') or item.get('image')}"
    chosen = cache.get(source_key, {}).get("src")

    if not chosen:
        cands: list[str] = []
        if item.get("image"):
            cands.append(item["image"])
        if item.get("url"):
            for c in images.candidates_from_page(item["url"]):
                if c not in cands:
                    cands.append(c)
        cands = [c for c in cands[:MAX_CANDIDATES * 2] if images.image_ok(c)][:MAX_CANDIDATES]
        idx = pick_product_only(cands)
        if idx < 0:
            item["image"] = ""
            return
        chosen = cands[idx]
        with _lock:
            cache[source_key] = {"src": chosen}
            _save_cache()

    path = make_cutout(chosen)
    item["image"] = path if path else (chosen if not _HAVE_REMBG else "")
    if path:
        item["source_image"] = chosen


def resolve_all(items: list[dict]) -> None:
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(items)))) as pool:
        list(pool.map(resolve, items))
