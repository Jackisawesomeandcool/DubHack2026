"""Offline tests for catalog search. Run: python3 backend/test_search.py

No network and no API key: the AI ranker is stubbed. The catalog is a temp
SQLite loaded from backend/dataset/catalog.json (the shared dataset), so the
tests exercise real product names and prices.
"""

import json
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
import finder  # noqa: E402
import intent  # noqa: E402
import llm  # noqa: E402
import ranker  # noqa: E402
from intent import Intent, matches, parse  # noqa: E402

catalog.DB_PATH = config.DATA_DIR / "catalog.sqlite"


def load_dataset() -> int:
    data = json.loads((HERE / "dataset" / "catalog.json").read_text(encoding="utf-8"))
    rows = data["items"]
    with catalog._lock:
        db = catalog._db()
        db.execute("DELETE FROM products")
        for it in rows:
            db.execute("INSERT INTO products (url,name,brand,price,category,tags,cutout_p,cutout_m,stock,source,last_checked,added_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                       (it["url"], it["name"], it["brand"], it["price"], it["category"], it.get("tags", ""),
                        "/cutouts/" + it["cutout_p"] if it.get("cutout_p") else None,
                        "/cutouts/" + it["cutout_m"] if it.get("cutout_m") else None,
                        it.get("stock", "in_stock"), it.get("source"), it.get("last_checked"), it.get("added_at")))
        db.execute("DELETE FROM results")
        db.commit()
    return len(rows)


N = load_dataset()


class Parse(unittest.TestCase):
    def test_price_phrasings(self):
        self.assertEqual(parse("shoes under 50 dollars").price_max, 50)
        self.assertEqual(parse("shoes below $50").price_max, 50)
        self.assertEqual(parse("shoes for 50 bucks").price_max, 50)
        self.assertEqual(parse("shoes under 50 dollars").key(), parse("shoes below $50").key())
        self.assertEqual((parse("joggers between 40 and 60").price_min, parse("joggers between 40 and 60").price_max), (40, 60))
        self.assertEqual(parse("jacket over 150").price_min, 150)
        self.assertEqual((parse("hoodie around $80").price_min, parse("hoodie around $80").price_max), (60, 100))

    def test_terms_and_categories(self):
        it = parse("shoes under 50 dollars")
        self.assertEqual((it.terms, it.categories), (["shoes"], ["shoes"]))
        self.assertEqual(parse("black hoodie below 80").colors, ["black"])
        self.assertEqual(parse("black hoodie below 80").terms, ["black hoodie"])
        self.assertEqual(parse("air max 90").price_max, None)
        self.assertEqual(parse("air max 90").terms, ["air max 90"])
        self.assertEqual(parse("fall fashion").categories, [])
        self.assertEqual(parse("fall fashion").terms, ["fall fashion"])

    def test_brand(self):
        self.assertEqual(parse("stussy hoodie").brands, ["stussy"])
        self.assertEqual(parse("adidas jacket under 80").brands, ["adidas"])

    def test_cheap(self):
        it = parse("cheap sneakers")
        self.assertEqual((it.price_max, it.sort, it.terms), (None, "price_asc", ["sneakers"]))

    def test_api_category(self):
        it = parse("something warm", "outerwear")
        self.assertEqual((it.categories, it.explicit_category), (["outerwear"], True))

    def test_swap_prompt_is_not_a_constraint(self):
        it = parse("pants similar in style to Nike Club Fleece Black Joggers under 80", "bottom")
        self.assertEqual(it.categories, ["bottom"])
        self.assertEqual((it.brands, it.colors, it.price_max), ([], [], None))
        self.assertTrue(it.explicit_category)


