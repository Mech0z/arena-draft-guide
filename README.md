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
- Log parsing was replayed line-by-line against real public Arena logs (Quick, Premier, Traditional and Pick-Two drafts, from andreagrandi/draftomen test fixtures): every pick produced a refreshed pack (14, 13, 12... cards) and Quick Draft's completion cleared the pack. It has not yet been run against your own live Reality Fracture draft; if the page shows Waiting for a draft pack..., check Detailed Logs is enabled.
- Ratings are aggregated opinions, not a pick for you; the page doesn't account for your colors so far (possible next step: use `PickedCards`).

## Tests

    py -3.12 -m unittest discover -s tests -t .

