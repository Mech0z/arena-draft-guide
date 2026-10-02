"""Fetch and cache draft ratings from Card Game Base, chunk.science, and 17Lands."""
from __future__ import annotations

import csv
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import warnings
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

PAGE_URL = "https://chunk.science/mtga-reality-fracture.html"
DATA_RE = re.compile(r'/mtga-reality-fracture/data/fra\.[0-9a-f]+\.js[^"\']*')
USER_AGENT = "arena-draft-guide/0.1 (personal local use)"
BROWSER_USER_AGENT = "Mozilla/5.0 (compatible; arena-draft-guide/0.1)"

def _get(url: str, user_agent: str = USER_AGENT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
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
                "scale": sources[key].get("scale"),
                "sourceUrl": rating.get("sourceUrl") or sources[key].get("url"),
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


def slim_multisource(raw: dict) -> dict:
    """Keep numeric source ratings and attribution, but not reviewer commentary."""
    data = slim(raw)
    data["source"] = "Multi-source ratings"
    for card in data["cards"]:
        card["ratings"] = [{key: value for key, value in rating.items() if key != "comment"} for rating in card["ratings"]]
        card["notes"] = []
    return data


def load(cache: Path, refresh: bool = False) -> dict:
    if cache.exists() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8"))
    data = slim(fetch_raw())
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data

# --- any set: 17Lands card ratings ---

LANDS17_URL = "https://www.17lands.com/card_ratings/data?expansion={code}&format={fmt}"
LANDS17_PAGE = "https://www.17lands.com/card_ratings"
MIN_GAMES = 200
CACHE_TTL = 12 * 3600
CARDGAMEBASE_URLS = {
    "FRA": "https://cardgamebase.com/reality-fracture-draft-tier-list/",
    "WOE": "https://cardgamebase.com/wilds-of-eldraine-draft-tier-list/",
}
DRAFTSIM_WOE_URL = "https://draftsim.com/mtg-woe-limited-set-review/"
MTGAZONE_WOE_URLS = (
    "https://mtgazone.com/wilds-of-eldraine-limited-set-review-white/",
    "https://mtgazone.com/wilds-of-eldraine-limited-set-review-blue/",
    "https://mtgazone.com/wilds-of-eldraine-limited-set-review-black/",
    "https://mtgazone.com/wilds-of-eldraine-limited-set-review-red/",
    "https://mtgazone.com/wilds-of-eldraine-limited-set-review-green/",
    "https://mtgazone.com/wilds-of-eldraine-limited-set-review-artifacts-lands-and-multicolor-part-1/",
    "https://mtgazone.com/wilds-of-eldraine-limited-set-review-multicolor-part-2/",
    "https://mtgazone.com/wilds-of-eldraine-limited-set-review-enchanting-tales/",
)
# Ordinal UI scores preserve the grade order; they are not win-rate estimates.
CARDGAMEBASE_GRADES = {
    "A+": 100, "A": 97, "A-": 94,
    "B+": 89, "B": 86, "B-": 83,
    "C+": 78, "C": 75, "C-": 72,
    "D+": 67, "D": 64, "D-": 61,
    "F": 30,
}
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


class _TierTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.table_depth = 0
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.cards: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table":
            if self.table_depth or "tierlist" in (attributes.get("class") or "").split():
                self.table_depth += 1
        elif self.table_depth and tag == "tr":
            self.row = []
        elif self.table_depth and tag in ("td", "th"):
            self.cell = []

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self.table_depth:
            return
        if tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if len(self.row) >= 2 and self.row[1] in CARDGAMEBASE_GRADES:
                self.cards.append((self.row[0], self.row[1]))
            self.row = None
        elif tag == "table":
            self.table_depth -= 1


def parse_cardgamebase(html: str, code: str) -> dict:
    parser = _TierTableParser()
    parser.feed(html)
    if not parser.cards:
        raise RuntimeError(f"Could not find card grades for {code} on Card Game Base")

    ranked = sorted(parser.cards, key=lambda item: (-CARDGAMEBASE_GRADES[item[1]], item[0].casefold()))
    rank_by_name = {name: len(ranked) - index for index, (name, _grade) in enumerate(ranked)}
    rank_of = len(ranked)
    cards = []
    for name, grade in parser.cards:
        score = CARDGAMEBASE_GRADES[grade]
        cards.append({
            "id": name,
            "name": name,
            "collectorNumber": "",
            "colors": [],
            "manaCost": "",
            "typeLine": "",
            "rarity": "",
            "image": None,
            "score": score,
            "grade": grade,
            "rank": rank_by_name[name],
            "rankOf": rank_of,
            "colorRank": None,
            "colorRankOf": None,
            "signal": None,
            "ratings": [{
                "source": "Card Game Base",
                "grade": grade,
                "score": score,
                "scale": "A+ to F",
                "sourceUrl": CARDGAMEBASE_URLS[code],
                "comment": f"Draft grade {grade}",
            }],
            "notes": [],
        })
    return {
        "set": {"code": code},
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "attribution": CARDGAMEBASE_URLS[code],
        "source": "Card Game Base",
        "cards": cards,
    }


def fetch_cardgamebase(code: str) -> dict:
    url = CARDGAMEBASE_URLS[code]
    return parse_cardgamebase(_get(url).decode("utf-8"), code)


def _rating_name_key(name: str) -> str:
    import unicodedata
    normalized = unicodedata.normalize("NFKD", name.split(" // ", 1)[0]).casefold()
    return re.sub(r"[^a-z0-9]", "", normalized.encode("ascii", "ignore").decode("ascii"))


class _DraftsimRatingsParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_heading = False
        self.heading_parts: list[str] = []
        self.card_name = ""
        self.cards: list[tuple[str, float]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "h3":
            self.in_heading = True
            self.heading_parts = []

    def handle_data(self, data: str) -> None:
        if self.in_heading:
            self.heading_parts.append(data)
            return
        match = re.search(r"Rating:\s*(\d+(?:\.\d+)?)\s*/\s*10", data, re.IGNORECASE)
        if match and self.card_name:
            self.cards.append((self.card_name, float(match.group(1))))

    def handle_endtag(self, tag: str) -> None:
        if tag == "h3" and self.in_heading:
            self.card_name = " ".join("".join(self.heading_parts).split())
            self.in_heading = False


def parse_draftsim_woe(html: str) -> dict:
    parser = _DraftsimRatingsParser()
    parser.feed(html)
    cards_by_key = {}
    for name, grade in parser.cards:
        key = _rating_name_key(name)
        if not key:
            continue
        cards_by_key.setdefault(key, (name, grade))
    if not cards_by_key:
        raise RuntimeError("Could not find card grades in the Draftsim WOE review")
    cards = []
    for name, grade in cards_by_key.values():
        cards.append({
            "id": name,
            "name": name,
            "score": round(grade * 10),
            "grade": grade,
            "ratings": [{
                "source": "Draftsim",
                "grade": f"{grade:g}",
                "score": round(grade * 10),
                "scale": "0 to 10",
                "sourceUrl": DRAFTSIM_WOE_URL,
            }],
        })
    return {
        "set": {"code": "WOE"},
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "attribution": DRAFTSIM_WOE_URL,
        "source": "Draftsim",
        "cards": cards,
    }


def fetch_draftsim_woe() -> dict:
    return parse_draftsim_woe(_get(DRAFTSIM_WOE_URL, BROWSER_USER_AGENT).decode("utf-8"),)


class _MtgaZoneRatingsParser(HTMLParser):
    def __init__(self, source_url: str):
        super().__init__()
        self.source_url = source_url
        self.heading_tag: str | None = None
        self.heading_parts: list[str] = []
        self.card_name = ""
        self.cards: list[tuple[str, float]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("h2", "h3"):
            self.heading_tag = tag
            self.heading_parts = []

    def handle_data(self, data: str) -> None:
        if self.heading_tag:
            self.heading_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != self.heading_tag:
            return
        text = " ".join("".join(self.heading_parts).split())
        if tag == "h2":
            self.card_name = text
        elif (match := re.search(r"Rating:\s*(\d+(?:\.\d+)?)\s*/\s*5", text, re.IGNORECASE)):
            self.cards.append((self.card_name, float(match.group(1))))
        self.heading_tag = None


def parse_mtgazone_woe_page(html: str, source_url: str) -> dict:
    parser = _MtgaZoneRatingsParser(source_url)
    parser.feed(html)
    cards_by_key = {}
    for name, grade in parser.cards:
        key = _rating_name_key(name)
        if not key:
            continue
        cards_by_key.setdefault(key, (name, grade))
    cards = []
    for name, grade in cards_by_key.values():
        cards.append({
            "id": name,
            "name": name,
            "score": round(grade * 20),
            "grade": grade,
            "ratings": [{
                "source": "MTG Arena Zone",
                "grade": f"{grade:.1f}",
                "score": round(grade * 20),
                "scale": "0.0 to 5.0",
                "sourceUrl": source_url,
            }],
        })
    return {"source": "MTG Arena Zone", "cards": cards}


def fetch_mtgazone_woe() -> dict:
    cards_by_key = {}
    used_urls = []
    for url in MTGAZONE_WOE_URLS:
        html = _get(url, BROWSER_USER_AGENT).decode("utf-8")
        page = parse_mtgazone_woe_page(html, url)
        used_urls.append(url)
        for card in page["cards"]:
            cards_by_key.setdefault(_rating_name_key(card["name"]), card)
    if not cards_by_key:
        raise RuntimeError("Could not find card grades in the MTG Arena Zone WOE reviews")
    return {
        "set": {"code": "WOE"},
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "attribution": MTGAZONE_WOE_URLS[0],
        "sources": used_urls,
        "source": "MTG Arena Zone",
        "cards": list(cards_by_key.values()),
    }


def combine_woe_sources(sources: list[dict]) -> dict:
    by_key = {}
    coverage = {}
    catalog_keys = {
        _rating_name_key(card.get("name", ""))
        for source_data in sources
        if source_data.get("source") == "Card Game Base"
        for card in source_data.get("cards", [])
    }
    for source_data in sources:
        source_name = source_data.get("source") or (
            "17Lands" if "17lands.com" in source_data.get("attribution", "") else "Unknown"
        )
        matched = set()
        for source_card in source_data.get("cards", []):
            key = _rating_name_key(source_card.get("name", ""))
            if source_name == "17Lands" and key in by_key and source_card.get("image") and not by_key[key]["image"]:
                by_key[key]["image"] = source_card["image"]
            if not source_card.get("ratings"):
                continue
            if not key or (catalog_keys and source_name != "Card Game Base" and key not in catalog_keys):
                continue
            card = by_key.setdefault(key, {
                "id": source_card.get("id", source_card["name"]),
                "name": source_card["name"],
                "collectorNumber": "",
                "colors": [],
                "manaCost": "",
                "typeLine": "",
                "rarity": "",
                "image": source_card.get("image"),
                "score": None,
                "rank": None,
                "rankOf": None,
                "colorRank": None,
                "colorRankOf": None,
                "signal": None,
                "ratings": [],
                "notes": [],
            })
            existing = {rating["source"] for rating in card["ratings"]}
            for rating in source_card.get("ratings", []):
                if rating.get("source") in existing:
                    continue
                clean = {
                    key: value for key, value in rating.items()
                    if key != "comment" or rating.get("source") == "17Lands"
                }
                if clean["source"] == "Card Game Base":
                    clean.setdefault("scale", "A+ to F")
                    clean.setdefault("sourceUrl", CARDGAMEBASE_URLS["WOE"])
                elif clean["source"] == "17Lands":
                    clean.setdefault("scale", "GIH percentile")
                    clean.setdefault("sourceUrl", source_data.get("attribution"))
                card["ratings"].append(clean)
                existing.add(clean["source"])
                matched.add(key)
        coverage[source_name] = len(matched)

    cards = list(by_key.values())
    for card in cards:
        review_scores = [
            rating["score"] for rating in card["ratings"]
            if rating.get("source") != "17Lands" and rating.get("score") is not None
        ]
        empirical_scores = [rating["score"] for rating in card["ratings"] if rating.get("source") == "17Lands" and rating.get("score") is not None]
        scores = review_scores or empirical_scores
        card["score"] = round(sum(scores) / len(scores)) if scores else None
        card["ratings"].sort(key=lambda rating: (
            ("Card Game Base", "Draftsim", "MTG Arena Zone", "17Lands").index(rating["source"])
            if rating["source"] in ("Card Game Base", "Draftsim", "MTG Arena Zone", "17Lands") else 99
        ))

    ranked = sorted((card for card in cards if card["score"] is not None), key=lambda card: (-card["score"], card["name"].casefold()))
    for index, card in enumerate(ranked):
        card["rank"] = len(ranked) - index
        card["rankOf"] = len(ranked)
    cards.sort(key=lambda card: (card["score"] is None, -(card["score"] or 0), card["name"].casefold()))
    return {
        "set": {"code": "WOE", "name": "Wilds of Eldraine"},
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "attribution": CARDGAMEBASE_URLS["WOE"],
        "source": "Multi-source ratings",
        "sources": [
            *([{"name": "Card Game Base", "url": CARDGAMEBASE_URLS["WOE"]}] if coverage.get("Card Game Base") else []),
            *([{"name": "Draftsim", "url": DRAFTSIM_WOE_URL}] if coverage.get("Draftsim") else []),
            *([{"name": "MTG Arena Zone", "urls": list(MTGAZONE_WOE_URLS)}] if coverage.get("MTG Arena Zone") else []),
            *([{"name": "17Lands"}] if coverage.get("17Lands") else []),
        ],
        "sourceCoverage": coverage,
        "cards": cards,
    }


def _card_key(name: str) -> str:
    name = name.split(" // ", 1)[0]
    normalized = unicodedata.normalize("NFKD", name.replace("_", ""))
    return re.sub(r"[^a-z0-9]", "", normalized.encode("ascii", "ignore").decode().lower())


def apply_picklist_csv(data: dict, csv_path: Path) -> dict:
    """Merge source-specific 0..scale ratings and optional comments from a per-set CSV."""
    if not csv_path.exists():
        return data

    cards = {_card_key(card["name"]): card for card in data.get("cards", [])}
    by_source: dict[str, dict[str, tuple[float, float, str, str]]] = {}
    source_urls: dict[str, str] = {}
    with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            source = (row.get("source") or "").strip()
            name = (row.get("card_name") or "").strip()
            if not source or not name:
                continue
            card_key = _card_key(name)
            if card_key not in cards:
                continue
            try:
                value = float(row["rating"])
                scale = float(row["rating_scale"])
            except (KeyError, TypeError, ValueError):
                continue
            if scale <= 0 or value < 0 or value > scale:
                continue
            by_source.setdefault(source, {})[card_key] = (
                value,
                scale,
                (row.get("comment") or "").strip(),
                (row.get("source_url") or "").strip(),
            )
            if row.get("source_url"):
                source_urls[source] = row["source_url"].strip()

    for card_key, card in cards.items():
        ratings_by_source = {
            (rating.get("source") or "").casefold(): rating
            for rating in card.get("ratings", [])
            if rating.get("source")
        }
        for source, source_ratings in by_source.items():
            if card_key not in source_ratings:
                continue
            value, scale, comment, source_url = source_ratings[card_key]
            score = value / scale * 100
            ratings_by_source[source.casefold()] = {
                "source": source,
                "grade": f"{value:g}/{scale:g}",
                "score": round(score),
                "comment": comment,
                "sourceUrl": source_url,
            }
        card["ratings"] = list(ratings_by_source.values())
        expert_ratings = [
            rating for rating in card["ratings"]
            if "17lands" not in rating["source"].casefold() and rating.get("score") is not None
        ]
        if expert_ratings:
            average_score = sum(rating["score"] for rating in expert_ratings) / len(expert_ratings)
            card["averageRating"] = average_score / 20
            card["ratingSourceCount"] = len(expert_ratings)
            card["score"] = round(average_score)

    if by_source:
        data["supplementalSources"] = [
            {"name": source, "url": source_urls.get(source, "")}
            for source in by_source
        ]
        if not data.get("attribution") and source_urls:
            data["attribution"] = next(iter(source_urls.values()))

    rated_cards = [card for card in cards.values() if card.get("averageRating") is not None]
    rated_cards.sort(key=lambda card: (-card["score"], card["name"].casefold()))
    for rank, card in enumerate(rated_cards, start=1):
        card["rank"], card["rankOf"] = rank, len(rated_cards)
    return data




class Store:
    """Per-set rating caches, combining independent grades where available."""

    def __init__(self, cache_dir: Path, refresh: bool = False):
        self.cache_dir = cache_dir
        self.refresh = refresh

    def _write_cache(self, cache: Path, data: dict) -> dict:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data

    def _cached_source(self, cache_name: str, fetcher) -> dict:
        cache = self.cache_dir / cache_name
        if cache.exists() and not self.refresh and time.time() - cache.stat().st_mtime < CACHE_TTL:
            return json.loads(cache.read_text(encoding="utf-8"))
        try:
            data = fetcher()
        except Exception as exc:
            if cache.exists():
                print(f"Warning: rating source refresh failed for {cache_name} ({exc}); using cached data.")
                return json.loads(cache.read_text(encoding="utf-8"))
            raise
        return self._write_cache(cache, data)

    def _get_woe(self, fmt: str) -> dict:
        cache = self.cache_dir / f"multi-source-WOE-{fmt}.json"
        if cache.exists() and not self.refresh and time.time() - cache.stat().st_mtime < CACHE_TTL:
            return json.loads(cache.read_text(encoding="utf-8"))

        source_specs = [
            ("Card Game Base", "cardgamebase-WOE.json", lambda: fetch_cardgamebase("WOE")),
            ("Draftsim", "draftsim-WOE.json", fetch_draftsim_woe),
            ("MTG Arena Zone", "mtgazone-WOE.json", fetch_mtgazone_woe),
            ("17Lands", f"17l-WOE-{fmt}.json", lambda: fetch_17lands("WOE", fmt)),
        ]
        sources = []
        for name, cache_name, fetcher in source_specs:
            try:
                data = self._cached_source(cache_name, fetcher)
            except Exception as exc:
                print(f"Warning: {name} WOE ratings unavailable ({exc}).")
                continue
            if name == "17Lands" and not any(card.get("ratings") for card in data.get("cards", [])):
                print(f"Warning: 17Lands has no usable WOE ratings for {fmt}; keeping its image data only.")
            sources.append(data)
        if not sources:
            raise RuntimeError("No WOE card-rating sources are currently available")
        return self._write_cache(cache, combine_woe_sources(sources))

    def _get_fra(self) -> dict:
        cache = self.cache_dir / "multi-source-FRA.json"
        if cache.exists() and not self.refresh and time.time() - cache.stat().st_mtime < CACHE_TTL:
            return json.loads(cache.read_text(encoding="utf-8"))
        try:
            data = slim_multisource(fetch_raw())
        except Exception as aggregate_error:
            fallback_cache = self.cache_dir / "cardgamebase-FRA.json"
            if fallback_cache.exists():
                return json.loads(fallback_cache.read_text(encoding="utf-8"))
            try:
                fallback = fetch_cardgamebase("FRA")
            except Exception as fallback_error:
                raise RuntimeError(
                    f"Could not fetch FRA multi-source ratings ({aggregate_error}) "
                    f"or Card Game Base fallback ({fallback_error})"
                ) from fallback_error
            return self._write_cache(fallback_cache, fallback)
        return self._write_cache(cache, data)

    def get(self, code: str, fmt: str = "PremierDraft") -> dict:
        code = code.upper()
        picklist_path = self.cache_dir / "picklists" / f"{code}.csv"
        try:
            data = self._get_public(code, fmt)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
            if not picklist_path.exists():
                raise
            warnings.warn(f"{code} public ratings unavailable; using local picklist CSV: {exc}", RuntimeWarning)
            cards = {}
            with picklist_path.open("r", encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream):
                    name = (row.get("card_name") or "").strip()
                    if name:
                        cards.setdefault(_card_key(name), {
                            "name": name.replace("_", " "), "score": None,
                            "rank": None, "rankOf": None, "ratings": [], "notes": [],
                        })
            data = {"set": {"code": code}, "cards": list(cards.values()), "attribution": ""}
        return apply_picklist_csv(data, picklist_path)

    def _get_public(self, code: str, fmt: str = "PremierDraft") -> dict:
        code = code.upper()
        if code == "FRA":
            return self._get_fra()
        if code == "WOE":
            return self._get_woe(fmt)
        if code in CARDGAMEBASE_URLS:
            cache = self.cache_dir / f"cardgamebase-{code}.json"
            if cache.exists() and not self.refresh and time.time() - cache.stat().st_mtime < CACHE_TTL:
                return json.loads(cache.read_text(encoding="utf-8"))
            try:
                data = fetch_cardgamebase(code)
            except Exception:
                if cache.exists():
                    return json.loads(cache.read_text(encoding="utf-8"))
                raise
            return self._write_cache(cache, data)
        cache = self.cache_dir / f"17l-{code}-{fmt}.json"
        if cache.exists() and not self.refresh and time.time() - cache.stat().st_mtime < CACHE_TTL:
            return json.loads(cache.read_text(encoding="utf-8"))
        try:
            data = fetch_17lands(code, fmt)
        except Exception:
            if cache.exists():
                return json.loads(cache.read_text(encoding="utf-8"))
            raise
        return self._write_cache(cache, data)