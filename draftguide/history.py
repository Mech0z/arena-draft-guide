"""Persistent local archive of Arena draft observations and sealed pools."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock


def default_history_path() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    base = Path(root) if root else Path.home() / ".local" / "share"
    return base / "ArenaDraftGuide" / "history.sqlite3"


def _json_ids(values) -> str:
    return json.dumps([int(value) for value in values], separators=(",", ":"))


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class HistoryStore:
    def __init__(self, path: Path | None = None):
        self.path = path or default_history_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._active_draft_id: str | None = None
        self._active_event: str | None = None
        self._previous_observation: tuple[str, int, tuple[int, ...], int | None, int | None] | None = None
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS drafts (
                    id TEXT PRIMARY KEY,
                    event TEXT NOT NULL,
                    start_key TEXT NOT NULL UNIQUE,
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS draft_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    draft_id TEXT NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
                    fingerprint TEXT NOT NULL,
                    pack_number INTEGER,
                    pick_number INTEGER,
                    card_ids TEXT NOT NULL,
                    picked_ids TEXT NOT NULL,
                    chosen_ids TEXT NOT NULL DEFAULT '[]',
                    source TEXT NOT NULL,
                    UNIQUE (draft_id, fingerprint)
                );
                CREATE INDEX IF NOT EXISTS observations_by_draft
                    ON draft_observations(draft_id, id);
                CREATE TABLE IF NOT EXISTS sealed_histories (
                    id TEXT PRIMARY KEY,
                    event TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    card_ids TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _observation_payload(observation, event: str) -> list:
        return [
            event,
            observation.pack_number,
            observation.pick_number,
            list(observation.card_ids),
            list(observation.picked_ids),
            observation.source,
        ]

    def record_pack(self, observation) -> None:
        with self._lock:
            event = observation.event_name or self._active_event or ""
            payload = self._observation_payload(observation, event)
            fingerprint = _digest(payload)
            position_is_start = (
                observation.pack_number in (0, 1) and observation.pick_number in (0, 1)
            )
            previous = self._previous_observation
            pack_rolled_back = (
                previous is not None
                and previous[3] is not None
                and observation.pack_number is not None
                and previous[3] > observation.pack_number
            )
            is_start = pack_rolled_back or (
                position_is_start and (
                    previous is None
                    or (event and self._active_event and event != self._active_event)
                    or (
                        previous[3] == observation.pack_number
                        and previous[4] is not None
                        and observation.pick_number is not None
                        and previous[4] > observation.pick_number
                    )
                )
            )
            start_key = ("start:" if is_start else "partial:") + _digest(
                [event, observation.pack_number, observation.pick_number, list(observation.card_ids)]
            )
            now = _now()
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT id FROM drafts WHERE start_key = ?", (start_key,)
                ).fetchone()
                if is_start or self._active_draft_id is None or (
                    event and self._active_event and event != self._active_event
                ):
                    if row:
                        draft_id = row["id"]
                    else:
                        connection.execute(
                            "INSERT OR IGNORE INTO drafts (id, event, start_key, started_at, updated_at) "
                            "VALUES (?, ?, ?, ?, ?)",
                            (str(uuid.uuid4()), event, start_key, now, now),
                        )
                        draft_id = connection.execute(
                            "SELECT id FROM drafts WHERE start_key = ?", (start_key,)
                        ).fetchone()["id"]
                    self._active_draft_id = draft_id
                    self._active_event = event
                    self._previous_observation = None
                else:
                    draft_id = self._active_draft_id
                if self._active_draft_id is None:
                    self._active_draft_id = draft_id
                    self._active_event = event
                if event:
                    self._active_event = event

                connection.execute(
                    "INSERT OR IGNORE INTO draft_observations "
                    "(draft_id, fingerprint, pack_number, pick_number, card_ids, picked_ids, source) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        draft_id,
                        fingerprint,
                        observation.pack_number,
                        observation.pick_number,
                        _json_ids(observation.card_ids),
                        _json_ids(observation.picked_ids),
                        observation.source,
                    ),
                )
                current = connection.execute(
                    "SELECT id FROM draft_observations WHERE draft_id = ? AND fingerprint = ?",
                    (draft_id, fingerprint),
                ).fetchone()
                if previous and previous[0] == draft_id:
                    previous_id, previous_picks = previous[1:3]
                    added = list((Counter(observation.picked_ids) - Counter(previous_picks)).elements())
                    if added:
                        connection.execute(
                            "UPDATE draft_observations SET chosen_ids = ? WHERE id = ?",
                            (_json_ids(added), previous_id),
                        )
                connection.execute(
                    "UPDATE drafts SET event = CASE WHEN event = '' THEN ? ELSE event END, updated_at = ? WHERE id = ?",
                    (event, now, draft_id),
                )
                self._previous_observation = (
                    draft_id,
                    current["id"],
                    tuple(observation.picked_ids),
                    observation.pack_number,
                    observation.pick_number,
                )

    def record_sealed(self, observation) -> None:
        with self._lock, self._connect() as connection:
            event = observation.event_name
            card_ids = list(observation.card_ids)
            fingerprint = _digest([event, card_ids])
            connection.execute(
                "INSERT OR IGNORE INTO sealed_histories (id, event, fingerprint, card_ids, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), event, fingerprint, _json_ids(card_ids), _now()),
            )

    def reset_log_context(self) -> None:
        with self._lock:
            self._active_draft_id = None
            self._active_event = None
            self._previous_observation = None

    @staticmethod
    def _taken_ids(observations: list[dict], current: dict) -> list[int]:
        if current["pack"] is None or current["pick"] is None:
            return []
        pack_number = current["pack"]
        current_counts = Counter(current["cardIds"])
        same_pack = [
            item for item in observations
            if item["pack"] == pack_number
            and item["pick"] is not None
            and item["pick"] < current["pick"]
        ]
        if not same_pack:
            return []
        first_pick = min(item["pick"] for item in same_pack)
        if current["pick"] - first_pick < 7:
            return []
        candidates = [
            item for item in observations
            if item["pack"] == pack_number
            and item["pick"] == first_pick
            and len(item["cardIds"]) > len(current["cardIds"])
            and not (current_counts - Counter(item["cardIds"]))
        ]
        if not candidates:
            return []
        origin = max(candidates, key=lambda item: len(item["cardIds"]))
        origin_counts = Counter(origin["cardIds"])
        taken = origin_counts - current_counts
        own_picks = Counter(
            card_id
            for item in observations
            if item["pack"] == pack_number
            and item["pick"] is not None
            and item["pick"] <= current["pick"]
            and not (Counter(item["cardIds"]) - origin_counts)
            for card_id in item["chosenIds"]
        )
        if not own_picks:
            own_picks = Counter(
                card_id for card_id in current["pickedIds"] if card_id in origin_counts
            )
        taken -= own_picks
        remaining = taken.copy()
        result = []
        for card_id in origin["cardIds"]:
            if remaining[card_id] > 0:
                result.append(card_id)
                remaining[card_id] -= 1
        return result

    def list_history(self) -> dict:
        with self._lock, self._connect() as connection:
            drafts = connection.execute(
                """
                SELECT d.id, d.event, d.started_at, d.updated_at,
                       SUM(CASE WHEN o.card_ids != '[]' THEN 1 ELSE 0 END) AS observations,
                       COUNT(DISTINCT o.pack_number) AS packs
                FROM drafts d LEFT JOIN draft_observations o ON o.draft_id = d.id
                GROUP BY d.id ORDER BY d.started_at DESC LIMIT 100
                """
            ).fetchall()
            sealed = connection.execute(
                "SELECT id, event, created_at, card_ids "
                "FROM sealed_histories ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
            counts = connection.execute(
                "SELECT (SELECT COUNT(*) FROM drafts) + (SELECT COUNT(*) FROM draft_observations) "
                "+ (SELECT COUNT(*) FROM sealed_histories)"
            ).fetchone()[0]
            return {
                "revision": counts,
                "drafts": [dict(row) for row in drafts],
                "sealed": [
                    {
                        "id": row["id"],
                        "event": row["event"],
                        "created_at": row["created_at"],
                        "card_count": len(json.loads(row["card_ids"])),
                    }
                    for row in sealed
                ],
            }

    def get_draft(self, draft_id: str) -> dict | None:
        with self._lock, self._connect() as connection:
            draft = connection.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
            if not draft:
                return None
            observations = connection.execute(
                "SELECT id, pack_number, pick_number, card_ids, picked_ids, chosen_ids, source "
                "FROM draft_observations WHERE draft_id = ? ORDER BY id",
                (draft_id,),
            ).fetchall()
            items = [
                {
                    "id": row["id"],
                    "pack": row["pack_number"],
                    "pick": row["pick_number"],
                    "cardIds": json.loads(row["card_ids"]),
                    "pickedIds": json.loads(row["picked_ids"]),
                    "chosenIds": json.loads(row["chosen_ids"]),
                    "source": row["source"],
                }
                for row in observations
            ]
            for item in items:
                item["takenIds"] = self._taken_ids(items, item)
            return {
                "id": draft["id"],
                "event": draft["event"],
                "startedAt": draft["started_at"],
                "updatedAt": draft["updated_at"],
                "observations": items,
            }

    def get_sealed(self, sealed_id: str) -> dict | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT id, event, card_ids, created_at FROM sealed_histories WHERE id = ?",
                (sealed_id,),
            ).fetchone()
            if not row:
                return None
            card_ids = json.loads(row["card_ids"])
            return {
                "id": row["id"],
                "event": row["event"],
                "createdAt": row["created_at"],
                "cardIds": card_ids,
                "cardCount": len(card_ids),
            }

    def current_taken_ids(self, observation) -> list[int]:
        if not self._active_draft_id:
            return []
        detail = self.get_draft(self._active_draft_id)
        if not detail:
            return []
        for item in reversed(detail["observations"]):
            if (
                item["pack"] == observation.pack_number
                and item["pick"] == observation.pick_number
                and item["cardIds"] == list(observation.card_ids)
                and item["pickedIds"] == list(observation.picked_ids)
            ):
                return item["takenIds"]
        return []
