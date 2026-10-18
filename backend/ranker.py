"""Search-bar understanding, part 2: the AI picks from the catalog.

Given the shopper's request and the catalog products that survive the hard
filters (intent.py), the LLM chooses and orders the best matches. It sees
compact lines — number, brand, name, price, category, color — and returns numbers,
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

# Speed/cost knobs: the model reads at most AI_POOL product lines and names at most AI_PICKS of them (each with a short
# reason); the rest of the tray is filled with keyword matches. Fewer tokens in and out = a much faster answer.
AI_POOL = 80
AI_PICKS = 10


def _line(n: int, it: dict) -> str:
    price = f"${it['price']:.0f}" if it.get("price") else "price n/a"
    return f"{n} | {it['brand']} | {it['name']} | {price} | {it['category']} | {it.get('color') or '-'}"


def _trim(it: Intent, pool: list[dict], models: bool, exclude: list[str]) -> list[dict]:
    """Too many candidates for a quick answer: keyword hits first, then the rest dealt out across categories
    (so a vague "fall fit" still gets tops, bottoms, shoes and outerwear to choose from)."""
    if len(pool) <= AI_POOL:
        return pool
    hits = catalog.search(it, models, exclude, limit=AI_POOL)
    seen = {h["url"] for h in hits}
    by_cat: dict[str, list[dict]] = {}
    for p in pool:
        if p["url"] not in seen:
            by_cat.setdefault(p.get("category", ""), []).append(p)
    fill: list[dict] = []
    while len(hits) + len(fill) < AI_POOL and any(by_cat.values()):
        for lst in by_cat.values():
            if lst and len(hits) + len(fill) < AI_POOL:
                fill.append(lst.pop(0))
    return hits + fill


def rank(prompt: str, it: Intent, pool: list[dict], count: int, models: bool, exclude: list[str],
         ai: bool = True) -> tuple[list[dict], str, str]:
    """(picked items best first, source, ai_error) where source is the provider name or 'keywords'; ai_error is a
    short reason when the AI was asked but its answer was not used (the shopper is told), else ''.
    ai=False is the shopper's "AI-powered fits" switch turned off: instant keyword ranking, no model call."""
    if not pool:
        return [], "none", ""
    if not ai or not llm.configured():
        return catalog.search(it, models, exclude, limit=count), "keywords", ""

    pool = _trim(it, pool, models, exclude)
    t0 = time.time()
    try:
        picks = llm.pick_products(prompt, [_line(i + 1, p) for i, p in enumerate(pool)], min(count, AI_PICKS))
    except llm.LLMError as err:
        print(f"[ranker] {llm.provider()} failed ({err}); keyword ranking", file=sys.stderr)
        return catalog.search(it, models, exclude, limit=count), "keywords", str(err)[:140]

    out, seen = [], set()
    for p in picks:
        n = p.get("n", 0)
        if not 1 <= n <= len(pool) or n in seen:
            continue
        item = pool[n - 1]
        if not intent_mod.matches(item, it):        # belt and braces: the LLM cannot un-filter
            continue
        seen.add(n)
        item = {**item, "by": llm.provider()}      # shown as "Suggested by Gemini" with the reason, when there is one
        if p.get("why"):
            item["why"] = str(p["why"]).strip()[:160]
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
        return catalog.search(it, models, exclude, limit=count), "keywords", "it didn't pick anything usable"
    # The model named its best few; keyword matches follow so the tray still fills up (they carry no AI label).
    have = {i["url"] for i in out}
    out += [k for k in catalog.search(it, models, exclude, limit=count) if k["url"] not in have][: max(0, count - len(out))]
    if it.sort == "price_asc":
        out.sort(key=lambda i: i.get("price") or 1e9)
    return out, llm.provider(), ""
