"""Fetch and slim the chunk.science Reality Fracture rating data (cached locally, never committed)."""
from __future__ import annotations

import json
import re
import urllib.request
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
