"""Product cutouts: a transparent PNG of just the item (or the item on a model
when the models toggle is on). Nothing is ever shown with its original
background.

Pipeline per product:
1. Choose the photo. Nike's search API hands us a product-only photo and an
   on-model photo directly, so no vision call is needed. Otherwise gather the
   listing page's photos and ask Grok (vision, images sent as base64) which one
   fits the mode; if none does, the product is dropped.
2. rembg removes the background; the result is trimmed and cached under
   backend/data/cutouts/ and served at /cutouts/<id>.png.

rembg is installed automatically on first run if missing.
"""

import hashlib
import io
import json
import sys
import threading
import urllib.request

import bgremove
import config
import images

CUTOUT_DIR = config.DATA_DIR / "cutouts"
MAX_CANDIDATES = 8
MAX_SIDE = 800
VISION_SIDE = 384

_lock = threading.Lock()
_cache_path = config.DATA_DIR / "cutouts.json"
_cache: dict[str, dict] | None = None

def available() -> bool:
    return bgremove.ready()


def warm() -> None:
    bgremove.warm()


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


def _fullres(url: str | None) -> str | None:
    """Nike CDN thumbnails carry a transform segment; ask for the large one."""
    if not url:
        return url
    return url.replace("/t_PDP_144_v1/", "/t_PDP_1280_v1/").replace("/t_PDP_144_v1,", "/t_PDP_1280_v1,").replace("/t_default/", "/t_PDP_1280_v1/")


# ---------------------------------------------------------------- fetch
def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": images.UA, "Accept": "image/*,*/*"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read(15_000_000)


def _thumb_jpeg(raw: bytes) -> bytes | None:
    """Small JPEG for the vision check."""
    if not bgremove.ready():
        return None
    try:
        im = bgremove.Image.open(io.BytesIO(raw)).convert("RGB")
        im.thumbnail((VISION_SIDE, VISION_SIDE))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=80)
        return buf.getvalue()
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- vision pick
def pick(candidates: list[bytes | None], allow_models: bool) -> int:
    """Index of the candidate photo that fits the mode, or -1.
    allow_models=False: must show ONLY the product (no person).
    allow_models=True:  prefer the item worn on a model."""
    import llm
    import people
    valid = [(i, raw) for i, raw in enumerate(candidates) if raw]
    if not valid:
        return -1
    if not llm.configured():
        # Free heuristic: skin-tone share decides "person present".
        judged = [(i, people.has_person(raw)) for i, raw in valid]
        if allow_models:
            return next((i for i, p in judged if p), judged[0][0])
        return next((i for i, p in judged if p is False), -1)
    if allow_models:
        ask = ("These are photos from one clothing listing. Which photo best shows the item worn on a model "
               "(full view, item clearly visible)? If none is on a model, pick the clearest full view of the item. "
               'Reply with JSON only: {"index": <0-based index>}.')
    else:
        ask = ("These are photos from one clothing listing. Which photo shows ONLY the product (flat lay / plain "
               "background / invisible mannequin) with NO person, model, face, hands or body visible? Prefer the "
               'clearest full view. Reply with JSON only: {"index": <0-based index>} or {"index": -1} if every photo '
               "includes a person.")
    thumbs, order = [], []
    for i, raw in valid:
        t = _thumb_jpeg(raw)
        if t:
            thumbs.append(t); order.append(i)
    if not thumbs:
        return valid[0][0]
    try:
        idx = llm.pick_index(ask, thumbs)
        return order[idx] if 0 <= idx < len(order) else -1
    except Exception as err:  # noqa: BLE001
        print(f"[cutouts] VISION CHECK FAILED ({err}) — product skipped", file=sys.stderr)
        return -1


# ---------------------------------------------------------------- cutout
def make_cutout(url: str, raw: bytes | None = None, allow_flat: bool = True) -> str | None:
    """Served path of a transparent PNG for this photo, or None."""
    cache = _load_cache()
    hit = cache.get(url)
    if hit and (CUTOUT_DIR / hit["file"]).exists():
        return f"/cutouts/{hit['file']}"
    if not available():
        return None
    try:
        raw = raw or _download(url)
        im = bgremove.Image.open(io.BytesIO(raw))
        if max(im.size) > MAX_SIDE:  # keep work small
            im.thumbnail((MAX_SIDE, MAX_SIDE))
            buf = io.BytesIO(); im.convert("RGB").save(buf, "JPEG", quality=92); raw = buf.getvalue()
        out, tier = bgremove.remove(raw, allow_flat=allow_flat)
        if out is None:
            print(f"[cutouts] no background remover available for {url}", file=sys.stderr)
            return None
        bbox = out.getchannel("A").getbbox()
        if not bbox:
            return None
        out = out.crop(bbox)
        name = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ".png"
        CUTOUT_DIR.mkdir(parents=True, exist_ok=True)
        out.save(CUTOUT_DIR / name, "PNG", optimize=True)
        with _lock:
            cache[url] = {"file": name, "tier": tier}
            _save_cache()
        return f"/cutouts/{name}"
    except Exception as err:  # noqa: BLE001
        print(f"[cutouts] failed for {url}: {err}", file=sys.stderr)
        return None


# ---------------------------------------------------------------- pipeline
def resolve(item: dict, allow_models: bool = False) -> None:
    """Set item['image'] to a cutout path, or '' to drop the item."""
    mode = "m" if allow_models else "p"
    cache = _load_cache()
    source_key = f"pick:{mode}:{item.get('url') or item.get('image')}"
    chosen = cache.get(source_key, {}).get("src")
    raw = None

    if not chosen:
        # Fast path: the source already told us which photo is which.
        direct = item.get("image_model" if allow_models else "image_product") or ""
        if direct and images.image_ok(direct):
            chosen = direct
        else:
            cands: list[str] = []
            for c in [item.get("image_product"), item.get("image_model"), item.get("image")] + list(item.get("candidates") or []):
                c = _fullres(c)
                if c and c not in cands:
                    cands.append(c)
            if item.get("url") and not item.get("candidates"):
                for c in images.candidates_from_page(item["url"]):
                    if c not in cands:
                        cands.append(c)
            cands = cands[: MAX_CANDIDATES * 2]
            from concurrent.futures import ThreadPoolExecutor
            def fetch(u):
                try:
                    return _download(u) if images.image_ok(u) else None
                except Exception:  # noqa: BLE001
                    return None
            with ThreadPoolExecutor(max_workers=8) as pool:
                blobs = list(pool.map(fetch, cands))
            keep = [(u, b) for u, b in zip(cands, blobs) if b][:MAX_CANDIDATES]
            idx = pick([b for _, b in keep], allow_models)
            if idx < 0:
                print(f"[cutouts] no suitable photo among {len(keep)} for {item.get('name')}", file=sys.stderr)
                item["image"] = ""
                return
            chosen, raw = keep[idx]
        with _lock:
            cache[source_key] = {"src": chosen}
            _save_cache()

    path = make_cutout(chosen, raw, allow_flat=True)
    item["image"] = path or ""
    for k in ("image_product", "image_model"):
        item.pop(k, None)


def resolve_all(items: list[dict], allow_models: bool = False) -> None:
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(items)))) as pool:
        list(pool.map(lambda it: resolve(it, allow_models), items))
