import unittest

from draftguide.sealed import analyze_archetypes


class SealedAnalysisTests(unittest.TestCase):
    def test_counts_bombs_playables_and_color_eligibility(self):
        cards = [
            {"name": "White bomb", "colors": ["W"], "score": 95, "count": 1},
            {"name": "Blue strong", "colors": ["U"], "score": 82, "count": 4},
            {"name": "Colorless playable", "colors": [], "score": 70, "count": 15},
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


if __name__ == "__main__":
    unittest.main()
