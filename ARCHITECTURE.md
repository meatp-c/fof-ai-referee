# Architecture of the rules engine

A guide for a developer who opens the code for the first time. The package is `fof/` (in the project
`werkzeuge/fof/`, in the public kit `tool/fof/`); the command line is `fof.py`, the booking wrapper `zug.py`.
Setup files, mission data and the German JSON keys are explained in GLOSSARY.md; this page explains the code.

## What the engine does

The engine is a referee, not a game. The player moves the counters on the real board and tells the engine what
happened. Every command is checked against the rules and then either

- refused: one line `VIOLATION: ... [RULE x p.y]`, exit code 2, nothing is saved, or
- booked: the game state is saved with a numbered protocol entry, the engine prints what has to change on the board
  (`Board: ...`) and a `CHECKSTAMP OK Turn t Phase p Entry n` line that player and AI compare.

An input the engine cannot know, mostly a card draw, comes as a refusal that says what to draw ("draw 2 Action
cards, ... then --success=yes|no"); nothing is saved and the command is repeated with the result. A third answer,
`OPEN: ...` (exit 0), means a step was saved up to an open draw and waits for it (the vehicle phase uses it).

## Module map

| group | module | responsibility |
|---|---|---|
| entry | `fof.py`, `cli.py` | command table (English names, German aliases, usage, minimum arguments), argv translation, dispatch, exit codes |
| | `options.py`, `messages.py` | `--key=value` parsing and option aliases; output vocabulary (`VIOLATION`, `ALLOWED`, `Board:`, rule format) |
| state | `state.py` | load, save, snapshots, accessors (`unit`, `card`, `units_on`, `pinned`, ...); type names `GameState`, `Unit`, `Card` |
| | `keys.py` | register of every state key with lifetime and meaning; key check on save |
| | `history.py`, `briefing.py` | undo; consistency check, board briefing (`BRIEFING.md`), CHECKSTAMP |
| rule data | `rules.py`, `geometry.py` | sequence of play, action menu, tables, default readings of open questions; cards, LOS, range, visibility |
| sequence | `phase.py` | phase machine (`phase next`), segment entry and exit, Clean Up and end of turn, capture, retreat |
| command phase | `commands.py` | activation, impulses, the order pipeline, movement, cover markers, Concentrate Fire, corrections |
| | `fire_support.py`, `grenades.py`, `pickup.py`, `pyro.py` | Call for Fire and Indirect Lay; Grenade Attacks and Jam; Pick Up and jeeps; pyrotechnics |
| | `comms.py` | visual-verbal, radio and phone nets, runners, chain of command, card counts |
| fire and combat | `fire.py` | derived fire: who fires at what, VOF and PDF, cease fire, fire after a move, Activity Level |
| | `combat.py` | Combat Effects: net modifier, HIT results, step loss, LATs, ammo, removal from play, prisoners |
| enemy | `enemy.py` | Activity Check hierarchy and the enemy actions; the one enemy move path `move_enemy` |
| | `contact.py`, `events.py` | potential contact, packages and their placement, mines; Higher HQ events |
| vehicles | `vehicles.py` | AT Combat & Vehicle Movement phase 3.6 as a queue of draws and per-action plans |
| setup | `setup.py`, `campaign.py` | terrain, objectives, unit setup, assets, radios; experience, mission end, patrols, reattempts |

Import cycles are normal here: modules import each other as module objects (`from . import commands`) and only
use attributes at call time. Tables built at import time never reference a function of another module directly
(`ORDER_HANDLERS` uses `lambda s, ctx: grenades.order_grenade_attack(s, ctx)` for that reason).

## The game state

`spielstand.json` in the game folder is one nested dict, called `s` everywhere:

- `s["einheiten"][name]`: a unit (side `seite` US or Feind, card `karte`, area `bereich` = `offen` or a cover marker id,
  `status` markers, `steps`, `ziel` = the card it fires at, ...)
- `s["karten"][id]`: a terrain card (id = row and column, `"34"`; `cover` markers, `extern` VOF markers, `pc`, ...)
- `s["kommandos"][hq]`, `s["protokoll"]`, `s["phase"]`, `s["zug"]`, and the mission tables from the setup file

The keys are German because every saved game uses them; the code is English. **Every key is listed in
`keys.py`** with a lifetime (setup, mission, attempt, turn, phase, action, command, legacy) and one line of meaning.
Tests and the regression run with `FOF_KEY_CHECK=1`: `save_state` then refuses a state with an unregistered key,
a source scan finds every literal key the code writes, and a generic test checks that every `turn` key is gone after
the end of the turn. A working flag that nobody clears was the most common bug class of the 2026-11-07 review, so
a new key needs an entry with "set by ... / cleared by ...".

Derived values (who fires, VOF on a card, Activity Level) are recomputed from the units, not stored twice.

## The way of a command

1. `fof.py order "1st PLT HQ" 1/1 4.2.2c --target=32 --success=yes`
2. `cli.main`: `argv_to_german` maps English command words, sub-words and option names to the internal German ones
   (`--target` to `--ziel`, `yes` to `ja`); the command table gives the handler and the minimum argument count.
3. `state.load_state` reads the game folder (`FOF_PARTIE` or `.aktuelle_partie`).
4. The handler checks and changes `s`. Any rule problem is `raise rules.Violation("... [RULE x p.y]")`; because nothing
   has been written yet, a refused command leaves no trace.
5. `state.save_state(s, text, rule)`: consistency check (and key check), protocol entry, atomic write of
   `spielstand.json`, snapshot `verlauf/<n>.json` for undo, `BRIEFING.md`, board lines and CHECKSTAMP.

`cmd_order` (commands.py) runs the action menu of chapter 4 as a fixed pipeline: `order_context` (parse),
`resolve_originator`, `check_recipient` (chain of command, communication), `check_repeat_and_budget` (one action per
unit and impulse, Commands), `apply_skill`, `pre_draw_checks` (everything that can refuse comes before the draw
prompt; `PRE_DRAW_CHECKS` per action), the handler from `ORDER_HANDLERS`, `book_order` (pay, note, save).

`zug.py` books one game step: it runs the commands in a scratch copy, books for real only if every one exits with
code 0, and commits the game folder to git.

## The phase machine

`s["phase"]` is a segment id of the sequence of play (`rules.SOP_OFFENSIVE` or `SOP_DEFENSIVE`). `phase next`
(`phase.cmd_phase`) runs the `LEAVE_CHECKS` of the current segment (each refuses while something is open: an impulse
not ended, a mine check, an unresolved PC marker, ...), moves to the next segment and runs its `ENTER_HOOKS` entry
(card draws for HQs, Activity Checks, the vehicle phase, Combat Effects lists). `endturn` runs Clean Up (3.8) and
starts the next turn. Locks such as `contact.mine_lock` or `vehicles.lock` refuse other commands while a draw is open.

## Conventions

- **Rule citations.** Every refusal and every board line names its source: `[RULE 6.1.2 p.40]`, campaign rules
  `[CSR 5 p.14]`, mission rules `[MSR 3]`, Q&A from BoardGameGeek `[BGG 3514510]`. The citation is the explanation.
- **L numbers.** Comments such as `# L534` point to the numbered change log of the author's project (German, not
  part of the kit; the kit CHANGELOG lists the L ranges per release). Where a comment changes rule behaviour it
  also carries the rule citation; technical ones (argument checks, refactorings) do not need one.
