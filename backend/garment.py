"""Cut just the clothing out of an on-model photo. Free, local, no API key.

    extract(img, category)       -> (RGBA of only the garment, info)   or (None, info)
    best_extract(photos, cat)    -> same, trying several photos and keeping the cleanest

Uses the U2Net cloth-segmentation model (the file rembg ships, ~170 MB, downloaded once from
GitHub into backend/data/models/) through onnxruntime. It labels each pixel background /
upper-body garment / lower-body garment / full-body garment, so head, hair, skin, hands and
shoes drop out and only the clothes remain. Categories it can do: top, outerwear, bottom.

To get a cleaner cut we spend more time per image: the photo is processed at up to 1200 px,
the model runs on the photo and its mirror image (predictions averaged), the mask is cleaned
(specks dropped, holes filled, edges closed and feathered), and when a product has several
photos each is tried and the best-scoring cut wins. A cut that is still too small, too
fragmented or too cut-off is rejected rather than shown.
"""

from __future__ import annotations

import io
import os
import threading
import urllib.request
from pathlib import Path

import config

MODEL_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net_cloth_seg.onnx"
MODEL_PATH = Path(config.DATA_DIR) / "models" / "u2net_cloth_seg.onnx"
SIZE = 768
MAX_SIDE = 1200
UPPER, LOWER, FULL = 1, 2, 3
WANT = {"top": (UPPER, FULL), "outerwear": (UPPER, FULL), "bottom": (LOWER, FULL)}
SEGMENTABLE = tuple(WANT)

MIN_SHARE = 0.04      # garment must be at least this share of the photo
MIN_SIDE = 220        # px on the short side after cropping (the UI shows these fairly large)
MIN_FILL = 0.35       # garment area / bounding-box area; very low means scattered fragments
MIN_MAIN = 0.85       # largest connected piece must hold this share of the garment (sets allowed below)

_lock = threading.Lock()
_session = None
_failed = False


def _load():
    global _session, _failed
    if _session is not None or _failed:
        return _session
    with _lock:
        if _session is not None or _failed:
            return _session
        try:
            import numpy  # noqa: F401
            import onnxruntime as ort
            if not MODEL_PATH.exists():
                MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
                print("(garment: downloading cloth-segmentation model, ~170 MB, one time)")
                tmp = MODEL_PATH.with_suffix(".part")
                with urllib.request.urlopen(MODEL_URL, timeout=300) as r, open(tmp, "wb") as f:
                    while chunk := r.read(1 << 20):
                        f.write(chunk)
                os.replace(tmp, MODEL_PATH)
            _session = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
        except Exception as err:  # noqa: BLE001
            print(f"(garment: segmentation unavailable: {err})")
            _failed = True
    return _session


def available() -> bool:
    return _load() is not None


def can_handle(category: str | None) -> bool:
    return category in SEGMENTABLE and available()


