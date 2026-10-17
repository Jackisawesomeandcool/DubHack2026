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

import base64
import hashlib
import importlib
import io
import json
import subprocess
import sys
import threading
import urllib.request

import config
import images

CUTOUT_DIR = config.DATA_DIR / "cutouts"
MAX_CANDIDATES = 8
MAX_SIDE = 800
VISION_SIDE = 384

_lock = threading.Lock()
_infer = threading.Semaphore(2)  # rembg is memory-hungry; at most 2 at once
_session = None
_cache_path = config.DATA_DIR / "cutouts.json"
_cache: dict[str, dict] | None = None

Image = None
_rembg = None


def _try_import() -> bool:
    global Image, _rembg
    try:
        from PIL import Image as _Image
        _rembg = importlib.import_module("rembg")
        Image = _Image
        return True
    except Exception:  # noqa: BLE001
        return False


def ensure_installed() -> bool:
    """Import rembg, installing it (and onnxruntime, pillow) if needed."""
    if _try_import():
        return True
    req = config.BACKEND_DIR / "requirements.txt"
    print("[cutouts] rembg not found — installing (one time, ~1 min)…", file=sys.stderr)
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(req)], check=True)
    except Exception as err:  # noqa: BLE001
        print(f"[cutouts] automatic install failed: {err}\n"
              f"          run manually:  {sys.executable} -m pip install -r {req}", file=sys.stderr)
        return False
    ok = _try_import()
    print("[cutouts] rembg ready" if ok else "[cutouts] rembg still unavailable after install", file=sys.stderr)
    return ok


def available() -> bool:
    return _rembg is not None


def warm() -> None:
    """Install if needed and load the model in the background."""
    def run():
        if ensure_installed():
            _get_session()
    threading.Thread(target=run, daemon=True).start()


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
        if _session is None and _rembg is not None:
            _session = _rembg.new_session("isnet-general-use")
        return _session


# ---------------------------------------------------------------- fetch
def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": images.UA, "Accept": "image/*,*/*"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read(15_000_000)


def _thumb_data_url(raw: bytes) -> str | None:
    """Small JPEG data URL for the vision check (xAI needn't fetch the CDN)."""
    if Image is None:
        return None
    try:
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        im.thumbnail((VISION_SIDE, VISION_SIDE))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=80)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- vision pick
def pick(candidates: list[bytes | None], allow_models: bool) -> int:
    """Index of the candidate photo that fits the mode, or -1.
    allow_models=False: must show ONLY the product (no person).
    allow_models=True:  prefer the item worn on a model."""
    valid = [(i, raw) for i, raw in enumerate(candidates) if raw]
    if not valid:
        return -1
    if not config.XAI_API_KEY:
        return valid[0][0]
    if allow_models:
        ask = ("These are photos from one clothing listing. Which photo best shows the item worn on a model "
               "(full view, item clearly visible)? If none is on a model, pick the clearest full view of the item. "
               'Reply with JSON only: {"index": <0-based index>}.')
    else:
        ask = ("These are photos from one clothing listing. Which photo shows ONLY the product (flat lay / plain "
               "background / invisible mannequin) with NO person, model, face, hands or body visible? Prefer the "
               'clearest full view. Reply with JSON only: {"index": <0-based index>} or {"index": -1} if every photo '
               "includes a person.")
    content = [{"type": "text", "text": ask}]
    order = []
    for i, raw in valid:
        data_url = _thumb_data_url(raw)
        if data_url:
            content.append({"type": "image_url", "image_url": {"url": data_url, "detail": "low"}})
            order.append(i)
    if not order:
        return valid[0][0]
    payload = {"model": config.XAI_VISION_MODEL, "messages": [{"role": "user", "content": content}],
               "response_format": {"type": "json_object"}, "temperature": 0}
    req = urllib.request.Request(
        f"{config.XAI_BASE_URL}/chat/completions", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {config.XAI_API_KEY}"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        idx = int(json.loads(data["choices"][0]["message"]["content"]).get("index", -1))
        return order[idx] if 0 <= idx < len(order) else -1
    except Exception as err:  # noqa: BLE001
        detail = getattr(err, "read", None)
        detail = detail().decode("utf-8", "replace")[:200] if callable(detail) else ""
        print(f"[cutouts] VISION CHECK FAILED ({err}) {detail} — product skipped", file=sys.stderr)
        return -1


# ---------------------------------------------------------------- cutout
def make_cutout(url: str, raw: bytes | None = None) -> str | None:
    """Served path of a transparent PNG for this photo, or None."""
    cache = _load_cache()
    hit = cache.get(url)
    if hit and (CUTOUT_DIR / hit["file"]).exists():
        return f"/cutouts/{hit['file']}"
    if not available() and not ensure_installed():
        return None
    try:
        raw = raw or _download(url)
        im = Image.open(io.BytesIO(raw)).convert("RGBA")
        im.thumbnail((MAX_SIDE, MAX_SIDE))
        with _infer:
            out = _rembg.remove(im, session=_get_session(), post_process_mask=True)
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
            for c in [item.get("image_product"), item.get("image_model"), item.get("image")]:
                if c and c not in cands:
                    cands.append(c)
            if item.get("url"):
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

    path = make_cutout(chosen, raw)
    item["image"] = path or ""
    for k in ("image_product", "image_model"):
        item.pop(k, None)


def resolve_all(items: list[dict], allow_models: bool = False) -> None:
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(items)))) as pool:
        list(pool.map(lambda it: resolve(it, allow_models), items))
