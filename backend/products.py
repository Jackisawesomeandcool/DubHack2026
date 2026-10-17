"""Product shape.

Public fields (spec): name, brand, price, image, stock.
Internal fields: url (listing page the image was pulled from), category,
x / y (board position in percent, set when the user drags a piece).
"""

import re

CATEGORIES = ("outerwear", "top", "bottom", "shoes", "bag", "accessory", "headwear")
STOCK_VALUES = ("in_stock", "out_of_stock")
MAX_ITEMS = 10


def _category(value) -> str:
    value = str(value or "").strip().lower()
    aliases = {
        "jacket": "outerwear", "coat": "outerwear",
        "shirt": "top", "tee": "top", "sweater": "top", "hoodie": "top",
        "pants": "bottom", "jeans": "bottom", "skirt": "bottom", "shorts": "bottom", "trousers": "bottom",
        "shoe": "shoes", "sneakers": "shoes", "boots": "shoes", "footwear": "shoes",
        "bags": "bag", "purse": "bag", "backpack": "bag",
        "accessories": "accessory", "jewelry": "accessory", "sunglasses": "accessory", "belt": "accessory",
        "hat": "headwear", "cap": "headwear", "beanie": "headwear",
    }
    value = aliases.get(value, value)
    return value if value in CATEGORIES else "accessory"


def _stock(value) -> str:
    value = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    return "out_of_stock" if value in ("out_of_stock", "outofstock", "sold_out") else "in_stock"


def _price(value) -> float:
    try:
        price = float(str(value).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return 0.0
    return round(max(0.0, min(price, 100000.0)), 2)


def _url(value) -> str:
    value = str(value or "").strip()
    return value if value.startswith("http") and len(value) < 2048 else ""


def _image_ref(value) -> str:
    """Either an absolute https URL or a served cutout path."""
    value = str(value or "").strip()
    if re.fullmatch(r"/cutouts/[a-f0-9]{16}\.png", value):
        return value
    return _url(value)


def _pct(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return round(max(0.0, min(100.0, v)), 2)


def normalize(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip()[:120]
    brand = str(raw.get("brand") or "").strip()[:80]
    if not name or not brand:
        return None
    item = {
        "name": name,
        "brand": brand,
        "price": _price(raw.get("price")),
        "image": _image_ref(raw.get("image")),
        "url": _url(raw.get("url")),
        "stock": _stock(raw.get("stock")),
        "category": _category(raw.get("category")),
    }
    x, y = _pct(raw.get("x")), _pct(raw.get("y"))
    if x is not None and y is not None:
        item["x"], item["y"] = x, y
    return item


def normalize_list(items) -> list[dict]:
    if not isinstance(items, list):
        return []
    out = []
    for raw in items:
        item = normalize(raw)
        if item:
            out.append(item)
        if len(out) >= MAX_ITEMS:
            break
    return out
