"""Grok (xAI) clothing curation with live web search.

Grok searches the web for real, currently listed products and returns the
product page URL for each. The image is then pulled from that page by
images.py, so every visual comes directly from the retailer's own site.
The API key never leaves this process.
"""

import json
import sys
import urllib.error
import urllib.request

import config
import images
from products import CATEGORIES, normalize_list

SYSTEM_PROMPT = f"""You curate fashion hauls. You never chat or explain.

Given a style prompt, use web search to find 5 to 7 REAL clothing products that are
currently listed for sale online and together form one cohesive outfit.

Hard rules:
- Every product must be a real listing you found via search. Use the exact product name
  and brand from the listing.
- url: the direct product page URL (the page for that specific item, not a search or
  category page). Prefer the brand's own site, otherwise a major retailer.
- image: the direct URL of the main product photo from that page if you saw one; otherwise "".
- price: current USD price as a number.
- stock: "in_stock" unless the page says sold out / unavailable.
- category: one of {", ".join(CATEGORIES)}. Use each at most once, except "accessory" (max 2).
  Always include a top, a bottom and shoes.
- color: the product's dominant color as a 6-digit hex like "#2f4766".
Return only JSON matching the schema."""

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
                    "color": {"type": "string"},
                },
                "required": ["name", "brand", "price", "url", "image", "stock", "category", "color"],
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


def _responses_with_search(prompt: str) -> list:
    """Responses API + web_search tool + strict JSON schema."""
    payload = {
        "model": config.XAI_MODEL,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "tools": [{"type": "web_search"}],
        "text": {
            "format": {"type": "json_schema", "name": "haul", "schema": SCHEMA, "strict": True}
        },
    }
    response = _post("/responses", payload)
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("type") == "output_text" and part.get("text"):
                return _parse_json(part["text"])
    raise GrokError("No message output in xAI response")


def _chat_completions(prompt: str) -> list:
    """Fallback without live search (model knowledge only)."""
    payload = {
        "model": config.XAI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "haul", "schema": SCHEMA, "strict": True},
        },
    }
    response = _post("/chat/completions", payload)
    try:
        return _parse_json(response["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as err:
        raise GrokError("Unexpected xAI response shape") from err


def curate(prompt: str) -> list[dict]:
    try:
        raw = _responses_with_search(prompt)
    except GrokError as err:
        print(f"[grok] web search path failed ({err}); retrying without search", file=sys.stderr)
        raw = _chat_completions(prompt)

    items = normalize_list(raw)
    if not items:
        raise GrokError("Grok returned no usable products")

    # Pull each product's photo from its own listing page.
    images.resolve_all(items)
    return items
