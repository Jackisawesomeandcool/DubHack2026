"""Background removal with three tiers, cheapest first.

1. flat-key   — product photos on a flat light background (Nike's product
                shots, most retailer flat lays): flood-fill the background
                from the corners and make it transparent. Milliseconds, free,
                needs only Pillow.
2. API        — Photoroom or remove.bg (key in backend/.env). ~1-2 s, paid
                per image, no local model. Used for on-model shots and busy
                backgrounds.
3. local      — rembg (isnet) on this machine. Free but a heavy install and
                a few seconds per image; installed lazily on first need.

Every photo is processed once (callers cache by URL).
"""

import importlib
import io
import json
import subprocess
import sys
import threading
import urllib.request
import uuid

import config

Image = None
ImageDraw = None
ImageStat = None
_rembg = None
_session = None
_lock = threading.Lock()
_infer = threading.Semaphore(2)

FLAT_TOL = 30          # color distance treated as "background" during the flood
FLAT_MIN_LUMA = 215    # corners must be at least this bright to count as a flat background
FLAT_MAX_SPREAD = 18   # and agree with each other within this much


# ---------------------------------------------------------------- deps
def _pillow() -> bool:
    global Image, ImageDraw, ImageStat
    if Image is not None:
        return True
    try:
        from PIL import Image as _I, ImageDraw as _D, ImageStat as _S
        Image, ImageDraw, ImageStat = _I, _D, _S
        return True
    except Exception:  # noqa: BLE001
        pass
    print("[bg] installing pillow…", file=sys.stderr)
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pillow"], check=True)
        from PIL import Image as _I, ImageDraw as _D, ImageStat as _S
        Image, ImageDraw, ImageStat = _I, _D, _S
        return True
    except Exception as err:  # noqa: BLE001
        print(f"[bg] pillow install failed: {err}", file=sys.stderr)
        return False


def _local() -> bool:
    """Import rembg, installing it on first need (slow, one time)."""
    global _rembg
    if _rembg is not None:
        return True
    with _lock:
        if _rembg is not None:
            return True
        try:
            _rembg = importlib.import_module("rembg")
            return True
        except Exception:  # noqa: BLE001
            pass
        print("[bg] rembg not found — installing in the background (one time, a few minutes)…", file=sys.stderr)
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "rembg", "onnxruntime"], check=True)
            _rembg = importlib.import_module("rembg")
            print("[bg] rembg ready", file=sys.stderr)
            return True
        except Exception as err:  # noqa: BLE001
            print(f"[bg] rembg install failed: {err}\n     set PHOTOROOM_API_KEY or REMOVEBG_API_KEY in backend/.env instead", file=sys.stderr)
            return False


def ready() -> bool:
    """Can we produce cutouts right now (at least the free flat-key tier)?"""
    return _pillow()


def warm() -> None:
    def run():
        if _pillow() and config.CUTOUT_PROVIDER == "local":
            _local()
    threading.Thread(target=run, daemon=True).start()


