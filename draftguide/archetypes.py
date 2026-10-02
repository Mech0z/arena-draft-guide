"""Load curated, per-set Limited archetype guides."""
from __future__ import annotations

import json
import re
from pathlib import Path

_SET_CODE = re.compile(r"^[A-Z0-9]{2,6}$")


def merge_tiers(guide: dict | None, live: list[dict] | None, code: str, set_name: str = "") -> dict | None:
    """Overlay live tier-list rows (matched by color combination) onto a curated guide, or build a basic one."""
    if not live:
        return guide
    guide = json.loads(json.dumps(guide)) if guide else {"set": {"code": code, "name": set_name or code}, "sources": [], "archetypes": []}
    by_colors = {frozenset(item["colors"]): item for item in guide["archetypes"]}
    for row in live:
        item = by_colors.get(frozenset(row["colors"]))
        if item is None:
            item = {"colors": row["colors"], "name": row["name"], "focus": ""}
            guide["archetypes"].append(item)
        item.update({key: row[key] for key in ("tier", "sixPlusWinRate", "matches", "tierSource")})
    guide["sources"] = [s for s in guide.get("sources", []) if not s.get("name", "").startswith("Untapped.gg tier list")]
    guide["sources"].append({"name": "Untapped.gg tier list", "url": live[0]["tierSource"]})
    return guide


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
