"""Track the local player's library during a match from GRE messages in Player.log.

The library is hidden information, so it is reconstructed as: submitted deck list minus
every card this seat owns that is currently in a visible zone (hand, battlefield,
graveyard, exile, stack). Only the player's own deck list and zones are used.
"""
from __future__ import annotations

import json
from collections import Counter

_VISIBLE_ZONES = {
    "ZoneType_Hand",
    "ZoneType_Battlefield",
    "ZoneType_Graveyard",
    "ZoneType_Exile",
    "ZoneType_Stack",
}
_CARD_TYPES = {"GameObjectType_Card", "GameObjectType_SplitCard", "GameObjectType_MDFCBack", "GameObjectType_Adventure"}
_MAX_BLOCK_LINES = 200_000


class GameTracker:
    def __init__(self) -> None:
        self.version = 0
        self.active = False
        self.deck: list[int] = []
        self.seat: int | None = None
        self._objects: dict[int, tuple[int, int | None]] = {}  # instanceId -> (grpId, ownerSeat)
        self._zones: dict[int, tuple[str, int | None, list[int]]] = {}
        self._armed = False
        self._buf: list[str] | None = None

    def feed_line(self, line: str) -> bool:
        if self._buf is not None:
            self._buf.append(line)
            if line.rstrip() == "}":
                try:
                    blob = json.loads("".join(self._buf))
                except ValueError:
                    blob = None
                if blob is not None:
                    self._buf = None
                    return self._handle(blob)
            if len(self._buf) > _MAX_BLOCK_LINES:
                self._buf = None
            return False

        stripped = line.strip()
        if "GreToClientEvent" in line:
            start = line.find("{")
            if start >= 0:
                try:
                    return self._handle(json.loads(line[start:]))
                except ValueError:
                    return False
            self._armed = True
            return False
        if self._armed:
            self._armed = False
            if stripped.startswith("{"):
                try:
                    return self._handle(json.loads(stripped))
                except ValueError:
                    self._buf = [line]
        return False

    def _handle(self, blob: dict) -> bool:
        event = blob.get("greToClientEvent")
        if not isinstance(event, dict):
            return False
        changed = False
        for message in event.get("greToClientMessages", []):
            seats = message.get("systemSeatIds") or []
            if len(seats) == 1:
                self.seat = seats[0]
            kind = message.get("type")
            if kind == "GREMessageType_ConnectResp":
                changed |= self._connect(message)
            elif kind in ("GREMessageType_GameStateMessage", "GREMessageType_QueuedGameStateMessage"):
                changed |= self._game_state(message.get("gameStateMessage") or {})
        if changed:
            self.version += 1
        return changed

    def _connect(self, message: dict) -> bool:
        deck = ((message.get("connectResp") or {}).get("deckMessage") or {}).get("deckCards") or []
        self.deck = [int(c) for c in deck]
        self._objects.clear()
        self._zones.clear()
        self.active = bool(self.deck)
        return True

    def _game_state(self, gsm: dict) -> bool:
        if gsm.get("type") == "GameStateType_Full":
            self._objects.clear()
            self._zones.clear()
        for zone in gsm.get("zones", []):
            self._zones[zone["zoneId"]] = (zone.get("type", ""), zone.get("ownerSeatId"), list(zone.get("objectInstanceIds", [])))
        for obj in gsm.get("gameObjects", []):
            if obj.get("type") in _CARD_TYPES:
                self._objects[obj["instanceId"]] = (obj.get("grpId", 0), obj.get("ownerSeatId"))
        for instance_id in gsm.get("diffDeletedInstanceIds", []):
            self._objects.pop(instance_id, None)
        if (gsm.get("gameInfo") or {}).get("stage") == "GameStage_GameOver":
            self.active = False
        return True

    def seen_grp_ids(self) -> list[int]:
        """Own cards currently visible outside the library."""
        seen = []
        for zone_type, _owner, instances in self._zones.values():
            if zone_type not in _VISIBLE_ZONES:
                continue
            for instance_id in instances:
                grp, owner = self._objects.get(instance_id, (0, None))
                if grp and owner == self.seat:
                    seen.append(grp)
        return seen

    def library_zone_size(self) -> int | None:
        for zone_type, owner, instances in self._zones.values():
            if zone_type == "ZoneType_Library" and owner == self.seat:
                return len(instances)
        return None

    def remaining(self, key=lambda grp: grp) -> Counter:
        """Deck copies not yet seen outside the library, keyed by key(grpId)."""
        left = Counter(key(g) for g in self.deck)
        left.subtract(Counter(key(g) for g in self.seen_grp_ids()))
        return Counter({k: v for k, v in left.items() if v > 0})

