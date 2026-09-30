"""Which instant-speed spells can the opponent cast with the mana they have untapped."""
from __future__ import annotations

_BASIC = {"SubType_Plains": "W", "SubType_Island": "U", "SubType_Swamp": "B", "SubType_Mountain": "R", "SubType_Forest": "G"}


def parse_cost(text: str) -> tuple[int, list[frozenset[str]]]:
    """Arena mana text ('o2oB', 'o1o(W/B)') -> (generic mana, list of coloured symbols as colour options).

    X counts as 0. Phyrexian symbols may be paid with life, so they are dropped.
    """
    generic = 0
    coloured: list[frozenset[str]] = []
    for sym in (text or "").split("o"):
        sym = sym.strip("()")
        if not sym or sym == "X":
            continue
        if sym.isdigit():
            generic += int(sym)
            continue
        parts = sym.split("/")
        if "P" in parts:
            continue
        options = frozenset(p for p in parts if p in "WUBRG" and len(p) == 1)
        if options:
            coloured.append(options)
        elif all(p.isdigit() for p in parts):
            generic += min(int(p) for p in parts)
    return generic, coloured


def can_pay(cost: str, pool: list[frozenset[str]]) -> bool:
    """True if the untapped mana sources (each produces one mana of one of its colours) can pay cost."""
    generic, coloured = parse_cost(cost)
    if generic + len(coloured) > len(pool):
        return False

    def assign(i: int, free: list[frozenset[str]]) -> bool:
        if i == len(coloured):
            return len(free) >= generic
        for idx, source in enumerate(free):
            if source & coloured[i] and assign(i + 1, free[:idx] + free[idx + 1:]):
                return True
        return False

    return assign(0, list(pool))


def land_colours(grp: int, subtypes: list[str], land_colors: dict[int, str]) -> frozenset[str]:
    basics = {_BASIC[s] for s in subtypes if s in _BASIC}
    return frozenset(basics or land_colors.get(grp, ""))


def guide(lands: list[tuple[int, list[str], bool]], seen: list[int], info: dict[int, dict],
          land_colors: dict[int, str], pool_set: str = "FRA") -> dict:
    """Build the instant-speed view from the opponent's lands and publicly seen cards."""
    untapped = [land_colours(g, s, land_colors) for g, s, tapped in lands if not tapped]
    all_colours: set[str] = set()
    for g, s, _tapped in lands:
        all_colours |= land_colours(g, s, land_colors)
    for grp in seen:
        card = info.get(grp)
        if card:
            all_colours |= set(card["colors"])
    shown, shown_names = [], set()
    for grp in seen:
        card = info.get(grp)
        if card and card["name"] not in shown_names:
            shown_names.add(card["name"])
            shown.append({"grp": grp, **card, "castable": can_pay(card["mana"], untapped)})
    possible, names = [], set(shown_names)
    for grp, card in sorted(info.items(), key=lambda kv: (kv[1]["name"], kv[0])):
        if card["set"] != pool_set or card["name"] in names:
            continue
        if card["colors"] and not set(card["colors"]) <= all_colours:
            continue
        if can_pay(card["mana"], untapped):
            names.add(card["name"])
            possible.append({"grp": grp, **card, "castable": True})
    shown.sort(key=lambda c: (not c["castable"], c["name"]))
    return {
        "untapped": len(untapped),
        "lands": len(lands),
        "colours": "".join(c for c in "WUBRG" if c in all_colours),
        "shown": shown,
        "possible": possible,
    }
