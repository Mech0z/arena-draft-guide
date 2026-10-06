import json
import os
import tempfile
import unittest
from pathlib import Path

from draftguide import logparse, ratings
from draftguide.server import Guide

BOT_ESCAPED = (
    '{"CurrentModule":"BotDraft","Payload":"{\\"Result\\":\\"Success\\",\\"EventName\\":\\"PremierDraft_FRA_20260929\\",'
    '\\"DraftStatus\\":\\"PickNext\\",\\"PackNumber\\":1,\\"PickNumber\\":4,\\"NumCardsInPack\\":3,'
    '\\"DraftPack\\":[\\"101\\",\\"102\\",\\"999\\"],\\"PickedCards\\":[\\"7\\",\\"8\\"]}"}'
)
BOT_PLAIN = '{"result":{"EventName":"QuickDraft_FRA","PackNumber":0,"PickNumber":0,"DraftPack":["101"],"PickedCards":[]}}'
QUICK = 'Draft.Notify {"draftId":"x","SelfPick":3,"SelfPack":2,"PackCards":"101,102"}'

RAW = {
    "set": {"code": "FRA"},
    "generatedAt": "t",
    "sourceOrder": ["a"],
    "sources": {"a": {"short": "Src A", "url": "https://example.com/review", "scale": "A to F"}},
    "creatorNotes": {"sources": {"jd": {"name": "Jim"}}, "notes": [{"sourceKey": "jd", "cardId": "id1", "summary": "Good."}]},
    "cards": [
        {"id": "id1", "name": "Alpha", "collectorNumber": "1", "ratings": {"a": {"native": "A", "normalized": 95, "comment": "Great."}}, "consensus": {"score": 95, "overallRank": 1, "overallOf": 2}},
        {"id": "id2", "name": "Beta // Gamma", "collectorNumber": "2", "ratings": {}, "consensus": {"score": 40, "overallRank": 2, "overallOf": 2}},
    ],
}


class ParseTests(unittest.TestCase):
    def test_bot_pack_escaped(self):
        obs = logparse.parse_line(BOT_ESCAPED)
        self.assertEqual(obs.card_ids, (101, 102, 999))
        self.assertEqual((obs.pack_number, obs.pick_number), (1, 4))
        self.assertEqual(obs.event_name, "PremierDraft_FRA_20260929")
        self.assertEqual(obs.picked_ids, (7, 8))

    def test_bot_pack_plain(self):
        self.assertEqual(logparse.parse_line(BOT_PLAIN).card_ids, (101,))

    def test_quick_draft_numbers_are_zero_based(self):
        obs = logparse.parse_line(QUICK)
        self.assertEqual((obs.card_ids, obs.pack_number, obs.pick_number), ((101, 102), 1, 2))

    def test_unrelated_lines_ignored(self):
        self.assertIsNone(logparse.parse_line('{"CardPool":[1,2,3]}'))

    def test_empty_pack_clears(self):
        state = logparse.DraftLogState()
        logparse.apply_lines(state, [BOT_PLAIN, '{"DraftPack":[],"PackNumber":0,"PickNumber":1}'])
        self.assertIsNone(state.pack)
        self.assertEqual(state.last_event_name, "QuickDraft_FRA")

    def test_draft_completion_requires_final_clear_after_three_distinct_packs(self):
        state = logparse.DraftLogState()
        event = "PremierDraft_FRA_20260929"
        for pack in range(3):
            pack_line = json.dumps({
                "DraftPack": [100 + pack],
                "PackNumber": pack,
                "PickNumber": 0,
                "EventName": event,
            })
            empty_line = json.dumps({
                "DraftPack": [],
                "PackNumber": pack,
                "PickNumber": 1,
                "EventName": event,
            })
            logparse.apply_lines(state, [pack_line])
            logparse.apply_lines(state, [empty_line])
            self.assertEqual(state.draft_completed, pack == 2)

        logparse.apply_lines(state, [json.dumps({
            "DraftPack": [200],
            "PackNumber": 0,
            "PickNumber": 0,
            "EventName": event,
        })])
        self.assertFalse(state.draft_completed)

    def test_duplicates_do_not_bump_version(self):
        state = logparse.DraftLogState()
        saved = []
        logparse.apply_lines(state, [BOT_PLAIN, BOT_PLAIN], on_pack=saved.append)
        self.assertEqual(state.version, 1)
        self.assertEqual(len(saved), 1)

    def test_poll_incremental_partial_line_and_rotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "Player.log"
            state = logparse.DraftLogState()
            log.write_text("noise\n" + BOT_PLAIN, encoding="utf-8")  # last line incomplete
            self.assertFalse(logparse.poll(state, log))
            with log.open("a", encoding="utf-8") as f:
                f.write("\n")
            self.assertTrue(logparse.poll(state, log))
            self.assertEqual(state.pack.card_ids, (101,))
            log.write_text("x\n", encoding="utf-8")  # Arena restarted and rewrote the log
            logparse.poll(state, log)
            self.assertIsNone(state.pack)
            self.assertIsNone(state.last_event_name)

    def test_nested_sealed_pool_preserves_duplicates(self):
        event = {
            "InternalEventName": "Sealed_FRA_20260929",
            "CardPool": [{"GrpId": index} for index in range(1, 46)],
        }
        line = json.dumps({"payload": json.dumps({"Course": event})})
        observation = logparse.parse_sealed_pool_line(line)
        self.assertEqual(observation.event_name, "Sealed_FRA_20260929")
        self.assertEqual(observation.card_ids, tuple(range(1, 46)))

    def test_sealed_pool_updates_state_and_is_cleared_by_draft_pack(self):
        state = logparse.DraftLogState()
        sealed_line = json.dumps({
            "InternalEventName": "TradSealed_FRA_20260929",
            "CardPool": [101] * 40,
        })
        self.assertTrue(logparse.apply_lines(state, [sealed_line]))
        self.assertEqual(len(state.sealed_pool.card_ids), 40)
        self.assertIsNone(state.pack)
        logparse.apply_lines(state, [BOT_PLAIN])
        self.assertIsNone(state.sealed_pool)
        self.assertIsNotNone(state.pack)


class GuideTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "Player.log"
        self.log.write_text(BOT_ESCAPED + "\n", encoding="utf-8")
        self.guide = Guide(
            ratings.slim(RAW),
            {101: "Beta // Gamma", 102: "Alpha"},
            self.log,
            history_path=Path(self.tmp.name) / "history.sqlite3",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_snapshot_sorted_with_unrated_last(self):
        snap = self.guide.snapshot()
        self.assertEqual([c["name"] for c in snap["cards"]], ["Alpha", "Beta // Gamma", "Unknown card (999)"])
        self.assertEqual((snap["pack"]["pack"], snap["pack"]["pick"]), (2, 5))
        self.assertTrue(snap["cards"][2]["unrated"])
        self.assertEqual(snap["history"]["drafts"][0]["observations"], 1)
        json.dumps(snap)

    def test_snapshot_identifies_the_completed_saved_draft(self):
        self.guide.snapshot()
        self.guide.state.draft_completed = True
        self.guide.state.last_event_name = "PremierDraft_FRA_20260929"

        snapshot = self.guide.snapshot()

        self.assertTrue(snapshot["draftCompleted"])
        self.assertEqual(snapshot["completedDraftId"], snapshot["history"]["drafts"][0]["id"])

    def test_instant_guide_uses_limited_event_or_dominant_deck_set(self):
        game = self.guide.state.game
        game.deck = [101, 102]
        self.guide.expansions = {101: "FRA", 102: "FRA"}
        self.assertIsNotNone(self.guide.instant_view(game))

        self.guide.state.last_event_name = "PremierDraft_FRA_20260929"
        self.assertIsNotNone(self.guide.instant_view(game))

        game.deck = [101, 102, 103]
        self.guide.expansions = {101: "FDN", 102: "WOE", 103: "ECL"}
        self.assertIsNone(self.guide.instant_view(game))

    def test_history_details_enrich_draft_and_sealed_cards(self):
        self.guide.history.record_pack(logparse.PackObservation(
            (101, 102), 0, 0, "PremierDraft_FRA_20261003",
        ))
        self.guide.history.record_pack(logparse.PackObservation(
            (102,), 0, 1, "PremierDraft_FRA_20261003", (101,),
        ))
        draft_id = self.guide.history.list_history()["drafts"][0]["id"]
        draft = self.guide.history_detail("draft", draft_id)
        self.assertEqual([card["name"] for card in draft["observations"][0]["cards"]], ["Beta // Gamma", "Alpha"])
        self.assertEqual(draft["observations"][0]["chosenCards"][0]["name"], "Beta // Gamma")
        self.assertEqual(len(draft["deckBuild"]["builds"][0]["cards"]), 1)

        self.guide.history.record_sealed(logparse.SealedObservation(
            (101, 101, 102), "Sealed_FRA_20261003",
        ))
        sealed_id = self.guide.history.list_history()["sealed"][0]["id"]
        sealed = self.guide.history_detail("sealed", sealed_id)
        self.assertEqual([(card["name"], card["count"]) for card in sealed["cards"]], [("Alpha", 1), ("Beta // Gamma", 2)])

    def test_demo_pack_uses_image_fallback_for_unillustrated_ratings(self):
        data = {
            "set": {"code": "WOE"},
            "cards": [
                {"name": f"Card {index}", "score": 100 - index, "image": None}
                for index in range(20)
            ],
        }
        demo = Guide(data, {}, self.log, demo=True, history_path=Path(self.tmp.name) / "demo-history.sqlite3")
        snapshot = demo.snapshot()
        self.assertEqual(len(snapshot["cards"]), 15)
        self.assertTrue(all(card["image"].startswith("https://api.scryfall.com/cards/named?") for card in snapshot["cards"]))

    def test_ratings_and_notes_carried(self):
        alpha = self.guide.snapshot()["cards"][0]
        self.assertEqual(alpha["ratings"][0]["comment"], "Great.")
        self.assertEqual(alpha["notes"], [{"source": "Jim", "text": "Good."}])

    def test_multisource_ratings_keep_grades_but_not_commentary(self):
        data = ratings.slim_multisource(RAW)
        alpha = data["cards"][0]
        self.assertEqual(data["source"], "Multi-source ratings")
        self.assertEqual(alpha["score"], 95)
        self.assertEqual(alpha["ratings"][0]["grade"], "A")
        self.assertEqual(alpha["ratings"][0]["scale"], "A to F")
        self.assertEqual(alpha["ratings"][0]["sourceUrl"], "https://example.com/review")
        self.assertNotIn("comment", alpha["ratings"][0])
        self.assertEqual(alpha["notes"], [])

    def test_new_pack_bumps_version(self):
        v = self.guide.snapshot()["version"]
        with self.log.open("a", encoding="utf-8") as f:
            f.write(BOT_PLAIN + "\n")
        self.assertGreater(self.guide.snapshot()["version"], v)

    def test_archetypes_are_attached_for_current_set(self):
        guide_dir = Path(self.tmp.name) / "archetypes"
        guide_dir.mkdir()
        (guide_dir / "FRA.json").write_text(json.dumps({
            "set": {"code": "FRA", "name": "Reality Fracture"},
            "sources": [],
            "archetypes": [{"colors": ["W", "U"], "name": "Fatehold", "focus": "Scry.", "tier": None}],
        }), encoding="utf-8")
        self.guide.archetype_dir = guide_dir
        first = self.guide.snapshot()
        self.assertEqual(first["archetypes"]["archetypes"][0]["name"], "Fatehold")
        guide_path = guide_dir / "FRA.json"
        updated = json.loads(guide_path.read_text(encoding="utf-8"))
        updated["archetypes"][0]["tier"] = "D"
        guide_path.write_text(json.dumps(updated), encoding="utf-8")
        stat = guide_path.stat()
        os.utime(guide_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
        second = self.guide.snapshot()
        self.assertNotEqual(first["version"], second["version"])
        self.assertEqual(second["archetypes"]["archetypes"][0]["tier"], "D")

    def test_sealed_pool_snapshot_enriches_cards_and_tier_fit(self):
        guide_dir = Path(self.tmp.name) / "sealed-archetypes"
        guide_dir.mkdir()
        (guide_dir / "FRA.json").write_text(json.dumps({
            "set": {"code": "FRA", "name": "Reality Fracture"},
            "sources": [],
            "archetypes": [
                {"colors": ["W", "U"], "name": "Fatehold", "tier": "A"},
                {"colors": ["B", "R"], "name": "Rift Aggro", "tier": "D"},
            ],
        }), encoding="utf-8")
        self.guide.archetype_dir = guide_dir
        self.guide.colors = {101: "WU", 102: "R"}
        self.guide.details = {101: ("oU", "Creature — Faerie"), 102: ("oR", "Creature — Wizard")}
        self.guide.state.sealed_pool = logparse.SealedObservation(
            (101, 101, 102), "Sealed_FRA_20260929",
        )
        self.guide.state.offset = self.log.stat().st_size

        snapshot = self.guide.snapshot()
        pool = snapshot["sealedPool"]
        self.assertEqual(pool["cardCount"], 3)
        self.assertEqual(pool["uniqueCount"], 2)
        beta = next(card for card in pool["cards"] if card["name"] == "Beta // Gamma")
        self.assertEqual(beta["count"], 2)
        self.assertEqual(beta["colors"], ["W", "U"])
        self.assertEqual(beta["typeLine"], "Creature — Faerie")
        self.assertEqual(snapshot["set"], "FRA")
        fatehold = next(item for item in pool["archetypes"] if item["name"] == "Fatehold")
        self.assertEqual(fatehold["tier"], "A")
        json.dumps(snapshot)


if __name__ == "__main__":
    unittest.main()
