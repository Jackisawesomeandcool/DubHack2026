"""20 end-to-end search prompts against the shared dataset. Run: python3 backend/test_prompts.py

Offline (no key): the AI ranker is stubbed with "pick in catalog order", so
these check the whole path a real request takes — intent parsing, the hard
filters, candidate retrieval, ranking fallback, result count — and assert
that every returned product actually satisfies what was typed. Prints a
table of prompt → parsed intent → results so the behaviour can be eyeballed.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
for k in ("GEMINI_API_KEY", "XAI_API_KEY", "GOOGLE_CSE_KEY", "WEB_SEARCH"):
    os.environ[k] = ""

import config  # noqa: E402

config.DATA_DIR = Path(tempfile.mkdtemp())
config.GEMINI_API_KEY = config.XAI_API_KEY = ""

import catalog  # noqa: E402
import dataset  # noqa: E402
import finder  # noqa: E402
import intent  # noqa: E402
from intent import matches, parse  # noqa: E402

dataset.load(quiet=True, images=False)

# prompt, expectations: cats (every result's category in set), price_max, brand (substring), color, min_results
CASES = [
    ("black jacket under 150",       dict(cats={"outerwear"}, price_max=150, color="black", min=1)),
    ("shoes",                        dict(cats={"shoes"}, min=15)),
    ("sneakers under $100",          dict(cats={"shoes"}, price_max=100, min=3)),
    ("nike hoodie",                  dict(cats={"top"}, brand="nike", min=3)),
    ("stussy",                       dict(brand="st", min=5)),
    ("uniqlo under 40",              dict(brand="uniqlo", price_max=40, min=1)),
    ("white tee",                    dict(cats={"top"}, color="white", min=1)),
    ("cargo pants",                  dict(cats={"bottom"}, min=1)),
    ("backpack",                     dict(cats={"bag"}, min=1)),
    ("beanie",                       dict(cats={"headwear"}, min=1)),
    ("socks",                        dict(cats={"accessory"}, min=1)),
    ("fall clothes",                 dict(min=5)),
    ("comfy loungewear",             dict(min=3)),
    ("streetwear",                   dict(min=5)),
    ("running shoes between 80 and 160", dict(cats={"shoes"}, price_min=80, price_max=160, min=1)),
    ("cheap hat",                    dict(cats={"headwear"}, min=1, sorted_asc=True)),
    ("red shirt",                    dict(cats={"top"}, color="red", min=1)),
    ("jordan shoes under 200",       dict(cats={"shoes"}, price_max=200, min=1)),
    ("gym fit",                      dict(min=5)),
    ("something warm for winter",    dict(min=3)),
]


def run(prompt: str) -> list[dict]:
    try:
        return finder.results(prompt, None, [], False, count=finder.COUNT)
    except finder.NoMatch:
        return []


class Prompts(unittest.TestCase):
    pass


def _make(prompt, exp):
    def test(self):
        it = parse(prompt)
        items = run(prompt)
        # Print one line per prompt so the output doubles as a report.
        names = ", ".join(f"{i['brand']} {i['name']} ${i['price']:.0f}" for i in items[:3])
        print(f"\n  {prompt!r:40} → {it.describe():45} → {len(items):2} results  e.g. {names}", file=sys.stderr)
        self.assertGreaterEqual(len(items), exp.get("min", 1), f"too few results for {prompt!r}")
        for i in items:
            self.assertTrue(matches(i, it), f"{i['name']} violates the hard filters for {prompt!r}")
            if "cats" in exp:
                self.assertIn(i["category"], exp["cats"], f"{i['name']} is {i['category']}, wanted {exp['cats']}")
            if "price_max" in exp:
                self.assertLessEqual(i["price"], exp["price_max"], f"{i['name']} ${i['price']} over budget")
            if "price_min" in exp:
                self.assertGreaterEqual(i["price"], exp["price_min"], f"{i['name']} ${i['price']} under minimum")
            if "brand" in exp:
                self.assertIn(exp["brand"], intent._norm(i["brand"]), f"{i['name']} is {i['brand']}, wanted {exp['brand']}")
            if "color" in exp:
                self.assertIn(exp["color"], intent.item_colors(i), f"{i['name']} is not {exp['color']}")
        if exp.get("sorted_asc"):
            prices = [i["price"] for i in items]
            self.assertEqual(prices, sorted(prices), "cheap → results should be ordered by price")
        # No duplicates, and never more than the tray cap.
        self.assertEqual(len({i["url"] for i in items}), len(items), "duplicate products returned")
        self.assertLessEqual(len(items), finder.COUNT)
    return test


for n, (prompt, exp) in enumerate(CASES, 1):
    setattr(Prompts, f"test_{n:02d}_{intent._WORD.sub('_', prompt)[:30]}", _make(prompt, exp))


if __name__ == "__main__":
    print(f"catalog: {catalog.count()} products · result cap {finder.COUNT}", file=sys.stderr)
    unittest.main(verbosity=1)
