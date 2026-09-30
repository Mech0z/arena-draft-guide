"""Local HTTP server: serves the page and the live pack state derived from Player.log."""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlparse

from . import arena_db, instants, logparse, ratings

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
DEFAULT_LOG = Path(os.environ.get("USERPROFILE", "~")) / "AppData/LocalLow/Wizards Of The Coast/MTGA/Player.log"
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}


def _norm(name: str) -> str:
    return name.casefold().strip()


class Guide:
    def __init__(self, data: dict, names: dict[int, str], log_path: Path, demo: bool = False, lands: set[int] | None = None, details: dict | None = None,
                 instant_info: dict | None = None, land_colors: dict | None = None):
        self.details = details or {}
        self.instant_info = instant_info or {}
        self.land_colors = land_colors or {}
        self.data = data
        self.names = names
        self.lands = lands or set()
        self.log_path = log_path
        self.demo = demo
        self.state = logparse.DraftLogState()
        self.updated_at: float | None = None
        self.lock = threading.Lock()
        self.by_name: dict[str, dict] = {}
        for card in data["cards"]:
            self.by_name.setdefault(_norm(card["name"]), card)
            self.by_name.setdefault(_norm(card["name"].split(" // ")[0]), card)

    def lookup(self, card_id: int) -> dict:
        name = self.names.get(card_id)
        if name is None:
            return {"arenaId": card_id, "name": f"Unknown card ({card_id})", "unrated": True}
        card = self.by_name.get(_norm(name)) or self.by_name.get(_norm(name.split(" // ")[0]))
        if card is None:
            return {"arenaId": card_id, "name": name, "unrated": True}
        return {**card, "arenaId": card_id, "unrated": False}

    def _name(self, grp: int) -> str:
        return self.names.get(grp, f"Unknown card ({grp})")

    def _image(self, grp: int) -> str:
        name = self._name(grp)
        rated = self.by_name.get(_norm(name)) or self.by_name.get(_norm(name.split(" // ")[0]))
        if rated and rated.get("image"):
            return rated["image"]
        return "https://api.scryfall.com/cards/named?format=image&version=normal&exact=" + quote(name.split(" // ")[0])

    def game_view(self) -> dict | None:
        game = self.state.game
        if not game.active or not game.deck:
            return None
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

    def instant_view(self, game) -> dict:
        view = instants.guide(game.opponent_lands(), game.opponent_seen_grp_ids(), self.instant_info, self.land_colors)
        for key in ("shown", "possible"):
            view[key] = [
                {"name": c["name"], "mana": c["mana"], "kind": c["kind"], "castable": c["castable"], "image": self._image(c["grp"])}
                for c in view[key]
            ]
        return view

    def refresh(self) -> None:
        if self.demo:
            return
        with self.lock:
            if logparse.poll(self.state, self.log_path):
                self.updated_at = time.time()

    def snapshot(self) -> dict:
        self.refresh()
        with self.lock:
            if self.demo:
                top = sorted(self.data["cards"], key=lambda c: -(c["score"] or 0))[2:17]
                cards, pack, version = [dict(c, unrated=False) for c in top], {"pack": 1, "pick": 1, "event": "Demo"}, 1
            else:
                obs, version = self.state.pack, self.state.version
                pack = None
                cards = []
                if obs:
                    pack = {
                        "pack": None if obs.pack_number is None else obs.pack_number + 1,
                        "pick": None if obs.pick_number is None else obs.pick_number + 1,
                        "event": obs.event_name,
                    }
                    cards = [self.lookup(i) for i in obs.card_ids]
            cards.sort(key=lambda c: (c.get("unrated", False), -(c.get("score") or 0)))
            return {
                "version": f"{version}.{self.state.game.version}",
                "game": self.game_view(),
                "pack": pack,
                "cards": cards,
                "status": {
                    "logFound": self.demo or self.log_path.exists(),
                    "cardDb": bool(self.names) or self.demo,
                    "demo": self.demo,
                    "updatedAt": self.updated_at,
                    "ratingsGeneratedAt": self.data.get("generatedAt"),
                    "attribution": self.data.get("attribution"),
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
            name = "index.html" if path in ("", "/") else path.lstrip("/")
            target = (WEB / name).resolve()
            if WEB.resolve() not in target.parents or not target.is_file():
                return self._send(404, b"not found", "text/plain")
            self._send(200, target.read_bytes(), CONTENT_TYPES.get(target.suffix, "application/octet-stream"))

    return Handler


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Live Reality Fracture draft guide")
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG, help="Path to Arena Player.log")
    ap.add_argument("--card-db", type=Path, help="Arena Raw_CardDatabase_*.mtga (auto-detected)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--refresh-ratings", action="store_true", help="Re-download rating data")
    ap.add_argument("--demo", action="store_true", help="Show a sample pack without Arena")
    args = ap.parse_args(argv)

    data = ratings.load(ROOT / "data" / "fra.json", refresh=args.refresh_ratings)
    db = args.card_db or arena_db.find_database()
    cards = arena_db.load_cards(db) if db else {}
    names = {grp: name for grp, (name, _land) in cards.items()}
    lands = {grp for grp, (_name, land) in cards.items() if land}
    if not names and not args.demo:
        print("Warning: Arena card database not found; pass --card-db or set MTGA_CARD_DB.")
    details = arena_db.load_details(db) if db else {}
    instant_info = arena_db.load_instant_speed(db) if db else {}
    land_colors = arena_db.load_land_colors(db) if db else {}
    guide = Guide(data, names, args.log, demo=args.demo, lands=lands, details=details,
                  instant_info=instant_info, land_colors=land_colors)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(guide))
    print(f"Draft guide on http://127.0.0.1:{args.port}  (log: {args.log})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0




