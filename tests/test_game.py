import json
import tempfile
import unittest
from pathlib import Path

from draftguide import logparse
from draftguide.game import GameTracker
from draftguide.server import Guide

from tests.test_draftguide import RAW
from draftguide import ratings

NAMES = {1: "Forest", 2: "Bear", 3: "Bolt", 10: "Forest"}  # 10 = alternate printing of Forest
LANDS = {1, 10}


def gre(*messages, pretty=False):
    body = {"greToClientEvent": {"greToClientMessages": list(messages)}}
    header = "[UnityCrossThreadLogger]12:00:00: Match to X: GreToClientEvent\n"
    return header + (json.dumps(body, indent=2) if pretty else json.dumps(body)) + "\n"


def connect(deck, seat=1):
    return {"type": "GREMessageType_ConnectResp", "systemSeatIds": [seat],
            "connectResp": {"deckMessage": {"deckCards": deck}}}


def state(zones, objects, deleted=(), full=False, over=False, seat=1):
    gsm = {"type": "GameStateType_Full" if full else "GameStateType_Diff", "zones": zones, "gameObjects": objects,
           "diffDeletedInstanceIds": list(deleted)}
    if over:
        gsm["gameInfo"] = {"stage": "GameStage_GameOver"}
    return {"type": "GREMessageType_GameStateMessage", "systemSeatIds": [seat], "gameStateMessage": gsm}


def obj(iid, grp, owner=1, kind="GameObjectType_Card"):
    return {"instanceId": iid, "grpId": grp, "ownerSeatId": owner, "type": kind}


def zone(zid, kind, ids, owner=None):
    z = {"zoneId": zid, "type": kind, "objectInstanceIds": ids}
    if owner is not None:
        z["ownerSeatId"] = owner
    return z


def feed(tracker, text):
    return [tracker.feed_line(line) for line in text.splitlines(keepends=True)]


DECK = [1, 1, 1, 2, 2, 3]


class TrackerTests(unittest.TestCase):
    def test_remaining_after_draw_and_play(self):
        t = GameTracker()
        feed(t, gre(connect(DECK)))
        feed(t, gre(state(
            [zone(1, "ZoneType_Library", [100, 101, 102], 1), zone(2, "ZoneType_Hand", [200, 201], 1),
             zone(3, "ZoneType_Battlefield", [300]), zone(4, "ZoneType_Hand", [400], 2)],
            [obj(200, 2), obj(201, 1), obj(300, 1), obj(400, 3, owner=2)], full=True)))
        self.assertTrue(t.active)
        self.assertEqual(sorted(t.remaining().elements()), [1, 2, 3])
        self.assertEqual(t.library_zone_size(), 3)

    def test_pretty_printed_block_and_partial_feed(self):
        t = GameTracker()
        text = gre(connect(DECK), pretty=True)
        feed(t, text)
        self.assertTrue(t.active)
        self.assertEqual(t.deck, DECK)

    def test_opponent_cards_and_tokens_ignored(self):
        t = GameTracker()
        feed(t, gre(connect(DECK)))
        feed(t, gre(state([zone(3, "ZoneType_Battlefield", [300, 301, 302])],
                          [obj(300, 3, owner=2), obj(301, 1, kind="GameObjectType_Token"), obj(302, 2)], full=True)))
        self.assertEqual(t.remaining()[3], 1)
        self.assertEqual(t.remaining()[1], 3)
        self.assertEqual(t.remaining()[2], 1)

    def test_deleted_and_moved_cards_return_to_library(self):
        t = GameTracker()
        feed(t, gre(connect(DECK)))
        feed(t, gre(state([zone(2, "ZoneType_Hand", [200], 1)], [obj(200, 3)], full=True)))
        self.assertEqual(t.remaining()[3], 0)
        feed(t, gre(state([zone(2, "ZoneType_Hand", [], 1), zone(1, "ZoneType_Library", [500], 1)], [], deleted=[200])))
        self.assertEqual(t.remaining()[3], 1)

    def test_limbo_and_library_zones_not_counted(self):
        t = GameTracker()
        feed(t, gre(connect(DECK)))
        feed(t, gre(state([zone(9, "ZoneType_Limbo", [200]), zone(1, "ZoneType_Library", [201], 1)],
                          [obj(200, 3), obj(201, 2)], full=True)))
        self.assertEqual(sum(t.remaining().values()), len(DECK))

    def test_game_over_and_new_game_reset(self):
        t = GameTracker()
        feed(t, gre(connect(DECK)))
        feed(t, gre(state([], [], over=True)))
        self.assertFalse(t.active)
        feed(t, gre(connect(DECK)))
        self.assertTrue(t.active)

    def test_no_deck_means_inactive(self):
        t = GameTracker()
        feed(t, gre(state([zone(2, "ZoneType_Hand", [200], 1)], [obj(200, 1)], full=True)))
        self.assertFalse(t.active)

    def test_multi_seat_messages_do_not_change_seat(self):
        t = GameTracker()
        feed(t, gre(connect(DECK, seat=2)))
        feed(t, gre({"type": "GREMessageType_TimerStateMessage", "systemSeatIds": [1, 2]}))
        self.assertEqual(t.seat, 2)

    def test_version_bumps_only_on_change(self):
        t = GameTracker()
        feed(t, "noise\n" * 5)
        self.assertEqual(t.version, 0)
        feed(t, gre(connect(DECK)))
        self.assertEqual(t.version, 1)


class GameViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "Player.log"
        self.guide = Guide(
            ratings.slim(RAW), NAMES, self.log, lands=LANDS,
            history_path=Path(self.tmp.name) / "history.sqlite3",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, *blocks):
        with self.log.open("a", encoding="utf-8") as f:
            f.write("".join(blocks))

    def test_chances_group_printings_by_name(self):
        self.write(gre(connect([1, 1, 10, 2, 2, 3])),
                   gre(state([zone(2, "ZoneType_Hand", [200, 201], 1)], [obj(200, 10), obj(201, 2)], full=True)))
        view = self.guide.snapshot()["game"]
        self.assertEqual(view["libraryCount"], 4)
        by = {c["name"]: c for c in view["cards"]}
        self.assertEqual(by["Forest"]["count"], 2)
        self.assertAlmostEqual(by["Forest"]["chance"], 0.5)
        self.assertAlmostEqual(by["Bolt"]["chance"], 0.25)
        self.assertTrue(by["Forest"]["isLand"])
        self.assertFalse(by["Bear"]["isLand"])
        self.assertAlmostEqual(sum(c["chance"] for c in view["cards"]), 1.0)
        self.assertTrue(by["Bolt"]["image"].startswith("https://api.scryfall.com/cards/named"))
        self.assertEqual([c["name"] for c in view["cards"]][-1], "Forest")  # lands last

    def test_mana_and_type_line_included(self):
        guide = Guide(
            ratings.slim(RAW), NAMES, self.log, lands=LANDS,
            details={2: ('o1oG', 'Creature \u2014 Bear')},
            history_path=Path(self.tmp.name) / "details-history.sqlite3",
        )
        self.write(gre(connect(DECK)))
        card = {c['name']: c for c in guide.snapshot()['game']['cards']}['Bear']
        self.assertEqual((card['mana'], card['typeLine']), ('o1oG', 'Creature \u2014 Bear'))

    def test_no_game_means_no_library_and_version_changes(self):
        snap = self.guide.snapshot()
        self.assertIsNone(snap["game"])
        self.write(gre(connect(DECK)))
        snap2 = self.guide.snapshot()
        self.assertIsNotNone(snap2["game"])
        self.assertNotEqual(snap["version"], snap2["version"])

    def test_game_hidden_after_game_over(self):
        self.write(gre(connect(DECK)), gre(state([], [], over=True)))
        self.assertIsNone(self.guide.snapshot()["game"])

    def test_log_rewrite_resets_game(self):
        self.write(gre(connect(DECK)))
        self.assertIsNotNone(self.guide.snapshot()["game"])
        self.log.write_text("fresh\n", encoding="utf-8")
        self.assertIsNone(self.guide.snapshot()["game"])


if __name__ == "__main__":
    unittest.main()
