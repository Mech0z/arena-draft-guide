"""Incremental parser for the draft packs Arena writes to Player.log (read-only file access)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

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


@dataclass
class DraftLogState:
    pack: PackObservation | None = None
    version: int = 0
    offset: int = 0
    _seen: tuple = field(default=(), repr=False)


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


def apply_lines(state: DraftLogState, lines) -> bool:
    changed = False
    for line in lines:
        obs = parse_line(line)
        if obs is None:
            continue
        key = (obs.card_ids, obs.pack_number, obs.pick_number)
        if key == state._seen:
            continue
        state._seen = key
        state.pack = obs if obs.card_ids else None
        state.version += 1
        changed = True
    return changed


def poll(state: DraftLogState, log_path: Path) -> bool:
    """Read newly appended log text; restart from the top when Arena rewrote the file."""
    try:
        size = log_path.stat().st_size
    except OSError:
        return False
    if size < state.offset:
        state.offset = 0
        state.pack = None
        state._seen = ()
        state.version += 1
    if size == state.offset:
        return False
    with log_path.open("rb") as handle:
        handle.seek(state.offset)
        chunk = handle.read()
    end = chunk.rfind(b"\n")
    if end < 0:
        return False
    state.offset += end + 1
    return apply_lines(state, chunk[: end + 1].decode("utf-8", errors="replace").splitlines())
