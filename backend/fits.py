"""Random fits, pre-built in the background so the board opens instantly.

A small pool of complete fits (one piece per category, all with verified
real photos) is kept on disk. GET /api/random-fit pops one and a background
thread refills the pool. The very first request on a fresh install has to
wait for one live search.
"""

import json
import random
import sys
import threading
import time

import config
import grok

POOL_SIZE = 4
_lock = threading.Lock()
_refilling = False
_path = config.DATA_DIR / "fits.json"

STYLES = [
    "late 2000s downtown fit with baggy pants and retro sneakers",
    "all-black minimal fit with a windbreaker and low-top sneakers",
    "gorpcore trail fit with a fleece, hiking pants and trail shoes",
    "y2k streetwear with cargo pants, a boxy tee and chunky sneakers",
    "summer court fit with shorts, a tank, a cap and white sneakers",
    "cozy fall fit with a tech fleece hoodie, joggers and dunks",
    "skater fit with wide-leg pants, a graphic tee and skate shoes",
    "clean athleisure fit in earth tones",
    "retro running fit with a track jacket and vintage runners",
    "basketball warm-up fit with a half-zip, mesh shorts and high-tops",
    "monochrome grey loungewear fit with a crewneck and sweatpants",
    "rainy day fit with a shell jacket, cargo pants and waterproof shoes",
]


def _read() -> list:
    if not _path.exists():
        return []
    try:
        return json.loads(_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _write(pool: list) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _path.with_suffix(".tmp")
    tmp.write_text(json.dumps(pool), encoding="utf-8")
    tmp.replace(_path)


def build_one() -> dict:
    """Build a random fit; one retry with a different style if the first
    attempt yields too few product-only pieces."""
    last: grok.GrokError | None = None
    for prompt in random.sample(STYLES, 2):
        try:
            return _build(prompt)
        except grok.GrokError as err:
            print(f"[fits] build '{prompt}' failed: {err}", file=sys.stderr)
            last = err
    raise last or grok.GrokError("Could not build a fit")


def _build(prompt: str) -> dict:
    items = grok.suggest(prompt, count=7)
    # One piece per category: keep the first of each.
    seen, picked = set(), []
    for it in items:
        if it["category"] in seen:
            continue
        seen.add(it["category"])
        picked.append(it)
    if len(picked) < 3:
        raise grok.GrokError("Not enough distinct pieces for a fit")
    return {"prompt": prompt, "items": picked}


def _refill() -> None:
    global _refilling
    try:
        while True:
            with _lock:
                if len(_read()) >= POOL_SIZE:
                    return
            try:
                fit = build_one()
            except grok.GrokError as err:
                print(f"[fits] background build failed: {err}", file=sys.stderr)
                return
            with _lock:
                pool = _read()
                pool.append(fit)
                _write(pool)
            print(f"[fits] pool now {len(pool)}", file=sys.stderr)
    finally:
        with _lock:
            _refilling = False


def ensure_pool() -> None:
    """Kick off background building if the pool is short."""
    global _refilling
    if not config.XAI_API_KEY:
        return
    with _lock:
        if _refilling or len(_read()) >= POOL_SIZE:
            return
        _refilling = True
    threading.Thread(target=_refill, daemon=True).start()


def take() -> dict:
    """Return a random fit immediately if one is pooled, else build one now.
    The background refill only starts after a synchronous build, so the first
    load isn't competing with it for the API."""
    with _lock:
        pool = _read()
        if pool:
            fit = pool.pop(random.randrange(len(pool)))
            _write(pool)
        else:
            fit = None
    if fit is None and _refilling:
        # A background build is already running — wait for it instead of
        # starting a second search in parallel.
        for _ in range(240):
            time.sleep(0.5)
            with _lock:
                pool = _read()
                if pool:
                    fit = pool.pop(0)
                    _write(pool)
                    break
            if not _refilling:
                break
    if fit is None:
        fit = build_one()
    ensure_pool()
    return fit
