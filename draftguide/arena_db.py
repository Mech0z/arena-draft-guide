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


def load_names(db_path: Path) -> dict[int, str]:
    return {grp: name for grp, (name, _land) in load_cards(db_path).items()}
