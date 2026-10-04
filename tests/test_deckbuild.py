import unittest

from draftguide.deckbuild import analyze_pool


class DraftDeckBuildTests(unittest.TestCase):
    def test_suggests_23_cards_for_best_supported_pair_and_excludes_lands(self):
        cards = [
            {
                "arenaId": index,
                "name": f"Azorius card {index}",
                "colors": ["W"] if index % 2 else ["U"],
                "score": 75 if index == 23 else 80 + index % 10,
                "manaArena": "o2oW" if index % 2 else "o1oU",
                "typeLine": "Creature — Human" if index < 14 else "Instant",
            }
            for index in range(24)
        ]
        cards.extend([
            {"name": "Basic land", "colors": ["W"], "score": 100, "isLand": True},
            {"name": "Off-color bomb", "colors": ["R"], "score": 100},
        ])
        guide = {"archetypes": [{"colors": ["W", "U"], "name": "Azorius", "tier": "A"}]}

        result = analyze_pool(cards, guide)

        build = result["builds"][0]
        self.assertEqual(build["name"], "Azorius")
        self.assertEqual(len(build["cards"]), 23)
        self.assertNotIn("Basic land", [card["name"] for card in build["cards"]])
        self.assertEqual(build["eligibleCount"], 24)
        self.assertEqual(build["cuts"][0]["name"], "Azorius card 23")
        self.assertEqual(build["cuts"][0]["cutReason"], "Below the top 23")
        self.assertEqual(build["cuts"][1]["name"], "Off-color bomb")
        self.assertEqual(build["cuts"][1]["cutReason"], "Outside these colors")

    def test_balance_checks_cover_creatures_curve_and_colored_mana(self):
        cards = [
            {
                "name": f"Card {index}",
                "colors": ["W"] if index % 2 else ["U"],
                "score": 90 - index,
                "manaArena": "o1oW" if index < 6 else "o4oU",
                "typeLine": "Creature — Human" if index < 14 else "Sorcery",
            }
            for index in range(23)
        ]

        build = analyze_pool(cards)["builds"][0]

        checks = {check["label"]: check for check in build["balance"]["checks"]}
        self.assertEqual(checks["Spell count"]["value"], "23/23")
        self.assertEqual(checks["Creatures"]["value"], "14")
        self.assertEqual(checks["Creatures"]["status"], "good")
        self.assertEqual(checks["Early plays"]["value"], "6")
        self.assertEqual(checks["Top end"]["value"], "17")
        self.assertEqual(checks["Top end"]["status"], "warning")
        self.assertGreater(build["balance"]["pips"]["W"], 0)
        self.assertGreater(build["balance"]["pips"]["U"], 0)

    def test_short_pool_marks_spell_count_and_creature_count_as_warnings(self):
        result = analyze_pool([
            {"name": "A", "colors": ["B"], "score": 70, "manaArena": "oX", "typeLine": "Instant"},
        ])
        checks = {check["label"]: check for check in result["builds"][0]["balance"]["checks"]}
        self.assertEqual(checks["Spell count"]["status"], "warning")
        self.assertEqual(checks["Creatures"]["status"], "warning")
        self.assertEqual(result["builds"][0]["balance"]["curve"], [{"manaValue": 0, "count": 1}])


if __name__ == "__main__":
    unittest.main()
