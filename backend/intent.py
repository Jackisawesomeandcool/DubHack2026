"""Search-bar understanding, part 1: the hard constraints.

    "shoes under 50 dollars"   → categories=["shoes"], price_max=50, terms=["shoes"]
    "black hoodie below $80"   → categories=["top"], colors=["black"], price_max=80, terms=["black hoodie"]
    "adidas jacket"            → categories=["outerwear"], brands=["adidas"]
    "fall fashion"             → no constraints; terms=["fall fashion"] (the AI ranker does the work)
    swap (API category given) → that category only; words in the product name are not constraints

Deterministic and instant (regex, no network). The constraints found here are
HARD: `matches(item, intent)` is the one predicate every result passes, so a
product outside the budget / category / brand / color is never shown or cached.
Everything softer — "fall", "sporty", "goes with" — is left to ranker.py.
"""

import re
from dataclasses import dataclass, field

from products import CATEGORIES

_WORD = re.compile(r"[a-z0-9]+")

# category synonyms (also used by catalog.py for keyword scoring)
SYN = {
    "jacket": "outerwear", "jackets": "outerwear", "coat": "outerwear", "coats": "outerwear", "windbreaker": "outerwear",
    "puffer": "outerwear", "outerwear": "outerwear", "parka": "outerwear", "vest": "outerwear", "anorak": "outerwear",
    "hoodie": "top", "hoodies": "top", "tee": "top", "tees": "top", "shirt": "top", "shirts": "top", "sweatshirt": "top",
    "crewneck": "top", "top": "top", "tops": "top", "sweater": "top", "tank": "top", "polo": "top", "jersey": "top",
    "pants": "bottom", "joggers": "bottom", "shorts": "bottom", "cargos": "bottom", "sweatpants": "bottom", "bottoms": "bottom",
    "trousers": "bottom", "jeans": "bottom", "leggings": "bottom", "tights": "bottom", "skirt": "bottom",
    "shoes": "shoes", "shoe": "shoes", "sneakers": "shoes", "sneaker": "shoes", "kicks": "shoes", "boots": "shoes", "boot": "shoes",
    "runners": "shoes", "dunks": "shoes", "footwear": "shoes", "slides": "shoes", "sandals": "shoes", "cleats": "shoes",
    "hat": "headwear", "hats": "headwear", "cap": "headwear", "caps": "headwear", "beanie": "headwear", "visor": "headwear",
    "bag": "bag", "bags": "bag", "backpack": "bag", "tote": "bag", "duffel": "bag", "crossbody": "bag",
    "socks": "accessory", "belt": "accessory", "accessory": "accessory", "accessories": "accessory", "gloves": "accessory",
    "scarf": "accessory", "sunglasses": "accessory",
}
STOP = {"a", "an", "the", "and", "or", "with", "for", "in", "on", "of", "to", "fit", "look", "outfit", "style",
        "mens", "womens", "men", "women", "some", "me", "find", "show", "want", "need", "please", "i", "something"}

# Filler that names no product ("comfortable clothes", "fall aesthetic"); ignored when matching.
FILLER = {"clothes", "clothing", "clothe", "apparel", "wear", "gear", "stuff", "things", "pieces", "items", "outfits",
          "looks", "aesthetic", "aesthetics", "vibe", "vibes", "trendy", "cute", "nice", "good", "best", "season",
          "seasonal", "inspo", "ideas", "popular", "new"}
STOP |= FILLER

# Subjective words → words that appear in catalog product names/tags that fit the mood. Used by the keyword
# ranker (no-AI fallback); the AI ranker reads the same idea from its prompt. Stems, lowercase.
_COMFY = {"fleece", "plush", "soft", "impossiblysoft", "club", "sweatshirt", "hoodie", "jogger", "sweatpant", "loose",
          "oversized", "relaxed", "pullover", "crew", "tee", "basic", "everyday", "short", "beanie", "therma", "lounge",
          "knit", "cozy", "full", "zip"}
