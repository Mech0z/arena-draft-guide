"""Load curated, per-set Limited archetype guides."""
from __future__ import annotations

import json
import re
from pathlib import Path

_SET_CODE = re.compile(r"^[A-Z0-9]{2,6}$")


def load_set(directory: Path, code: str | None) -> dict | None:
    """Load a set's archetype guide, or return None when there is no guide for it."""
    code = (code or "").upper()
    if not _SET_CODE.fullmatch(code):
        return None

    path = directory / f"{code}.json"
    if not path.is_file():
        return None

    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("set", {}).get("code") != code:
        raise ValueError(f"Archetype guide set code does not match filename: {path}")
    if not isinstance(data.get("archetypes"), list):
        raise ValueError(f"Archetype guide must contain an archetypes list: {path}")
    return data
