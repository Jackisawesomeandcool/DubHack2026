"""Search-bar understanding, part 2: the AI picks from the catalog.

Given the shopper's request and the catalog products that survive the hard
filters (intent.py), the LLM chooses and orders the best matches. It sees
compact lines — number, brand, name, price, category — and returns numbers,
so it can only pick real products; every pick is re-checked against the hard
filters afterwards. No LLM key (or an LLM error) → keyword ranking instead.

Scales with the catalog: with no constraints the whole catalog is offered up
to MAX_CANDIDATES; beyond that the keyword scorer trims the pool first.
"""

import sys
import time

import catalog
import intent as intent_mod
import llm
from intent import Intent

MAX_CANDIDATES = 600     # ~15 tokens per line; well inside any current model's context


def _line(n: int, it: dict) -> str:
    price = f"${it['price']:.0f}" if it.get("price") else "price n/a"
    return f"{n} | {it['brand']} | {it['name']} | {price} | {it['category']}"


def _trim(it: Intent, pool: list[dict], models: bool, exclude: list[str]) -> list[dict]:
    """Too many candidates: keep the keyword hits first, fill with the rest."""
    if len(pool) <= MAX_CANDIDATES:
        return pool
    hits = catalog.search(it, models, exclude, limit=MAX_CANDIDATES)
    seen = {h["url"] for h in hits}
    return hits + [p for p in pool if p["url"] not in seen][: MAX_CANDIDATES - len(hits)]


def rank(prompt: str, it: Intent, pool: list[dict], count: int, models: bool, exclude: list[str]) -> tuple[list[dict], str]:
    """(picked items best first, source) where source is the provider name or 'keywords'."""
    if not pool:
        return [], "none"
    if not llm.configured():
        return catalog.search(it, models, exclude, limit=count), "keywords"

    pool = _trim(it, pool, models, exclude)
    t0 = time.time()
    try:
        picks = llm.pick_products(prompt, [_line(i + 1, p) for i, p in enumerate(pool)], count)
    except llm.LLMError as err:
        print(f"[ranker] {llm.provider()} failed ({err}); keyword ranking", file=sys.stderr)
        return catalog.search(it, models, exclude, limit=count), "keywords"

    out, seen = [], set()
    for p in picks:
        n = p.get("n", 0)
        if not 1 <= n <= len(pool) or n in seen:
            continue
        item = pool[n - 1]
        if not intent_mod.matches(item, it):        # belt and braces: the LLM cannot un-filter
            continue
        seen.add(n)
        out.append(item)
        if p.get("why"):
            print(f"[ranker]   {item['name']} — {p['why']}", file=sys.stderr)
        if len(out) >= count:
            break
    print(f"[ranker] {llm.provider()} {time.time() - t0:.1f}s · {len(pool)} candidates → {len(out)} picks", file=sys.stderr)
    if not out:
        # The AI named nothing usable (empty list, or numbers outside the list). The catalog does have
        # candidates within the hard filters, so fall back rather than show an empty tray.
        print(f"[ranker] {llm.provider()} returned no usable picks ({len(picks)} raw); keyword ranking", file=sys.stderr)
        return catalog.search(it, models, exclude, limit=count), "keywords"
    if it.sort == "price_asc":
        out.sort(key=lambda i: i.get("price") or 1e9)
    return out, llm.provider()
