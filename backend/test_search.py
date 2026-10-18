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
            parts = [x.strip() for x in ln.split(" | ")]
            n, name = parts[0], " | ".join(parts[2:-3])     # names may contain ' | '
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


class Accounts(unittest.TestCase):
    def setUp(self):
        import auth
        self.auth = auth
        auth._conn = None
        auth.DB_PATH = config.DATA_DIR / "users-test.sqlite"
        if auth.DB_PATH.exists():
            auth.DB_PATH.unlink()

    def test_clear_data_keeps_the_account(self):
        a = self.auth
        user, tok = a.signup("Ann", "ann", "ann@x.co", "password1")
        a.set_state(user["id"], [{"name": "x"}], [{"items": [{"name": "y"}]}], [{"prompt": "hi"}])
        a.clear_data(user["id"])
        self.assertEqual(a.get_state(user["id"])["favorites"], [])
        self.assertEqual(a.get_state(user["id"])["hauls"], [])
        self.assertEqual(a.user_for(tok)["username"], "ann")
        a.login("ann", "password1")

    def test_delete_account_removes_everything_and_signs_out_every_device(self):
        a = self.auth
        user, tok = a.signup("Ann", "ann", "ann@x.co", "password1")
        _, tok2 = a.login("ann@x.co", "password1")
        a.set_state(user["id"], [{"name": "x"}], [], [])
        a.delete_account(user["id"])
        self.assertIsNone(a.user_for(tok))
        self.assertIsNone(a.user_for(tok2))
        self.assertEqual(a.get_state(user["id"])["favorites"], [])
        with self.assertRaises(a.AuthError):
            a.login("ann", "password1")
        a.signup("Ann", "ann", "ann@x.co", "password1")        # the name and email are free again


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
        self.assertRegex(str(cm.exception), r"^No shoes under \$1 — the closest is \$\d+")
        near = cm.exception.closest                       # nearest-priced shoes, offered by the search bar
        self.assertTrue(near and all(i["category"] == "shoes" and i["price"] > 1 for i in near))
        self.assertEqual([i["price"] for i in near], sorted(i["price"] for i in near))
        with self.assertRaises(finder.NoMatch) as cm:
            finder.results("adidas jacket")
        self.assertEqual(str(cm.exception), "No adidas outerwear in the catalog")

    def test_llm_picks_are_filtered_and_used(self):
        with StubLLM(want="fleece") as stub:
            items = finder.results("cozy fall fit", count=4)
        self.assertEqual(len(stub.calls), 1)
        unique = len({p["name"].lower() for p in catalog.candidates(parse("fall fashion"), False, [])})
        self.assertEqual(stub.calls[0][1], min(unique, ranker.AI_POOL), "the model reads a small slice, not the whole catalog")
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

    def test_ai_switch_off_skips_the_model_and_has_its_own_cache(self):
        with StubLLM(want="fleece") as stub:
            fast = finder.results("cozy fall fit", count=4, ai=False)
            self.assertEqual(stub.calls, [], "switch off: no model call")
            smart = finder.results("cozy fall fit", count=4, ai=True)
            self.assertEqual(len(stub.calls), 1, "switch on after off: not served from the keyword cache")
            self.assertTrue(all("fleece" in i["name"].lower() for i in smart))
            finder.results("cozy fall fit", count=4, ai=True)
            finder.results("cozy fall fit", count=4, ai=False)
            self.assertEqual(len(stub.calls), 1, "both answers are cached")
        self.assertTrue(fast)

    def test_instant_keyword_results_first_then_ai_picks_replace_them(self):
        with StubLLM(want="fleece") as stub:
            events = list(finder.stream("cozy winter layers"))
            names = [next(iter(e)) for e in events]
            self.assertEqual(names, ["items", "ai", "replace", "done"])
            self.assertTrue(events[0]["items"] and all("by" not in i for i in events[0]["items"]))
            final = events[2]["replace"]
            self.assertLessEqual(stub.calls[0][2], ranker.AI_PICKS, "the model is asked for a few picks only")
            self.assertTrue(all(i["by"] == "stub" for i in final[: stub.calls[0][2]]))
            self.assertGreater(len(final), stub.calls[0][2], "the rest of the tray is keyword matches")
            self.assertEqual(len({i["url"] for i in final}), len(final), "no duplicates")
            again = list(finder.stream("cozy winter layers"))
            self.assertEqual([next(iter(e)) for e in again], ["items", "done"], "an answered search is instant, no second pass")
            self.assertEqual(len(stub.calls), 1)

    def test_failed_ai_call_is_not_cached_as_the_ai_answer(self):
        with StubLLM(fail=True) as down:
            fallback = finder.results("cozy winter fit", count=4)
        self.assertTrue(fallback and all("by" not in i for i in fallback), "fallback results are keyword results")
        class Why(StubLLM):
            def pick(self, prompt, lines, count):
                self.calls.append(prompt)
                return [{"n": 1, "why": "Warm and soft"}]
        with Why() as up:
            again = finder.results("cozy winter fit", count=4)
        self.assertEqual(len(up.calls), 1, "Gemini is asked again once it is back")
        self.assertEqual(again[0]["by"], "stub")

    def test_shopper_is_told_when_ai_was_asked_but_not_used(self):
        with StubLLM(fail=True):
            events = list(finder.stream("cozy autumn fit", count=4))
        self.assertTrue(events[0]["items"])
        self.assertIn("stub down", next(e["ai_error"] for e in events if "ai_error" in e))
        with StubLLM() as ok:
            events = list(finder.stream("cozy autumn layers", count=4))
        self.assertFalse(any("ai_error" in e for e in events), "no warning when the AI answered")
        with StubLLM(fail=True):
            events = list(finder.stream("cozy autumn fit", count=4, ai=False))
        self.assertFalse(any("ai_error" in e for e in events), "no warning when the switch is off")

    def test_gemini_reasons_are_one_sentence_and_survive_a_cut_off_reply(self):
        import gemini
        self.assertEqual(gemini.one_sentence("Soft fleece for fall. Also cheap and nice."), "Soft fleece for fall.")
        self.assertLessEqual(len(gemini.one_sentence("x" * 400)), 140)
        cut = '{"picks": [{"n": 3, "why": "Warm fleece, perfect for fall."}, {"n": 5, "why": "Easy to layer."}, {"n": 9, "why": "Cut o'
        saved = gemini._post
        gemini._post = lambda *a, **k: {"candidates": [{"content": {"parts": [{"text": cut}]}}]}
        try:
            picks = gemini.pick_products("fall", ["1 | x"], 5)
        finally:
            gemini._post = saved
        self.assertEqual([(p["n"], p["why"]) for p in picks], [(3, "Warm fleece, perfect for fall."), (5, "Easy to layer."), (9, "")])

    def test_ai_picks_carry_who_and_why_even_from_the_cache(self):
        class Why(StubLLM):
            def pick(self, prompt, lines, count):
                self.calls.append(prompt)
                return [{"n": 1, "why": "Cozy fleece for a chilly day"}, {"n": 2}]
        with Why() as stub:
            first = finder.results("cozy fall fit", count=4)
            again = finder.results("cozy fall fit", count=4)
        self.assertEqual(len(stub.calls), 1)
        for items in (first, again):
            self.assertEqual(items[0]["by"], "stub")
            self.assertEqual(items[0]["why"], "Cozy fleece for a chilly day")
            self.assertEqual(items[1]["by"], "stub")
            self.assertNotIn("why", items[1])
        keyword = finder.results("cozy fall fit", count=4, ai=False)
        self.assertTrue(all("by" not in i for i in keyword), "keyword picks are not labelled as AI")

    def test_normalize_keeps_ai_note_for_shared_hauls(self):
        from products import normalize
        item = normalize({"name": "Tee", "brand": "X", "price": 5, "by": "gemini", "why": "  Soft and plain  "})
        self.assertEqual((item["by"], item["why"]), ("gemini", "Soft and plain"))
        self.assertNotIn("by", normalize({"name": "Tee", "brand": "X", "by": "someone else"}))

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

    def test_mood_queries_return_mixed_results_without_llm(self):
        for q in ("comfortable clothes", "fall athletic", "fall aesthetic", "cozy fall outfit"):
            with self.subTest(q=q):
                items = finder.results(q)
                self.assertGreaterEqual(len(items), 4)
                self.assertGreaterEqual(len({i["category"] for i in items}), 2, "a mood returns a mix, not one kind")

    def test_fall_athletic_prefers_cold_weather_performance_pieces(self):
        names = " ".join(i["name"].lower() for i in finder.results("fall athletic"))
        self.assertTrue(any(w in names for w in ("therma", "fleece", "windrunner", "woven", "dri-fit")))

    def test_mood_keeps_hard_filters(self):
        items = finder.results("comfortable shoes under 100 dollars")
        self.assertTrue(items and all(i["category"] == "shoes" and i["price"] <= 100 for i in items))

    def test_brand_alone_returns_that_brand(self):
        # Brand is a hard filter; names/tags need not repeat it (Uniqlo names never say "Uniqlo").
        with catalog._lock:
            catalog._db().execute("UPDATE products SET tags=REPLACE(REPLACE(tags,'uniqlo',''),'nike','')")
            catalog._db().execute("DELETE FROM results")
            catalog._db().commit()
        try:
            for q, brand in (("uniqlo", "Uniqlo"), ("Nike", "Nike"), ("stüssy", "Stüssy"), ("uniqlo under 40 dollars", "Uniqlo")):
                with self.subTest(q=q):
                    items = finder.results(q)
                    self.assertTrue(items and all(i["brand"] == brand for i in items))
            self.assertGreaterEqual(len({i["category"] for i in finder.results("uniqlo")}), 2, "a brand alone gives a mix")
            with self.assertRaises(finder.NoMatch):
                finder.results("adidas")
        finally:
            load_dataset()

    def test_brandy_melville_by_its_short_name(self):
        for q in ("brandy", "brandy melville"):
            got = finder.find(q, count=30)
            self.assertTrue(got, q)
            self.assertTrue(all("brandy" in i["brand"].lower() for i in got), q)

    def test_brand_plus_garment(self):
        got = finder.find("brandy cardigan")
        self.assertTrue(got)
        self.assertTrue(all("brandy" in i["brand"].lower() and "cardigan" in i["name"].lower() for i in got))

    def test_misspelling_is_corrected_when_nothing_matches(self):
        got = finder.find("cartigans", count=30)
        self.assertTrue(got)
        self.assertTrue(all("cardigan" in i["name"].lower() for i in got))
        self.assertEqual(finder.find("zzqxv"), [])        # a word near nothing is still a miss

    def test_style_word_ranks_but_the_garment_is_required(self):
        for q, cat in (("oversized hoodie", "top"), ("baggy jeans", "bottom"), ("cozy sweater", "top")):
            got = finder.find(q, count=30)
            self.assertTrue(got, q)
            self.assertEqual({i["category"] for i in got}, {cat}, q)      # not an outfit mix of whatever feels baggy
        self.assertIn("jean", finder.find("baggy jeans")[0]["name"].lower())

    def test_occasions_and_eras_find_an_outfit_mix(self):
        for q in ("date night outfit", "outfit for a rainy day", "interview outfit", "y2k", "preppy", "hiking", "beach"):
            got = finder.find(q, count=30)
            self.assertTrue(got, q)
            self.assertGreaterEqual(len({i["category"] for i in got}), 2, q)

    def test_color_groups(self):
        self.assertEqual(set(parse("neutral tops under 60").colors), {"black", "white", "grey", "beige", "brown"})
        self.assertIn("green", parse("earth tones").colors)
        self.assertEqual(parse("earth tones").price_max, None)
        for q in ("neutral tops under 60", "earth tones", "something neutral"):
            got = finder.find(q, count=30)
            self.assertTrue(got, q)
        self.assertTrue(all(i["category"] == "top" and i["price"] <= 60 for i in finder.find("neutral tops under 60", count=30)))

    def test_gibberish_still_matches_nothing(self):
        with self.assertRaises(finder.NoMatch):
            finder.results("xyzzy qwerty")

    def test_ai_empty_answer_falls_back_to_keywords(self):
        with StubLLM(want="no-such-product-zzz") as stub:       # the AI returns no picks at all
            items = finder.results("comfortable clothes")
        self.assertEqual(len(stub.calls), 1)
        self.assertTrue(items, "an empty AI answer must not produce an empty tray")

    def test_ai_error_falls_back_to_keywords_for_moods(self):
        with StubLLM(fail=True):
            self.assertTrue(finder.results("fall athletic"))

    def test_gemini_salvages_truncated_json(self):
        import gemini
        post, text = gemini._post, gemini._text
        gemini._post = lambda *a, **k: {}
        gemini._text = lambda _r: '{"picks": [{"n": 3, "why": "cozy"}, {"n": 7, "why": "soft fl'
        try:
            self.assertEqual([p["n"] for p in gemini.pick_products("cozy", ["1 | a | b | $1 | top"], 6)], [3, 7])
        finally:
            gemini._post, gemini._text = post, text

    def test_find_swallows_no_match(self):
        self.assertEqual(finder.find("shoes under 1 dollar"), [])


