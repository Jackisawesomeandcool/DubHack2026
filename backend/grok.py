"""Grok (xAI) clothing curation. The API key never leaves this process."""

import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import config
from products import CATEGORIES, normalize_list

SYSTEM_PROMPT = f"""You curate fashion hauls. You never chat or explain.
Given a style prompt, select 5 to 7 REAL, currently or recently sold clothing products from real brands
that together form one cohesive outfit ("haul").

Rules:
- Every product must be a real product that exists, with its real product name and real brand.
- Price is the typical USD retail price as a number.
- image: a direct https URL to the product's official image (jpg/png/webp) ONLY if you are confident it is
  real. Otherwise use an empty string. Never invent URLs.
- stock: "in_stock" or "out_of_stock". Most products should be "in_stock".
- category: one of {", ".join(CATEGORIES)}. Use each category at most once, except "accessory" (max 2).
  Always include a top, a bottom and shoes.
- color: the product's dominant color as a 6-digit hex string like "#2f4766".
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
                    "image": {"type": "string"},
                    "stock": {"type": "string", "enum": ["in_stock", "out_of_stock"]},
                    "category": {"type": "string", "enum": list(CATEGORIES)},
                    "color": {"type": "string"},
                },
                "required": ["name", "brand", "price", "image", "stock", "category", "color"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


class GrokError(Exception):
    pass


def _post(payload: dict) -> dict:
    req = urllib.request.Request(
        f"{config.XAI_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.XAI_API_KEY}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")[:300]
        raise GrokError(f"xAI API returned {err.code}: {detail}") from err
    except (urllib.error.URLError, TimeoutError) as err:
        raise GrokError(f"Could not reach xAI API: {err}") from err


def _extract_items(response: dict) -> list:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as err:
        raise GrokError("Unexpected xAI response shape") from err
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        content = content[content.find("{"):]
    try:
        data = json.loads(content)
    except json.JSONDecodeError as err:
        raise GrokError("Grok did not return valid JSON") from err
    return data.get("items", []) if isinstance(data, dict) else data


def _image_ok(url: str) -> bool:
    """Keep only image URLs that actually resolve to an image."""
    if not url:
        return False
    req = urllib.request.Request(
        url,
        headers={"Range": "bytes=0-2047", "User-Agent": "Mozilla/5.0 (HaulCurator image check)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            ctype = resp.headers.get("Content-Type", "")
            return resp.status < 400 and ctype.startswith("image/")
    except Exception:
        return False


def curate(prompt: str) -> list[dict]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    base = {"model": config.XAI_MODEL, "messages": messages, "temperature": 0.7}
    try:
        response = _post({
            **base,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "haul", "schema": SCHEMA, "strict": True},
            },
        })
    except GrokError:
        # Some models/accounts reject json_schema; fall back to plain JSON mode.
        response = _post({**base, "response_format": {"type": "json_object"}})

    items = normalize_list(_extract_items(response))
    if not items:
        raise GrokError("Grok returned no usable products")

    with ThreadPoolExecutor(max_workers=8) as pool:
        valid = list(pool.map(lambda it: _image_ok(it["image"]), items))
    for item, ok in zip(items, valid):
        if not ok:
            item["image"] = ""
    return items
