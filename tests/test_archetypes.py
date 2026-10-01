import unittest
from pathlib import Path

from draftguide.archetypes import load_set


ROOT = Path(__file__).resolve().parents[1]


class ArchetypeGuideTests(unittest.TestCase):
    def test_loads_seeded_guide_for_set(self):
        guide = load_set(ROOT / "guides" / "archetypes", "fra")
        self.assertEqual(guide["set"]["name"], "Reality Fracture")
        self.assertEqual(len(guide["archetypes"]), 10)
        self.assertIn(
            "https://mtga.untapped.gg/limited/draft/reality-fracture/tier-list",
            [source["url"] for source in guide["sources"]],
        )
        by_colors = {tuple(item["colors"]): item for item in guide["archetypes"]}
        self.assertEqual(by_colors[("W", "U")]["tier"], "A")
        self.assertEqual(by_colors[("G", "W")]["tier"], "C")
        self.assertEqual(by_colors[("W", "U")]["sixPlusWinRate"], 10.5)

    def test_unknown_or_invalid_set_has_no_guide(self):
        directory = ROOT / "guides" / "archetypes"
        self.assertIsNone(load_set(directory, "FDN"))
        self.assertIsNone(load_set(directory, "../FRA"))

    def test_loads_wilds_of_eldraine_guide(self):
        guide = load_set(ROOT / "guides" / "archetypes", "WOE")
        self.assertEqual(guide["set"]["name"], "Wilds of Eldraine")
        self.assertEqual(len(guide["archetypes"]), 10)
        by_colors = {tuple(item["colors"]): item for item in guide["archetypes"]}
        self.assertEqual(by_colors[("B", "R")]["tier"], "A")
        self.assertEqual(by_colors[("B", "R")]["sixPlusWinRate"], 13.6)
        self.assertEqual(by_colors[("G", "U")]["tier"], "D")


if __name__ == "__main__":
    unittest.main()
