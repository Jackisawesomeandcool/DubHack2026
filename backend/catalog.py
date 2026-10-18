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
import intent as intent_mod
from intent import Intent

DB_PATH = config.DATA_DIR / "catalog.sqlite"
RESULT_TTL = 60 * 60          # cached search results stay valid this long
MIN_FOR_RANDOM = 12
RANDOM_FIT_MIN, RANDOM_FIT_MAX = 6, 7   # pieces in a random fit — few enough to sit uncluttered on the board

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

_WORD = intent_mod._WORD
_SYN = intent_mod.SYN
_STOP = intent_mod.STOP


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
                source TEXT, last_checked REAL, added_at REAL,
                color TEXT, color_src TEXT      -- canonical colors, dominant first ("green", "black white"); see colors.py
            );
            CREATE INDEX IF NOT EXISTS idx_products_cat ON products(category);
            CREATE TABLE IF NOT EXISTS results (
                key TEXT PRIMARY KEY, urls TEXT NOT NULL, created REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS blocked (      -- hand-removed products: never re-added by scrapers/seed
                url TEXT PRIMARY KEY, removed_at REAL NOT NULL, snapshot TEXT
            );
            CREATE TABLE IF NOT EXISTS reviewed (     -- products a human has looked at and approved
                url TEXT PRIMARY KEY, at REAL NOT NULL
            );
        """)
        have = {r[1] for r in _conn.execute("PRAGMA table_info(products)")}
        for col in ("color", "color_src"):             # databases created before the color columns
            if col not in have:
                _conn.execute(f"ALTER TABLE products ADD COLUMN {col} TEXT")
        _conn.commit()
    return _conn


def _row_to_item(r: sqlite3.Row, models: bool) -> dict:
    return {
        "name": r["name"], "brand": r["brand"], "price": r["price"], "url": r["url"],
        "image": (r["cutout_m"] if models else r["cutout_p"]) or r["cutout_p"] or r["cutout_m"] or "",
        "stock": r["stock"], "category": r["category"], "color": r["color"] or "",
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
            if db.execute("SELECT 1 FROM blocked WHERE url=?", (url,)).fetchone():
                continue                      # removed by hand in view_catalog.py
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


def is_blocked(url: str) -> bool:
    with _lock:
        return _db().execute("SELECT 1 FROM blocked WHERE url=?", (url,)).fetchone() is not None


def set_color(url: str, colors: list[str], src: str) -> None:
    """Record a product's colors (canonical names, dominant first) and where they came from."""
    with _lock:
        _db().execute("UPDATE products SET color=?, color_src=? WHERE url=?", (" ".join(colors), src, url))
        _db().commit()


def clear_results() -> None:
    """Forget cached searches (call after bulk changes that alter what a search would return)."""
    with _lock:
        _db().execute("DELETE FROM results")
        _db().commit()


def set_stock(url: str, stock: str) -> None:
    with _lock:
        _db().execute("UPDATE products SET stock=?, last_checked=? WHERE url=?", (stock, time.time(), url))
        _db().commit()


def cache_results(intent_: Intent, models: bool, items: list[dict]) -> None:
    key = _result_key(intent_, models)
    with _lock:
        _db().execute("INSERT OR REPLACE INTO results (key, urls, created) VALUES (?,?,?)",
                      (key, json.dumps([_url_key(i) for i in items if i.get("image")]), time.time()))
        _db().commit()


# ---------------------------------------------------------------- read
KEY_VERSION = "v3"   # bump when the key format changes; old rows simply never match again


def _result_key(intent_: Intent, models: bool) -> str:
    """Keyed by the *parsed* intent, so 'shoes under $50' and 'shoes below 50 dollars' share a cache."""
    return f"{KEY_VERSION}|{intent_.key()}|{'m' if models else 'p'}"


def _filter_item(r: sqlite3.Row, models: bool) -> dict:
    """Item plus the fields the hard filter looks at."""
    return {**_row_to_item(r, models), "tags": r["tags"] or ""}


def cached_results(intent_: Intent, models: bool, exclude: list[str]) -> list[dict] | None:
    """Products from an earlier identical search, if still fresh, in stock and still within the filters."""
    with _lock:
        row = _db().execute("SELECT urls, created FROM results WHERE key=?", (_result_key(intent_, models),)).fetchone()
        if not row or time.time() - row["created"] > RESULT_TTL:
            return None
        ex = {n.lower() for n in exclude}
        out = []
        for url in json.loads(row["urls"]):
            r = _db().execute("SELECT * FROM products WHERE url=? AND stock='in_stock'", (url,)).fetchone()
            if r and r["name"].lower() not in ex and intent_mod.matches(_filter_item(r, models), intent_):
                item = _row_to_item(r, models)
                if item["image"]:
                    out.append(item)
        return out


def _rows(intent_: Intent, ignore_price: bool = False) -> list[sqlite3.Row]:
    """In-stock rows with a cutout that satisfy the intent's hard constraints (price optional)."""
    sql = "SELECT * FROM products WHERE stock='in_stock' AND (cutout_p IS NOT NULL OR cutout_m IS NOT NULL)"
    args: list = []
    if intent_.categories:
        sql += f" AND category IN ({','.join('?' * len(intent_.categories))})"
        args += intent_.categories
    if not ignore_price and (intent_.price_max is not None or intent_.price_min is not None):
        sql += " AND price > 0"                      # unknown price never satisfies a budget
        if intent_.price_max is not None:
            sql += " AND price <= ?"
            args.append(intent_.price_max)
        if intent_.price_min is not None:
            sql += " AND price >= ?"
            args.append(intent_.price_min)
    with _lock:
        rows = _db().execute(sql, args).fetchall()
    probe = intent_ if not ignore_price else Intent(raw=intent_.raw, categories=intent_.categories,
                                                     colors=intent_.colors, brands=intent_.brands)
    return [r for r in rows if intent_mod.matches(_filter_item(r, False), probe)]


def candidates(intent_: Intent, models: bool, exclude: list[str]) -> list[dict]:
    """Every catalog product that passes the hard filters — the pool the AI ranker chooses from."""
    ex = {n.lower() for n in exclude}
    return [_row_to_item(r, models) for r in _rows(intent_) if r["name"].lower() not in ex]


def closest(intent_: Intent, n: int = 3, models: bool = False, exclude: list[str] | None = None) -> list[dict]:
    """When nothing fits the budget: the in-stock products that match everything else, nearest in price
    to the budget first (just above a maximum, just below a minimum). One per product name."""
    lo, hi = intent_.price_min, intent_.price_max
    ex = {x.lower() for x in (exclude or [])}
    scored = []
    for r in _rows(intent_, ignore_price=True):
        price = r["price"] or 0
        if price <= 0 or r["name"].lower() in ex:
            continue
        gap = (price - hi) if hi is not None and price > hi else (lo - price) if lo is not None and price < lo else None
        if gap is not None:
            scored.append((gap, price, r))
    words = intent_.term_words()
    on_topic = [t for t in scored if _score(t[2], words) > 0] if words else scored
    scored = on_topic or scored          # prefer the garment the user named ("hoodie"); else anything in the category
    scored.sort(key=lambda t: (t[0], t[1]))
    out, seen = [], set()
    for _, _, r in scored:
        if r["name"].lower() in seen:
            continue
        seen.add(r["name"].lower())
        out.append(_row_to_item(r, models))
        if len(out) >= n:
            break
    return out


def floor_price(intent_: Intent) -> float | None:
    """Cheapest in-stock price among items matching everything except the price — for 'cheapest is $X'."""
    prices = [r["price"] for r in _rows(intent_, ignore_price=True) if (r["price"] or 0) > 0]
    return min(prices) if prices else None


# Category words satisfied by the category alone; other synonyms ("hoodie", "joggers")
# name a specific garment and must appear on the item.
_GENERIC = {"shoes", "shoe", "sneakers", "sneaker", "kicks", "footwear", "top", "tops", "bottom", "bottoms", "pants",
            "outerwear", "jacket", "jackets", "coat", "coats", "hat", "hats", "headwear", "bag", "bags", "accessory", "accessories"}


def _stem(w: str) -> str:
    return w[:-1] if len(w) > 3 and w.endswith("s") else w


def _score_term(r: sqlite3.Row, words: list[str], strict: bool = True) -> float:
    name = {_stem(w) for w in _WORD.findall(r["name"].lower())}   # whole words: "low" must not match "flower"
    tags = {_stem(w) for w in (r["tags"] or "").split()}
    specific = [w for w in words if w not in _GENERIC and w not in intent_mod.COLOR_WORD and not w.isdigit()
                and w not in intent_mod.BRANDS]
    if strict and specific and not all(_stem(w) in name or _stem(w) in tags for w in specific):
        return 0.0            # "dunk low": every product word the user typed must be on the item
    score = 0.0
    for w in words:
        s = _stem(w)
        if s in name:
            score += 2.0
        elif s in tags:
            score += 1.0
        elif w in _SYN and _SYN[w] == r["category"]:
            score += 1.0
    return score


def _score(r: sqlite3.Row, term_words: list[list[str]], strict: bool = True) -> float:
    return max((_score_term(r, ws, strict) for ws in term_words), default=0.0)


def _vibe_scored(pool: list[sqlite3.Row], words: list[str]) -> list[tuple[float, sqlite3.Row]]:
    """Score rows against mood words via intent.VIBES. Each query word that matches contributes; items that
    satisfy more of the words ("fall" AND "athletic") rank higher. Words that are neither a mood nor on the
    item contribute nothing, and a query with no mood word and no literal hit scores nothing at all."""
    out = []
    for r in pool:
        have = {_stem(w) for w in _WORD.findall(r["name"].lower())} | {_stem(w) for w in (r["tags"] or "").split()}
        brand = intent_mod._norm(r["brand"] or "")
        score, mood = 0.0, False
        for w in words:
            exp = intent_mod.VIBES.get(w)
            hits = len(have & exp) if exp else 0
            if exp and (hits or brand in intent_mod.VIBE_BRANDS.get(w, ())):
                score += 3 + 0.5 * min(hits, 3)
                mood = True
            elif _stem(w) in have:
                score += 2          # a literal word only boosts; it never makes a match by itself
        if mood:
            out.append((score, r))
    return out


def _diversify(scored: list[tuple[float, sqlite3.Row]], limit: int) -> list[tuple[float, sqlite3.Row]]:
    """Best-first but no more than two of one category until the others are used, one per product name."""
    scored = sorted(scored, key=lambda t: (-t[0], -(t[1]["last_checked"] or 0)))
    seen, per, first, rest = set(), {}, [], []
    for t in scored:
        name = t[1]["name"].lower()
        if name in seen:
            continue
        seen.add(name)
        cat = t[1]["category"]
        if per.get(cat, 0) < 2:
            per[cat] = per.get(cat, 0) + 1
            first.append(t)
        else:
            rest.append(t)
    return (first + rest)[:limit]


def search(intent_: Intent, models: bool, exclude: list[str], limit: int = 6) -> list[dict]:
    """Keyword-ranked catalog hits within the hard filters. Used when no AI ranker is available
    (and by the ranker as a tie-break)."""
    ex = {n.lower() for n in exclude}
    term_words = intent_.term_words()
    pool = [r for r in _rows(intent_) if r["name"].lower() not in ex]
    scored = [(s, r) for r in pool for s in [_score(r, term_words)] if s > 0]
    words = intent_.words()
    # Words that are a filter and nothing more: brand, color, number, filler, or a bare category
    # name ("shoes", "tops"). A garment word like "tee" or "hoodie" stays a real search term.
    def _bare_category(w):
        return w in _SYN and _SYN[w] in (w, w.rstrip("s"), w + "s")
    filterish = bool(pool) and bool(words) and all(
        w in intent_mod.VIBES or w in _GENERIC or _bare_category(w) or w in intent_mod.COLOR_WORD
        or w in intent_mod._BRAND_WORDS or w.isdigit() for w in words)
    if filterish and not any(w in intent_mod.VIBES for w in words):
        # "stussy", "nike shoes under 100": every word is already a hard filter, so the whole
        # filtered pool is the answer. Literal name hits still float to the top.
        hit = {id(r): s for s, r in scored}
        scored = [(hit.get(id(r), 0.1), r) for r in pool]
    if any(w in intent_mod.VIBES for w in words):
        # A mood word ("gym", "fall", "comfy") reaches past the literal hits: "gym" should bring
        # training gear, not only the one product with "Gym" in its name.
        seen = {id(r) for _, r in scored}
        scored += [(s, r) for s, r in _vibe_scored(pool, words) if id(r) not in seen]
    if not scored and sum(len(ws) for ws in term_words) >= 3:
        # A descriptive request ("skater fit with wide-leg pants and skate shoes"): no item carries
        # every word, so rank by how many it does carry. Hard filters still apply.
        scored = [(s, r) for r in pool for s in [_score(r, term_words, strict=False)] if s > 0]
    if not scored:
        # A mood or season ("comfortable", "fall athletic"): no product name says so, so match the words
        # that suggest it (fleece, therma, dri-fit…) and mix categories like an outfit.
        scored = _vibe_scored(pool, intent_.words())
        if not scored and pool and (intent_.categories or intent_.has_filters()) and all(
                w in intent_mod.VIBES or w in _GENERIC or w in _SYN or w in intent_mod.COLOR_WORD
                or w in intent_mod._BRAND_WORDS or w.isdigit() for w in intent_.words()):
            # Every word typed is already a hard filter or a mood: "uniqlo", "nike shoes under 100",
            # "comfortable shoes under $100". Nothing more to rank by; the pool IS the answer, so
            # offer a mix of what satisfies the filters rather than nothing.
            scored = [(0.1, r) for r in pool]
        if scored:
            return [_row_to_item(r, models) for _, r in _diversify(scored, limit)]
    if intent_.sort == "price_asc":
        scored.sort(key=lambda t: (t[1]["price"] or 1e9, -t[0]))
    else:
        scored.sort(key=lambda t: (-t[0], -(t[1]["last_checked"] or 0)))
    return [_row_to_item(r, models) for _, r in scored[:limit]]


def random_fit(models: bool) -> dict | None:
    """One in-stock piece per category from the catalog, or None if too thin."""
    with _lock:   # on-model mode falls back to product cutouts (see _row_to_item)
        rows = _db().execute("SELECT * FROM products WHERE stock='in_stock' AND (cutout_p IS NOT NULL OR cutout_m IS NOT NULL)").fetchall()
    if len(rows) < MIN_FOR_RANDOM:
        return None
    by_cat: dict[str, list] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    if not all(c in by_cat for c in ("top", "bottom", "shoes")):
        return None
    # A random fit has 6–7 pieces: always a top, bottom and shoes, then the rest
    # drawn from every category (extras can repeat a category — two tops, a
    # second pair of shoes), never the same product twice.
    n = random.randint(RANDOM_FIT_MIN, RANDOM_FIT_MAX)
    picked: list = []
    seen: set[str] = set()

    def grab(cat: str) -> None:
        options = [r for r in by_cat.get(cat, []) if r["url"] not in seen]
        if options:
            r = random.choice(options)
            seen.add(r["url"])
            picked.append(r)

    for c in ("top", "bottom", "shoes"):
        grab(c)
    extras = [c for c in ("outerwear", "headwear", "bag", "accessory", "top", "bottom", "shoes") if c in by_cat]
    weights = {"outerwear": 3, "headwear": 2, "bag": 2, "accessory": 2, "top": 1.5, "bottom": 1, "shoes": 1}
    tries = 0
    while len(picked) < n and tries < 40:
        tries += 1
        grab(random.choices(extras, weights=[weights[c] for c in extras])[0])
    return {"prompt": "from popular items", "models": models,
            "items": [_row_to_item(r, models) for r in picked]}


def random_items(n: int = 24, models: bool = False) -> list[dict]:
    """A shuffled handful of in-stock pieces across categories (the Browse reel)."""
    with _lock:
        rows = _db().execute(
            "SELECT * FROM products WHERE stock='in_stock' AND (cutout_p IS NOT NULL OR cutout_m IS NOT NULL) "
            "ORDER BY RANDOM() LIMIT ?", (max(1, min(60, n)),)).fetchall()
    return [_row_to_item(r, models) for r in rows]


def known_urls(models: bool | None = None) -> set[str]:
    col = "cutout_m" if models else "cutout_p"
    with _lock:
        rows = _db().execute(f"SELECT url FROM products" + ("" if models is None else f" WHERE {col} IS NOT NULL")).fetchall()
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
