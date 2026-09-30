# Arena draft guide (Reality Fracture)

A local, auto-refreshing web page for a second monitor. While you draft in MTG Arena it shows the cards in your current pack with card art, aggregate rating, per-reviewer grades, and written comments/notes from [chunk.science's Reality Fracture tier list](https://chunk.science/mtga-reality-fracture.html). The best-rated card is outlined green and the pack is sorted best-first.

## Run

Python 3.12+, standard library only (no installs).

    py -3.12 -m draftguide            # then open http://127.0.0.1:8765
    py -3.12 -m draftguide --demo     # sample pack, no Arena needed

Options: `--log PATH` (default: Arena's `Player.log`), `--card-db PATH` (auto-detected in Steam/Wizards install folders, or env `MTGA_CARD_DB`), `--port`, `--refresh-ratings`.

In Arena: Options > Account > enable **Detailed Logs (Plugin Support)**, then restart Arena. Without it Arena doesn't log draft packs.

## How it works

- Read-only: tails `Player.log` for `DraftPack` (Premier/Traditional) and `Draft.Notify` `PackCards` (Quick draft) lines; maps Arena card ids to names from the game's local card database (opened read-only). No input is sent to Arena, no memory or network access to the game.
- Ratings are downloaded once from chunk.science into `data/fra.json` (git-ignored; the site is "all rights reserved", so the data is not redistributed here). Refresh with `--refresh-ratings`. Card images load from Scryfall in your browser.
- The page polls `/api/state` every second and redraws when a new pack arrives.

## Limits

- Only the Reality Fracture set is rated; cards not in it show "No rating found".
- Log line formats were implemented from known Arena formats and tested with synthetic lines and real card ids; it has not yet been checked against a live draft (the local log contained only a Sealed event). If a live draft shows "Waiting for a draft pack…", share a few `DraftPack`/`Draft.Notify` lines from `Player.log` so the parser can be adjusted.
- Ratings are aggregated opinions, not a pick for you; the page doesn't account for your colors so far (possible next step: use `PickedCards`).

## Tests

    py -3.12 -m unittest discover -s tests -t .
