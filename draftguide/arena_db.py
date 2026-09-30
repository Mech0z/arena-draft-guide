"""Map Arena card ids (GrpId) to names using the game's local card database (read-only)."""
from __future__ import annotations

import glob
import os
import sqlite3
from pathlib import Path

_CANDIDATE_GLOBS = [
    r"*:\SteamLibrary\steamapps\common\MTGA\MTGA_Data\Downloads\Raw\Raw_CardDatabase_*.mtga",
    r"C:\Program Files (x86)\Steam\steamapps\common\MTGA\MTGA_Data\Downloads\Raw\Raw_CardDatabase_*.mtga",
    r"C:\Program Files\Wizards of the Coast\MTGA\MTGA_Data\Downloads\Raw\Raw_CardDatabase_*.mtga",
    r"C:\Program Files (x86)\Wizards of the Coast\MTGA\MTGA_Data\Downloads\Raw\Raw_CardDatabase_*.mtga",
]


def find_database() -> Path | None:
    env = os.environ.get("MTGA_CARD_DB")
    if env and Path(env).exists():
        return Path(env)
    found: list[str] = []
    for drive in "CDEFGH":
        for pattern in _CANDIDATE_GLOBS:
            found += glob.glob(pattern.replace("*:", drive + ":", 1))
    if not found:
        return None
    return Path(max(found, key=os.path.getmtime))


def load_cards(db_path: Path) -> dict[int, tuple[str, bool]]:
    """GrpId -> (English name, is_land)."""
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT c.GrpId, l.Loc, c.Types FROM Cards c "
            "JOIN Localizations_enUS l ON l.LocId = c.TitleId"
        ).fetchall()
    finally:
        con.close()
    return {int(grp): (name, "5" in str(types or "").split(",")) for grp, name, types in rows}


def load_details(db_path: Path) -> dict[int, tuple[str, str]]:
    """GrpId -> (Arena mana text such as 'o2oB', type line such as 'Creature - Zombie Cleric')."""
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT c.GrpId, c.OldSchoolManaText, t.Loc, s.Loc FROM Cards c "
            "LEFT JOIN Localizations_enUS t ON t.LocId = c.TypeTextId "
            "LEFT JOIN Localizations_enUS s ON s.LocId = c.SubtypeTextId"
        ).fetchall()
    finally:
        con.close()
    out = {}
    for grp, mana, types, subtypes in rows:
        line = types or ""
        if subtypes:
            line += " \u2014 " + subtypes
        out[int(grp)] = (mana or "", line)
    return out


def load_names(db_path: Path) -> dict[int, str]:
    return {grp: name for grp, (name, _land) in load_cards(db_path).items()}


_COLOR_LETTERS = {"1": "W", "2": "U", "3": "B", "4": "R", "5": "G"}


def _letters(text) -> str:
    return "".join(_COLOR_LETTERS[x] for x in str(text or "").split(",") if x in _COLOR_LETTERS)


def load_instant_speed(db_path: Path) -> dict[int, dict]:
    """GrpId -> info for instants and flash permanents (non-token, primary faces)."""
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT c.GrpId, l.Loc, c.OldSchoolManaText, c.ExpansionCode, c.Types, c.AbilityIds, c.Colors "
            "FROM Cards c JOIN Localizations_enUS l ON l.LocId = c.TitleId "
            "WHERE c.IsToken = 0 AND c.IsPrimaryCard = 1"
        ).fetchall()
    finally:
        con.close()
    out = {}
    for grp, name, mana, expansion, types, abilities, colors in rows:
        type_ids = str(types or "").split(",")
        flash = any(a.split(":")[0] == "7" for a in str(abilities or "").split(","))
        if "4" in type_ids or flash:
            out[int(grp)] = {
                "name": name, "mana": mana or "", "set": expansion or "",
                "kind": "Instant" if "4" in type_ids else "Flash", "colors": _letters(colors),
            }
    return out


def load_land_colors(db_path: Path) -> dict[int, str]:
    """GrpId -> colours a land can produce, approximated by its colour identity."""
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT GrpId, ColorIdentity, Types FROM Cards WHERE Types LIKE '%5%'").fetchall()
    finally:
        con.close()
    return {int(g): _letters(ci) for g, ci, types in rows if "5" in str(types).split(",")}
