"""Incremental parser for the draft packs Arena writes to Player.log (read-only file access)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from .game import GameTracker

_BOT_PACK = re.compile(r'"DraftPack"\s*:\s*\[([^\]]*)\]')
_QUICK_PACK = re.compile(r'"PackCards"\s*:\s*"([0-9,\s]*)"')
_NUM = {
    "pack": re.compile(r'"(?:PackNumber|SelfPack)"\s*:\s*(\d+)'),
    "pick": re.compile(r'"(?:PickNumber|SelfPick)"\s*:\s*(\d+)'),
}
_EVENT = re.compile(r'"EventName"\s*:\s*"([^"]+)"')
_PICKED = re.compile(r'"PickedCards"\s*:\s*\[([^\]]*)\]')
_DIGITS = re.compile(r"\d+")


@dataclass(frozen=True)
class PackObservation:
    card_ids: tuple[int, ...]
    pack_number: int | None = None
    pick_number: int | None = None
    event_name: str | None = None
    picked_ids: tuple[int, ...] = ()
    source: str = "bot"


@dataclass(frozen=True)
class SealedObservation:
    card_ids: tuple[int, ...]
    event_name: str


@dataclass
class DraftLogState:
    pack: PackObservation | None = None
    sealed_pool: SealedObservation | None = None
    last_event_name: str | None = None
    version: int = 0
    offset: int = 0
    _seen: tuple = field(default=(), repr=False)
    game: GameTracker = field(default_factory=GameTracker)


def parse_line(line: str) -> PackObservation | None:
    text = line.replace('\\"', '"')
    if "DraftPack" in text:
        match, source = _BOT_PACK.search(text), "bot"
    elif "PackCards" in text:
        match, source = _QUICK_PACK.search(text), "quick"
    else:
        return None
    if not match:
        return None
    ids = tuple(int(n) for n in _DIGITS.findall(match.group(1)))
    pack = _NUM["pack"].search(text)
    pick = _NUM["pick"].search(text)
    event = _EVENT.search(text)
    picked = _PICKED.search(text)
    offset = 1 if source == "quick" else 0  # Draft.Notify numbers picks/packs from 1
    return PackObservation(
        card_ids=ids,
        pack_number=int(pack.group(1)) - offset if pack else None,
        pick_number=int(pick.group(1)) - offset if pick else None,
        event_name=event.group(1) if event else None,
        picked_ids=tuple(int(n) for n in _DIGITS.findall(picked.group(1))) if picked else (),
        source=source,
    )


def _nested_json(value, depth=0):
    if depth > 8:
        return
    if isinstance(value, dict):
        yield value
        for child in value.values():
            if isinstance(child, (dict, list)):
                yield from _nested_json(child, depth + 1)
            elif isinstance(child, str) and child.lstrip().startswith(("{", "[")):
                try:
                    yield from _nested_json(json.loads(child), depth + 1)
                except (ValueError, RecursionError):
                    pass
    elif isinstance(value, list):
        for child in value:
            yield from _nested_json(child, depth + 1)


def _pool_ids(value) -> tuple[int, ...]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            value = value.split(",")
    if not isinstance(value, list):
        return ()
    ids = []
    for item in value:
        if isinstance(item, dict):
            item = next((item[key] for key in ("GrpId", "grpId", "CardId", "cardId") if key in item), None)
        try:
            card_id = int(item)
        except (TypeError, ValueError):
            continue
        if card_id > 0:
            ids.append(card_id)
    return tuple(ids)


def parse_sealed_pool_line(line: str) -> SealedObservation | None:
    """Find a complete Sealed CardPool in a direct or nested Arena log payload."""
    if "CardPool" not in line and "cardPool" not in line:
        return None
    start = line.find("{")
    if start < 0:
        return None
    try:
        payload, _ = json.JSONDecoder().raw_decode(line[start:])
    except ValueError:
        return None
    for value in _nested_json(payload):
        event_name = value.get("InternalEventName") or value.get("internalEventName") or value.get("EventName") or value.get("eventName")
        pool = value.get("CardPool", value.get("cardPool"))
        if not isinstance(event_name, str) or "sealed" not in event_name.casefold():
            continue
        card_ids = _pool_ids(pool)
        if len(card_ids) >= 40:
            return SealedObservation(card_ids, event_name)
    return None


def apply_lines(state: DraftLogState, lines, on_pack=None, on_sealed=None) -> bool:
    changed = False
    for line in lines:
        if state.game.feed_line(line):
            changed = True
        sealed = parse_sealed_pool_line(line)
        if sealed is not None and sealed != state.sealed_pool:
            state.sealed_pool = sealed
            state.last_event_name = sealed.event_name
            state.pack = None
            state._seen = ()
            state.version += 1
            changed = True
            if on_sealed:
                on_sealed(sealed)
        obs = parse_line(line)
        if obs is None:
            continue
        if obs.event_name:
            state.last_event_name = obs.event_name
        key = (obs.card_ids, obs.pack_number, obs.pick_number, obs.picked_ids, obs.event_name, obs.source)
        if key == state._seen:
            continue
        state._seen = key
        if state.sealed_pool is not None:
            state.sealed_pool = None
        state.pack = obs if obs.card_ids else None
        state.version += 1
        changed = True
        if on_pack:
            on_pack(obs if obs.event_name else replace(obs, event_name=state.last_event_name))
    return changed


def poll(state: DraftLogState, log_path: Path, on_pack=None, on_sealed=None, on_reset=None) -> bool:
    """Read newly appended log text; restart from the top when Arena rewrote the file."""
    try:
        size = log_path.stat().st_size
    except OSError:
        return False
    if size < state.offset:
        state.offset = 0
        state.pack = None
        state.sealed_pool = None
        state.last_event_name = None
        state._seen = ()
        state.game = GameTracker()
        state.version += 1
        if on_reset:
            on_reset()
    if size == state.offset:
        return False
    with log_path.open("rb") as handle:
        handle.seek(state.offset)
        chunk = handle.read()
    end = chunk.rfind(b"\n")
    if end < 0:
        return False
    state.offset += end + 1
    return apply_lines(
        state,
        chunk[: end + 1].decode("utf-8", errors="replace").splitlines(),
        on_pack=on_pack,
        on_sealed=on_sealed,
    )
