import unittest

from draftguide.sealed import SCORE_THRESHOLDS, analyze_archetypes


class SealedAnalysisTests(unittest.TestCase):
    def test_counts_bombs_playables_and_color_eligibility(self):
        cards = [
            {"name": "White bomb", "colors": ["W"], "score": 95, "count": 1},
            {"name": "Blue strong", "colors": ["U"], "score": 82, "count": 4},
            {"name": "Colorless playable", "colors": [], "score": 65, "count": 15},
            {"name": "Off-color bomb", "colors": ["R"], "score": 100, "count": 1},
            {"name": "Basic land", "colors": ["W"], "score": 100, "count": 4, "isLand": True},
        ]
        guide = {
            "archetypes": [
                {"colors": ["W", "U"], "name": "Azorius", "tier": "A"},
                {"colors": ["B", "R"], "name": "Rakdos", "tier": "D"},
            ],
        }

        result = analyze_archetypes(cards, guide)
        azorius = result[0]
        self.assertEqual(azorius["name"], "Azorius")
        self.assertEqual(azorius["bombs"], 1)
        self.assertEqual(azorius["strong"], 5)
        self.assertEqual(azorius["playables"], 20)
        self.assertEqual(azorius["eligibleCards"], 20)
        self.assertEqual(azorius["potential"], "Promising")
        self.assertNotIn("highlights", azorius)
        rakdos = next(item for item in result if item["name"] == "Rakdos")
        self.assertEqual(rakdos["bombs"], 1)
        self.assertEqual(rakdos["playables"], 16)

    def test_empty_guide_returns_no_archetype_summary(self):
        self.assertEqual(analyze_archetypes([], None), [])
        self.assertEqual(analyze_archetypes([], {"archetypes": []}), [])

    def test_archetypes_sort_by_fit_then_playable_support(self):
        cards = [
            {"name": "Colorless playable", "colors": [], "score": 65, "count": 10},
            {"name": "Azorius support", "colors": ["W"], "score": 60, "count": 5},
            {"name": "Rakdos bomb", "colors": ["B"], "score": 100, "count": 1},
        ]
        guide = {
            "archetypes": [
                {"colors": ["B", "R"], "name": "Rakdos", "tier": "A"},
                {"colors": ["W", "U"], "name": "Azorius", "tier": "D"},
            ],
        }

        result = analyze_archetypes(cards, guide)
        self.assertEqual([item["name"] for item in result], ["Azorius", "Rakdos"])
        self.assertEqual(result[0]["eligibleCards"], 15)
        self.assertEqual(result[0]["playables"], 15)

    def test_live_grade_thresholds_and_excellent_fit(self):
        self.assertEqual(SCORE_THRESHOLDS, {"bomb": 85, "strong": 70, "playable": 60})
        cards = [
            {"name": "Bomb", "colors": ["W"], "score": 90, "count": 1},
            {"name": "Strong", "colors": ["U"], "score": 75, "count": 5},
            {"name": "Playable", "colors": [], "score": 65, "count": 12},
        ]
        guide = {"archetypes": [{"colors": ["W", "U"], "name": "Azorius", "tier": "A"}]}

        result = analyze_archetypes(cards, guide)[0]
        self.assertEqual((result["bombs"], result["strong"], result["playables"]), (1, 6, 18))
        self.assertEqual(result["potential"], "Excellent fit")

    def test_playable_type_counts_exclude_unplayable_eligible_cards(self):
        cards = [
            {"name": "Creature", "colors": ["W"], "score": 75, "count": 2, "typeLine": "Creature — Human"},
            {"name": "Removal", "colors": ["U"], "score": 65, "count": 1, "typeLine": "Instant"},
            {"name": "Weak creature", "colors": ["W"], "score": 55, "count": 4, "typeLine": "Creature — Beast"},
        ]
        guide = {"archetypes": [{"colors": ["W", "U"], "name": "Azorius"}]}

        result = analyze_archetypes(cards, guide)[0]
        self.assertEqual(result["eligibleCards"], 7)
        self.assertEqual(result["playables"], 3)
        self.assertEqual(result["playableCreatures"], 2)
        self.assertEqual(result["playableNoncreatures"], 1)


if __name__ == "__main__":
    unittest.main()
