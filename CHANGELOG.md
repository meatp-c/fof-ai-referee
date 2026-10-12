# Changelog

## 2026-10-12 (restructuring, same behaviour)
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
