"""Demo curation used when XAI_API_KEY is not configured (local testing).

All entries are real products from real brands with typical retail prices.
Images are left empty so the frontend renders a clean garment cutout instead
of hotlinking retailer assets.
"""

import random
import re

from products import normalize_list

_HAULS = {
    "y2k_downtown": {
        "keys": ["2000", "y2k", "downtown", "baggy", "boots", "grunge", "skate", "indie"],
        "items": [
            {"name": "Carpenter Jean", "brand": "Carhartt WIP", "price": 128, "stock": "in_stock", "category": "bottom", "color": "#5c6b80"},
            {"name": "Detroit Jacket", "brand": "Carhartt WIP", "price": 198, "stock": "in_stock", "category": "outerwear", "color": "#3b3a37"},
            {"name": "Essentials Reverse Weave Tee", "brand": "Champion", "price": 30, "stock": "in_stock", "category": "top", "color": "#e8e4dc"},
            {"name": "1460 Smooth Leather Boot", "brand": "Dr. Martens", "price": 170, "stock": "in_stock", "category": "shoes", "color": "#1c1b1a"},
            {"name": "Classic Supreme Backpack", "brand": "Herschel", "price": 70, "stock": "out_of_stock", "category": "bag", "color": "#6a4b32"},
            {"name": "Lumberjack Trucker Hat", "brand": "Stüssy", "price": 48, "stock": "in_stock", "category": "headwear", "color": "#2a3a52"},
        ],
    },
    "quiet_luxury": {
        "keys": ["luxury", "minimal", "quiet", "neutral", "beige", "clean", "office", "tailored", "old money"],
        "items": [
            {"name": "Wool Cashmere Overcoat", "brand": "COS", "price": 350, "stock": "in_stock", "category": "outerwear", "color": "#b8a68c"},
            {"name": "The Oversized Cashmere Crew", "brand": "Everlane", "price": 150, "stock": "in_stock", "category": "top", "color": "#efe9df"},
            {"name": "Wide-Leg Wool Trousers", "brand": "Arket", "price": 149, "stock": "in_stock", "category": "bottom", "color": "#4a4745"},
            {"name": "Modern Loafer", "brand": "Everlane", "price": 198, "stock": "in_stock", "category": "shoes", "color": "#2b2622"},
            {"name": "Le Pliage Original Tote", "brand": "Longchamp", "price": 145, "stock": "in_stock", "category": "bag", "color": "#7a6a55"},
            {"name": "Metal Frame Sunglasses", "brand": "Ray-Ban", "price": 171, "stock": "out_of_stock", "category": "accessory", "color": "#8c7a5a"},
        ],
    },
    "gorpcore": {
        "keys": ["gorp", "outdoor", "hiking", "trail", "techwear", "fleece", "rain", "pnw", "camp"],
        "items": [
            {"name": "Nuptse Jacket", "brand": "The North Face", "price": 320, "stock": "in_stock", "category": "outerwear", "color": "#1f2a3a"},
            {"name": "Better Sweater Fleece", "brand": "Patagonia", "price": 159, "stock": "in_stock", "category": "top", "color": "#6b7f6a"},
            {"name": "Convertible Hiking Pants", "brand": "Arc'teryx", "price": 190, "stock": "in_stock", "category": "bottom", "color": "#3f4a3f"},
            {"name": "Moab 3 Hiking Shoe", "brand": "Merrell", "price": 120, "stock": "in_stock", "category": "shoes", "color": "#5a4a3a"},
            {"name": "Hip Pack 1L", "brand": "Cotopaxi", "price": 40, "stock": "in_stock", "category": "bag", "color": "#d9623b"},
            {"name": "Trail Cap", "brand": "Salomon", "price": 35, "stock": "out_of_stock", "category": "headwear", "color": "#222222"},
        ],
    },
    "streetwear": {
        "keys": ["street", "hype", "sneaker", "hoodie", "cargo", "oversized", "fit", "drip", "casual"],
        "items": [
            {"name": "Box Logo Hooded Sweatshirt", "brand": "Supreme", "price": 168, "stock": "out_of_stock", "category": "top", "color": "#1a1a1a"},
            {"name": "Cargo Pant", "brand": "Carhartt WIP", "price": 158, "stock": "in_stock", "category": "bottom", "color": "#5e5a48"},
            {"name": "Air Jordan 1 Mid", "brand": "Nike", "price": 125, "stock": "in_stock", "category": "shoes", "color": "#c2362f"},
            {"name": "Varsity Jacket", "brand": "Stüssy", "price": 290, "stock": "in_stock", "category": "outerwear", "color": "#2d3e5a"},
            {"name": "Crossbody Shoulder Bag", "brand": "Carhartt WIP", "price": 60, "stock": "in_stock", "category": "bag", "color": "#333333"},
            {"name": "Reversible Beanie", "brand": "New Era", "price": 28, "stock": "in_stock", "category": "headwear", "color": "#8a8a8a"},
        ],
    },
    "coastal_summer": {
        "keys": ["summer", "beach", "coastal", "linen", "vacation", "sun", "resort", "boat", "hot"],
        "items": [
            {"name": "Linen Camp Collar Shirt", "brand": "Uniqlo", "price": 40, "stock": "in_stock", "category": "top", "color": "#e9dcc3"},
            {"name": "Baggies Shorts 5\"", "brand": "Patagonia", "price": 65, "stock": "in_stock", "category": "bottom", "color": "#4f86b8"},
            {"name": "Arizona Oiled Leather Sandal", "brand": "Birkenstock", "price": 135, "stock": "in_stock", "category": "shoes", "color": "#7a5a3a"},
            {"name": "Woven Straw Tote", "brand": "Madewell", "price": 98, "stock": "in_stock", "category": "bag", "color": "#cfb27a"},
            {"name": "Classic Round Sunglasses", "brand": "Ray-Ban", "price": 161, "stock": "in_stock", "category": "accessory", "color": "#1f1f1f"},
            {"name": "Bucket Hat", "brand": "Kangol", "price": 50, "stock": "out_of_stock", "category": "headwear", "color": "#f1ece3"},
        ],
    },
    "dark_academia": {
        "keys": ["academia", "vintage", "library", "tweed", "autumn", "fall", "preppy", "classic", "oxford", "scholar"],
        "items": [
            {"name": "Wool Tweed Blazer", "brand": "J.Crew", "price": 298, "stock": "in_stock", "category": "outerwear", "color": "#5a4a3c"},
            {"name": "Cable-Knit Turtleneck", "brand": "Ralph Lauren", "price": 165, "stock": "in_stock", "category": "top", "color": "#d8cdb8"},
            {"name": "Pleated Wool Trousers", "brand": "Banana Republic", "price": 150, "stock": "in_stock", "category": "bottom", "color": "#2f2a26"},
            {"name": "Penny Loafer", "brand": "G.H. Bass", "price": 175, "stock": "in_stock", "category": "shoes", "color": "#4a2a1a"},
            {"name": "Leather Satchel", "brand": "Fossil", "price": 220, "stock": "out_of_stock", "category": "bag", "color": "#6b3f23"},
            {"name": "Tortoise Round Glasses", "brand": "Warby Parker", "price": 95, "stock": "in_stock", "category": "accessory", "color": "#7a5230"},
        ],
    },
}


def curate(prompt: str) -> list[dict]:
    words = set(re.findall(r"[a-z0-9']+", prompt.lower()))
    best, best_score = None, -1
    for haul in _HAULS.values():
        score = sum(1 for k in haul["keys"] if k in words or any(k in w for w in words))
        if score > best_score:
            best, best_score = haul, score
    if best_score <= 0:
        best = random.choice(list(_HAULS.values()))
    items = [dict(it) for it in best["items"]]
    # Small variation so repeated prompts feel alive: occasionally drop one accessory.
    if len(items) > 5 and random.random() < 0.4:
        extras = [i for i in items if i["category"] in ("accessory", "headwear", "bag")]
        if extras:
            items.remove(random.choice(extras))
    return normalize_list(items)
