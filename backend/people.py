"""Free 'is there a person in this photo?' check when no vision model is
available: fraction of skin-toned pixels (YCbCr range), plus a sanity check
that the skin region is a sizeable blob rather than scattered noise.
Good enough to separate on-model shots from product shots in most listings."""

import io

SKIN_FRACTION = 0.025   # >= this share of pixels skin-toned -> treat as a person


def has_person(raw: bytes) -> bool | None:
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001
        return None
    # Local YOLOX person detector when available (quality.py); skin tone otherwise.
    try:
        import quality
        if quality.available():
            verdict = quality.shows_person(Image.open(io.BytesIO(raw)))
            if verdict is not None:
                return verdict
    except Exception:  # noqa: BLE001
        pass
    try:
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        im.thumbnail((256, 256))
        ycc = im.convert("YCbCr")
        y, cb, cr = ycc.split()
        # Skin: Cb in ~[77,127], Cr in ~[133,173] (Chai & Ngan), bright enough to be skin not shadow.
        cb_m = cb.point(lambda v: 255 if 77 <= v <= 127 else 0)
        cr_m = cr.point(lambda v: 255 if 133 <= v <= 173 else 0)
        y_m = y.point(lambda v: 255 if v >= 60 else 0)
        from PIL import ImageChops, ImageFilter
        skin = ImageChops.multiply(ImageChops.multiply(cb_m, cr_m), y_m)
        skin = skin.filter(ImageFilter.MinFilter(3))  # drop speckle; keep blobs
        hist = skin.histogram()
        frac = hist[255] / float(im.size[0] * im.size[1])
        return frac >= SKIN_FRACTION
    except Exception:  # noqa: BLE001
        return None
