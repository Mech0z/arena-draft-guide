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
    "sources": {"a": {"short": "Src A"}},
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

    def test_duplicates_do_not_bump_version(self):
        state = logparse.DraftLogState()
        logparse.apply_lines(state, [BOT_PLAIN, BOT_PLAIN])
        self.assertEqual(state.version, 1)

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


class GuideTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "Player.log"
        self.log.write_text(BOT_ESCAPED + "\n", encoding="utf-8")
        self.guide = Guide(ratings.slim(RAW), {101: "Beta // Gamma", 102: "Alpha"}, self.log)

    def tearDown(self):
        self.tmp.cleanup()

    def test_snapshot_sorted_with_unrated_last(self):
        snap = self.guide.snapshot()
        self.assertEqual([c["name"] for c in snap["cards"]], ["Alpha", "Beta // Gamma", "Unknown card (999)"])
        self.assertEqual((snap["pack"]["pack"], snap["pack"]["pick"]), (2, 5))
        self.assertTrue(snap["cards"][2]["unrated"])
        json.dumps(snap)

    def test_ratings_and_notes_carried(self):
        alpha = self.guide.snapshot()["cards"][0]
        self.assertEqual(alpha["ratings"][0]["comment"], "Great.")
        self.assertEqual(alpha["notes"], [{"source": "Jim", "text": "Good."}])

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


if __name__ == "__main__":
    unittest.main()
