"""Stock freshness.

A background thread re-checks the oldest-checked listings (rate-limited, one
page per few seconds) by reading the page's JSON-LD offer availability. A
light re-check is also queued whenever a product is shown or placed on the
board. Products that turn out to be unavailable stop being served.
"""

import json
import queue
import sys
import threading
import time
import urllib.error

import catalog
import images

CHECK_EVERY = 60          # seconds between background sweeps
PAGE_GAP = 3.0            # seconds between page fetches (politeness)
_queue: queue.Queue[str] = queue.Queue()
_recent: dict[str, float] = {}
_started = False


def _has_priced_offer(blocks: list[str]) -> bool:
    """True if the JSON-LD declares a Product with an offer that carries a price."""
    def walk(node) -> bool:
        if isinstance(node, dict):
            if "price" in node and node.get("price") not in (None, ""):
                return True
            return any(walk(v) for v in node.values())
        if isinstance(node, list):
            return any(walk(v) for v in node)
        return False

    for b in blocks:
        try:
            if walk(json.loads(b)):
                return True
        except (json.JSONDecodeError, TypeError):
            continue
    return False


def availability_from_page(url: str) -> str | None:
    """'in_stock' / 'out_of_stock' for a listing, or None if it can't be told.

    - 404/410, or a redirect off a /t/ product page (Nike sends retired
      products to a landing page): out_of_stock.
    - JSON-LD `availability` when the page has it.
    - Nike pages carry no `availability`; a Product with a priced offer
      means the listing is live: in_stock.
    - Network errors / blocked pages: None (unknown, never flips the state).
    """
    try:
        html, final_url = images._fetch_html(url)
    except urllib.error.HTTPError as err:
        if err.code in (404, 410):
            return "out_of_stock"
        print(f"[stock] HTTP {err.code} for {url}; leaving as is", file=sys.stderr)
        return None
    except Exception as err:  # noqa: BLE001 — transient failure: don't change state
        print(f"[stock] fetch failed {url}: {err}", file=sys.stderr)
        return None

    if "/t/" in url and "/t/" not in final_url:
        return "out_of_stock"

    parser = images._MetaParser()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001
        pass
    blocks = parser.jsonld

    found: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            a = node.get("availability")
            if isinstance(a, str):
                found.append(a)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for b in blocks:
        try:
            walk(json.loads(b))
        except (json.JSONDecodeError, TypeError):
            continue
    if found:
        avail = " ".join(found).lower()
        return "in_stock" if "instock" in avail or "limitedavailability" in avail or "preorder" in avail else "out_of_stock"
    if _has_priced_offer(blocks):
        return "in_stock"
    return None


def recheck(url: str) -> None:
    """Queue a light re-check (debounced to once per 30 min per listing)."""
    if not url.startswith("http"):
        return
    if time.time() - _recent.get(url, 0) < 1800:
        return
    _recent[url] = time.time()
    _queue.put(url)


def _touch(url: str) -> None:
    with catalog._lock:
        catalog._db().execute("UPDATE products SET last_checked=? WHERE url=?", (time.time(), url))
        catalog._db().commit()


def _check(url: str) -> None:
    state = availability_from_page(url)
    if state:
        catalog.set_stock(url, state)
        if state != "in_stock":
            print(f"[stock] now unavailable: {url}", file=sys.stderr)
    else:
        _touch(url)  # unknown: keep the current state, but mark it checked so the sweep moves on


def _loop() -> None:
    last_sweep = 0.0
    while True:
        try:
            url = _queue.get(timeout=5)
        except queue.Empty:
            url = None
        if url:
            _check(url)
            time.sleep(PAGE_GAP)
            continue
        if time.time() - last_sweep >= CHECK_EVERY:
            last_sweep = time.time()
            for u in catalog.stale(limit=5):
                _check(u)
                time.sleep(PAGE_GAP)


def start() -> None:
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, daemon=True).start()
