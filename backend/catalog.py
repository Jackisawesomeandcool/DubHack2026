"""Offline options used ONLY when XAI_API_KEY is not configured, so the UI
can be exercised without network. Entries are real Nike products, but with
no live search there are no verified photos, so the frontend renders cutouts.
"""

import random

from products import normalize_list

_ITEMS = [
    {"name": "Sportswear Tech Fleece Windrunner Hoodie", "brand": "Nike", "price": 145, "category": "outerwear", "color": "#2b2b2b"},
    {"name": "Windrunner Woven Jacket", "brand": "Nike", "price": 110, "category": "outerwear", "color": "#1f3a5a"},
    {"name": "ACG Wolf Tree Pullover", "brand": "Nike", "price": 150, "category": "outerwear", "color": "#5c6b4f"},
    {"name": "Sportswear Club Fleece Crew", "brand": "Nike", "price": 60, "category": "top", "color": "#8c8c8c"},
    {"name": "Dri-FIT Legend Tee", "brand": "Nike", "price": 30, "category": "top", "color": "#efe9df"},
    {"name": "Solo Swoosh Tee", "brand": "Nike", "price": 45, "category": "top", "color": "#1a1a1a"},
    {"name": "Sportswear Tech Fleece Joggers", "brand": "Nike", "price": 120, "category": "bottom", "color": "#3a3a3a"},
    {"name": "Club Cargo Pants", "brand": "Nike", "price": 80, "category": "bottom", "color": "#5e5a48"},
    {"name": "Dri-FIT Challenger Shorts", "brand": "Nike", "price": 45, "category": "bottom", "color": "#222222"},
    {"name": "Dunk Low Retro", "brand": "Nike", "price": 115, "category": "shoes", "color": "#2f4766"},
    {"name": "Air Force 1 '07", "brand": "Nike", "price": 115, "category": "shoes", "color": "#f4f4f4"},
    {"name": "P-6000", "brand": "Nike", "price": 115, "category": "shoes", "color": "#b9b4aa"},
    {"name": "Heritage Crossbody Bag", "brand": "Nike", "price": 30, "category": "bag", "color": "#1a1a1a"},
    {"name": "Brasilia 9.5 Training Backpack", "brand": "Nike", "price": 45, "category": "bag", "color": "#333333"},
    {"name": "Club Unstructured Futura Wash Cap", "brand": "Nike", "price": 28, "category": "headwear", "color": "#d9d1c2"},
    {"name": "Peak Beanie", "brand": "Nike", "price": 25, "category": "headwear", "color": "#1a1a1a"},
    {"name": "Everyday Plus Cushioned Crew Socks", "brand": "Nike", "price": 22, "category": "accessory", "color": "#f1f1f1"},
    {"name": "Elite Cuffed Belt", "brand": "Nike", "price": 25, "category": "accessory", "color": "#222222"},
]


def suggest(prompt: str, category: str | None = None, exclude: list[str] | None = None) -> list[dict]:
    pool = [dict(i, stock="in_stock") for i in _ITEMS if i["name"] not in set(exclude or [])]
    if category:
        pool = [i for i in pool if i["category"] == category]
    random.shuffle(pool)
    if not category:
        seen, mixed = set(), []
        for i in pool:
            if i["category"] not in seen:
                seen.add(i["category"])
                mixed.append(i)
        pool = mixed
    return normalize_list(pool[: 4 if category else 6])
