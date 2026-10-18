"""Google Gemini: product search with Google Search grounding, and the photo
check (vision). Standard library only; the key never leaves this process."""

import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request

import config
from products import CATEGORIES, normalize_list

SEARCH_SYSTEM = f"""You find real clothing products. You never chat or explain.
Given a request, use Google Search to find REAL products that are currently listed for sale online
and match the request. Return them as options.

Hard rules:
- Every product must be a real listing you found via search, with its exact product name and brand.
- url: the direct product page URL (the page for that specific item, not a search or category page).
- image: the direct URL of the main product photo (og:image) on the listing page if visible, else "".
- price: current USD price as a number.
- stock: "in_stock" or "out_of_stock". Default "in_stock".
- category: one of {", ".join(CATEGORIES)}.
- Options must be distinct products. Do not include products listed under "already on the board".
Reply with ONLY a JSON object: {{"items": [{{"name","brand","price","url","image","stock","category"}}]}}
No markdown, no commentary."""

if config.ALLOWED_DOMAINS:
    SEARCH_SYSTEM += (
        f"\n\nSTORE RESTRICTION: every product must be a listing on {', '.join(config.ALLOWED_DOMAINS)} "
        f"(search with site:{config.ALLOWED_DOMAINS[0]}) and url must point to a product page on that site."
    )


class GeminiError(Exception):
    pass


_model_override: dict[str, str] = {}  # model -> replacement Google told us to use
_gate = threading.Semaphore(1)        # one Gemini call at a time: free tiers are per-minute limited
_quota_blocked_until = 0.0            # after a hard quota error, stop calling for a while


class QuotaError(GeminiError):
    pass


def _url(model: str) -> str:
    return f"{config.GEMINI_BASE_URL}/models/{model}:generateContent"


def _post(model: str, payload: dict, timeout: int = 120, _retries: int = 2) -> dict:
    global _quota_blocked_until
    if time.time() < _quota_blocked_until:
        raise QuotaError(f"Gemini quota exhausted; paused for {int(_quota_blocked_until - time.time())}s")
    model = _model_override.get(model, model)
    req = urllib.request.Request(_url(model), data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": config.GEMINI_API_KEY},
                                 method="POST")
    try:
        with _gate, urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")
        try:
            message = json.loads(detail)["error"]["message"]
        except Exception:  # noqa: BLE001
            message = detail[:300]
        # Retired model? Google names the replacement — switch to it and retry once.
        m = re.search(r"use models/([\w.\-]+)", message)
        if err.code == 404 and m and m.group(1) != model:
            print(f"[gemini] model {model} unavailable; switching to {m.group(1)}", file=sys.stderr)
            _model_override[model] = m.group(1)
            return _post(model, payload, timeout)
        if err.code == 429:
            delay = re.search(r"retry in ([\d.]+)s|retryDelay\"?:\s*\"?(\d+)", detail, re.I)
            wait = float(next((g for g in (delay.groups() if delay else ()) if g), 0) or 0)
            if "billing" in message.lower() or "plan" in message.lower() or wait > 60 or _retries <= 0:
                _quota_blocked_until = time.time() + max(wait, 300)
                raise QuotaError(f"Gemini API returned 429 (quota): {message[:160]}") from err
            time.sleep(max(wait, 8))
            return _post(model, payload, timeout, _retries - 1)
        raise GeminiError(f"Gemini API returned {err.code}: {message[:200]}") from err
    except (urllib.error.URLError, TimeoutError) as err:
        raise GeminiError(f"Could not reach Gemini API: {err}") from err


def _text(response: dict) -> str:
    try:
        parts = response["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError) as err:
        block = response.get("promptFeedback", {}).get("blockReason")
        raise GeminiError(f"Unexpected Gemini response ({block or 'no candidates'})") from err
    return "".join(p.get("text", "") for p in parts if isinstance(p, dict))


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)  # grounded replies sometimes add prose around the JSON
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    raise GeminiError("Gemini did not return valid JSON")