def _probs(im, sess):
    """Per-class probabilities, [4, H, W] at the photo's own size."""
    import numpy as np
    from PIL import Image
    w, h = im.size
    scale = SIZE / max(w, h)
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    canvas = Image.new("RGB", (SIZE, SIZE), (255, 255, 255))      # letterbox: nothing is stretched
    ox, oy = (SIZE - nw) // 2, (SIZE - nh) // 2
    canvas.paste(im.resize((nw, nh), Image.LANCZOS), (ox, oy))
    arr = np.asarray(canvas, dtype=np.float32)
    arr = arr / max(float(arr.max()), 1e-6)
    arr = (arr - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array([0.229, 0.224, 0.225], dtype=np.float32)
    x = np.ascontiguousarray(arr.transpose(2, 0, 1)[None].astype(np.float32))
    out = sess.run(None, {sess.get_inputs()[0].name: x})[0][0]      # [4, 768, 768] logits
    e = np.exp(out - out.max(axis=0, keepdims=True))
    p = (e / e.sum(axis=0, keepdims=True))[:, oy:oy + nh, ox:ox + nw]
    return np.stack([np.asarray(Image.fromarray(c).resize((w, h), Image.BILINEAR)) for c in p])


def _clean(mask):
    """bool [H,W] -> (feathered PIL 'L' alpha, share of the garment in its largest piece)."""
    import numpy as np
    from PIL import Image, ImageFilter
    main = 1.0
    try:
        from scipy import ndimage as ndi
    except Exception:  # noqa: BLE001
        ndi = None
    if ndi is not None:
        k = max(3, int(max(mask.shape) / 150)) | 1
        mask = ndi.binary_closing(mask, structure=np.ones((k, k)))     # bridge thin gaps (dark-on-dark seams)
        lab, n = ndi.label(mask)
        if n > 1:
            sizes = ndi.sum(mask, lab, range(1, n + 1))
            main = float(sizes.max() / sizes.sum())
            keep = [i + 1 for i, s in enumerate(sizes) if s >= 0.12 * sizes.max()]   # keep pairs/sets, drop specks
            mask = np.isin(lab, keep)
        mask = ndi.binary_fill_holes(mask)
    m = Image.fromarray((mask * 255).astype("uint8"))
    r = max(1, int(max(m.size) / 400))
    m = m.filter(ImageFilter.MedianFilter(2 * r + 3)).filter(ImageFilter.GaussianBlur(r + 0.5))
    return m, main


def extract(img, category: str | None = None, tta: bool = True, multi_ok: bool = False):
    """(garment RGBA cropped to its bounding box, info). The image is None if the cut isn't good enough."""
    sess = _load()
    if sess is None:
        return None, {"reason": "segmentation unavailable", "score": 0.0}
    import numpy as np
    from PIL import Image
    if isinstance(img, (bytes, bytearray)):
        img = Image.open(io.BytesIO(img))
    rgba = img.convert("RGBA")
    if max(rgba.size) > MAX_SIDE:
        rgba.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    flat = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    flat.alpha_composite(rgba)
    rgb = flat.convert("RGB")

    p = _probs(rgb, sess)
    if tta:
        p = (p + _probs(rgb.transpose(Image.FLIP_LEFT_RIGHT), sess)[:, :, ::-1]) / 2
    want = WANT.get(category or "", (UPPER, LOWER, FULL))
    mask = np.isin(p.argmax(axis=0), want)
    if mask.sum() < 50:
        return None, {"reason": "no garment found", "score": 0.0}
    alpha, main = _clean(mask)
    a = np.asarray(alpha) > 127
    ys, xs = np.where(a)
    if len(ys) == 0:
        return None, {"reason": "no garment found", "score": 0.0}
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    area = float(a.sum())
    bw, bh = box[2] - box[0], box[3] - box[1]
    info = {
        "share": area / a.size, "w": bw, "h": bh, "fill": area / max(1, bw * bh), "main": main,
        "touch_edge": sum([box[0] <= 1, box[1] <= 1, box[2] >= a.shape[1] - 1, box[3] >= a.shape[0] - 1]),
    }
    ok, why = judge(info, multi_ok)
    info["reason"] = why
    # higher is better: solid, one piece, big, not sliced by the frame
    info["score"] = round(info["fill"] * min(1.0, info["share"] / 0.15) * (0.5 + 0.5 * main) - 0.08 * info["touch_edge"], 4) if ok else 0.0
    if not ok:
        return None, info
    out = rgba.copy()
    out.putalpha(Image.fromarray(np.minimum(np.asarray(alpha), np.asarray(rgba.getchannel("A")))))
    return out.crop(box), info


def judge(info: dict, multi_ok: bool = False) -> tuple[bool, str]:
    if info["share"] < MIN_SHARE:
        return False, "garment too small in the photo"
    if min(info["w"], info["h"]) < MIN_SIDE:
        return False, "garment too small after crop"
    if info["fill"] < MIN_FILL:
        return False, "garment mask is fragmented"
    if not multi_ok and info["main"] < MIN_MAIN:
        return False, "garment is split into pieces"
    return True, "ok"


def best_extract(photos: list, category: str | None, multi_ok: bool = False, tta: bool = True):
    """Try each photo (bytes or PIL), return the best (image, info, index) or (None, last info, -1)."""
    best, best_info, best_i = None, {"reason": "no photos", "score": 0.0}, -1
    for i, ph in enumerate(photos):
        if ph is None:
            continue
        try:
            img, info = extract(ph, category, tta=tta, multi_ok=multi_ok)
        except Exception as err:  # noqa: BLE001
            img, info = None, {"reason": f"error: {err}", "score": 0.0}
        if img is not None and info["score"] > (best_info.get("score") or 0.0):
            best, best_info, best_i = img, info, i
        elif best is None:
            best_info = info
    return best, best_info, best_i
