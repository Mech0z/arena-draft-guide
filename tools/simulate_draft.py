"""Write a fake Quick Draft session into a log file so the guide can be tried without Arena.

    py -3.12 tools/simulate_draft.py --log sim.log --interval 4
    py -3.12 -m draftguide --log sim.log --port 8780

A new pack (one card fewer, the simulated "pick" removed) is appended every --interval seconds.
Uses real Reality Fracture card ids from your local Arena card database.
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from draftguide import arena_db  # noqa: E402


def set_ids(db: Path, code: str) -> list[int]:
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT GrpId FROM Cards WHERE ExpansionCode=? AND IsPrimaryCard=1 AND IsToken=0 "
            "AND Rarity BETWEEN 2 AND 5 AND Types NOT LIKE '%5%'", (code,)
        ).fetchall()
    finally:
        con.close()
    return [int(r[0]) for r in rows]


def line(pack: list[int], picked: list[int], pick_no: int, code: str = "FRA") -> str:
    body = {"result": {"EventName": f"QuickDraft_{code}_20260929", "PackNumber": 0, "PickNumber": pick_no,
                       "DraftPack": [str(i) for i in pack], "PickedCards": [str(i) for i in picked]}}
    return json.dumps(body) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", type=Path, required=True)
    ap.add_argument("--interval", type=float, default=4.0)
    ap.add_argument("--picks", type=int, default=5, help="how many picks to simulate")
    ap.add_argument("--set", default="FRA", help="set code, e.g. FDN")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    db = arena_db.find_database()
    if db is None:
        sys.exit("Arena card database not found (set MTGA_CARD_DB).")
    rng = random.Random(args.seed)
    pack = rng.sample(set_ids(db, args.set.upper()), 14)
    picked: list[int] = []
    args.log.write_text("", encoding="utf-8")
    for pick_no in range(args.picks):
        with args.log.open("a", encoding="utf-8") as f:
            f.write(line(pack, picked, pick_no, args.set.upper()))
        print(f"pick {pick_no + 1}: pack of {len(pack)} written")
        time.sleep(args.interval)
        choice = pack.pop(rng.randrange(len(pack)))
        picked.append(choice)


if __name__ == "__main__":
    main()