class Colors(unittest.TestCase):
    """colors.py (pixel pass), the color column and color search."""

    def setUp(self):
        load_dataset()
        import colors
        self.colors = colors

    def _img(self, parts, size=(80, 80)):
        """PNG with transparent background; parts = [(rgb, x0, x1)] vertical bands."""
        from PIL import Image
        im = Image.new("RGBA", size, (0, 0, 0, 0))
        for rgb, x0, x1 in parts:
            im.paste(Image.new("RGBA", (x1 - x0, size[1]), (*rgb, 255)), (x0, 0))
        path = Path(tempfile.mkdtemp()) / "x.png"
        im.save(path)
        return path

    def test_pixel_solid_colors(self):
        for rgb, want in (((20, 120, 40), "green"), ((10, 10, 10), "black"), ((250, 250, 250), "white"),
                          ((200, 30, 30), "red"), ((30, 40, 110), "blue"), ((255, 105, 180), "pink"),
                          ((128, 128, 128), "grey"), ((120, 80, 40), "brown"), ((235, 220, 190), "beige")):
            with self.subTest(want=want):
                self.assertEqual(self.colors.from_pixels(self._img([(rgb, 0, 80)])), [want])

    def test_pixel_ignores_transparent_background_and_small_trim(self):
        # 90% navy shirt, 10% white trim, transparent corners: navy only
        got = self.colors.from_pixels(self._img([((30, 40, 110), 0, 72), ((250, 250, 250), 72, 80)]))
        self.assertEqual(got, ["blue"])

    def test_pixel_two_tone_keeps_both(self):
        got = self.colors.from_pixels(self._img([((30, 40, 110), 0, 48), ((240, 120, 20), 48, 80)]))
        self.assertEqual(got, ["blue", "orange"])

    def test_pixel_unreadable_or_empty_image(self):
        self.assertEqual(self.colors.from_pixels(Path("/nonexistent.png")), [])
        self.assertEqual(self.colors.from_pixels(self._img([])), [])

    def test_color_field_is_matched_and_name_colors_still_count(self):
        green = {"name": "Nike Pegasus 41", "tags": "", "category": "shoes", "price": 100, "color": "green white"}
        named = {"name": "Nike Dunk Low Olive", "tags": "", "category": "shoes", "price": 100, "color": ""}
        other = {"name": "Nike Pegasus 41", "tags": "", "category": "shoes", "price": 100, "color": "black"}
        it = parse("green shoes")
        self.assertTrue(matches(green, it) and matches(named, it) and not matches(other, it))

    def test_tag_colors_ignored_once_the_image_was_read(self):
        cardigan = {"name": "Merino Cardigan", "tags": "black blue pink purple", "category": "top", "price": 40, "color": "grey"}
        unread = {**cardigan, "color": ""}
        self.assertFalse(matches(cardigan, parse("pink")))          # the picture is grey, whatever else it comes in
        self.assertTrue(matches(cardigan, parse("grey")))
        self.assertTrue(matches(unread, parse("pink")))             # no image color yet: tags still count

    def test_search_uses_the_color_column(self):
        with catalog._lock:
            row = catalog._db().execute("SELECT url, name FROM products WHERE category='shoes' AND name NOT LIKE '%green%' LIMIT 1").fetchone()
        catalog.set_color(row["url"], ["green", "white"], "vision")
        items = finder.results("green shoes")
        self.assertIn(row["name"], [i["name"] for i in items])
        self.assertTrue(all("green" in intent.item_colors(i) for i in items))
        with self.assertRaises(finder.NoMatch):
            finder.results("purple socks under 3 dollars")

    def test_set_color_invalidates_nothing_stale(self):
        # results cached before colors existed use another key version
        self.assertTrue(catalog.KEY_VERSION >= "v3")

    def test_pixel_pass_fills_missing_colors_from_real_cutouts(self):
        import shutil
        (config.DATA_DIR / "cutouts").mkdir(exist_ok=True)
        with catalog._lock:
            rows = catalog._db().execute("SELECT url, cutout_p FROM products WHERE stock='in_stock' LIMIT 6").fetchall()
        done = 0
        for r in rows:
            src = HERE / "dataset" / "cutouts" / Path(r["cutout_p"]).name
            if src.exists():
                shutil.copy2(src, config.DATA_DIR / "cutouts" / src.name)
                done += 1
        self.assertGreater(done, 0)
        n = self.colors.pixel_pass()
        self.assertGreaterEqual(n, done)
        with catalog._lock:
            got = catalog._db().execute("SELECT color, color_src FROM products WHERE color IS NOT NULL").fetchall()
        self.assertTrue(got and all(g["color_src"] == "pixel" and g["color"] for g in got))

    def test_old_database_gets_color_columns(self):
        import sqlite3
        old = Path(tempfile.mkdtemp()) / "old.sqlite"
        db = sqlite3.connect(old)
        db.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, url TEXT UNIQUE NOT NULL, name TEXT NOT NULL, brand TEXT NOT NULL, "
                   "price REAL NOT NULL, category TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '', cutout_p TEXT, cutout_m TEXT, "
                   "stock TEXT NOT NULL DEFAULT 'in_stock', source TEXT, last_checked REAL, added_at REAL)")
        db.execute("INSERT INTO products (url,name,brand,price,category) VALUES ('u','n','b',1,'top')")
        db.commit()
        db.close()
        saved = catalog._conn, catalog.DB_PATH
        try:
            catalog._conn, catalog.DB_PATH = None, old
            cols = {r[1] for r in catalog._db().execute("PRAGMA table_info(products)")}
            self.assertTrue({"color", "color_src"} <= cols)
            self.assertEqual(catalog._db().execute("SELECT COUNT(*) FROM products").fetchone()[0], 1)
        finally:
            catalog._conn.close()
            catalog._conn, catalog.DB_PATH = saved

    def test_ranker_line_carries_color(self):
        line = ranker._line(3, {"brand": "Nike", "name": "Pegasus", "price": 120, "category": "shoes", "color": "green"})
        self.assertEqual(line, "3 | Nike | Pegasus | $120 | shoes | green")
        self.assertTrue(ranker._line(1, {"brand": "a", "name": "b", "price": 0, "category": "top"}).endswith("| -"))

    def test_gemini_vision_answer_is_limited_to_known_colors(self):
        import gemini
        post, text = gemini._post, gemini._text
        gemini._post = lambda *a, **k: {}
        gemini._text = lambda _r: '{"colors": ["Gray", "sparkly", "white", "grey"]}'
        try:
            self.assertEqual(gemini.product_color(b"x", self.colors.CANON), ["grey", "white"])
        finally:
            gemini._post, gemini._text = post, text

    def _vision_env(self, from_vision):
        import llm
        c = self.colors
        self._saved = (c.from_vision, c._file, c.VISION_PAUSE, llm.provider)
        c.from_vision, c._file, c.VISION_PAUSE, llm.provider = from_vision, (lambda cutout: Path("x.png") if cutout else None), 0, (lambda: "gemini")

    def _vision_restore(self):
        import llm
        c = self.colors
        c.from_vision, c._file, c.VISION_PAUSE, llm.provider = self._saved

    def test_vision_pass_overwrites_pixel_guess_and_resumes(self):
        with catalog._lock:
            catalog._db().execute("UPDATE products SET color='black', color_src='pixel'")
            catalog._db().commit()
        self._vision_env(lambda f: ["green"])
        try:
            done, why = self.colors.vision_pass()
            self.assertEqual(why, "complete")
            with catalog._lock:
                srcs = {r[0] for r in catalog._db().execute("SELECT color_src FROM products WHERE stock='in_stock' AND (cutout_p IS NOT NULL OR cutout_m IS NOT NULL)")}
            self.assertEqual(srcs, {"vision"})
            self.assertEqual(self.colors.vision_pass(), (0, "complete"), "already verified products are not asked again")
        finally:
            self._vision_restore()

    def test_vision_pass_stops_on_quota_and_keeps_progress(self):
        import gemini
        n = {"calls": 0}

        def flaky(f):
            n["calls"] += 1
            if n["calls"] > 3:
                raise gemini.QuotaError("quota")
            return ["blue"]
        with catalog._lock:
            catalog._db().execute("UPDATE products SET color=NULL, color_src=NULL")
            catalog._db().commit()
        self._vision_env(flaky)
        try:
            self.assertEqual(self.colors.vision_pass(), (3, "quota"))
            with catalog._lock:
                self.assertEqual(catalog._db().execute("SELECT COUNT(*) FROM products WHERE color_src='vision'").fetchone()[0], 3)
        finally:
            self._vision_restore()

    def test_no_key_means_no_vision_calls(self):
        import llm
        self.assertEqual(self.colors.vision_pass(), (0, "no-key"))

    def test_dataset_load_and_export_share_colors(self):
        import dataset
        from PIL import Image
        tmp = Path(tempfile.mkdtemp())
        (tmp / "cutouts").mkdir()
        Image.new("RGBA", (20, 20), (20, 120, 40, 255)).save(tmp / "cutouts" / "aaaaaaaaaaaaaaaa.png")
        saved = (dataset.DIR, dataset.ITEMS, dataset.REMOVED, dataset.IMG, dataset.LOCAL_IMG)
        dataset.DIR, dataset.ITEMS, dataset.REMOVED, dataset.IMG = tmp, tmp / "catalog.json", tmp / "removed.json", tmp / "cutouts"
        dataset.LOCAL_IMG = config.DATA_DIR / "cutouts"
        url = "https://example.com/p/1"
        row = {"url": url, "name": "Test Fleece", "brand": "Nike", "price": 50.0, "category": "top", "tags": "fleece",
               "cutout_p": "aaaaaaaaaaaaaaaa.png", "cutout_m": None, "stock": "in_stock", "source": "t",
               "last_checked": 100.0, "added_at": 1.0, "color": "green", "color_src": "vision"}
        try:
            dataset._write_items({url: row})
            dataset.REMOVED.write_text("[]")
            with catalog._lock:
                catalog._db().execute("DELETE FROM products")
                catalog._db().commit()
            dataset.load(quiet=True)                                   # new row arrives with its color
            r = catalog._db().execute("SELECT color, color_src FROM products WHERE url=?", (url,)).fetchone()
            self.assertEqual((r["color"], r["color_src"]), ("green", "vision"))
            catalog.set_color(url, ["black"], "pixel")                 # a local pixel guess ...
            dataset.load(quiet=True)                                   # ... is replaced by the shared AI color
            r = catalog._db().execute("SELECT color, color_src FROM products WHERE url=?", (url,)).fetchone()
            self.assertEqual((r["color"], r["color_src"]), ("green", "vision"))
            # export: a weaker local color never overwrites the shared AI color
            catalog.set_color(url, ["red"], "pixel")
            dataset.export(quiet=True)
            self.assertEqual(dataset._read_items()[url]["color"], "green")
            # export: a color computed locally reaches a dataset row that has none
            dataset._write_items({url: {**row, "color": None, "color_src": None}})
            catalog.set_color(url, ["blue"], "vision")
            dataset.export(quiet=True)
            self.assertEqual((dataset._read_items()[url]["color"], dataset._read_items()[url]["color_src"]), ("blue", "vision"))
        finally:
            dataset.DIR, dataset.ITEMS, dataset.REMOVED, dataset.IMG, dataset.LOCAL_IMG = saved
            load_dataset()

    def test_dataset_shares_colors(self):
        import dataset
        self.assertIn("color", dataset.FIELDS)
        self.assertIn("color_src", dataset.FIELDS)


if __name__ == "__main__":
    unittest.main(verbosity=1)