- **Open readings.** Where the rules leave a question open, the engine uses a named default (`rules.DEFAULT_OPTIONS`,
  `U12_...`), says so in the output (`[open U12]`) and lets a mission change it in `optionen`.
- **One move path per side.** A unit changes its card only in `commands.move_unit` (US, vehicles) or
  `enemy.move_enemy` (enemy), so Grenade expiry, mines, ammo surplus, phone lines and fire after the move always run.
  Placements (setup, entering units) are the only other writers; a test guards the list.
- **Lifetimes.** Fire working fields are cleared by `fire.cease_fire` / `fire.set_target`, bunker flags by
  `enemy.leave_structure`, pending checks of a removed counter by `state.forget_pending`.
- **Types.** The module boundaries `state`, `rules`, `options`, `comms` are annotated and pass mypy
  (`tests/test_types.py`, skipped where mypy is not installed). Inside the modules the code is untyped.

## Tests

`pytest` runs in seconds: unit tests on a synthetic 3x3 board (`tests/conftest.py`: `board`, `unit`, `cli_game` for
the command line, shared fixtures of the review blocks), worked examples of the rulebook as tests
(`test_examples_*`), and structural guards (key register, move paths, types). The project additionally replays two
complete test games against golden end states (`normandy/regression.sh`, mission data, not in the kit).
