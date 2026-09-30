import json, tempfile, time, unittest
from pathlib import Path
from draftguide import ratings
from draftguide.server import Guide


def rows():
    return [
        {"name": "Alpha", "mtga_id": 1, "color": "W", "rarity": "common", "url": "http://x/a.jpg", "types": ["Creature"],
         "avg_pick": 3.2, "ever_drawn_game_count": 1000, "ever_drawn_win_rate": 0.60, "drawn_improvement_win_rate": 0.05},
        {"name": "Beta", "mtga_id": 2, "color": "U", "rarity": "rare", "url": "http://x/b.jpg", "types": ["Instant"],
         "avg_pick": 9.0, "ever_drawn_game_count": 1000, "ever_drawn_win_rate": 0.50, "drawn_improvement_win_rate": None},
        {"name": "Gamma", "mtga_id": 3, "color": "", "rarity": "common", "url": "http://x/c.jpg", "types": ["Artifact"],
         "avg_pick": None, "ever_drawn_game_count": 5, "ever_drawn_win_rate": 0.9, "drawn_improvement_win_rate": None},
    ]


NAMES = {1: "Alpha", 2: "Beta", 3: "Gamma", 4: "Delta"}


class MultiSetTests(unittest.TestCase):
    def test_parse_event(self):
        self.assertEqual(ratings.parse_event("PremierDraft_FDN_20241111"), ("PremierDraft", "FDN"))
        self.assertEqual(ratings.parse_event("QuickDraft_dsk_20240101"), ("QuickDraft", "DSK"))
        self.assertEqual(ratings.parse_event("Traditional_Draft_X_1")[0], "TradDraft") if ratings.parse_event("Traditional_Draft_X_1") else None
        self.assertIsNone(ratings.parse_event(None))
        self.assertIsNone(ratings.parse_event("Cube"))

    def test_slim_17lands(self):
        data = ratings.slim_17lands(rows(), "FDN", "PremierDraft")
        by = {c["name"]: c for c in data["cards"]}
        self.assertEqual((by["Alpha"]["score"], by["Alpha"]["rank"], by["Alpha"]["rankOf"]), (100, 1, 2))
        self.assertEqual(by["Beta"]["score"], 0)
        self.assertIsNone(by["Gamma"]["score"])  # too few games
        self.assertEqual(by["Alpha"]["image"], "http://x/a.jpg")
        self.assertIn("GIH WR 60.0%", by["Alpha"]["ratings"][0]["comment"])

    def _guide(self, calls, fail=False):
        def provider(code, fmt):
            calls.append((code, fmt))
            if fail:
                raise OSError("down")
            return ratings.slim_17lands(rows(), code, fmt)
        d = tempfile.mkdtemp()
        log = Path(d) / "Player.log"
        log.write_text(json.dumps({"result": {"EventName": "QuickDraft_FDN_1", "PackNumber": 0, "PickNumber": 0,
                                              "DraftPack": ["1", "2", "4"], "PickedCards": []}}) + "\n")
        return Guide(None, NAMES, log, provider=provider, details={1: ("o1oW", "Creature")})

    def test_pack_uses_event_set_and_caches(self):
        calls = []
        g = self._guide(calls)
        snap = g.snapshot()
        g.snapshot()
        self.assertEqual(calls, [("FDN", "QuickDraft")])
        self.assertEqual(snap["set"], "FDN")
        names = [c["name"] for c in snap["cards"]]
        self.assertEqual(names, ["Alpha", "Beta", "Delta"])
        self.assertTrue(snap["cards"][2]["unrated"])
        self.assertEqual(snap["cards"][0]["manaArena"], "o1oW")
        self.assertEqual(snap["status"]["source"], "17Lands")

    def test_failure_is_negative_cached(self):
        calls = []
        g = self._guide(calls, fail=True)
        snap = g.snapshot()
        g.snapshot()
        self.assertEqual(len(calls), 1)
        self.assertTrue(all(c["unrated"] for c in snap["cards"]))
        self.assertFalse(snap["status"]["ratingsAvailable"])

    def test_detect_game_set(self):
        g = self._guide([])
        g.expansions = {1: "FDN", 2: "FDN", 3: "DSK", 9: "FDN"}
        g.lands = {9}
        g.state.game.deck = [1, 2, 3, 9, 9, 9, 9]
        self.assertEqual(g.detect_game_set(), "FDN")
        g.state.game.deck = []
        self.assertIsNone(g.detect_game_set())

    def test_store_uses_cache(self):
        d = Path(tempfile.mkdtemp())
        (d / "17l-FDN-PremierDraft.json").write_text(json.dumps({"cards": [], "set": {"code": "FDN"}}))
        self.assertEqual(ratings.Store(d).get("FDN")["set"]["code"], "FDN")


if __name__ == "__main__":
    unittest.main()
