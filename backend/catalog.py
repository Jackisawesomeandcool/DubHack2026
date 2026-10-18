"""Local product catalog (SQLite, standard library only).

Products are keyed by listing URL and carry a finished cutout per mode
(product-only / on-model), tags for matching, stock state and freshness
timestamps. Searches, swap alternatives and random fits are answered from
here first; live search only fills what's missing, and everything it finds
is written back. Out-of-stock products are never served.
"""

import json
import random
import re
import sqlite3
import sys
import threading
import time

import config

DB_PATH = config.DATA_DIR / "catalog.sqlite"
RESULT_TTL = 60 * 60          # cached search results stay valid this long
MIN_FOR_RANDOM = 12           # items needed before random fits come from the catalog

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None
_warming = False

POPULAR = [
    "dunk low", "air force 1", "air jordan 1", "air max", "pegasus", "vomero", "p-6000",
    "tech fleece hoodie", "tech fleece joggers", "windrunner jacket", "club fleece crew",
    "cargo pants", "sportswear shorts", "dri-fit tee", "solo swoosh", "half-zip",
    "puffer jacket", "acg jacket", "acg pants", "beanie", "futura cap", "bucket hat",
    "backpack", "crossbody bag", "crew socks", "windbreaker", "sweatpants", "track jacket",
]

_WORD = re.compile(r"[a-z0-9]+")
_SYN = {
    "jacket": "outerwear", "jackets": "outerwear", "coat": "outerwear", "coats": "outerwear", "windbreaker": "outerwear", "puffer": "outerwear", "outerwear": "outerwear",
    "hoodie": "top", "hoodies": "top", "tee": "top", "tees": "top", "shirt": "top", "shirts": "top", "sweatshirt": "top", "crewneck": "top", "top": "top", "tops": "top", "sweater": "top",
    "pants": "bottom", "joggers": "bottom", "shorts": "bottom", "cargos": "bottom", "sweatpants": "bottom", "bottoms": "bottom", "trousers": "bottom", "jeans": "bottom",
    "shoes": "shoes", "shoe": "shoes", "sneakers": "shoes", "sneaker": "shoes", "kicks": "shoes", "boots": "shoes", "runners": "shoes", "dunks": "shoes",
    "hat": "headwear", "hats": "headwear", "cap": "headwear", "caps": "headwear", "beanie": "headwear",
    "bag": "bag", "bags": "bag", "backpack": "bag", "tote": "bag",
    "socks": "accessory", "belt": "accessory", "accessory": "accessory", "accessories": "accessory",
}
_STOP = {"a", "an", "the", "and", "or", "with", "for", "in", "on", "of", "to", "fit", "look", "outfit", "style", "nike", "mens", "womens", "men", "women"}


