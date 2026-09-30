"""Local HTTP server: serves the page and the live pack state derived from Player.log."""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import arena_db, logparse, ratings

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
DEFAULT_LOG = Path(os.environ.get("USERPROFILE", "~")) / "AppData/LocalLow/Wizards Of The Coast/MTGA/Player.log"
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}


def _norm(name: str) -> str:
    return name.casefold().strip()


class Guide:
    def __init__(self, data: dict, names: dict[int, str], log_path: Path, demo: bool = False):
        self.data = data
        self.names = names
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
                "version": version,
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
    names = arena_db.load_names(db) if db else {}
    if not names and not args.demo:
        print("Warning: Arena card database not found; pass --card-db or set MTGA_CARD_DB.")
    guide = Guide(data, names, args.log, demo=args.demo)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(guide))
    print(f"Draft guide on http://127.0.0.1:{args.port}  (log: {args.log})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
