"""Google Gemini: product search with Google Search grounding, and the photo
check (vision). Standard library only; the key never leaves this process."""

import json
import re
import sys
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


def _url(model: str) -> str:
    return f"{config.GEMINI_BASE_URL}/models/{model}:generateContent?key={config.GEMINI_API_KEY}"


def _post(model: str, payload: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(_url(model), data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")[:300]
        raise GeminiError(f"Gemini API returned {err.code}: {detail}") from err
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
    try:
        data = _parse_json(_text(_post(config.GEMINI_MODEL, payload)))
    except GeminiError as err:
        if "google_search" not in str(err) and "tool" not in str(err).lower():
            raise
        print(f"[gemini] search grounding unavailable ({err}); retrying without it", file=sys.stderr)
        payload.pop("tools")
        payload["generationConfig"]["responseMimeType"] = "application/json"
        data = _parse_json(_text(_post(config.GEMINI_MODEL, payload)))
    items = normalize_list(data.get("items", []) if isinstance(data, dict) else data)
    if category:
        items = [it for it in items if it["category"] == category] or items
    if not items:
        raise GeminiError("Gemini returned no usable products")
    return items


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
