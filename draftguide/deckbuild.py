"""Heuristic deck suggestions for completed draft pools."""
from __future__ import annotations

from itertools import combinations

from .sealed import SCORE_THRESHOLDS


_COLORS = "WUBRG"
_COLOR_NAMES = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}
_SPELL_COUNT = 23


def _mana_value(card: dict) -> int | None:
    mana_cost = str(card.get("manaArena") or "")
    if not mana_cost:
        return None
    value = 0
    for symbol in mana_cost.split("o"):
        symbol = symbol.strip("()")
        if not symbol:
            continue
        if symbol.isdigit():
            value += int(symbol)
        elif "/" in symbol and any(part.isdigit() for part in symbol.split("/")):
            value += max(int(part) for part in symbol.split("/") if part.isdigit())
        elif symbol.upper() != "X":
            value += 1
    return value


def _creature(card: dict) -> bool:
    return "creature" in str(card.get("typeLine") or "").casefold()


def _eligible(card: dict, colors: set[str]) -> bool:
    card_colors = set(card.get("colors") or [])
    return not card.get("isLand") and card_colors.issubset(colors)


def _balance(cards: list[dict]) -> dict:
    creatures = sum(_creature(card) for card in cards)
    mana_values = [_mana_value(card) for card in cards]
    known_mana_costs = sum(value is not None for value in mana_values)
    early = sum(value is not None and value <= 2 for value in mana_values)
    top_end = sum(value is not None and value >= 5 for value in mana_values)
    counts = {}
    for value in mana_values:
        if value is None:
            continue
        counts[value] = counts.get(value, 0) + 1

    checks = [
        {
            "label": "Spell count",
            "value": f"{len(cards)}/{_SPELL_COUNT}",
            "status": "good" if len(cards) == _SPELL_COUNT else "warning",
            "detail": "Limited decks usually play 23 nonland cards.",
        },
        {
            "label": "Creatures",
            "value": str(creatures),
            "status": "good" if 14 <= creatures <= 17 else "warning",
            "detail": "A common target is 14–17 creatures.",
        },
        {
            "label": "Early plays",
            "value": str(early),
            "status": "good" if early >= 6 else "warning",
            "detail": f"Cards costing 1–2 mana; fewer than 6 may leave a slow start ({known_mana_costs} costs known).",
        },
        {
            "label": "Top end",
            "value": str(top_end),
            "status": "good" if top_end <= 5 else "warning",
            "detail": f"Cards costing 5+ mana; too many can clog your hand ({known_mana_costs} costs known).",
        },
    ]

    pips = {color: 0 for color in _COLORS}
    for card in cards:
        for symbol in str(card.get("manaArena") or "").split("o"):
            for color in _COLORS:
                if color in symbol:
                    pips[color] += 1
    return {
        "checks": checks,
        "curve": [{"manaValue": value, "count": counts[value]} for value in sorted(counts)],
        "knownManaCosts": known_mana_costs,
        "pips": {color: count for color, count in pips.items() if count},
    }


def analyze_pool(cards: list[dict], guide: dict | None = None) -> dict:
    """Rank two-color builds and report a rating-led 23-spell sample with balance checks."""
    if not cards:
        return {"builds": []}

    archetypes = {
        frozenset(item.get("colors") or []): item
        for item in (guide or {}).get("archetypes", [])
        if len(item.get("colors") or []) == 2
    }
    builds = []
    for colors in combinations(_COLORS, 2):
        color_set = set(colors)
        archetype = archetypes.get(frozenset(colors), {})
        eligible = [
            (index, card) for index, card in enumerate(cards)
            if _eligible(card, color_set)
        ]

        def card_order(item: tuple[int, dict]) -> tuple:
            card = item[1]
            score = card.get("score")
            return (
                -(float(score) if score is not None else -1),
                -int(_creature(card)),
                _mana_value(card) if _mana_value(card) is not None else 99,
                str(card.get("name") or "").casefold(),
                item[0],
            )

        ranked = sorted(eligible, key=card_order)
        deck_entries = ranked[:_SPELL_COUNT]
        deck = [card for _, card in deck_entries]
        selected = {index for index, _ in deck_entries}
        cut_cards = [
            (index, card) for index, card in enumerate(cards)
            if index not in selected and not card.get("isLand")
        ]
        cut_cards.sort(key=lambda item: (
            int(not set(item[1].get("colors") or []).issubset(color_set)),
            float(item[1]["score"]) if item[1].get("score") is not None else 101,
            str(item[1].get("name") or "").casefold(),
            item[0],
        ))
        rated_scores = [float(card["score"]) for card in deck if card.get("score") is not None]
        average = sum(rated_scores) / len(rated_scores) if rated_scores else 0
        colored = sum(bool(card.get("colors")) for card in deck)
        builds.append({
            "colors": list(colors),
            "name": archetype.get("name") or "-".join(_COLOR_NAMES[color] for color in colors),
            "tier": archetype.get("tier"),
            "eligibleCount": len(eligible),
            "averageScore": round(average, 1) if rated_scores else None,
            "cards": deck,
            "cuts": [
                {
                    **card,
                    "cutReason": (
                        "Outside these colors"
                        if not set(card.get("colors") or []).issubset(color_set)
                        else "Low grade" if card.get("score") is not None
                        and card["score"] < SCORE_THRESHOLDS["playable"]
                        else "Below the top 23"
                    ),
                }
                for _, card in cut_cards[:8]
            ],
            "balance": _balance(deck),
            "_rank": (
                average * len(deck) / _SPELL_COUNT + len(deck) * 0.15 + colored * 0.05,
                len(deck),
                colored,
            ),
        })

    builds.sort(key=lambda item: (-item["_rank"][0], -item["_rank"][1], -item["_rank"][2], item["name"]))
    for build in builds:
        del build["_rank"]
    return {"builds": builds}
