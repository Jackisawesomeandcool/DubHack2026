"""Random fits, pre-built in the background so the board opens instantly.

A small pool of complete fits (one piece per category, picked by the AI
ranker from the catalog for one of the STYLES prompts) is kept on disk.
GET /api/random-fit pops one and a background thread refills the pool; when
the pool is empty a random one-per-category fit is served instantly instead.
"""

import json
import random
import sys
import threading
import time

import catalog
import config
import finder
import llm

POOL_SIZE = 3  # per mode (product-only / with models)
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


def build_one(models: bool = False) -> dict:
    """Build a random fit; one retry with a different style if the first
    attempt yields too few usable pieces."""
    last: llm.LLMError | None = None
    for prompt in random.sample(STYLES, 2):
        try:
            return _build(prompt, models)
        except llm.LLMError as err:
            print(f"[fits] build '{prompt}' failed: {err}", file=sys.stderr)
            last = err
    raise last or llm.LLMError("Could not build a fit")


def _build(prompt: str, models: bool) -> dict:
    items = finder.find(prompt, models, count=7)   # catalog only: the AI picks a coherent fit
    if not items:
        raise llm.LLMError("No pieces with a usable photo")
    # One piece per category: keep the first of each.
    seen, picked = set(), []
    for it in items:
        if it["category"] in seen:
            continue
        seen.add(it["category"])
        picked.append(it)
    if len(picked) < 3:
        raise llm.LLMError("Not enough distinct pieces for a fit")
    return {"prompt": prompt, "models": models, "items": picked}


def _short_modes(pool: list) -> list[bool]:
    return [m for m in (False, True) if sum(1 for f in pool if bool(f.get("models")) == m) < POOL_SIZE]


def _refill() -> None:
    global _refilling
    try:
        while True:
            with _lock:
                short = _short_modes(_read())
            if not short:
                return
            try:
                fit = build_one(short[0])
            except llm.LLMError as err:
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
    with _lock:
        if _refilling or not _short_modes(_read()):
            return
        _refilling = True
    threading.Thread(target=_refill, daemon=True).start()


def _pop(pool: list, models: bool):
    idx = [i for i, f in enumerate(pool) if bool(f.get("models")) == models]
    if not idx:
        return None
    return pool.pop(random.choice(idx))


def take(models: bool = False) -> dict:
    """Random fit: a pre-built AI-picked fit from the pool when one is ready,
    else a random one-piece-per-category fit from the catalog (instant), else
    build one now."""
    with _lock:
        pool = _read()
        fit = _pop(pool, models)
        if fit:
            _write(pool)
    if fit is None:
        fit = catalog.random_fit(models) or build_one(models)
    ensure_pool()
    return fit