def search_products(prompt: str, category: str | None, exclude: list[str], count: int) -> list[dict]:
    lines = [f"Request: {prompt}"]
    lines.append(f"Only return products in the category: {category}." if category
                 else "Return a mix of categories that would work together for this request.")
    lines.append(f"Return exactly {count} options.")
    if exclude:
        lines.append("Already on the board (exclude): " + "; ".join(exclude[:12]))
    payload = {
        "systemInstruction": {"parts": [{"text": SEARCH_SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": "\n".join(lines)}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.4},
    }
    global _quota_blocked_until
    try:
        data = _parse_json(_text(_post(config.GEMINI_MODEL, payload)))
    except QuotaError as err:
        if "tools" not in payload:
            raise
        # Grounded search may be what's over quota; plain generation is a separate bucket.
        print(f"[gemini] grounded search over quota ({err}); trying without grounding", file=sys.stderr)
        _quota_blocked_until = 0.0
        payload.pop("tools", None)
        payload["generationConfig"]["responseMimeType"] = "application/json"
        data = _parse_json(_text(_post(config.GEMINI_MODEL, payload)))
    except GeminiError as err:
        msg = str(err).lower()
        if not any(k in msg for k in ("google_search", "tool", "grounding", "not supported", "invalid argument", "400")):
            raise
        # Grounding rejected on this plan/model: plain generation. Results are still
        # verified downstream by fetching each product page and its photo.
        print(f"[gemini] search grounding unavailable ({err}); generating without it", file=sys.stderr)
        payload.pop("tools", None)
        payload["generationConfig"]["responseMimeType"] = "application/json"
        data = _parse_json(_text(_post(config.GEMINI_MODEL, payload)))
    items = normalize_list(data.get("items", []) if isinstance(data, dict) else data)
    if category:
        items = [it for it in items if it["category"] == category] or items
    if not items:
        raise GeminiError("Gemini returned no usable products")
    return items


PICK_SYSTEM = """You are a personal shopper choosing from a store's own catalog. You do not chat; your only output is the JSON below.

You get a shopper's request and a numbered list of the products available (brand, name, price,
category, color — read from the product photo, "-" if unknown). Pick the products that best answer the request, best first.

Rules:
- Use only the numbers in the list. Never invent products.
- Judge by what the names tell you: product line, garment type, material (fleece, down, shell,
  denim, corduroy), fit, season cues (therma, windrunner, puffer = cold; shorts, tank = warm),
  colorway words, sport, and brand style (Stüssy = streetwear, Uniqlo = basics, Nike = athletic).
- Moods and seasons are NOT in the product names, so translate them: "comfortable/cozy/casual" =
  fleece, plush, joggers, sweatpants, hoodies, club, loose or oversized fits, soft knits; "fall/autumn"
  = layers and cold-weather pieces (jackets, fleece, Therma-FIT, windrunner, bombers, vests, hoodies,
  long sleeves, beanies, boots, earth tones); "athletic/sporty/gym" = Dri-FIT, training, running,
  track, performance shorts/tops/shoes; "streetwear" = Stüssy, Jordan, graphic, denim, baggy, cargo.
  Combine them: "fall athletic" = cold-weather performance pieces (Therma-FIT, fleece joggers, track
  jackets, running shoes).
- If the request describes a whole outfit, a "fit", or only a mood/season/style (no single garment
  type), pick a coherent mix across categories (top, bottom, shoes, plus outerwear/headwear/bag where
  they fit) rather than six of one kind.
- Otherwise pick the closest matches; vary models rather than listing near-duplicates.
- The list is already limited to what the shopper may buy, so ALWAYS return picks: choose the closest
  matches even when none is perfect. Return an empty list only if the request is gibberish.
- EVERY pick needs a "why": the shopper reads it under the product, so make it one short sentence (max
  10 words) saying what about THIS product fits THEIR request, in plain friendly words. Good: "Soft fleece that keeps you warm on a cool fall day." / "Baggy dark denim, just
  the relaxed streetwear look you asked for." Bad: "Good match." / "Matches your request." / the list number.
Reply with ONLY a JSON object: {"picks": [{"n": <number>, "why": "<one sentence>"}]}"""


def one_sentence(text, limit: int = 140) -> str:
    """The reason shown under a product: its first sentence only, trimmed."""
    t = " ".join(str(text or "").split())
    m = re.match(r"(.+?[.!?])(\s|$)", t)
    t = m.group(1) if m else t
    return t if len(t) <= limit else t[: limit - 1].rstrip(" ,;:") + "…"


def pick_products(prompt: str, lines: list[str], count: int) -> list[dict]:
    """Rank the catalog candidates for a request. `lines` are "n | brand | name | $price | category".
    Returns [{"n": int, "why": str}] best first. Raises GeminiError."""
    user = (f"Request: {prompt}\nPick up to {count}.\n\nProducts:\n" + "\n".join(lines))
    payload = {
        "systemInstruction": {"parts": [{"text": PICK_SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json", "maxOutputTokens": 4096},
    }
    text = _text(_post(config.GEMINI_MODEL, payload, timeout=45))
    try:
        data = _parse_json(text)
    except GeminiError:
        # Truncated or chatty reply: salvage the numbers that were written ({"n": 12, ...}).
        # keep the reasons of the picks that were written completely: {"n": 12, "why": "..."}
        pairs = re.findall(r'"n"\s*:\s*(\d+)\s*,\s*"why"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
        nums = re.findall(r'"n"\s*:\s*(\d+)', text)
        if not nums:
            raise
        whys = {int(n): w.replace('\\"', '"') for n, w in pairs}
        data = {"picks": [{"n": int(n), "why": whys.get(int(n), "")} for n in nums]}
    picks = data.get("picks", []) if isinstance(data, dict) else data
    out = []
    for p in picks if isinstance(picks, list) else []:
        try:
            out.append({"n": int(p["n"] if isinstance(p, dict) else p), "why": one_sentence(p.get("why", "") if isinstance(p, dict) else "")})
        except (KeyError, TypeError, ValueError):
            continue
    return out


def product_color(jpeg: bytes, allowed: list[str]) -> list[str]:
    """Vision: the garment's color(s) from a product photo, dominant first, limited to `allowed`.
    Raises GeminiError / QuotaError."""
    import base64
    prompt = ("Which colors is the product in this photo? Answer for the garment/item itself: ignore the "
              "white background, skin, hands, small logos, laces, soles and stitching. Choose only from: "
              + ", ".join(allowed) + ". Dominant color first; give a second color only if it covers a large "
              "part of the item (two-tone), a third only if it is truly multicolor. "
              'Reply with ONLY JSON: {"colors": ["..."]}')
    payload = {
        "contents": [{"role": "user", "parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(jpeg).decode("ascii")}}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "maxOutputTokens": 256},
    }
    data = _parse_json(_text(_post(config.GEMINI_VISION_MODEL, payload, timeout=60)))
    raw = data.get("colors", []) if isinstance(data, dict) else data
    out: list[str] = []
    for c in raw if isinstance(raw, list) else []:
        c = str(c).strip().lower().replace("gray", "grey")
        if c in allowed and c not in out:
            out.append(c)
    return out[:3]


def pick_index(question: str, jpeg_blobs: list[bytes]) -> int:
    """Vision: which photo answers the question. Returns an index or -1."""
    import base64
    parts = [{"text": question}]
    for raw in jpeg_blobs:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(raw).decode("ascii")}})
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    data = _parse_json(_text(_post(config.GEMINI_VISION_MODEL, payload, timeout=60)))
    idx = int(data.get("index", -1)) if isinstance(data, dict) else -1
    return idx if 0 <= idx < len(jpeg_blobs) else -1