_COLD = {"fleece", "therma", "jacket", "windrunner", "bomber", "anorak", "vest", "hoodie", "sweatshirt", "pullover",
         "beanie", "glove", "woven", "repel", "puffer", "down", "denim", "corduroy", "utility", "shell", "heattech",
         "long", "coach", "parka", "coat", "sherpa", "flannel", "acg", "tech", "zip", "hooded"}
_SPORT = {"dri", "training", "running", "track", "sportswear", "tech", "flow", "metcon", "zoom", "basketball", "soccer",
          "short", "tank", "jogger", "pegasus", "vomero", "speed", "academy", "strike", "jersey", "performance", "air",
          "max", "run", "road", "swoosh", "sport", "sports", "gym", "athletic", "football"}
_STREET = {"graphic", "denim", "loose", "cargo", "baggy", "jordan", "dunk", "stussy", "tears", "oversized", "bomber",
           "heritage", "classic", "force", "trucker", "tee"}
VIBES = {
    "comfortable": _COMFY, "comfy": _COMFY, "cozy": _COMFY, "soft": _COMFY, "relaxed": _COMFY, "lounge": _COMFY,
    "loungewear": _COMFY, "casual": _COMFY | {"club", "classic"}, "chill": _COMFY, "everyday": _COMFY,
    "fall": _COLD, "autumn": _COLD, "chilly": _COLD, "cold": _COLD, "winter": _COLD, "layer": _COLD, "layering": _COLD,
    "warm": _COLD,
    "athletic": _SPORT, "athleisure": _SPORT | _COMFY, "sporty": _SPORT, "sport": _SPORT, "sports": _SPORT,
    "workout": _SPORT, "gym": _SPORT, "training": _SPORT, "active": _SPORT, "activewear": _SPORT, "performance": _SPORT,
    "sportswear": _SPORT, "running": _SPORT | {"road"}, "run": _SPORT, "runner": _SPORT,
    "streetwear": _STREET, "street": _STREET, "urban": _STREET, "skate": _STREET, "skater": _STREET, "hype": _STREET,
    "basics": {"basic", "tee", "crew", "everyday", "classic", "polo", "heattech", "uniqlo"},
    "minimal": {"basic", "tee", "crew", "classic", "everyday", "uniqlo"}, "simple": {"basic", "tee", "crew", "classic"},
}
# brand a mood leans toward (matched against the brand field, lowercase, ü stripped)
VIBE_BRANDS = {"streetwear": {"stussy"}, "street": {"stussy"}, "skate": {"stussy"}, "skater": {"stussy"},
               "urban": {"stussy"}, "hype": {"stussy", "jordan"}, "basics": {"uniqlo"}, "minimal": {"uniqlo"},
               "simple": {"uniqlo"}, "athletic": {"nike"}, "sporty": {"nike"}, "workout": {"nike"}, "gym": {"nike"}}

# canonical color → words that count as that color in a product name / tags
COLORS = {
    "black": {"black", "anthracite"},
    "white": {"white", "sail", "summit"},
    "grey": {"grey", "gray", "smoke", "iron", "wolf", "pewter", "heather"},
    "blue": {"blue", "navy", "royal", "obsidian", "cobalt", "indigo", "denim"},
    "red": {"red", "crimson", "maroon", "burgundy", "bordeaux", "cardinal"},
    "green": {"green", "olive", "forest", "sage", "mint", "jade"},
    "brown": {"brown", "tan", "khaki", "chocolate", "mocha", "coffee", "hemp", "wheat", "baroque"},
    "beige": {"beige", "cream", "bone", "oatmeal", "sand", "stone", "coconut", "phantom", "natural"},
    "pink": {"pink", "rose", "fuchsia", "magenta", "coral"},
    "purple": {"purple", "violet", "lavender", "lilac", "plum", "grape"},
    "orange": {"orange", "rust", "amber"},
    "yellow": {"yellow", "gold", "mustard", "citron", "lemon"},
}
COLOR_WORD = {w: c for c, ws in COLORS.items() for w in ws}

# brands in the catalog and common asks; matched as whole words, "stussy" also matches "Stüssy"
BRANDS = {"nike", "jordan", "stussy", "uniqlo", "adidas", "puma", "new balance", "asics", "reebok",
          "converse", "vans", "under armour", "lululemon", "patagonia", "north face", "carhartt", "levis", "zara"}

