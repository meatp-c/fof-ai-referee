# Changelog

## 2026-10-13 (third release)
Engine updates found during Normandy Mission 4 play (counter attack, grenade fights, retreats and captures), plus
the fall-back and grenade rulings collected from the BGG rules forum after the mission:
- New command `retreat <unit> [<card>]` (German `rueckzug`) for 3.5.2: checks whether a retreat is mandatory
  (unpinned, not Exposed, under a VOF; Litter Teams only with a casualty), picks the card one row towards the
  friendly edge without a VOF, then the highest C&C (ties by R#), the Litter Team takes the casualty along, the
  unit becomes Exposed. `phase next` out of 3.5.2 is refused while a mandatory retreat is still open. L110, L123
- Capture (3.5.1, 8.15): Paralyzed/Litter Teams that are alone on their card are taken as one group with a single
  guard step; enemy casualties on that card are captured right after. L117
- Enemy fall back (8.6.3): priority 1 (off-map) is enforced when the unit stands on or behind the top mission row
  and one of the three places towards the enemy edge has no card, or when it stands beyond a side boundary;
  `--target=off-map` is rejected in every other position. L125
- Grenade attacks hit the whole stack under a cover marker (7.10.1), for enemy attacks too; Critical Hit (7.10.3)
  with `--critical=yes`; no Grenade Miss marker while part of the hit stack remains (7.10.4); the free grenade
  response (7.10.5) is offered only against a point-blank attack from the same card, never from a bunker or
  pillbox, never while Pinned, and is listed per unit of the hit stack. L112, L115, L116, L124
- Opening fire: a unit on a card that already has a friendly PDF joins that fire (6.1.1); no target behind a
  nearer card with visible enemies (6.1.2); a PDF that already lies on the same card to the same target is
  reported instead of a second marker. L121, L122
- Cease Fire and Shift Fire reach every firing unit of the card, not only those with the same target (4.3.1
  note). L114
- Every save now reports changed VOF markers (strongest VOF per card), Crossfire markers, and new or ended mutual
  PDFs (6.3.1) as Board lines before the CHECKSTAMP; during 3.7.4 these reports are held back and compared once
  against the state at the start of the segment. L111, L113, L119
- Every movement lists the markers that travel with the unit (Pinned, ammo, Out of Ammo, assets, radios). L109
- Infiltrate (4.2.2c) checks 5.1.4 (a VOF on the start or target card) before asking for the card draw;
  Engineers infiltrating within a mine card need no `--area` (Normandy CSR 10). L107, L120
- An enemy moving onto a card where spotted and unspotted enemies would mix makes the whole card spotted
  (8.5). L108
- Small fixes: English area names in the move-within-a-card message, `hit` without arguments prints its usage. L105, L118

## 2026-10-12 (restructuring, same behaviour)
- New command `undo <entry> --reason=..` (German `zurueck`): every save keeps a snapshot of the state in
  `<game>/verlauf/<entry>.json` (last 40 entries); undo restores one and lists the discarded entries.
- Fix after the rename: 35 keyword arguments that write game-state keys (`update(karte=...)`, `dict(punkte=...)`)
  had been renamed to English; restored, guarded by `tests/test_state_keys.py`.
Verified with two state-based regression games (454 commands): identical exit codes and identical final game
states before and after every step.
- One engine package `tool/fof/` (16 modules) instead of a 9000-line file; `tool/fof.py` is the entry point.
- English identifiers for functions, constants, parameters and locals (4560 renames); JSON keys and stored values
  stay German (GLOSSARY.md), so existing game states keep working.
- `ruff format` (line length 120) and `ruff check` clean; `pyproject.toml`.
- The 550-line order function is one handler per action class (`ORDER_HANDLERS`), enemy actions one handler per
  result (`ENEMY_ACTION_HANDLERS`), phase changes and enemy placement split into smaller functions.
- `lateorder` counts the Commands an HQ already spent from the game state instead of parsing protocol text; no more
  monkeypatching of the save function.
- One `COMMANDS` table drives dispatch, English aliases and the new `help` command; a missing file is a
  VIOLATION line instead of a traceback.
- `messages.py` holds the output vocabulary (ALLOWED, VIOLATION, Board, Note, CHECKSTAMP) and the rule citation
  format; `Violation(msg, rule=...)`.
- `tests/`: unit tests on a synthetic board (geometry, LOS, VOF, Commands, CLI), no game data needed.

Internal change numbers (L..) refer to the gap list kept during play. Rule references are Series Rules 3rd Edition
(page numbers) and the Normandy Campaign Book (CSR/MSR).

## 2026-10-12 (second release)
Engine updates found during Normandy Mission 3 and 4 play:
- Enemy leaders with Rifle Grenades act as G! units along their card's PDF (8.9); offensive table rows fixed
  (Assault 1/4 No Action, 2-3/4 Grenade Attack, 4/4 Advance; Overrun Auto). L67, L86, L89
- Upper Story / Church Tower count as +1 elevation for LOS and spotting (5.2.2); Multi-Story symbol recorded with
  `multistory <card>`; Rifle Grenades and rocket launchers (Bazooka, Panzerschreck, RCL) cannot fire from
  building/bunker/cave/pillbox cover (7.4, 7.6). L73, L79, L84, L85, L97
- Smoke/Incoming/Air Strike on an intervening card moves the VOF back along the PDF to the blocking card instead of
  ceasing fire (6.1.2 p.44); fire ceases only when LOS or range is really lost, with the real reason. L94-L96
- Counter attack (Normandy M4 MSR 4): PC A placement, two face-up PC markers (8.2.3), enemy tactic switch. L74, L88
- Engineers clear mine paths (CSR 10) and draw 1 card for mine checks; mines package redraw. L82
- Spotter counters per firing agency (Arty/Mortar), one concentration marker per type (7.16.5); AT guns with a Small
  Arms VOF use no ammo (CSR 7); FJ squad breakdown keeps the MG ammo with the A fire team (Normandy p.48). L87, L91, L93
- Setup rules for missions with a setup row and one extra card (M4), 16-step stacking at setup, setup hints
  (assets in the pool, signals without an order, CCP). L75-L77
- New commands: `lateorder` (order for an HQ whose impulse already ended, cost from its saved Commands),
  `correct casualty|status|grenade|ammo|target` (fix a wrong booking with a reason), `drop <unit> <asset>`,
  `radio check <HQ>` (every unit the HQ can reach), command track display above 10. L78, L80, L83, L92, L98, L99
- Unknown options are rejected instead of silently ignored (`--agency` and friends are accepted as aliases). L72
- Grenade markers expire on movement/fall back (7.10.4); removed counters report their markers; grenade-back rule
  messages (7.10.5). L69, L70, L92
- Dead code removed, f-string and unused-variable cleanups (pyflakes clean). L81

## 2026-10-09 (first release)
Engine as used for Field Manual 1 and Normandy Missions 1 to 3, with English output and English command aliases.
