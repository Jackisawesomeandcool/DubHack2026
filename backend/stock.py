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

import catalog
import images

CHECK_EVERY = 60          # seconds between background sweeps
PAGE_GAP = 3.0            # seconds between page fetches (politeness)
_queue: queue.Queue[str] = queue.Queue()
_recent: dict[str, float] = {}
_started = False


def availability_from_page(url: str) -> str | None:
    """'in_stock' / 'out_of_stock' from the listing's JSON-LD, or None if unknown."""
    blocks = images.jsonld_blocks(url)
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
    if not found:
        return None
    avail = " ".join(found).lower()
    return "in_stock" if "instock" in avail or "limitedavailability" in avail or "preorder" in avail else "out_of_stock"


def recheck(url: str) -> None:
    """Queue a light re-check (debounced to once per 30 min per listing)."""
    if not url.startswith("http"):
        return
    if time.time() - _recent.get(url, 0) < 1800:
        return
    _recent[url] = time.time()
    _queue.put(url)


def _check(url: str) -> None:
    state = availability_from_page(url)
    if state:
        catalog.set_stock(url, state)
        if state != "in_stock":
            print(f"[stock] now unavailable: {url}", file=sys.stderr)
    else:
        catalog.set_stock(url, "in_stock")  # page unreadable: keep, but mark checked


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
