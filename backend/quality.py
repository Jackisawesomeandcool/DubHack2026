"""Free, local photo-quality checks for catalog cutouts. No API key needed.

    person_score(img)   YOLOX-tiny "person" confidence (0..1), run through onnxruntime
    skin_fraction(img)  share of skin-toned pixels
    shows_person(img)   combined verdict: True if a model is wearing the product
    check_cutout(path)  (ok, reason) for a cutout PNG on disk

Why two signals: the detector alone also calls flat-laid jackets and hoodies "people"
(a flat hoodie looks like a torso), and skin tone alone misses dark clothing on dark
backgrounds. Requiring the detector AND some skin/face evidence fixed most of both
on our 391 real cutouts. Rule of thumb, tuned on that set (see docs):

    person  =  detector >= 0.5  and  (face-height skin >= 7%  or  skin >= 3.5%  or  a tall narrow body)
    (stricter for shoes/accessories/headwear, looser for bags; see shows_person)

Needs `pip install onnxruntime numpy` (both optional). The 20 MB model is downloaded
once from GitHub into backend/data/models/. If anything is missing every function
returns None ("unknown") and callers fall back to the old skin-tone check.
"""

from __future__ import annotations

import io
import os
import threading
import urllib.request
from pathlib import Path

import config

MODEL_URL = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_tiny.onnx"
MODEL_PATH = Path(config.DATA_DIR) / "models" / "yolox_tiny.onnx"
SIZE = 416
PERSON_SCORE = 0.5
SKIN_MIN = 0.035

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
                tmp = MODEL_PATH.with_suffix(".part")
                with urllib.request.urlopen(MODEL_URL, timeout=120) as r, open(tmp, "wb") as f:
                    while chunk := r.read(1 << 20):
                        f.write(chunk)
                os.replace(tmp, MODEL_PATH)
            _session = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
        except Exception as err:  # noqa: BLE001
            print(f"(quality: person detector unavailable: {err})")
            _failed = True
    return _session


def available() -> bool:
    return _load() is not None


def _to_rgb_on_white(img):
    """Accepts PNG/JPEG bytes or a PIL image; transparent areas become white."""
    from PIL import Image
    if isinstance(img, (bytes, bytearray)):
        img = Image.open(io.BytesIO(img))
    img = img.convert("RGBA")
    bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
    bg.alpha_composite(img)
    return bg.convert("RGB")


def person_score(img) -> float | None:
    sess = _load()
    if sess is None:
        return None
    import numpy as np
    from PIL import Image
    im = _to_rgb_on_white(img)
    scale = SIZE / max(im.size)
    w, h = max(1, round(im.size[0] * scale)), max(1, round(im.size[1] * scale))
    canvas = np.full((SIZE, SIZE, 3), 114, dtype=np.float32)
    canvas[:h, :w] = np.asarray(im.resize((w, h), Image.BILINEAR), dtype=np.float32)[:, :, ::-1]  # BGR, 0-255
    x = np.ascontiguousarray(canvas.transpose(2, 0, 1)[None])
    out = sess.run(None, {sess.get_inputs()[0].name: x})[0][0]   # [anchors, 85]: x y w h obj cls...
    return float((out[:, 4] * out[:, 5]).max())


def _skin_stats(img) -> tuple[float, float, float]:
    """(whole-frame skin share, skin share of the product's top 35%, bbox width/height)."""
    import numpy as np
    from PIL import Image
    if isinstance(img, (bytes, bytearray)):
        img = Image.open(io.BytesIO(img))
    rgba = img.convert("RGBA")
    alpha = np.asarray(rgba.getchannel("A")) > 128
    ys, xs = np.where(alpha)
    if len(ys) == 0:
        return 0.0, 0.0, 1.0
    box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    aspect = (box[2] - box[0]) / max(1, box[3] - box[1])
    sub = rgba.crop(box)
    sub.thumbnail((200, 200))
    ycc = np.asarray(sub.convert("RGB").convert("YCbCr")).astype(int)
    a = np.asarray(sub.getchannel("A")) > 128
    m = ((ycc[:, :, 1] >= 77) & (ycc[:, :, 1] <= 127) & (ycc[:, :, 2] >= 133) & (ycc[:, :, 2] <= 173)
         & (ycc[:, :, 0] >= 60) & a)
    cut = max(1, int(m.shape[0] * 0.35))
    whole = m.sum() / max(1, a.sum())
    top = m[:cut].sum() / max(1, a[:cut].sum())   # a face sits up here; logos and prints are lower or smaller
    return float(whole), float(top), float(aspect)


def skin_fraction(img) -> float:
    return _skin_stats(img)[0]


def shows_person(img, category: str | None = None) -> bool | None:
    """True when a person is wearing/holding the product. None if the detector is unavailable."""
    s = person_score(img)
    if s is None:
        return None
    if s < PERSON_SCORE:
        return False
    whole, top, aspect = _skin_stats(img)
    if category in ("shoes", "accessory"):
        # tiny items: pink socks and tan boots look like skin, so ask for a lot of it
        return whole >= 0.07
    if category == "headwear":
        return whole >= 0.04          # a face under a cap/visor
    if category == "bag":
        # flat-lay bags score low on the detector; a high score means somebody is carrying it
        if s >= 0.75 or top >= 0.03 or whole >= 0.02:
            return True
    elif top >= 0.07 or whole >= (0.02 if category == "bottom" else 0.035):   # a face up top, or plenty of skin
        return True   # (flat pants show ~0% skin, so legs/ankles at 2% mean a body)
    # Back views and dark hair show no skin, but a tall narrow figure is still a body.
    return s >= 0.85 and aspect < (0.36 if category == "bottom" else 0.4)


def check_cutout(path: str | Path, category: str | None = None) -> tuple[bool, str]:
    """(ok, reason). ok=False means a person is wearing it. Unknown counts as ok."""
    try:
        from PIL import Image
        im = Image.open(path)
        verdict = shows_person(im, category)
    except Exception as err:  # noqa: BLE001
        return True, f"unchecked ({err})"
    if verdict:
        return False, "a person is wearing it"
    return True, "ok"
