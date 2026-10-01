import json, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
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

    def test_parse_cardgamebase(self):
        html = """
        <table class="tablepress tierlist"><tbody>
          <tr><th>White</th><th>Grade</th></tr>
          <tr><td><a>Minecart Daredevil // Ride the Rails</a></td><td>C+</td></tr>
          <tr><td><a>Kindred Judgment</a></td><td>A-</td></tr>
        </tbody></table>
        <table class="unrelated"><tr><td>Wrong Card</td><td>A+</td></tr></table>
        """
        data = ratings.parse_cardgamebase(html, "WOE")
        by = {card["name"]: card for card in data["cards"]}
        self.assertEqual(by["Minecart Daredevil // Ride the Rails"]["grade"], "C+")
        self.assertEqual(by["Minecart Daredevil // Ride the Rails"]["score"], 78)
        self.assertEqual(by["Kindred Judgment"]["rank"], 2)
        self.assertEqual(data["source"], "Card Game Base")
        self.assertEqual(len(data["cards"]), 2)
        guide = Guide(data, {8: "Minecart Daredevil"}, Path(tempfile.mkdtemp()) / "Player.log")
        match = guide.lookup(8)
        self.assertEqual(match["grade"], "C+")
        self.assertFalse(match["unrated"])
        self.assertIn("scryfall.com/cards/named?format=image", match["image"])

    def test_parse_cardgamebase_requires_tier_table(self):
        with self.assertRaisesRegex(RuntimeError, "Could not find card grades"):
            ratings.parse_cardgamebase("<table><tr><td>Unrelated</td><td>A</td></tr></table>", "FRA")

    def test_parse_draftsim_and_mtgazone_grades(self):
        draftsim = ratings.parse_draftsim_woe(
            "<h3>Kindred Judgment</h3><p><strong>Rating: 8/10</strong></p>"
            "<h3>The Creature Lands</h3><p><strong>Rating: 7/10</strong></p>"
        )
        mtgazone = ratings.parse_mtgazone_woe_page(
            "<h2><span>Kindred Judgment</span></h2><h3>Rating: 4.0/5</h3>",
            "https://example.com/woe-review",
        )
        self.assertEqual(draftsim["cards"][0]["ratings"][0]["score"], 80)
        self.assertEqual(draftsim["cards"][0]["ratings"][0]["scale"], "0 to 10")
        self.assertEqual(mtgazone["cards"][0]["ratings"][0]["score"], 80)
        self.assertEqual(mtgazone["cards"][0]["ratings"][0]["sourceUrl"], "https://example.com/woe-review")

    def test_combine_woe_sources_keeps_original_scales_and_averages_expert_grades(self):
        cardgamebase = ratings.parse_cardgamebase(
            '<table class="tierlist"><tr><td>Kindred Judgment</td><td>A-</td></tr></table>', "WOE",
        )
        draftsim = ratings.parse_draftsim_woe(
            "<h3>Kindred Judgment</h3><p><strong>Rating: 8/10</strong></p>"
        )
        mtgazone = ratings.parse_mtgazone_woe_page(
            "<h2>Kindred Judgment</h2><h3>Rating: 4.0/5</h3>",
            "https://example.com/woe-review",
        )
        lands = {
            "attribution": "https://www.17lands.com/card_ratings?expansion=WOE&format=PremierDraft",
            "cards": [{
                "name": "Kindred Judgment",
                "image": "https://cards.scryfall.io/normal/example.jpg",
                "ratings": [],
            }],
        }
        data = ratings.combine_woe_sources([cardgamebase, draftsim, mtgazone, lands])
        self.assertEqual(len(data["cards"]), 1)
        card = data["cards"][0]
        self.assertEqual(card["score"], 85)
        self.assertEqual(card["image"], "https://cards.scryfall.io/normal/example.jpg")
        self.assertEqual([rating["source"] for rating in card["ratings"]],
                         ["Card Game Base", "Draftsim", "MTG Arena Zone"])
        self.assertEqual([rating["grade"] for rating in card["ratings"]], ["A-", "8", "4.0"])
        self.assertEqual(data["sourceCoverage"], {
            "Card Game Base": 1, "Draftsim": 1, "MTG Arena Zone": 1, "17Lands": 0,
        })
        self.assertEqual(data["source"], "Multi-source ratings")

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

    def test_store_uses_woe_multisource_cache(self):
        d = Path(tempfile.mkdtemp())
        (d / "multi-source-WOE-QuickDraft.json").write_text(json.dumps({
            "cards": [], "set": {"code": "WOE"}, "source": "Multi-source ratings",
        }))
        self.assertEqual(ratings.Store(d).get("WOE", "QuickDraft")["source"], "Multi-source ratings")

    def test_woe_store_uses_cached_sources_when_other_providers_are_unavailable(self):
        d = Path(tempfile.mkdtemp())
        (d / "cardgamebase-WOE.json").write_text(json.dumps({
            "cards": [{"name": "Sample", "score": 90, "ratings": [{
                "source": "Card Game Base", "grade": "A", "score": 97,
            }]}],
            "set": {"code": "WOE"},
            "source": "Card Game Base",
        }))
        with (
            patch("draftguide.ratings.fetch_draftsim_woe", side_effect=OSError("offline")),
            patch("draftguide.ratings.fetch_mtgazone_woe", side_effect=OSError("offline")),
            patch("draftguide.ratings.fetch_17lands", side_effect=OSError("offline")),
        ):
            data = ratings.Store(d).get("WOE", "QuickDraft")
        self.assertEqual(data["cards"][0]["name"], "Sample")
        self.assertEqual(data["sourceCoverage"]["Card Game Base"], 1)

    def test_store_uses_fra_multisource_cache(self):
        d = Path(tempfile.mkdtemp())
        (d / "multi-source-FRA.json").write_text(json.dumps({
            "cards": [], "set": {"code": "FRA"}, "source": "Multi-source ratings"
        }))
        self.assertEqual(ratings.Store(d).get("FRA")["source"], "Multi-source ratings")


if __name__ == "__main__":
    unittest.main()
