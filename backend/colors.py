"""Product color from the cutout image (the catalog has no color field and names rarely say it).

Two passes, both resumable and both written to the `color` / `color_src` columns of the catalog:

  pixel   instant and free: classify the opaque pixels of the cutout into the 12 canonical colors
          (intent.COLORS). Good for plain garments; can be fooled by skin, soles, big prints.
  vision  Gemini looks at the image (one small JPEG per product) and names the garment's colors.
          Authoritative: overwrites a pixel guess. Needs GEMINI_API_KEY; rate-limited; stops
          politely when the quota is used up and resumes later (the progress is in the database).

`sweep()` runs both in a background thread started by the server, then re-checks every
few minutes for products that were added since. A product's color is shared with the team
through dataset/catalog.json (dataset.FIELDS), so each product is looked at once, by whoever
runs the server first.
"""

import colorsys
import io
import sys
import threading
import time
from pathlib import Path

import catalog
import config
import intent as intent_mod

CANON = list(intent_mod.COLORS)          # black white grey blue red green brown beige pink purple orange yellow
VISION_PAUSE = 4.5                       # seconds between vision calls (~13/min, inside free-tier limits)
RESCAN_EVERY = 600                       # seconds between looks for newly added products

_started = False
_lock = threading.Lock()


# ---------------------------------------------------------------- pixel pass
def _classify(r: int, g: int, b: int) -> str:
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    h *= 360
    if v < 0.20:
        return "black"
    if s < 0.13:
        return "white" if v > 0.78 else "grey"
    if s < 0.30 and v > 0.55 and 20 <= h < 60:
        return "beige"
    if h < 15 or h >= 345:
        return "pink" if (v > 0.8 and s < 0.5) else "red"
    if h < 45:
        return "brown" if v < 0.62 else "orange"
    if h < 68:
        return "yellow" if v > 0.6 else "brown"
    if h < 170:
        return "green"
    if h < 255:
        return "blue"
    if h < 290:
        return "purple"
    return "pink"


def from_pixels(path: str | Path) -> list[str]:
    """Colors of the opaque part of a cutout, dominant first ([] if the image is unreadable or empty)."""
    from PIL import Image
    try:
        im = Image.open(path).convert("RGBA")
    except Exception:  # noqa: BLE001 — missing/corrupt file
        return []
    im.thumbnail((96, 96))
    counts: dict[str, int] = {}
    total = 0
    raw = im.tobytes()                                  # RGBA, 4 bytes per pixel (works on every Pillow version)
    for i in range(0, len(raw), 4):
        r, g, b, a = raw[i], raw[i + 1], raw[i + 2], raw[i + 3]
        if a < 200:
            continue                                   # background / edge
        c = _classify(r, g, b)
        counts[c] = counts.get(c, 0) + 1
        total += 1
    if total < 40:
        return []
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    # chromatic colors count from 12% of the garment, neutrals from 25% (soles, trims, shadows are neutral);
    # the dominant color is always kept.
    keep = [c for i, (c, n) in enumerate(ranked)
            if i == 0 or n / total >= (0.25 if c in ("black", "white", "grey") else 0.12)]
    return keep[:3]


# ---------------------------------------------------------------- vision pass
def _jpeg(path: Path) -> bytes:
    from PIL import Image
    im = Image.open(path).convert("RGBA")
    im.thumbnail((512, 512))
    bg = Image.new("RGB", im.size, (255, 255, 255))
    bg.paste(im, mask=im.split()[3])
    out = io.BytesIO()
    bg.save(out, "JPEG", quality=85)
    return out.getvalue()


def from_vision(path: str | Path) -> list[str]:
    """Colors as named by the vision model ([] if it names none we know). Raises llm/Gemini errors."""
    import gemini
    return gemini.product_color(_jpeg(Path(path)), CANON)


# ---------------------------------------------------------------- sweep
def _file(cutout: str | None) -> Path | None:
    if not cutout:
        return None
    p = Path(config.DATA_DIR) / "cutouts" / Path(cutout).name
    return p if p.exists() else None


def _pending(src_not: tuple[str, ...]) -> list[tuple[str, str]]:
    """(url, cutout) of in-stock products whose color source is not in `src_not` (NULL counts as none)."""
    with catalog._lock:
        rows = catalog._db().execute(
            "SELECT url, COALESCE(cutout_p, cutout_m) AS c, color_src FROM products "
            "WHERE stock='in_stock' AND (cutout_p IS NOT NULL OR cutout_m IS NOT NULL)").fetchall()
    return [(r["url"], r["c"]) for r in rows if (r["color_src"] or "") not in src_not]


def pixel_pass() -> int:
    n = 0
    for url, cutout in _pending(("pixel", "vision", "name")):
        f = _file(cutout)
        cols = from_pixels(f) if f else []
        if cols:
            catalog.set_color(url, cols, "pixel")
            n += 1
    if n:
        catalog.clear_results()
    return n


def vision_pass() -> tuple[int, str]:
    """(done, why it stopped): 'complete' | 'quota' | 'error'."""
    import llm
    import gemini
    if llm.provider() != "gemini":
        return 0, "no-key"
    done = 0
    for url, cutout in _pending(("vision",)):
        f = _file(cutout)
        if not f:
            continue
        try:
            cols = from_vision(f)
        except gemini.QuotaError as err:
            print(f"[colors] vision paused: {err}", file=sys.stderr)
            return done, "quota"
        except Exception as err:  # noqa: BLE001
            print(f"[colors] vision failed for {Path(cutout).name}: {err}", file=sys.stderr)
            return done, "error"
        if cols:
            catalog.set_color(url, cols, "vision")
            done += 1
            if done % 10 == 0:
                catalog.clear_results()
        time.sleep(VISION_PAUSE)
    if done:
        catalog.clear_results()
    return done, "complete"


def _loop() -> None:
    while True:
        try:
            n = pixel_pass()
            if n:
                print(f"[colors] pixel pass: {n} products · {progress()}", file=sys.stderr)
            done, why = vision_pass() if config.COLOR_VISION else (0, "off")
            if done or why not in ("complete", "no-key", "off"):
                print(f"[colors] vision pass: {done} products ({why}) · {progress()}", file=sys.stderr)
        except Exception as err:  # noqa: BLE001 — never kill the thread
            print(f"[colors] sweep error: {err}", file=sys.stderr)
        time.sleep(RESCAN_EVERY)


def progress() -> str:
    """'colors: 410/558 by image (320 verified by AI)'."""
    with catalog._lock:
        total, have, ai = catalog._db().execute(
            "SELECT COUNT(*), SUM(color IS NOT NULL AND color!=''), SUM(color_src='vision') FROM products").fetchone()
    return f"colors: {have or 0}/{total} by image, {ai or 0} verified by AI"


def sweep() -> None:
    """Start the background color sweep once (idempotent)."""
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, name="colors", daemon=True).start()