_BRAND_WORDS = {w for b in BRANDS for w in b.split()} | {"stüssy", "levi"}   # single words of the brand names

# words that signal a constraint; stripped from the search terms
_CONSTRAINT_WORDS = {"under", "below", "over", "above", "between", "around", "about", "within", "cheap", "cheaper",
                     "cheapest", "budget", "affordable", "inexpensive", "expensive", "than", "less", "more", "least", "most"}


# ---------------------------------------------------------------- intent
@dataclass
class Intent:
    raw: str
    terms: list[str] = field(default_factory=list)        # the request minus its constraint phrases
    categories: list[str] = field(default_factory=list)   # subset of CATEGORIES; [] = any
    explicit_category: bool = False                       # category came from the API (a swap), not the words
    price_max: float | None = None
    price_min: float | None = None
    colors: list[str] = field(default_factory=list)       # canonical COLORS keys
    brands: list[str] = field(default_factory=list)       # lowercase
    sort: str | None = None                               # "price_asc" for 'cheap' with no number

    def key(self) -> str:
        """Canonical cache key — phrasing variants of the same intent share it."""
        return "|".join([
            " ".join(sorted(set(self.terms))),
            ",".join(sorted(self.categories)),
            f"{self.price_min or ''}-{self.price_max or ''}",
            ",".join(sorted(self.colors)),
            ",".join(sorted(self.brands)),
            self.sort or "",
        ])

    def has_filters(self) -> bool:
        return bool(self.price_max is not None or self.price_min is not None or self.colors or self.brands)

    def term_words(self) -> list[list[str]]:
        return [[w for w in _WORD.findall(t.lower()) if w not in STOP and len(w) > 1] for t in (self.terms or [self.raw])]

    def words(self) -> list[str]:
        return list(dict.fromkeys(w for ws in self.term_words() for w in ws))

    def describe(self) -> str:
        bits = [", ".join(self.terms) or self.raw]
        if self.categories:
            bits.append("/".join(self.categories))
        if self.price_min is not None and self.price_max is not None:
            bits.append(f"${self.price_min:g}-{self.price_max:g}")
        elif self.price_max is not None:
            bits.append(f"≤${self.price_max:g}")
        elif self.price_min is not None:
            bits.append(f"≥${self.price_min:g}")
        if self.colors:
            bits.append("color=" + ",".join(self.colors))
        if self.brands:
            bits.append("brand=" + ",".join(self.brands))
        if self.sort:
            bits.append(self.sort)
        return " · ".join(bits)


# ---------------------------------------------------------------- matching
def _norm(s: str) -> str:
    return s.lower().replace("ü", "u").replace("'", "")


def item_colors(item: dict) -> set[str]:
    """Canonical colors of an item. Once colors.py has read the product image (`color` field), the
    colors are the picture's plus any the name states; tags are ignored then, because they can list
    every colorway the product comes in (Uniqlo) while the cutout shows only one. Until the image has
    been read, the name and tags decide."""
    own = {c for c in (item.get("color") or "").split() if c in COLORS}
    text = item.get("name", "") if own else f"{item.get('name', '')} {item.get('tags', '')}"
    words = set(_WORD.findall(text.lower()))
    return own | {COLOR_WORD[w] for w in words if w in COLOR_WORD}


def matches(item: dict, intent: Intent) -> bool:
    """Hard filter. An item that fails is never shown or cached for this search."""
    if intent.categories and item.get("category") not in intent.categories:
        return False
    if intent.price_max is not None or intent.price_min is not None:
        price = float(item.get("price") or 0)
        if price <= 0:
            return False                      # unknown price ≠ within budget
        if intent.price_max is not None and price > intent.price_max:
            return False
        if intent.price_min is not None and price < intent.price_min:
            return False
    if intent.colors and not (set(intent.colors) & item_colors(item)):
        return False
    if intent.brands:
        text = _norm(f"{item.get('brand', '')} {item.get('name', '')}")
        if not any(_norm(b) in text for b in intent.brands):
            return False
    return True


