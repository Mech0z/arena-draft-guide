"""Untapped.gg limited pick-order and color-combination tier list (public pages, parsed from the page data)."""
from __future__ import annotations

import html
import json
import re
import unicodedata
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

BASE = "https://mtga.untapped.gg/limited/draft/{slug}/{page}"
USER_AGENT = "Mozilla/5.0 (compatible; arena-draft-guide/0.1)"
SOURCE = "Untapped.gg"
COLOR_LETTERS = {0: "C", 1: "W", 2: "U", 3: "B", 4: "R", 5: "G"}
RARITY_NAMES = {2: "common", 3: "uncommon", 4: "rare", 5: "mythic"}
MIN_OFFERS = 50
TOP_N = 5

_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)

GUILDS = {
    "azorius": "WU", "dimir": "UB", "rakdos": "BR", "gruul": "RG", "selesnya": "GW",
    "orzhov": "WB", "izzet": "UR", "golgari": "BG", "boros": "RW", "simic": "GU",
    "esper": "WUB", "grixis": "UBR", "jund": "BRG", "naya": "RGW", "bant": "GWU",
    "mardu": "RWB", "temur": "GUR", "abzan": "WBG", "jeskai": "URW", "sultai": "BGU",
    "mono white": "W", "mono blue": "U", "mono black": "B", "mono red": "R", "mono green": "G",
}


def slugify(name: str) -> str:
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower().replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-")


def slug_candidates(name: str) -> list[str]:
    slugs = []
    for part in [name, *(name.split(": ", 1) if ": " in name else [])]:
        slug = slugify(part)
        if slug and slug not in slugs:
            slugs.append(slug)
    return slugs


def _get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def _next_props(page: str) -> dict:
    match = _NEXT_DATA.search(page)
    if not match:
        raise RuntimeError("Untapped.gg page has no embedded data")
    return json.loads(match.group(1))["props"]["pageProps"]["ssrProps"]


def parse_pick_order(page: str, code: str, url: str) -> dict:
    """Per-card average pick (lower is earlier) plus color/rarity for per-color top-pick rankings."""
    props = _next_props(page)
    mtga = props["minifiedMtgaJsonData"]
    names = {row[0]: row[1] for row in mtga["localeData"]}
    cards_by_title = {}
    for row in mtga["cardData"]:
        if row[6] != code or row[5]:
            continue
        cards_by_title.setdefault(row[1], row)

    picks = []
    for entry in props["limitedDraftInfo"]["data"]:
        row = cards_by_title.get(entry["title_id"])
        name = names.get(entry["title_id"])
        if row is None or not name:
            continue
        offered = entry.get("offered_qty") or {}
        total = sum(offered.values())
        if total < MIN_OFFERS:
            continue
        average = sum(value * offered.get(rank, 0) for rank, value in (entry.get("avg_pick_chosen") or {}).items()) / total
        colors = [COLOR_LETTERS[c] for c in (row[14] or []) if c in COLOR_LETTERS and c != 0]
        picks.append({"name": name, "avgPick": round(average, 2), "colors": colors, "rarity": RARITY_NAMES.get(row[9], "common"), "offered": total})
    if not picks:
        raise RuntimeError(f"No Untapped.gg pick-order data found for {code}")

    order = sorted(picks, key=lambda card: (card["avgPick"], card["name"].casefold()))
    by_rarity: dict[str, list[dict]] = defaultdict(list)
    for card in order:
        by_rarity[card["rarity"]].append(card)
    top_picks: dict[str, list[str]] = defaultdict(list)
    for rarity, group in by_rarity.items():
        for color in "WUBRG":
            in_color = [card for card in group if card["colors"] == [color]]
            for position, card in enumerate(in_color[:TOP_N], start=1):
                top_picks[card["name"]].append(f"#{position} {rarity} in {color}")

    cards = []
    for rarity, group in by_rarity.items():
        count = len(group)
        for index, card in enumerate(group):
            score = round(100 * (count - 1 - index) / max(count - 1, 1))
            cards.append({
                "id": card["name"],
                "pickOrder": {"avgPick": card["avgPick"], "rank": index + 1, "rankOf": count, "rarity": rarity, "score": score},
                "name": card["name"],
                "score": score,
                "avgPick": card["avgPick"],
                "topPicks": top_picks.get(card["name"], []),
                "ratings": [{
                    "source": SOURCE,
                    "grade": f"ATA {card['avgPick']:.1f} (#{index + 1} {rarity})",
                    "score": score,
                    "scale": "avg pick",
                    "sourceUrl": url,
                }],
            })

    return {
        "set": {"code": code},
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "attribution": url,
        "source": SOURCE,
        "cards": cards,
    }


def parse_tier_list(page: str, url: str) -> list[dict]:
    """Color-combination tiers (A-D, '?' = low match volume) with 6+ win rate and match counts."""
    body = page.split('<script id="__NEXT_DATA__"')[0]
    body = re.sub(r"<style.*?</style>", "", body, flags=re.S)
    text = html.unescape(re.sub(r"\|+", "|", re.sub(r"<[^>]+>", "|", body)))
    start = text.find("|Tier|")
    end = text.find("What Do the Tiers Mean")
    if start == -1:
        raise RuntimeError("Could not find the Untapped.gg tier list")
    tokens = [token.strip() for token in text[start:end if end > start else None].split("|") if token.strip()]
    results = []
    tier = None
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "Tier" and index + 1 < len(tokens) and len(tokens[index + 1]) <= 2:
            tier = tokens[index + 1]
            index += 2
            continue
        colors = GUILDS.get(token.lower())
        if (colors and tier and index + 2 < len(tokens) and tokens[index + 1].endswith("%")
                and re.fullmatch(r"[\d,]+", tokens[index + 2])):
            results.append({
                "colors": sorted(colors, key="WUBRG".index),
                "name": token,
                "tier": tier if tier in ("A", "B", "C", "D") else None,
                "sixPlusWinRate": float(tokens[index + 1].rstrip("%")),
                "matches": int(tokens[index + 2].replace(",", "")),
                "tierSource": url,
            })
            index += 3
            continue
        index += 1
    if not results:
        raise RuntimeError("Could not parse the Untapped.gg tier list")
    return results


def _fetch_page(slugs: list[str], page_name: str, parse):
    last_error: Exception = RuntimeError("No Untapped.gg set slug known")
    for slug in slugs:
        url = BASE.format(slug=slug, page=page_name)
        try:
            return parse(_get(url), url)
        except Exception as exc:
            last_error = exc
    raise last_error


def fetch_pick_order(code: str, slugs: list[str]) -> dict:
    return _fetch_page(slugs, "pick-order", lambda page, url: parse_pick_order(page, code, url))


def fetch_tier_list(slugs: list[str]) -> list[dict]:
    return _fetch_page(slugs, "tier-list", parse_tier_list)
