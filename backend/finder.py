"""Search orchestration — catalog only, streamed as NDJSON events:

    {"items": [...]}       finished products (every catalog product already has its cutout)
    {"reason": "...", "closest": [items]}
                           only when items is empty: why, e.g. "No shoes under $50 — closest is $55", plus the
                           products nearest the budget (the frontend offers them behind a "Show closest" button)
    {"done": true}

The `append` / `image` / `drop` events of the old live-search flow are no
longer emitted; the frontend still understands them, so nothing breaks there.
The `reason` event is new and additive — today's frontend ignores it and shows
its own "no alternatives found" line; the search bar now displays the sentence and the closest items.

    prompt ──intent.parse──▶ hard constraints (price, category, brand, color)
           ──catalog.candidates──▶ every product within them
           ──ranker.rank──▶ the AI picks the best `count` for the request
                            (keyword ranking when no AI key is configured)

`results()` raises NoMatch with the human-readable reason; `stream()` turns
that into the empty-items + reason events (HTTP 200). Results are cached for
an hour per *parsed* intent, so phrasing variants share the cache.
"""

import sys
import time

import catalog
import intent as intent_mod
import llm
import ranker

COUNT = 30   # the tray scrolls, so show everything that fits the request (up to this)


class NoMatch(Exception):
    """Nothing in the catalog satisfies the request; str(err) is the reason to show.
    `closest` holds the nearest-priced products when the budget is what ruled everything out."""

    def __init__(self, reason: str, closest: list[dict] | None = None):
        super().__init__(reason)
        self.closest = closest or []


def _reason(it: intent_mod.Intent, near: list[dict] | None = None) -> str:
    what = "/".join(it.categories) if it.categories else "items"
    if it.brands:
        what = f"{'/'.join(it.brands)} {what}"
    if it.colors:
        what = f"{'/'.join(it.colors)} {what}"
    if it.price_max is not None:
        tail = f" — the closest is ${near[0]['price']:,.0f}" if near else ""
        return f"No {what} under ${it.price_max:,.0f}{tail}"
    if it.price_min is not None:
        tail = f" — the closest is ${near[0]['price']:,.0f}" if near else ""
        return f"No {what} over ${it.price_min:,.0f}{tail}"
    if it.brands or it.colors or it.categories:
        return f"No {what} in the catalog"
    return f"Nothing in the catalog matches \"{it.raw.strip()}\""


class Picked(list):
    """Results plus, when the AI was asked and its answer was not used, why (shown to the shopper)."""
    ai_error = ""


def _dedupe(items: list[dict]) -> list[dict]:
    """One entry per product name (the dataset has several colorways of some products)."""
    seen, out = set(), []
    for i in items:
        k = i["name"].lower()
        if k not in seen:
            seen.add(k)
            out.append(i)
    return out


def results(prompt: str, category: str | None = None, exclude: list[str] | None = None,
            models: bool = False, count: int = COUNT, ai: bool = True) -> list[dict]:
    """Finished products for a request (all from the catalog). Raises NoMatch.
    When nothing matches, a misspelling ("cartigans") is corrected against the catalog's words and tried once more."""
    try:
        return _results(prompt, category, exclude, models, count, ai)
    except NoMatch:
        fixed = catalog.correct(prompt)
        if fixed:
            print(f"[finder] nothing for {prompt!r}; trying {fixed!r}", file=sys.stderr)
            try:
                return _results(fixed, category, exclude, models, count, ai)
            except NoMatch:
                pass
        raise


def _results(prompt: str, category: str | None = None, exclude: list[str] | None = None,
             models: bool = False, count: int = COUNT, ai: bool = True) -> list[dict]:
    exclude = exclude or []
    ai = ai and llm.configured()          # the "AI-powered fits" switch only matters when a provider is set up
    t0 = time.time()
    it = intent_mod.parse(prompt, category)

    cached = catalog.cached_results(it, models, exclude, ai)
    if cached:
        print(f"[finder] {it.describe()} · cache hit {1000 * (time.time() - t0):.0f}ms · {len(cached)} items", file=sys.stderr)
        return cached[:count]

    pool = _dedupe(catalog.candidates(it, models, exclude))
    if not pool:
        near = catalog.closest(it, 3, models, exclude) if (it.price_max is not None or it.price_min is not None) else []
        reason = _reason(it, near)
        print(f"[finder] {it.describe()} · 0 candidates · {reason}", file=sys.stderr)
        raise NoMatch(reason, near)

    picked, source, ai_error = ranker.rank(prompt, it, pool, count, models, exclude, ai)
    picked = Picked(_dedupe(picked))
    picked.ai_error = ai_error
    print(f"[finder] {it.describe()} · {len(pool)} candidates → {len(picked)} via {source} · {1000 * (time.time() - t0):.0f}ms",
          file=sys.stderr)
    if not picked:
        raise NoMatch(f"Nothing in the catalog matches \"{prompt.strip()}\"")
    # A keyword answer that stood in for a failed/empty AI call is cached as a keyword answer, never as the AI one:
    # otherwise one hiccup (quota, timeout) would keep serving unlabelled results after Gemini is back.
    catalog.cache_results(it, models, picked, ai and source != "keywords")
    return picked


def stream(prompt: str, category: str | None = None, exclude: list[str] | None = None,
           models: bool = False, count: int = COUNT, local_first: bool = True, ai: bool = True):
    """NDJSON event generator for /api/suggest. `local_first` is accepted for
    compatibility and ignored: everything is local now."""
    if ai and llm.configured() and not catalog.cached_results(intent_mod.parse(prompt, category), models, exclude or [], True):
        # Not asked before: show the instant keyword matches now, then swap in Gemini's picks when they arrive.
        try:
            yield {"items": results(prompt, category, exclude, models, count, ai=False)}
        except NoMatch as err:
            yield {"items": []}
            yield {"reason": str(err), "closest": err.closest}
            yield {"done": True}
            return
        yield {"ai": "thinking"}
        try:
            final = results(prompt, category, exclude, models, count, ai=True)
        except NoMatch:
            final = Picked()
        if getattr(final, "ai_error", ""):
            yield {"ai_error": final.ai_error}
        elif final:
            yield {"replace": final}
        yield {"done": True}
        return
    try:
        items = results(prompt, category, exclude, models, count, ai)
    except NoMatch as err:
        yield {"items": []}
        yield {"reason": str(err), "closest": err.closest}
        yield {"done": True}
        return
    yield {"items": items}
    if getattr(items, "ai_error", ""):
        yield {"ai_error": items.ai_error}
    yield {"done": True}


def find(prompt: str, models: bool = False, category: str | None = None, exclude: list[str] | None = None,
         count: int = COUNT, local_first: bool = True) -> list[dict]:
    """Non-streaming variant (fits, warm-up). Empty list instead of NoMatch."""
    try:
        return results(prompt, category, exclude, models, count)
    except NoMatch:
        return []
