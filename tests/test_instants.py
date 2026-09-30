import unittest
from draftguide import instants as I

S = frozenset


class InstantTests(unittest.TestCase):
    def test_cost_payment(self):
        self.assertTrue(I.can_pay("o2oU", [S("U")] * 3))
        self.assertFalse(I.can_pay("o2oUoU", [S("U"), S("W"), S("W")]))
        self.assertTrue(I.can_pay("o1o(W/B)", [S("B"), S("R")]))
        self.assertFalse(I.can_pay("o3", [S("U")] * 2))
        self.assertTrue(I.can_pay("oXoU", [S("U")]))

    def test_colour_not_wasted_on_generic(self):
        self.assertTrue(I.can_pay("o1oU", [S("W"), S("U")]))

    def test_guide_uses_untapped_lands_and_colours(self):
        info = {
            1: {"name": "Zap", "mana": "oR", "set": "FRA", "kind": "Instant", "colors": "R"},
            2: {"name": "Dunk", "mana": "o2oU", "set": "FRA", "kind": "Instant", "colors": "U"},
            3: {"name": "Old", "mana": "oU", "set": "XXX", "kind": "Instant", "colors": "U"},
            4: {"name": "Seen", "mana": "o3oU", "set": "XXX", "kind": "Flash", "colors": "U"},
        }
        lands = [(10, ["SubType_Island"], False)] * 2 + [(11, ["SubType_Mountain"], True)]
        view = I.guide(lands, [4], info, {})
        self.assertEqual(view["untapped"], 2)
        self.assertEqual(view["colours"], "UR")
        self.assertEqual([c["name"] for c in view["possible"]], [])
        self.assertFalse(view["shown"][0]["castable"])
        lands.append((10, ["SubType_Island"], False))
        view = I.guide(lands, [], info, {})
        self.assertEqual([c["name"] for c in view["possible"]], ["Dunk"])