class Matches(unittest.TestCase):
    def test_price(self):
        it = Intent(raw="", categories=["shoes"], price_max=50)
        self.assertTrue(matches({"name": "x", "brand": "Nike", "price": 45, "category": "shoes"}, it))
        self.assertFalse(matches({"name": "x", "brand": "Nike", "price": 120, "category": "shoes"}, it))
        self.assertFalse(matches({"name": "x", "brand": "Nike", "price": 0, "category": "shoes"}, it), "unknown price fails a budget")
        self.assertTrue(matches({"name": "x", "brand": "Nike", "price": 0, "category": "shoes"}, Intent(raw="")))

    def test_brand_unicode(self):
        it = Intent(raw="", brands=["stussy"])
        self.assertTrue(matches({"name": "Basic Tee", "brand": "Stüssy", "price": 40, "category": "top"}, it))
        self.assertFalse(matches({"name": "Basic Tee", "brand": "Nike", "price": 40, "category": "top"}, it))

    def test_color(self):
        it = Intent(raw="", colors=["grey"])
        self.assertTrue(matches({"name": "Dunk Low Wolf Grey", "brand": "Nike", "price": 110, "category": "shoes"}, it))
        self.assertTrue(matches({"name": "Club Fleece", "tags": "club fleece gray", "brand": "Nike", "price": 60, "category": "top"}, it))
        self.assertFalse(matches({"name": "Club Fleece Sail", "brand": "Nike", "price": 60, "category": "top"}, it))


class CatalogQueries(unittest.TestCase):
    def test_dataset_loaded(self):
        self.assertEqual(catalog.count(), N)
        self.assertGreater(N, 100)

    def test_candidates_respect_budget(self):
        it = parse("shoes under 100 dollars")
        pool = catalog.candidates(it, False, [])
        self.assertTrue(pool)
        self.assertTrue(all(0 < p["price"] <= 100 and p["category"] == "shoes" for p in pool))

    def test_candidates_brand(self):
        pool = catalog.candidates(parse("stussy"), False, [])
        self.assertTrue(pool)
        self.assertTrue(all(p["brand"] == "Stüssy" for p in pool))

    def test_no_constraints_is_whole_catalog(self):
        self.assertEqual(len(catalog.candidates(parse("fall fashion"), False, [])), N)

    def test_floor_price(self):
        it = parse("shoes under 1 dollar")
        self.assertEqual(catalog.candidates(it, False, []), [])
        floor = catalog.floor_price(it)
        self.assertIsNotNone(floor)
        self.assertGreater(floor, 1)

    def test_keyword_search_whole_words(self):
        hits = catalog.search(parse("dunk low"), False, [])
        self.assertTrue(hits)
        self.assertTrue(all("dunk" in h["name"].lower() and "low" in h["name"].lower() for h in hits))

    def test_specific_garment_word_required(self):
        for h in catalog.search(parse("hoodie"), False, [], limit=50):
            self.assertIn("hoodie", (h["name"] + " ").lower())

    def test_descriptive_prompt_relaxes_to_any_word(self):
        self.assertEqual(catalog.search(parse("zzzq shoes"), False, []), [], "short prompt stays strict")
        hits = catalog.search(parse("skater fit with wide-leg pants, a graphic tee and skate shoes"), False, [])
        self.assertTrue(hits)
        self.assertTrue({h["category"] for h in hits} <= {"bottom", "top", "shoes"})

    def test_cheap_sorts_ascending(self):
        hits = catalog.search(parse("cheap shoes"), False, [])
        prices = [h["price"] for h in hits]
        self.assertEqual(prices, sorted(prices))

    def test_models_mode_falls_back_to_product_cutout(self):
        self.assertTrue(catalog.candidates(parse("shoes"), True, []))

    def test_cache_rechecks_filters(self):
        it = parse("shoes under 100 dollars")
        cheap = catalog.candidates(it, False, [])[0]
        dear = next(p for p in catalog.candidates(parse("shoes"), False, []) if p["price"] > 150)
        catalog.cache_results(it, False, [cheap, dear])
        self.assertEqual([c["url"] for c in catalog.cached_results(it, False, [])], [cheap["url"]])


