"""Fetch and slim the chunk.science Reality Fracture rating data (cached locally, never committed)."""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PAGE_URL = "https://chunk.science/mtga-reality-fracture.html"
DATA_RE = re.compile(r'/mtga-reality-fracture/data/fra\.[0-9a-f]+\.js[^"\']*')
USER_AGENT = "arena-draft-guide/0.1 (personal local use)"


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def fetch_raw() -> dict:
    page = _get(PAGE_URL).decode("utf-8")
    match = DATA_RE.search(page)
    if not match:
        raise RuntimeError("Could not find the FRA data script on the ratings page")
    script = _get("https://chunk.science" + match.group(0)).decode("utf-8")
    return json.loads(script[script.index("{"):].rstrip().rstrip(";"))


def slim(raw: dict) -> dict:
    sources = raw["sources"]
    notes: dict[str, list[dict]] = {}
    cn = raw.get("creatorNotes", {})
    cn_sources = cn.get("sources", {})
    for note in cn.get("notes", []):
        name = cn_sources.get(note["sourceKey"], sources.get(note["sourceKey"], {})).get("name", note["sourceKey"])
        notes.setdefault(note["cardId"], []).append({"source": name, "text": note["summary"]})

    cards = []
    for card in raw["cards"]:
        ratings = []
        for key in raw["sourceOrder"]:
            rating = card["ratings"].get(key)
            if not rating or rating.get("normalized") is None:
                continue
            ratings.append({
                "source": sources[key]["short"],
                "grade": rating.get("native"),
                "score": rating["normalized"],
                "comment": rating.get("comment"),
            })
        cons = card.get("consensus") or {}
        cards.append({
            "id": card["id"],
            "name": card["name"],
            "collectorNumber": card["collectorNumber"],
            "colors": card.get("colors", []),
            "manaCost": card.get("manaCost", ""),
            "typeLine": card.get("typeLine", ""),
            "rarity": card.get("rarity", ""),
            "image": card.get("image"),
            "score": cons.get("score"),
            "rank": cons.get("overallRank"),
            "rankOf": cons.get("overallOf"),
            "colorRank": cons.get("rank"),
            "colorRankOf": cons.get("of"),
            "signal": cons.get("signal"),
            "ratings": ratings,
            "notes": notes.get(card["id"], []),
        })
    return {
        "set": raw["set"],
        "generatedAt": raw["generatedAt"],
        "attribution": PAGE_URL,
        "cards": cards,
    }


def load(cache: Path, refresh: bool = False) -> dict:
    if cache.exists() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8"))
    data = slim(fetch_raw())
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data

# --- any set: 17Lands card ratings (used when chunk.science has no page for the set) ---

CHUNK_SETS = {"FRA"}
LANDS17_URL = "https://www.17lands.com/card_ratings/data?expansion={code}&format={fmt}"
LANDS17_PAGE = "https://www.17lands.com/card_ratings"
MIN_GAMES = 200
CACHE_TTL = 12 * 3600
_EVENT_RE = re.compile(r"^(?P<fmt>[A-Za-z]+?)_(?P<code>[A-Za-z0-9]{2,6})_")
_FORMATS = {"PremierDraft", "QuickDraft", "TradDraft", "Sealed", "TradSealed", "PickTwoDraft"}


def parse_event(event_name: str | None) -> tuple[str, str] | None:
    """'PremierDraft_FDN_20241111' -> ('PremierDraft', 'FDN'); None when no set code is present."""
    match = _EVENT_RE.match(event_name or "")
    if not match:
        return None
    fmt = match.group("fmt")
    if fmt.lower().startswith("traditional"):
        fmt = "TradDraft"
    return (fmt if fmt in _FORMATS else "PremierDraft"), match.group("code").upper()


def slim_17lands(rows: list[dict], code: str, fmt: str) -> dict:
    """17Lands card_ratings rows -> same shape as slim(); score is the GIH win-rate percentile (0-100)."""
    rated = sorted(
        (r for r in rows if (r.get("ever_drawn_game_count") or 0) >= MIN_GAMES and r.get("ever_drawn_win_rate") is not None),
        key=lambda r: r["ever_drawn_win_rate"],
    )
    rank_of = len(rated)
    position = {id(r): i for i, r in enumerate(rated)}
    cards = []
    for r in rows:
        card = {
            "id": str(r.get("mtga_id")),
            "name": r["name"],
            "collectorNumber": "",
            "colors": list(r.get("color") or ""),
            "manaCost": "",
            "typeLine": (r.get("types") or [""])[0],
            "rarity": r.get("rarity", ""),
            "image": r.get("url") or None,
            "score": None, "rank": None, "rankOf": rank_of or None,
            "colorRank": None, "colorRankOf": None, "signal": None,
            "ratings": [], "notes": [],
        }
        if id(r) in position:
            i = position[id(r)]
            card["score"] = round(100 * i / max(rank_of - 1, 1))
            card["rank"] = rank_of - i
            bits = [f"GIH WR {r['ever_drawn_win_rate']:.1%}"]
            if r.get("drawn_improvement_win_rate") is not None:
                bits.append(f"IWD {r['drawn_improvement_win_rate'] * 100:+.1f}pp")
            if r.get("avg_pick") is not None:
                bits.append(f"ATA {r['avg_pick']:.1f}")
            bits.append(f"{r['ever_drawn_game_count']:,} games")
            card["ratings"] = [{"source": "17Lands", "grade": None, "score": card["score"], "comment": " · ".join(bits)}]
        cards.append(card)
    return {
        "set": {"code": code},
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "attribution": f"{LANDS17_PAGE}?expansion={code}&format={fmt}",
        "cards": cards,
    }


def fetch_17lands(code: str, fmt: str) -> dict:
    url = LANDS17_URL.format(code=urllib.parse.quote(code), fmt=urllib.parse.quote(fmt))
    return slim_17lands(json.loads(_get(url).decode("utf-8")), code, fmt)


class Store:
    """Per-set rating data with an on-disk cache. FRA uses chunk.science; every other set uses 17Lands."""

    def __init__(self, cache_dir: Path, refresh: bool = False):
        self.cache_dir = cache_dir
        self.refresh = refresh

    def get(self, code: str, fmt: str = "PremierDraft") -> dict:
        code = code.upper()
        if code in CHUNK_SETS:
            return load(self.cache_dir / f"{code.lower()}.json", refresh=self.refresh)
        cache = self.cache_dir / f"17l-{code}-{fmt}.json"
        if cache.exists() and not self.refresh and time.time() - cache.stat().st_mtime < CACHE_TTL:
            return json.loads(cache.read_text(encoding="utf-8"))
        try:
            data = fetch_17lands(code, fmt)
        except Exception:
            if cache.exists():
                return json.loads(cache.read_text(encoding="utf-8"))
            raise
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data