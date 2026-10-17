"""Grok (xAI) product finder with live web search.

Given a short request (and optionally one category), Grok searches the
configured store(s) for real, currently listed products and returns a few
options. Each option's photo is then pulled from its own product page by
images.py. The API key never leaves this process.
"""

import json
import sys
import urllib.error
import urllib.request

import config
from products import CATEGORIES, normalize_list

SYSTEM_PROMPT = f"""You find real clothing products. You never chat or explain.

Given a request, use web search to find REAL products that are currently listed for sale
online and match the request. Return them as options. Be fast: one or two searches is
enough; do not deliberate.

Hard rules:
- Every product must be a real listing you found via search. Use the exact product name
  and brand from the listing.
- url: the direct product page URL (the page for that specific item, not a search or
  category page).
- image: the direct URL of the main product photo (the <meta property="og:image"> or main
  product image URL on the listing page). Always try to include it; use "" only if none was visible.
- price: current USD price as a number.
- stock: "in_stock" unless the page says sold out / unavailable.
- category: one of {", ".join(CATEGORIES)}.
- Options must be distinct products. Do not include products listed under "already on the board".
Return only JSON matching the schema."""

if config.ALLOWED_DOMAINS:
    SYSTEM_PROMPT += (
        f"\n\nSTORE RESTRICTION: every product must be a listing on {', '.join(config.ALLOWED_DOMAINS)} "
        "and url must point to a product page on that site. Interpret the request using only "
        "what that store sells (its own apparel, footwear, bags, hats, socks and accessories)."
    )

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "brand": {"type": "string"},
                    "price": {"type": "number"},
                    "url": {"type": "string"},
                    "image": {"type": "string"},
                    "stock": {"type": "string", "enum": ["in_stock", "out_of_stock"]},
                    "category": {"type": "string", "enum": list(CATEGORIES)},
                },
                "required": ["name", "brand", "price", "url", "image", "stock", "category"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


class GrokError(Exception):
    pass


def _post(path: str, payload: dict, timeout: int = 180) -> dict:
    req = urllib.request.Request(
        f"{config.XAI_BASE_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.XAI_API_KEY}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")[:300]
        raise GrokError(f"xAI API returned {err.code}: {detail}") from err
    except (urllib.error.URLError, TimeoutError) as err:
        raise GrokError(f"Could not reach xAI API: {err}") from err


def _parse_json(text: str) -> list:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as err:
        raise GrokError("Grok did not return valid JSON") from err
    return data.get("items", []) if isinstance(data, dict) else data


def _user_message(prompt: str, category: str | None, exclude: list[str], count: int) -> str:
    lines = [f"Request: {prompt}"]
    if category:
        lines.append(f"Only return products in the category: {category}.")
    else:
        lines.append("Return a mix of categories that would work together for this request.")
    lines.append(f"Return exactly {count} options.")
    if exclude:
        lines.append("Already on the board (exclude): " + "; ".join(exclude[:12]))
    return "\n".join(lines)


def _responses_with_search(user: str) -> list:
    payload = {
        "model": config.XAI_MODEL,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        "tools": [
            {"type": "web_search", "filters": {"allowed_domains": config.ALLOWED_DOMAINS}}
            if config.ALLOWED_DOMAINS
            else {"type": "web_search"}
        ],
        "text": {
            "format": {"type": "json_schema", "name": "options", "schema": SCHEMA, "strict": True}
        },
    }
    if config.XAI_REASONING:
        payload["reasoning"] = {"effort": config.XAI_REASONING}
    try:
        response = _post("/responses", payload)
    except GrokError as err:
        if "reasoning" not in payload or "400" not in str(err):
            raise
        payload.pop("reasoning")
        response = _post("/responses", payload)

    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("type") == "output_text" and part.get("text"):
                return _parse_json(part["text"])
    raise GrokError("No message output in xAI response")


def _chat_completions(user: str) -> list:
    """Fallback without live search (model knowledge only)."""
    payload = {
        "model": config.XAI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "options", "schema": SCHEMA, "strict": True},
        },
    }
    response = _post("/chat/completions", payload)
    try:
        return _parse_json(response["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as err:
        raise GrokError("Unexpected xAI response shape") from err


def search_products(prompt: str, category: str | None = None, exclude: list[str] | None = None, count: int = 6) -> list[dict]:
    """Products from Grok's live web search (no images resolved yet)."""
    user = _user_message(prompt, category, exclude or [], count)
    try:
        raw = _responses_with_search(user)
    except GrokError as err:
        print(f"[grok] web search path failed ({err}); retrying without search", file=sys.stderr)
        raw = _chat_completions(user)
    items = normalize_list(raw)
    if category:
        items = [it for it in items if it["category"] == category] or items
    if not items:
        raise GrokError("Grok returned no usable products")
    return items


def pick_index(question: str, jpeg_blobs: list[bytes]) -> int:
    """Vision via xAI chat completions (images as base64)."""
    import base64
    content = [{"type": "text", "text": question}]
    for raw in jpeg_blobs:
        content.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii"), "detail": "low"}})
    payload = {"model": config.XAI_VISION_MODEL, "messages": [{"role": "user", "content": content}],
               "response_format": {"type": "json_object"}, "temperature": 0}
    data = _post("/chat/completions", payload, timeout=60)
    idx = int(json.loads(data["choices"][0]["message"]["content"]).get("index", -1))
    return idx if 0 <= idx < len(jpeg_blobs) else -1
