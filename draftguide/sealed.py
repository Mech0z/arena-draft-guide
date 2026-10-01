"""Sealed-pool summaries and heuristic archetype fit estimates."""
from __future__ import annotations


_BOMB_SCORE = 90
_STRONG_SCORE = 80
_PLAYABLE_SCORE = 65
_DECK_SIZE = 23
_GOOD_TIERS = {"S", "A+", "A", "A-", "B+", "B"}
_TIER_ORDER = {"S": 0, "A+": 1, "A": 2, "A-": 3, "B+": 4, "B": 5, "B-": 6, "C+": 7, "C": 8, "C-": 9, "D": 10, "F": 11}


def _tier_key(tier) -> str:
    return str(tier or "").strip().upper().removeprefix("TIER ").replace("−", "-")


def analyze_archetypes(cards: list[dict], guide: dict | None) -> list[dict]:
    """Estimate color-pair support from card grades, alongside the set's archetype tier."""
    if not guide:
        return []

    analyses = []
    for archetype in guide.get("archetypes", []):
        pair = set(archetype.get("colors") or [])
        eligible = []
        for card in cards:
            if card.get("isLand"):
                continue
            card_colors = set(card.get("colors") or [])
            if card_colors and not card_colors.issubset(pair):
                continue
            eligible.append(card)

        rated_copies = []
        playable_count = strong_count = bomb_count = 0
        for card in eligible:
            score = card.get("score")
            count = max(0, int(card.get("count") or 0))
            if score is None or not count:
                continue
            rated_copies.extend([float(score)] * count)
            if score >= _PLAYABLE_SCORE:
                playable_count += count
            if score >= _STRONG_SCORE:
                strong_count += count
            if score >= _BOMB_SCORE:
                bomb_count += count

        top_scores = sorted(rated_copies, reverse=True)[:_DECK_SIZE]
        top_average = sum(top_scores) / len(top_scores) if top_scores else None
        tier = _tier_key(archetype.get("tier"))
        high_tier = tier in _GOOD_TIERS
        if playable_count >= 20 and strong_count >= 6 and bomb_count >= 1 and high_tier:
            potential, potential_rank = "Excellent fit", 3
        elif playable_count >= 18 and strong_count >= 4 and (bomb_count or high_tier):
            potential, potential_rank = "Promising", 2
        elif playable_count >= 15 and strong_count >= 3:
            potential, potential_rank = "Playable pool", 1
        else:
            potential, potential_rank = "Needs support", 0

        analyses.append({
            "colors": archetype.get("colors", []),
            "name": archetype.get("name", ""),
            "focus": archetype.get("focus", ""),
            "tier": archetype.get("tier"),
            "tierSource": archetype.get("tierSource"),
            "eligibleCards": sum(int(card.get("count") or 0) for card in eligible),
            "playables": playable_count,
            "strong": strong_count,
            "bombs": bomb_count,
            "top23Average": round(top_average, 1) if top_average is not None else None,
            "potential": potential,
            "potentialRank": potential_rank,
        })

    return sorted(
        analyses,
        key=lambda item: (
            -item["potentialRank"],
            -(item["top23Average"] if item["top23Average"] is not None else -1),
            _TIER_ORDER.get(_tier_key(item["tier"]), 99),
            item["name"].casefold(),
        ),
    )
