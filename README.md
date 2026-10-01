# Arena draft guide (any draft set)

A local, auto-refreshing web page for a second monitor. While you draft in MTG Arena it shows the cards in your current pack with card art and draft ratings. Reality Fracture combines available grades from multiple limited reviewers; Wilds of Eldraine uses [Card Game Base](https://cardgamebase.com/wilds-of-eldraine-draft-tier-list/). Other sets use 17Lands.

## Run

Python 3.12+, standard library only (no installs).

    py -3.12 -m draftguide            # then open http://127.0.0.1:8765
    py -3.12 -m draftguide --demo     # sample pack, no Arena needed

Options: `--log PATH` (default: Arena's `Player.log`), `--card-db PATH` (auto-detected in Steam/Wizards install folders, or env `MTGA_CARD_DB`), `--port`, `--refresh-ratings`.

In Arena: Options > Account > enable **Detailed Logs (Plugin Support)**, then restart Arena. Without it Arena doesn't log draft packs.

## How it works

- Read-only: tails `Player.log` for `DraftPack` payloads (Quick and Premier draft share this same code path; Traditional and Pick-Two use it too) and, as a fallback, `Draft.Notify` `PackCards` lines; maps Arena card ids to names from the game's local card database (opened read-only). No input is sent to Arena, no memory or network access to the game.
- Ratings are cached as per-set JSON files under `data/` (git-ignored, not redistributed). FRA's feed includes Draftsim, MTG Arena Zone, Card Game Base, and other reviewers; individual native grades and source links are shown alongside the consensus score. WOE uses Card Game Base. These ratings refresh every 12 hours; use `--refresh-ratings` to fetch them again. Card images load from Scryfall in your browser.
- Curated Limited archetype guides are stored as `guides/archetypes/<SET>.json`, separately from the ignored rating cache. During a draft, use **Color tiers** for the sorted color-pair ratings, or toggle the **Archetypes** sidebar for themes and sources. Guide JSON is reloaded when its file changes. Archetypes with a `tier` value sort highest-first; entries without a tier remain at the end.
- The FRA feed currently exposes per-card grades for Draftsim, MTG Arena Zone, Card Game Base, and additional reviewers. The supplied Untapped.gg and TCGplayer pages do not provide ratings through this feed and are not included.
- The page polls `/api/state` every second and redraws when a new pack arrives.

## Limits

- Works for any set: the set and format are read from the draft's event name (Premier/Quick/Traditional) and, in games, from the expansion codes in your deck. FRA combines available numeric grades from the multi-source feed into a consensus score and displays each reviewer's original grade; this is cached as `data/multi-source-FRA.json`. WOE uses Card Game Base letter grades (A+ through F), cached as `data/cardgamebase-WOE.json`. Other sets use 17Lands win-rate data (score = percentile of games-in-hand win rate among cards with 200+ games, cached in `data/17l-<SET>-<format>.json` for 12h). Cards without an available review grade appear unrated; 17Lands cards without enough data show "Not enough data" with art and mana cost. If a source is unreachable, cached ratings are used when available, otherwise cards show unrated and retry after 5 minutes. 17Lands has no data for brand-new sets until players have logged games, and only FRA packs have been seen live; other sets are covered by unit tests and a simulated FDN draft (`python tools/simulate_draft.py --log X --set FDN`).
- Log parsing was replayed line-by-line against real public Arena logs (Quick and Premier drafts, the formats this tool targets, from andreagrandi/draftomen test fixtures): every pick produced a refreshed pack (14, 13, 12... cards) and Quick Draft's completion cleared the pack. It has not yet been run against your own live Reality Fracture draft; if the page shows Waiting for a draft pack..., check Detailed Logs is enabled.
- Ratings are aggregated opinions, not a pick for you; the page doesn't account for your colors so far (possible next step: use `PickedCards`).

## Tests

    py -3.12 -m unittest discover -s tests -t .




## Game mode: library and draw chances

When a match starts, the page switches to a library view: every card still in
your library, its count and the chance to draw it next. Hovering a row shows
the card image from Scryfall. After the
game ends it falls back to the draft view.

How it works: the library is hidden in the log, so it is derived as your
deck list (from the GRE `ConnectResp`) minus your own cards seen in hand,
battlefield, graveyard, exile and stack. Printings are grouped by name. A
"?" warning shows if the derived size differs from Arena's library zone size
(tokens, stolen or copied cards can skew counts).

Limits: needs Detailed Logs enabled; tested on synthetic and old public GRE
fixtures only, not yet on a live modern match. A match joined mid-game has no
deck list, so no library view.

### Opponent instant-speed guide (bottom bar)

In game mode a bar at the bottom shows what the opponent could cast at instant
speed right now: it counts the opponent's untapped lands (basic type, or the
colour identity of non-basics), then lists (1) instants/flash cards they have
already shown (battlefield, graveyard, exile, stack) and (2) instants/flash creatures from the detected set
instant/flash cards in their colours that their untapped mana can pay for.
Greyed cards are shown but not currently affordable. Hover for a larger image.

Limits: the opponent's hand and deck are hidden, so "could have" is a pool
guess, not knowledge. Mana from creatures, treasures or other non-land sources
and X costs/cost reductions are not modelled; phyrexian mana is treated as free.

## Screenshots

Draft pick 1 of a simulated Quick Draft (`tools/simulate_draft.py`), then the next pick after a card is taken; the page refreshes by itself:

![Draft pick 1](docs/draft-pick-1.png)
![Draft pick 2](docs/draft-pick-2.png)

In-game mode on a real match: library with draw chances, mana costs and types, plus the opponent instant-speed bar:

![Game mode](docs/game-mode.png)

### Try it without Arena

```
py -3.12 tools/simulate_draft.py --log sim.log --interval 4
py -3.12 -m draftguide --log sim.log --port 8780
```