# ---------------------------------------------------------------- db
def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY,
                url TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL, brand TEXT NOT NULL, price REAL NOT NULL,
                category TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '',
                cutout_p TEXT, cutout_m TEXT,
                stock TEXT NOT NULL DEFAULT 'in_stock',
                source TEXT, last_checked REAL, added_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_products_cat ON products(category);
            CREATE TABLE IF NOT EXISTS results (
                key TEXT PRIMARY KEY, urls TEXT NOT NULL, created REAL NOT NULL
            );
        """)
    return _conn


def _row_to_item(r: sqlite3.Row, models: bool) -> dict:
    return {
        "name": r["name"], "brand": r["brand"], "price": r["price"], "url": r["url"],
        "image": (r["cutout_m"] if models else r["cutout_p"]) or "",
        "stock": r["stock"], "category": r["category"],
    }


def _url_key(item: dict) -> str:
    return item.get("url") or f"name:{item.get('brand','').lower()}|{item.get('name','').lower()}"


# ---------------------------------------------------------------- write
def upsert(items: list[dict], models: bool, query: str = "", source: str = "") -> None:
    """Store finished products (with a cutout for this mode)."""
    now = time.time()
    with _lock:
        db = _db()
        for it in items:
            if not it.get("image"):
                continue
            url = _url_key(it)
            words = {w for w in _WORD.findall(f"{query} {it.get('name','')}".lower()) if w not in _STOP and len(w) > 1}
            row = db.execute("SELECT tags, cutout_p, cutout_m FROM products WHERE url=?", (url,)).fetchone()
            col = "cutout_m" if models else "cutout_p"
            if row:
                tags = set((row["tags"] or "").split()) | words
                db.execute(
                    f"UPDATE products SET name=?, brand=?, price=?, category=?, tags=?, {col}=?, stock=?, source=COALESCE(?, source), last_checked=? WHERE url=?",
                    (it["name"], it["brand"], float(it.get("price") or 0), it["category"], " ".join(sorted(tags)),
                     it["image"], it.get("stock", "in_stock"), source or None, now, url))
            else:
                db.execute(
                    f"INSERT INTO products (url, name, brand, price, category, tags, {col}, stock, source, last_checked, added_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (url, it["name"], it["brand"], float(it.get("price") or 0), it["category"], " ".join(sorted(words)),
                     it["image"], it.get("stock", "in_stock"), source, now, now))
        db.commit()


def set_stock(url: str, stock: str) -> None:
    with _lock:
        _db().execute("UPDATE products SET stock=?, last_checked=? WHERE url=?", (stock, time.time(), url))
        _db().commit()


def cache_results(prompt: str, category: str | None, models: bool, items: list[dict]) -> None:
    key = _result_key(prompt, category, models)
    with _lock:
        _db().execute("INSERT OR REPLACE INTO results (key, urls, created) VALUES (?,?,?)",
                      (key, json.dumps([_url_key(i) for i in items if i.get("image")]), time.time()))
        _db().commit()


# ---------------------------------------------------------------- read
def _result_key(prompt: str, category: str | None, models: bool) -> str:
    return f"{' '.join(_WORD.findall(prompt.lower()))}|{category or ''}|{'m' if models else 'p'}"


def cached_results(prompt: str, category: str | None, models: bool, exclude: list[str]) -> list[dict] | None:
    """Products from an earlier identical search, if still fresh and in stock."""
    with _lock:
        row = _db().execute("SELECT urls, created FROM results WHERE key=?", (_result_key(prompt, category, models),)).fetchone()
        if not row or time.time() - row["created"] > RESULT_TTL:
            return None
        col = "cutout_m" if models else "cutout_p"
        ex = {n.lower() for n in exclude}
        out = []
        for url in json.loads(row["urls"]):
            r = _db().execute(f"SELECT * FROM products WHERE url=? AND stock='in_stock' AND {col} IS NOT NULL", (url,)).fetchone()
            if r and r["name"].lower() not in ex:
                out.append(_row_to_item(r, models))
        return out


def _score(r: sqlite3.Row, words: list[str], cat_hint: str | None) -> float:
    if cat_hint and r["category"] != cat_hint:
        return 0.0
    name = r["name"].lower()
    tags = set((r["tags"] or "").split())
    score = 0.0
    for w in words:
        if w in _SYN and _SYN[w] == r["category"]:
            score += 1.0
        elif w in name:
            score += 2.0
        elif w in tags:
            score += 1.0
    return score


def search(prompt: str, category: str | None, models: bool, exclude: list[str], limit: int = 6) -> list[dict]:
    words = [w for w in _WORD.findall(prompt.lower()) if w not in _STOP and len(w) > 1]
    cat_hint = category or next((_SYN[w] for w in words if w in _SYN), None)
    col = "cutout_m" if models else "cutout_p"
    ex = {n.lower() for n in exclude}
    with _lock:
        rows = _db().execute(
            f"SELECT * FROM products WHERE stock='in_stock' AND {col} IS NOT NULL" + (" AND category=?" if cat_hint else ""),
            (cat_hint,) if cat_hint else ()).fetchall()
    scored = [(_score(r, words, cat_hint), r) for r in rows if r["name"].lower() not in ex]
    scored = [(s, r) for s, r in scored if s > 0]
    scored.sort(key=lambda t: (-t[0], -(t[1]["last_checked"] or 0)))
    return [_row_to_item(r, models) for _, r in scored[:limit]]


def random_fit(models: bool) -> dict | None:
    """One in-stock piece per category from the catalog, or None if too thin."""
    col = "cutout_m" if models else "cutout_p"
    with _lock:
        rows = _db().execute(f"SELECT * FROM products WHERE stock='in_stock' AND {col} IS NOT NULL").fetchall()
    if len(rows) < MIN_FOR_RANDOM:
        return None
    by_cat: dict[str, list] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    if not all(c in by_cat for c in ("top", "bottom", "shoes")):
        return None
    cats = ["top", "bottom", "shoes"] + [c for c in ("outerwear", "headwear", "bag", "accessory") if c in by_cat and random.random() < 0.7]
    return {"prompt": "from popular items", "models": models,
            "items": [_row_to_item(random.choice(by_cat[c]), models) for c in cats]}


def known_urls(models: bool | None = None) -> set[str]:
    col = "cutout_m" if models else "cutout_p"
    with _lock:
        rows = _db().execute(f"SELECT url FROM products" + ("" if models is None else f" WHERE {col} IS NOT NULL")).fetchall()
    return {r["url"] for r in rows}


def raw_urls(models: bool = False) -> set[str]:
    """Listings still showing the retailer's own photo (no cutout built yet)."""
    col = "cutout_m" if models else "cutout_p"
    with _lock:
        rows = _db().execute(f"SELECT url FROM products WHERE {col} LIKE 'http%'").fetchall()
    return {r["url"] for r in rows}


