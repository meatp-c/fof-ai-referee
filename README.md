# Fields of Fire Deluxe: AI rules referee kit

A command-line "shadow board" plus a working method that lets an AI assistant referee a solo game of
**Fields of Fire Deluxe** (GMT Games, Series Rules 3rd Edition) while you play on the real table.
You announce your moves in chat, the AI checks them with the tool and tells you what is legal,
which rule applies and which markers to place.

Unofficial fan project. Not affiliated with or endorsed by GMT Games. No rule text, card data or mission data is
included; you need your own copy of the game and its PDFs.

## What is in the kit
| path | content |
|---|---|
| `AI_BRIEFING.md` | the working contract for the AI (roles, "tool first", answer format, shorthand). Give it to the AI first. |
| `tool/fof.py` | the engine: game state, sequence of play, action checks, VOF/PDF/Crossfire, NCM, enemy activity, PC markers, fire missions, campaign/reattempt |
| `tool/build_rules_index.py` | builds the rule text index from your own rulebook PDF, used by `fof.py rule <no>` |
| `templates/mission_template.json` | skeleton of a mission setup (fill it from your Mission Book) |
| `templates/action_cards_template.json` | skeleton of an action card archive (optional, for ":NN" card lookups) |
| `GLOSSARY.md` | German identifiers, JSON keys and values used inside the engine |

## How it works
1. **The AI runs the tool.** The AI needs a shell (for example Claude with a code/terminal environment, or any
   agent that can run `python3`). The tool keeps the full board in `<game>/spielstand.json`.
2. **You describe, the tool decides.** You say "Move 2/2 to 44" or "E" (success) or "4" (a value you read off a card).
   The AI translates that into a tool call. Illegal steps come back as `VIOLATION: ... [RULE x.y p.n]` and nothing is saved.
3. **Board instructions come back.** Every booked step prints `Board:` lines (markers to place, flip, remove) and ends
   with `CHECKSTAMP OK Turn X Phase Y Entry N`.
4. **Status on demand.** `fof.py status` prints a full board briefing and writes `<game>/BRIEFING.md`.
   That file is what the AI reads after a context reset.
5. **Probe, then book.** The AI tests each step in a scratch copy of the game folder first, then books it for real.

## Requirements
- Python 3.9 or newer, no extra packages.
- `pdftotext` (poppler-utils) only for building the rule index.

## Setup
```
project/
  tool/fof.py
  tool/build_rules_index.py
  data/            <- rule texts built from your PDFs (not included)
  <game folders>   <- created by `fof.py new`
```
1. Rule texts (once): `python3 tool/build_rules_index.py --rules "<Series Rules PDF>" --clarifications "<Clarifications PDF>" --extra "<Mission Book PDF>"`
2. Mission setup: copy `templates/mission_template.json`, fill every `<...>` from your Mission Book
   (units with their counter values, terrain card values, packages, event tables, fire support, assets).
   Keys stay German, see GLOSSARY.md.
3. `python3 tool/fof.py new my_mission.json game1` creates the game folder `game1` and makes it current.
4. Before turn 1 the tool lists what is still missing (terrain per card, objectives, setup positions, visibility ...).
   Fill those in with `terrain`, `setup`, `objective`, `visibility`, then `phase next` starts the game.

## Commands (English; the German originals also work)
Run `python3 tool/fof.py` without arguments for the full list. Most used:
```
status | check | rule <no> | search <term> | options
phase next | event ? yes <R#> | event ? no
hq <HQ> | card ? <number> | activate <HQ> | order <HQ|GI> <unit> <action id> [--target=<card>] [--success=yes|no] [--area=C1|open] | done
gi ? <number> | enemycheck | enemyaction <enemy> "<result>" | pc reveal <card> <A|B|C> | pc <card> | pc contact <card> <package> --direction=Front|Left|Right
ncm <unit> | hit <unit> HIT|PIN|MISS [letters] | mine <unit> yes|no | capture <enemy> <guard> | endturn
setup <unit> <card> [--area=C1] [--platoon=<n>] [--asset=<type>] | terrain <card> <type> | extend <row> <col> <type>
objective primary|route|cop|concentration ... | visibility <light> | illum <card> <top> [<bottom>]
patrol start|next <platoon> [--with=a,b] | reattempt done | reconstitute <unit> --from=<LATs> | xp [add|spend <n> <reason>]
```
Action ids follow the Action Menus (4.2.2a Move, 4.2.2b Move a Platoon, 4.2.2c Infiltrate, 4.2.2e Seek Cover,
4.2.3a Rally, 4.2.4a Spot, 4.2.4d Grenade Attack, 4.2.4i Call for Fire, 4.2.4k Cease Fire, ...).

## Scope and limits
- Built and tested on Field Manual 1 (platoon and company courses) and the Normandy campaign missions 1 to 3
  (offensive missions, night patrols, reattempts, campaign experience). Several hundred turns of real play.
- Not implemented: vehicles and AT combat (chapter 10), helicopters/air assault, urban combat (13.0).
  Other campaigns need their own setup data and may need code for their special rules.
- Where the rules are unclear the tool uses a documented reading. `fof.py options` lists these, and output marks
  them as `[open Uxx]`. You can switch them in the setup's `optionen`.
- The engine trusts the values you enter for draws. It does not draw cards.

## License
Code and documentation: MIT, see LICENSE. Rules, charts, cards and mission texts of the game are GMT Games' property and are
not part of this repository; `.gitignore` keeps the files you build from your own PDFs out of git.
