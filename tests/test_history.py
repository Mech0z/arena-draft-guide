import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

from draftguide.history import HistoryStore
from draftguide.logparse import PackObservation, SealedObservation
from draftguide.server import Guide, make_handler


class HistoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "history.sqlite3"
        self.history = HistoryStore(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_draft_observations_persist_and_returned_pack_marks_other_picks(self):
        original = list(range(1, 16))
        picked = []
        for pick in range(8):
            if pick == 0:
                cards = original
            elif pick < 7:
                cards = list(range(100 + pick * 15, 115 + pick * 15))
            else:
                cards = list(range(4, 16))
            self.history.record_pack(PackObservation(
                tuple(cards),
                pack_number=0,
                pick_number=pick,
                event_name="PremierDraft_FRA_20261003",
                picked_ids=tuple(picked),
            ))
            if pick == 0:
                picked.append(1)
            elif pick < 7:
                picked.append(cards[0])

        summary = self.history.list_history()
        self.assertEqual(len(summary["drafts"]), 1)
        draft_id = summary["drafts"][0]["id"]
        detail = self.history.get_draft(draft_id)
        self.assertEqual(len(detail["observations"]), 8)
        self.assertEqual(detail["observations"][0]["chosenIds"], [1])
        self.assertEqual(detail["observations"][6]["takenIds"], [])
        self.assertEqual(detail["observations"][-1]["takenIds"], [2, 3])
        self.assertEqual(self.history.current_taken_ids(PackObservation(
            tuple(range(4, 16)),
            pack_number=0,
            pick_number=7,
            event_name="PremierDraft_FRA_20261003",
            picked_ids=tuple(picked),
        )), [2, 3])

        reopened = HistoryStore(self.path)
        self.assertEqual(len(reopened.get_draft(draft_id)["observations"]), 8)

    def test_replaying_log_is_idempotent_and_a_new_draft_starts_a_new_history(self):
        first = PackObservation((1, 2, 3), 0, 0, "QuickDraft_FRA_1")
        self.history.record_pack(first)
        original_id = self.history.list_history()["drafts"][0]["id"]
        self.history.record_pack(first)
        self.assertEqual(len(self.history.list_history()["drafts"]), 1)

        for pick in range(1, 15):
            self.history.record_pack(PackObservation(
                (10 + pick, 20 + pick),
                0,
                pick,
                "QuickDraft_FRA_1",
            ))
        self.history.record_pack(PackObservation((4, 5, 6), 0, 0, "QuickDraft_FRA_1"))
        drafts = self.history.list_history()["drafts"]
        self.assertEqual(len(drafts), 2)
        self.assertTrue(any(item["id"] != original_id for item in drafts))

    def test_sealed_pool_is_saved_once_with_duplicate_card_copies(self):
        pool = SealedObservation((101, 101, 102, 103), "Sealed_FRA_20261003")
        self.history.record_sealed(pool)
        self.history.record_sealed(pool)
        sealed = self.history.list_history()["sealed"]
        self.assertEqual(len(sealed), 1)
        detail = self.history.get_sealed(sealed[0]["id"])
        self.assertEqual(detail["cardIds"], [101, 101, 102, 103])
        self.assertEqual(detail["cardCount"], 4)

    def test_history_api_lists_and_opens_saved_pools(self):
        log = Path(self.tmp.name) / "Player.log"
        guide = Guide(
            {"set": {"code": "FRA"}, "cards": []},
            {},
            log,
            history_path=self.path,
        )
        guide.history.record_sealed(SealedObservation((101,) * 40, "Sealed_FRA_20261003"))
        guide.history.record_pack(PackObservation((11, 12), 0, 0, "QuickDraft_FRA_1"))
        sealed_id = guide.history.list_history()["sealed"][0]["id"]
        draft_id = guide.history.list_history()["drafts"][0]["id"]
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(guide))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            root = f"http://127.0.0.1:{server.server_port}"
            with urlopen(root + "/api/history") as response:
                listing = json.loads(response.read())
            with urlopen(root + "/api/state") as response:
                state = json.loads(response.read())
            with urlopen(root + f"/api/history/sealed/{sealed_id}") as response:
                detail = json.loads(response.read())
            with urlopen(root + f"/api/history/draft/{draft_id}") as response:
                draft = json.loads(response.read())
            with urlopen(root + "/") as response:
                page = response.read().decode("utf-8")
            self.assertEqual(len(listing["sealed"]), 1)
            self.assertEqual(detail["cardCount"], 40)
            self.assertEqual(detail["cards"][0]["count"], 40)
            self.assertEqual(draft["observations"][0]["cardIds"], [11, 12])
            self.assertTrue(state["history"]["drafts"])
            self.assertIn('data-view="history"', page)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_guide_snapshot_exposes_cards_taken_from_returned_pack(self):
        log = Path(self.tmp.name) / "Player.log"
        original = list(range(1, 16))
        picked = []
        lines = []
        for pick in range(8):
            if pick == 0:
                cards = original
            elif pick < 7:
                cards = list(range(100 + pick * 15, 115 + pick * 15))
            else:
                cards = list(range(4, 16))
            lines.append(json.dumps({
                "result": {
                    "EventName": "QuickDraft_FRA_20261003",
                    "PackNumber": 0,
                    "PickNumber": pick,
                    "DraftPack": cards,
                    "PickedCards": picked,
                },
            }))
            if pick == 0:
                picked.append(1)
            elif pick < 7:
                picked.append(cards[0])
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        names = {card_id: f"Card {card_id}" for card_id in range(1, 16)}
        guide = Guide(
            {"set": {"code": "FRA"}, "cards": []},
            names,
            log,
            history_path=self.path,
        )

        snapshot = guide.snapshot()
        self.assertEqual([card["arenaId"] for card in snapshot["takenCards"]], [2, 3])
        self.assertTrue(all(card["takenByOthers"] for card in snapshot["takenCards"]))


if __name__ == "__main__":
    unittest.main()