class StubLLM:
    """Pretend provider: picks the first `count` candidates whose name contains `want`."""

    def __init__(self, want: str = "", fail: bool = False):
        self.want, self.fail, self.calls = want.lower(), fail, []

    def __enter__(self):
        self._prov, self._conf, self._pick = llm.provider, llm.configured, llm.pick_products
        llm.provider = lambda: "stub"
        llm.configured = lambda: True
        llm.pick_products = self.pick
        return self

    def __exit__(self, *a):
        llm.provider, llm.configured, llm.pick_products = self._prov, self._conf, self._pick

    def pick(self, prompt, lines, count):
        self.calls.append((prompt, len(lines), count))
        if self.fail:
            raise llm.LLMError("stub down")
        out = []
        for ln in lines:
            n, _, name, _, _ = [x.strip() for x in ln.split(" | ")]
            if self.want in name.lower():
                out.append({"n": int(n), "why": "stub"})
            if len(out) >= count:
                break
        # one bogus number: must be ignored
        out.append({"n": 99999, "why": "bogus"})
        return out


def stub_pool(stub):
    """Candidates the stub was shown, reconstructed from the offered lines count: re-query the catalog."""
    return catalog.candidates(parse("pants similar in style to Stüssy Junya Cargo Pants", "bottom"), False, ["Junya Cargo Pants"])


class Finder(unittest.TestCase):
    def setUp(self):
        with catalog._lock:
            catalog._db().execute("DELETE FROM results")
            catalog._db().commit()

    def test_keyword_path_without_llm(self):
        items = finder.results("shoes under 100 dollars")
        self.assertTrue(items)
        self.assertTrue(all(i["price"] <= 100 for i in items))

    def test_no_match_reason(self):
        with self.assertRaises(finder.NoMatch) as cm:
            finder.results("shoes under 1 dollar")
        self.assertRegex(str(cm.exception), r"^No shoes under \$1 — cheapest is \$\d+")
        with self.assertRaises(finder.NoMatch) as cm:
            finder.results("adidas jacket")
        self.assertEqual(str(cm.exception), "No adidas outerwear in the catalog")

    def test_llm_picks_are_filtered_and_used(self):
        with StubLLM(want="fleece") as stub:
            items = finder.results("cozy fall fit", count=4)
        self.assertEqual(len(stub.calls), 1)
        unique = len({p["name"].lower() for p in catalog.candidates(parse("fall fashion"), False, [])})
        self.assertEqual(stub.calls[0][1], unique, "no constraints → whole catalog (one line per product name) offered")
        self.assertTrue(items and all("fleece" in i["name"].lower() for i in items))
        self.assertLessEqual(len(items), 4)

    def test_llm_cannot_unfilter(self):
        with StubLLM(want="") as stub:            # picks the first N candidates it is shown
            items = finder.results("shoes under 100 dollars")
        self.assertTrue(all(i["price"] <= 100 and i["category"] == "shoes" for i in items))
        self.assertLess(stub.calls[0][1], N, "only the SQL-filtered pool was offered")

    def test_llm_failure_falls_back_to_keywords(self):
        with StubLLM(fail=True):
            items = finder.results("dunk low")
        self.assertTrue(items and all("dunk" in i["name"].lower() for i in items))

    def test_cache_hit_skips_llm(self):
        with StubLLM(want="") as stub:
            finder.results("shoes under 100 dollars")
            finder.results("shoes below $100")
        self.assertEqual(len(stub.calls), 1)

    def test_stream_shape(self):
        evs = list(finder.stream("shoes under 100 dollars"))
        self.assertEqual([list(e)[0] for e in evs], ["items", "done"])
        self.assertTrue(all(e.get("image") for e in evs[0]["items"]))

    def test_stream_empty_has_reason(self):
        evs = list(finder.stream("shoes under 1 dollar"))
        self.assertEqual([list(e)[0] for e in evs], ["items", "reason", "done"])
        self.assertEqual(evs[0]["items"], [])
        self.assertRegex(evs[1]["reason"], r"^No shoes under \$1")

    def test_swap_offers_other_pieces_of_the_category(self):
        with StubLLM(want="") as stub:
            items = finder.results("pants similar in style to Stüssy Junya Cargo Pants", "bottom", exclude=["Junya Cargo Pants"])
        self.assertTrue(items and all(i["category"] == "bottom" for i in items))
        self.assertTrue(any(i["brand"] != "Stüssy" for i in stub_pool(stub)), "swap pool is not brand-locked")

    def test_find_swallows_no_match(self):
        self.assertEqual(finder.find("shoes under 1 dollar"), [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