# ---------------------------------------------------------------- parsing
_NUM = r"\$?\s*(\d+(?:\.\d+)?)\s*(?:dollars?|bucks|usd|\$)?"
_RANGE = re.compile(rf"(?:between|from)\s+{_NUM}\s+(?:and|to|-)\s+{_NUM}", re.I)
_DASH_RANGE = re.compile(rf"{_NUM}\s*(?:-|–|to)\s*{_NUM}", re.I)
_MAX = re.compile(rf"(?:under|below|less\s+than|cheaper\s+than|(?<!air\s)max(?:imum)?|up\s+to|at\s+most|no\s+more\s+than|within|<=?|not\s+over)\s*{_NUM}", re.I)
_MIN = re.compile(rf"(?:over|above|more\s+than|at\s+least|min(?:imum)?|starting\s+(?:at|from)|>=?)\s*{_NUM}", re.I)
_AROUND = re.compile(rf"(?:around|about|approx(?:imately)?|roughly|~)\s*{_NUM}", re.I)
_BARE = re.compile(rf"(?:\$\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*(?:dollars?|bucks|usd))(?!\s*(?:and|to|-))", re.I)
_CHEAP = re.compile(r"\b(cheap(?:er|est)?|budget|affordable|inexpensive|low[-\s]?cost|bargain)\b", re.I)
_PRICE_WORD = re.compile(r"\b(price[sd]?|cost(?:s|ing)?|dollars?|bucks|usd)\b", re.I)


def _categories_from(words: list[str]) -> list[str]:
    return list(dict.fromkeys(SYN[w] for w in words if w in SYN))


def parse(prompt: str, category: str | None = None) -> Intent:
    """Prompt (+ optional API category) → Intent. Pure function, no network."""
    text = prompt.strip()
    it = Intent(raw=prompt)

    if category in CATEGORIES:
        # A swap: the API names the category and the prompt is built from a product name
        # ("pants similar in style to Nike Club Fleece Joggers"). Brand, color and price words in
        # a product name are not the shopper's constraints, so only the category is enforced;
        # the AI ranker still reads the whole prompt.
        it.categories, it.explicit_category = [category], True
        words = [w for w in _WORD.findall(text.lower()) if w not in STOP]
        it.terms = [" ".join(words)] if words else []
        return it

    def take(rx, lo=None, hi=None, around=False) -> bool:
        nonlocal text
        m = rx.search(text)
        if not m:
            return False
        if around:
            v = float(m.group(1))
            it.price_min, it.price_max = round(v * 0.75, 2), round(v * 1.25, 2)
        else:
            if lo is not None:
                it.price_min = float(m.group(lo))
            if hi is not None:
                g = m.group(hi) or (m.group(hi + 1) if hi < len(m.groups()) else None)
                it.price_max = float(g)
        text = text[:m.start()] + " " + text[m.end():]
        return True

    if not take(_RANGE, lo=1, hi=2):
        took = take(_MAX, hi=1) | take(_MIN, lo=1)
        if not took:
            take(_AROUND, around=True) or take(_DASH_RANGE, lo=1, hi=2) or take(_BARE, hi=1)
    if it.price_min is not None and it.price_max is not None and it.price_min > it.price_max:
        it.price_min, it.price_max = it.price_max, it.price_min

    if _CHEAP.search(text):
        text = _CHEAP.sub(" ", text)
        if it.price_max is None:
            it.sort = "price_asc"
    text = _PRICE_WORD.sub(" ", text)

    low = _norm(text)
    for b in sorted(BRANDS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(_norm(b))}\b", low) and _norm(b) not in [_norm(x) for x in it.brands]:
            it.brands.append(b)
    words = [w for w in _WORD.findall(text.lower()) if w not in STOP]
    it.colors = list(dict.fromkeys(COLOR_WORD[w] for w in words if w in COLOR_WORD))
    it.categories = _categories_from(words)
    term = " ".join(w for w in words if w not in _CONSTRAINT_WORDS)
    it.terms = [term] if term else []
    return it
