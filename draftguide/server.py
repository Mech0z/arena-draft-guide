"""Local HTTP server: serves the page and the live pack state derived from Player.log."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from . import archetypes, arena_db, history, instants, logparse, ratings, sealed

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
DEFAULT_LOG = Path(os.environ.get("USERPROFILE", "~")) / "AppData/LocalLow/Wizards Of The Coast/MTGA/Player.log"
TIER_REFRESH = 7 * 24 * 3600
TIER_RETRY = 600
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}


def _norm(name: str) -> str:
    return name.casefold().strip()


_LIMITED_EVENT = re.compile(
    r"^(?:PremierDraft|QuickDraft|TradDraft|Traditional_Draft|PickTwoDraft|Sealed|TradSealed)_(?P<set>[A-Za-z0-9]{2,6})(?:_|$)",
    re.IGNORECASE,
)


class Guide:
    def __init__(self, data: dict, names: dict[int, str], log_path: Path, demo: bool = False, lands: set[int] | None = None, details: dict | None = None,
                 instant_info: dict | None = None, land_colors: dict | None = None,
                 expansions: dict | None = None, provider=None, archetype_dir: Path | None = None, tier_provider=None,
                 colors: dict[int, str] | None = None, history_path: Path | None = None):
        self.expansions = expansions or {}
        self.colors = colors or {}
        self.provider = provider
        self.tier_provider = tier_provider
        self.archetype_revision = 0
        self.archetype_dir = archetype_dir or ROOT / "guides" / "archetypes"
        self.archetype_cache: dict[str, tuple[int, dict | None, float, bool, int]] = {}
        self.indexes: dict[tuple[str, str], dict | None] = {}
        self.fail_until: dict[tuple[str, str], float] = {}
        self.current_set: str | None = None
        self.current_fmt = "PremierDraft"
        self.set_data: dict[str, dict] = {}
        self.details = details or {}
        self.instant_info = instant_info or {}
        self.land_colors = land_colors or {}
        self.data = data or {"cards": []}
        self.history = history.HistoryStore(history_path)
        self.names = names
        self.lands = lands or set()
        self.log_path = log_path
        self.demo = demo
        self.state = logparse.DraftLogState()
        self.updated_at: float | None = None
        self.lock = threading.Lock()
        self.default_set = (((data or {}).get("set") or {}).get("code") or "").upper() or None
        if data:
            self.set_data[self.default_set or ""] = data
            self.indexes[(self.default_set or "", "*")] = self._index(data)

    @staticmethod
    def _index(data: dict) -> dict[str, dict]:
        by_name: dict[str, dict] = {}
        for card in data["cards"]:
            by_name.setdefault(_norm(card["name"]), card)
            by_name.setdefault(_norm(card["name"].split(" // ")[0]), card)
        return by_name

    def _ratings_for(self, code: str | None, fmt: str) -> tuple[dict, dict]:
        """(data, name index) for a set; empty when unavailable. Failures are retried after 5 minutes."""
        code = (code or self.default_set or "").upper()
        if (code, "*") in self.indexes:
            return self.set_data[code], self.indexes[(code, "*")]
        key = (code, fmt)
        if key not in self.indexes and self.provider and code and time.time() >= self.fail_until.get(key, 0):
            try:
                data = self.provider(code, fmt)
                self.set_data[f"{code}/{fmt}"] = data
                self.indexes[key] = self._index(data)
            except Exception:
                self.fail_until[key] = time.time() + 300
        if key not in self.indexes:
            return {}, {}
        return self.set_data[f"{code}/{fmt}"], self.indexes[key]

    @property
    def by_name(self) -> dict[str, dict]:
        return self._ratings_for(self.current_set, self.current_fmt)[1]

    def detect_game_set(self) -> str | None:
        counts: dict[str, int] = {}
        for grp in self.state.game.deck:
            if grp in self.lands:
                continue
            code = self.expansions.get(grp)
            if code:
                counts[code] = counts.get(code, 0) + 1
        return max(counts, key=counts.get) if counts else None

    def lookup(self, card_id: int) -> dict:
        return self.lookup_from_index(card_id, self.by_name)

    def lookup_from_index(self, card_id: int, by_name: dict[str, dict]) -> dict:
        name = self.names.get(card_id)
        if name is None:
            return {"arenaId": card_id, "name": f"Unknown card ({card_id})", "unrated": True}
        card = by_name.get(_norm(name)) or by_name.get(_norm(name.split(" // ")[0]))
        if card is None:
            return {"arenaId": card_id, "name": name, "unrated": True}
        if not card.get("image"):
            card = {**card, "image": self._image(card_id)}
        return {**card, "arenaId": card_id, "unrated": False}

    def _name(self, grp: int) -> str:
        return self.names.get(grp, f"Unknown card ({grp})")

    def _archetypes_for(self, code: str | None) -> tuple[dict | None, int]:
        code = (code or "").upper()
        path = self.archetype_dir / f"{code}.json"
        modified = path.stat().st_mtime_ns if path.is_file() else 0
        cached = self.archetype_cache.get(code)
        now = time.time()
        stale = cached is not None and now - cached[2] > (TIER_REFRESH if cached[3] else TIER_RETRY)
        if cached is None or cached[0] != modified or (self.tier_provider and stale):
            live = None
            if self.tier_provider and code:
                try:
                    live = self.tier_provider(code)
                except Exception:
                    live = None
            guide = archetypes.load_set(self.archetype_dir, code)
            if live and guide is None:
                guide = archetypes.merge_tiers(None, live, code, ratings.KNOWN_SET_NAMES.get(code) or ratings.set_name(code))
            elif live:
                guide = archetypes.merge_tiers(guide, live, code)
            self.archetype_revision += 1
            cached = (modified, guide, now, bool(live) or not self.tier_provider, self.archetype_revision)
            self.archetype_cache[code] = cached
        return cached[1], modified + cached[4]

    def _image(self, grp: int) -> str:
        return self._image_for_name(self._name(grp))

    def _image_for_name(self, name: str) -> str:
        rated = self.by_name.get(_norm(name)) or self.by_name.get(_norm(name.split(" // ")[0]))
        if rated and rated.get("image"):
            return rated["image"]
        return "https://api.scryfall.com/cards/named?format=image&version=normal&exact=" + quote(name.split(" // ")[0])

    def game_view(self) -> dict | None:
        game = self.state.game
        if not game.active or not game.deck:
            return None
        self.current_set = self.detect_game_set() or self.current_set
        remaining = game.remaining(key=self._name)
        total = sum(remaining.values())
        rep = {}
        for grp in game.deck:
            rep.setdefault(self._name(grp), grp)
        cards = [
            {
                "name": name,
                "count": count,
                "chance": count / total if total else 0.0,
                "isLand": rep[name] in self.lands,
                "mana": self.details.get(rep[name], ('', ''))[0],
                "typeLine": self.details.get(rep[name], ('', ''))[1],
                "image": self._image(rep[name]),
            }
            for name, count in remaining.items()
        ]
        cards.sort(key=lambda c: (c["isLand"], -c["count"], c["name"]))
        zone_size = game.library_zone_size()
        return {
            "libraryCount": total,
            "deckSize": len(game.deck),
            "libraryZoneSize": zone_size,
            "consistent": zone_size is None or zone_size == total,
            "cards": cards,
            "instants": self.instant_view(game),
        }

    def sealed_view(self, archetype_data: dict | None) -> dict | None:
        observation = self.state.sealed_pool
        if observation is None:
            return None

        cards_by_name = {}
        for card_id, count in Counter(observation.card_ids).items():
            card = self.lookup(card_id)
            mana, type_line = self.details.get(card_id, ("", ""))
            card["manaArena"] = card.get("manaArena") or mana
            card["typeLine"] = card.get("typeLine") or type_line
            colors = card.get("colors") or self.colors.get(card_id, "")
            if isinstance(colors, str):
                colors = list(colors)
            card["colors"] = list(colors)
            card["isLand"] = "land" in card["typeLine"].casefold()
            card["count"] = count
            key = _norm(card["name"])
            if key in cards_by_name:
                cards_by_name[key]["count"] += count
            else:
                cards_by_name[key] = card

        cards = list(cards_by_name.values())
        return {
            "event": observation.event_name,
            "cardCount": sum(card["count"] for card in cards),
            "uniqueCount": len(cards),
            "cards": cards,
            "archetypes": sealed.analyze_archetypes(cards, archetype_data),
            "scoreThresholds": sealed.SCORE_THRESHOLDS,
        }

    def instant_view(self, game) -> dict | None:
        observation = self.state.sealed_pool or self.state.pack
        event_name = observation.event_name if observation else self.state.last_event_name
        match = _LIMITED_EVENT.match(event_name or "")
        if not match or not game.deck:
            return None
        pool_set = match.group("set").upper()
        nonlands = [grp for grp in game.deck if grp not in self.lands]
        matching_cards = sum(self.expansions.get(grp) == pool_set for grp in nonlands)
        if not nonlands or matching_cards * 2 < len(nonlands):
            return None
        view = instants.guide(game.opponent_lands(), game.opponent_seen_grp_ids(), self.instant_info, self.land_colors,
                              pool_set=pool_set)
        for key in ("shown", "possible"):
            view[key] = [
                {"name": c["name"], "mana": c["mana"], "kind": c["kind"], "castable": c["castable"], "image": self._image(c["grp"])}
                for c in view[key]
            ]
        return view

    def history_detail(self, kind: str, item_id: str) -> dict | None:
        if kind == "draft":
            detail = self.history.get_draft(item_id)
            if not detail:
                return None
            parsed = ratings.parse_event(detail["event"])
            fmt, code = parsed if parsed else (self.current_fmt, self.current_set)
            _, by_name = self._ratings_for(code, fmt)
            detail["observations"] = [
                observation for observation in detail["observations"] if observation["cardIds"]
            ]
            for observation in detail["observations"]:
                observation["cards"] = [
                    self._historical_card(card_id, by_name)
                    for card_id in observation["cardIds"]
                ]
                observation["takenCards"] = [
                    self._historical_card(card_id, by_name)
                    for card_id in observation["takenIds"]
                ]
                observation["chosenCards"] = [
                    self._historical_card(card_id, by_name)
                    for card_id in observation["chosenIds"]
                ]
            return detail
        if kind == "sealed":
            detail = self.history.get_sealed(item_id)
            if not detail:
                return None
            parsed = ratings.parse_event(detail["event"])
            fmt, code = parsed if parsed else (self.current_fmt, self.current_set)
            _, by_name = self._ratings_for(code, fmt)
            counts = Counter(detail.pop("cardIds"))
            detail["cards"] = []
            for card_id, count in counts.items():
                card = self._historical_card(card_id, by_name)
                card["count"] = count
                detail["cards"].append(card)
            detail["cards"].sort(key=lambda card: (card.get("unrated", False), -(card.get("score") or 0), card["name"]))
            return detail
        return None

    def _historical_card(self, card_id: int, by_name: dict[str, dict]) -> dict:
        card = self.lookup_from_index(card_id, by_name)
        if card_id in self.details:
            card["manaArena"], card["typeLine"] = self.details[card_id]
        if card_id in self.colors:
            card["colors"] = list(self.colors[card_id])
        elif isinstance(card.get("colors"), str):
            card["colors"] = list(card["colors"])
        card["isLand"] = "land" in card.get("typeLine", "").casefold()
        return card

    def refresh(self) -> None:
        if self.demo:
            return
        with self.lock:
            if logparse.poll(
                self.state,
                self.log_path,
                on_pack=self.history.record_pack,
                on_sealed=self.history.record_sealed,
                on_reset=self.history.reset_log_context,
            ):
                self.updated_at = time.time()

    def snapshot(self) -> dict:
        self.refresh()
        with self.lock:
            if self.demo:
                top = sorted(self.data["cards"], key=lambda c: -(c["score"] or 0))[2:17]
                cards = []
                for card in top:
                    card = dict(card, unrated=False)
                    if not card.get("image"):
                        card["image"] = self._image_for_name(card["name"])
                    cards.append(card)
                pack, version = {"pack": 1, "pick": 1, "event": "Demo"}, 1
            else:
                obs, version = self.state.pack, self.state.version
                pack = None
                cards = []
                if self.state.sealed_pool:
                    parsed = ratings.parse_event(self.state.sealed_pool.event_name)
                    if parsed:
                        self.current_fmt, self.current_set = parsed
                if obs:
                    pack = {
                        "pack": None if obs.pack_number is None else obs.pack_number + 1,
                        "pick": None if obs.pick_number is None else obs.pick_number + 1,
                        "event": obs.event_name,
                    }
                    parsed = ratings.parse_event(obs.event_name)
                    if parsed:
                        self.current_fmt, self.current_set = parsed
                    cards = [self.lookup(i) for i in obs.card_ids]
                    for c in cards:
                        if c.get("arenaId") in self.details:
                            c["manaArena"] = self.details[c["arenaId"]][0]
            cards.sort(key=lambda c: (c.get("unrated", False), -(c.get("score") or 0)))
            code = self.current_set or self.default_set
            ratings_data, _ = self._ratings_for(code, self.current_fmt) if not self.demo else (self.data, {})
            archetype_data, archetype_version = self._archetypes_for(code)
            sealed_data = self.sealed_view(archetype_data)
            history_data = self.history.list_history()
            taken_cards = [
                self.lookup(card_id)
                for card_id in self.history.current_taken_ids(obs)
            ] if not self.demo and obs else []
            for card in taken_cards:
                card["takenByOthers"] = True
            rating_revision = hashlib.sha256(json.dumps(
                [(c.get("name"), c.get("score"), c.get("ratings", [])) for c in ratings_data.get("cards", [])],
                ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            ).encode("utf-8")).hexdigest()[:12]
            return {
                "version": f"{version}.{self.state.game.version}.{archetype_version}.{rating_revision}.{history_data['revision']}",
                "set": code,
                "archetypes": archetype_data,
                "sealedPool": sealed_data,
                "game": self.game_view(),
                "pack": pack,
                "cards": cards,
                "takenCards": taken_cards,
                "history": history_data,
                "status": {
                    "logFound": self.demo or self.log_path.exists(),
                    "cardDb": bool(self.names) or self.demo,
                    "demo": self.demo,
                    "updatedAt": self.updated_at,
                    "ratingsGeneratedAt": ratings_data.get("generatedAt"),
                    "attribution": ratings_data.get("attribution"),
                    "source": ratings_data.get("source") or (
                        "17Lands" if "17lands" in (ratings_data.get("attribution") or "") else "chunk.science"
                    ),
                    "ratingsAvailable": bool(ratings_data),
                },
            }


def make_handler(guide: Guide):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep the console quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/state":
                return self._send(200, json.dumps(guide.snapshot()).encode(), "application/json")
            if path == "/api/history":
                return self._send(200, json.dumps(guide.history.list_history()).encode(), "application/json")
            if path.startswith("/api/history/"):
                parts = [unquote(part) for part in path.split("/") if part]
                if len(parts) == 4 and parts[2] in ("draft", "sealed"):
                    with guide.lock:
                        detail = guide.history_detail(parts[2], parts[3])
                    if detail is None:
                        return self._send(404, b"not found", "text/plain")
                    return self._send(200, json.dumps(detail).encode(), "application/json")
            name = "index.html" if path in ("", "/") else path.lstrip("/")
            target = (WEB / name).resolve()
            if WEB.resolve() not in target.parents or not target.is_file():
                return self._send(404, b"not found", "text/plain")
            self._send(200, target.read_bytes(), CONTENT_TYPES.get(target.suffix, "application/octet-stream"))

    return Handler


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Live Arena draft guide (any set)")
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG, help="Path to Arena Player.log")
    ap.add_argument("--card-db", type=Path, help="Arena Raw_CardDatabase_*.mtga (auto-detected)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--refresh-ratings", action="store_true", help="Re-download rating data")
    ap.add_argument("--demo", action="store_true", help="Show a sample pack without Arena")
    args = ap.parse_args(argv)

    store = ratings.Store(ROOT / "data", refresh=args.refresh_ratings)
    try:
        data = store.get("FRA")
    except Exception as exc:
        print(f"Warning: default ratings unavailable ({exc}); other sets load on demand.")
        data = None
    db = args.card_db or arena_db.find_database()
    cards = arena_db.load_cards(db) if db else {}
    names = {grp: name for grp, (name, _land) in cards.items()}
    lands = {grp for grp, (_name, land) in cards.items() if land}
    if not names and not args.demo:
        print("Warning: Arena card database not found; pass --card-db or set MTGA_CARD_DB.")
    details = arena_db.load_details(db) if db else {}
    colors = arena_db.load_colors(db) if db else {}
    instant_info = arena_db.load_instant_speed(db) if db else {}
    land_colors = arena_db.load_land_colors(db) if db else {}
    expansions = arena_db.load_expansions(db) if db else {}
    guide = Guide(data, names, args.log, demo=args.demo, lands=lands, details=details,
                  instant_info=instant_info, land_colors=land_colors, expansions=expansions, provider=store.get, tier_provider=store.untapped_tiers,
                  colors=colors)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(guide))
    print(f"Draft guide on http://127.0.0.1:{args.port}  (log: {args.log})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