# ---------------------------------------------------------------- tier 1: flat key
def _corner_stats(im):
    w, h = im.size
    k = max(2, min(w, h) // 25)
    boxes = [(0, 0, k, k), (w - k, 0, w, k), (0, h - k, k, h), (w - k, h - k, w, h)]
    means = []
    for b in boxes:
        st = ImageStat.Stat(im.crop(b))
        means.append(tuple(st.mean[:3]))
    lumas = [0.299 * r + 0.587 * g + 0.114 * b for r, g, b in means]
    spread = max(max(c) - min(c) for c in zip(*means))
    return means, min(lumas), spread


def is_flat_background(raw: bytes) -> bool:
    if not _pillow():
        return False
    try:
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        _, luma, spread = _corner_stats(im)
        return luma >= FLAT_MIN_LUMA and spread <= FLAT_MAX_SPREAD
    except Exception:  # noqa: BLE001
        return False


def flat_key(raw: bytes):
    """Transparent RGBA for a flat-background photo, or None if it isn't one.

    The connected-background flood runs on a small copy (fast), then the mask
    is refined at full resolution by color distance to the backdrop, so edges
    stay crisp and light-colored parts *inside* the item are kept.
    """
    from PIL import ImageChops, ImageFilter
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    means, luma, spread = _corner_stats(im)
    if luma < FLAT_MIN_LUMA or spread > FLAT_MAX_SPREAD:
        return None
    w, h = im.size
    bg = tuple(int(sum(c) / 4) for c in zip(*means))

    # Full-res "looks like backdrop" mask (channel ops only).
    diff = ImageChops.difference(im, Image.new("RGB", (w, h), bg)).convert("L")
    near_bg = diff.point(lambda v: 255 if v <= FLAT_TOL else 0)

    # Connectivity to the edges, decided on a small copy.
    scale = max(1, max(w, h) // 180)
    small = im.resize((max(8, w // scale), max(8, h // scale)), Image.BILINEAR)
    sw, sh = small.size
    marker = (255, 0, 255)
    seeds = [(x, 0) for x in range(0, sw, 4)] + [(x, sh - 1) for x in range(0, sw, 4)] \
          + [(0, y) for y in range(0, sh, 4)] + [(sw - 1, y) for y in range(0, sh, 4)]
    for xy in seeds:
        if small.getpixel(xy) != marker:
            ImageDraw.floodfill(small, xy, marker, thresh=FLAT_TOL)
    r, g, b = small.split()
    conn_small = ImageChops.multiply(ImageChops.multiply(
        r.point(lambda v: 255 if v == 255 else 0), g.point(lambda v: 255 if v == 0 else 0)),
        b.point(lambda v: 255 if v == 255 else 0))
    conn = conn_small.filter(ImageFilter.MaxFilter(3)).resize((w, h), Image.BILINEAR).point(lambda v: 255 if v > 90 else 0)

    backdrop = ImageChops.multiply(conn, near_bg)
    alpha = ImageChops.invert(backdrop).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    out = im.convert("RGBA")
    out.putalpha(alpha)
    return out


# ---------------------------------------------------------------- tier 2: APIs
def _multipart(fields: dict, file_field: str, filename: str, data: bytes, ctype: str) -> tuple[bytes, str]:
    boundary = "----haul" + uuid.uuid4().hex
    body = io.BytesIO()
    for k, v in fields.items():
        body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename=\"{filename}\"\r\nContent-Type: {ctype}\r\n\r\n".encode())
    body.write(data)
    body.write(f"\r\n--{boundary}--\r\n".encode())
    return body.getvalue(), f"multipart/form-data; boundary={boundary}"


def _post(url: str, headers: dict, body: bytes, ctype: str) -> bytes:
    req = urllib.request.Request(url, data=body, headers={**headers, "Content-Type": ctype}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def photoroom(raw: bytes) -> bytes:
    body, ctype = _multipart({"format": "png"}, "image_file", "photo.jpg", raw, "image/jpeg")
    return _post("https://sdk.photoroom.com/v1/segment", {"x-api-key": config.PHOTOROOM_API_KEY, "Accept": "image/png"}, body, ctype)


def removebg(raw: bytes) -> bytes:
    body, ctype = _multipart({"size": "auto", "format": "png"}, "image_file", "photo.jpg", raw, "image/jpeg")
    return _post("https://api.remove.bg/v1.0/removebg", {"X-Api-Key": config.REMOVEBG_API_KEY, "Accept": "image/png"}, body, ctype)


# ---------------------------------------------------------------- tier 3: local
def local(raw: bytes):
    if not _local():
        return None
    global _session
    with _lock:
        if _session is None:
            _session = _rembg.new_session("isnet-general-use")
    im = Image.open(io.BytesIO(raw)).convert("RGBA")
    with _infer:
        return _rembg.remove(im, session=_session, post_process_mask=True)


# ---------------------------------------------------------------- entry
def remove(raw: bytes, allow_flat: bool = True):
    """RGBA image with transparent background, or None. Returns (image, tier)."""
    if not _pillow():
        return None, "none"
    if allow_flat:
        try:
            out = flat_key(raw)
            if out is not None:
                return out, "flat"
        except Exception as err:  # noqa: BLE001
            print(f"[bg] flat key failed: {err}", file=sys.stderr)
    provider = config.CUTOUT_PROVIDER
    try:
        if provider == "photoroom" and config.PHOTOROOM_API_KEY:
            return Image.open(io.BytesIO(photoroom(raw))).convert("RGBA"), "photoroom"
        if provider == "removebg" and config.REMOVEBG_API_KEY:
            return Image.open(io.BytesIO(removebg(raw))).convert("RGBA"), "removebg"
    except Exception as err:  # noqa: BLE001
        detail = getattr(err, "read", None)
        detail = detail().decode("utf-8", "replace")[:200] if callable(detail) else ""
        print(f"[bg] {provider} failed ({err}) {detail}; trying local", file=sys.stderr)
    out = local(raw)
    return (out, "local") if out is not None else (None, "none")
