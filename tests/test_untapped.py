import unittest
from draftguide import archetypes, ratings, untapped


class UntappedTests(unittest.TestCase):
    def test_slugs(self):
        self.assertEqual(untapped.slugify("Reality Fracture"), "reality-fracture")
        self.assertIn("reality-fracture", untapped.slug_candidates("Magic: Reality Fracture") + ["reality-fracture"])

    def test_apply_untapped_keeps_score(self):
        data = {"cards": [{"name": "Alpha", "score": 50, "ratings": []}, {"name": "Other", "score": 10, "ratings": []}]}
        order = {"attribution": "http://u", "cards": [{"name": "Alpha", "score": 99,
                 "pickOrder": {"avgPick": 1.5, "rank": 1, "rankOf": 10, "score": 100},
                 "topPicks": ["#1 pick in W"],
                 "ratings": [{"source": "Untapped.gg", "grade": "ATA 1.5"}]}]}
        ratings.apply_untapped(data, order)
        alpha = data["cards"][0]
        self.assertEqual(alpha["score"], 50)
        self.assertEqual(alpha["pickOrder"]["rank"], 1)
        self.assertEqual(alpha["topPicks"], ["#1 pick in W"])
        self.assertEqual(data["cards"][1]["ratings"], [])

    def test_merge_tiers(self):
        live = [{"colors": ["W", "U"], "name": "Azorius", "tier": "A", "sixPlusWinRate": 0.1, "matches": 5, "tierSource": "http://t"},
                {"colors": ["B", "R"], "name": "Rakdos", "tier": "C", "sixPlusWinRate": 0.0, "matches": 5, "tierSource": "http://t"}]
        guide = {"set": {"code": "X", "name": "X"}, "sources": [], "archetypes": [{"colors": ["U", "W"], "name": "WU", "focus": "f", "tier": "D"}]}
        merged = archetypes.merge_tiers(guide, live, "X")
        self.assertEqual(merged["archetypes"][0]["tier"], "A")
        self.assertEqual(len(merged["archetypes"]), 2)
        self.assertEqual(guide["archetypes"][0]["tier"], "D")
        self.assertEqual(archetypes.merge_tiers(None, live, "X", "Xset")["set"]["name"], "Xset")
        self.assertIsNone(archetypes.merge_tiers(None, None, "X"))