def count(models: bool | None = None) -> int:
    with _lock:
        if models is None:
            return _db().execute("SELECT COUNT(*) FROM products").fetchone()[0]
        col = "cutout_m" if models else "cutout_p"
        return _db().execute(f"SELECT COUNT(*) FROM products WHERE {col} IS NOT NULL").fetchone()[0]


def stale(limit: int = 5, max_age: float = 6 * 3600) -> list[str]:
    """Listing URLs whose stock hasn't been checked recently (oldest first)."""
    with _lock:
        rows = _db().execute(
            "SELECT url FROM products WHERE url LIKE 'http%' AND (last_checked IS NULL OR last_checked < ?) ORDER BY last_checked LIMIT ?",
            (time.time() - max_age, limit)).fetchall()
    return [r["url"] for r in rows]


def has_tags(words: list[str]) -> bool:
    with _lock:
        rows = _db().execute("SELECT tags FROM products").fetchall()
    seen = {t for r in rows for t in (r["tags"] or "").split()}
    return all(w in seen for w in words)


# ---------------------------------------------------------------- warm-up
def warm(find) -> None:
    """Background: run the popular searches once (product-only mode)."""
    global _warming
    with _lock:
        if _warming:
            return
        _warming = True

    def run():
        global _warming
        try:
            for term in POPULAR:
                if has_tags([w for w in _WORD.findall(term) if w not in _STOP]):
                    continue
                try:
                    items = find(term, False)
                    print(f"[catalog] warmed '{term}' → {len(items)} items (catalog {count()})", file=sys.stderr)
                except Exception as err:  # noqa: BLE001
                    print(f"[catalog] warm '{term}' failed: {err}", file=sys.stderr)
                    if "quota" in str(err).lower() or "429" in str(err):
                        print("[catalog] warm-up paused — AI quota exhausted; will resume on next restart or search", file=sys.stderr)
                        return
                time.sleep(4.0)  # be gentle with the keyless search endpoints
        finally:
            with _lock:
                _warming = False

    threading.Thread(target=run, daemon=True).start()
