"""Local catalog of popular, fully processed listings.

Every product that passes the cutout pipeline — from background warm-up
searches of popular items, random-fit builds, or user searches — is stored
here with its finished cutout. Random fits, swap alternatives and most
searches are then answered instantly from disk; live search only fills gaps.
"""

import json
import random
import re
import sys
import threading
import time

import config

_path = config.DATA_DIR / "catalog.json"
_lock = threading.Lock()
_items: list[dict] | None = None
_warming = False

# Popular searches warmed in the background (product-only mode first).
POPULAR = [
    "dunk low", "air force 1", "air jordan 1", "air max", "pegasus", "vomero", "p-6000",
    "tech fleece hoodie", "tech fleece joggers", "windrunner jacket", "club fleece crew",
    "cargo pants", "sportswear shorts", "dri-fit tee", "solo swoosh", "half-zip",
    "puffer jacket", "acg jacket", "acg pants", "beanie", "futura cap", "bucket hat",
    "backpack", "crossbody bag", "crew socks", "windbreaker", "sweatpants", "track jacket",
]
MIN_FOR_RANDOM = 12  # items needed before random fits come from the catalog

_WORD = re.compile(r"[a-z0-9]+")
_SYN = {
    "jacket": "outerwear", "jackets": "outerwear", "coat": "outerwear", "coats": "outerwear", "windbreaker": "outerwear", "puffer": "outerwear",
    "hoodie": "top", "hoodies": "top", "tee": "top", "tees": "top", "shirt": "top", "shirts": "top", "sweatshirt": "top", "crewneck": "top", "top": "top", "tops": "top",
    "pants": "bottom", "joggers": "bottom", "shorts": "bottom", "cargos": "bottom", "sweatpants": "bottom", "bottoms": "bottom", "trousers": "bottom",
    "shoes": "shoes", "shoe": "shoes", "sneakers": "shoes", "sneaker": "shoes", "kicks": "shoes", "boots": "shoes", "runners": "shoes",
    "hat": "headwear", "hats": "headwear", "cap": "headwear", "caps": "headwear", "beanie": "headwear",
    "bag": "bag", "bags": "bag", "backpack": "bag", "tote": "bag",
    "socks": "accessory", "belt": "accessory", "accessory": "accessory", "accessories": "accessory",
}


def _load() -> list[dict]:
    global _items
    if _items is None:
        try:
            _items = json.loads(_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _items = []
    return _items


def _save() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _path.with_suffix(".tmp")
    tmp.write_text(json.dumps(_items), encoding="utf-8")
    tmp.replace(_path)


def _key(item: dict) -> str:
    return f"{item.get('brand','').lower()}|{item.get('name','').lower()}"


def add(items: list[dict], models: bool, query: str = "") -> None:
    """Store finished products (with cutouts) for the given mode."""
    with _lock:
        cat = _load()
        by_key = {(_key(i), bool(i.get("models"))): i for i in cat}
        changed = False
        for it in items:
            if not it.get("image"):
                continue
            k = (_key(it), models)
            entry = by_key.get(k)
            tags = set((entry or {}).get("tags", []))
            tags.update(_WORD.findall(query.lower()))
            rec = {k2: v for k2, v in it.items() if k2 not in ("x", "y", "uid", "pending")}
            rec.update({"models": models, "tags": sorted(tags), "seen": time.time()})
            if entry:
                entry.update(rec)
            else:
                cat.append(rec)
                by_key[k] = rec
            changed = True
        if changed:
            _save()


def _score(item: dict, words: list[str], category: str | None) -> float:
    if category and item.get("category") != category:
        return 0.0
    hay = f"{item.get('name','')} {' '.join(item.get('tags', []))}".lower()
    score = 0.0
    for w in words:
        if w in _SYN and _SYN[w] == item.get("category"):
            score += 1.0
        elif w in hay:
            score += 2.0 if w in item.get("name", "").lower() else 1.0
    return score


def search(prompt: str, category: str | None, models: bool, exclude: list[str], limit: int = 6) -> list[dict]:
    words = [w for w in _WORD.findall(prompt.lower()) if len(w) > 1]
    cat_hint = category or next((_SYN[w] for w in words if w in _SYN), None)
    ex = {n.lower() for n in exclude}
    with _lock:
        pool = [i for i in _load() if bool(i.get("models")) == models and i.get("name", "").lower() not in ex]
    scored = [(_score(i, words, cat_hint), i) for i in pool]
    scored = [(s, i) for s, i in scored if s > 0]
    scored.sort(key=lambda t: (-t[0], -t[1].get("seen", 0)))
    return [dict(i) for _, i in scored[:limit]]


def random_fit(models: bool) -> dict | None:
    """One piece per category from the catalog, or None if too thin."""
    with _lock:
        pool = [i for i in _load() if bool(i.get("models")) == models and i.get("image")]
    if len(pool) < MIN_FOR_RANDOM:
        return None
    by_cat: dict[str, list] = {}
    for i in pool:
        by_cat.setdefault(i["category"], []).append(i)
    if not all(c in by_cat for c in ("top", "bottom", "shoes")):
        return None
    cats = ["top", "bottom", "shoes"] + [c for c in ("outerwear", "headwear", "bag", "accessory") if c in by_cat and random.random() < 0.7]
    items = [dict(random.choice(by_cat[c])) for c in cats]
    for it in items:
        it.pop("tags", None); it.pop("seen", None); it.pop("models", None)
    return {"prompt": "from popular items", "models": models, "items": items}


def count(models: bool | None = None) -> int:
    with _lock:
        cat = _load()
    return len(cat) if models is None else sum(1 for i in cat if bool(i.get("models")) == models)


def warm(find) -> None:
    """Background: run the popular searches once (product-only), storing results.
    `find(term, models)` must return finished items with cutouts."""
    global _warming
    with _lock:
        if _warming:
            return
        _warming = True

    def run():
        global _warming
        try:
            done = {t for i in _load() for t in i.get("tags", [])}
            for term in POPULAR:
                if all(w in done for w in _WORD.findall(term)):
                    continue
                try:
                    items = find(term, False)
                    add(items, False, term)
                    print(f"[catalog] warmed '{term}' → {len(items)} items (catalog {count()})", file=sys.stderr)
                except Exception as err:  # noqa: BLE001
                    print(f"[catalog] warm '{term}' failed: {err}", file=sys.stderr)
        finally:
            with _lock:
                _warming = False

    threading.Thread(target=run, daemon=True).start()
