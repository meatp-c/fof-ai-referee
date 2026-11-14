# Glossary: the game state

The game state JSON (`<game>/game_state.json`) and the setup files use English keys and values. Up to the eighth
release (2026-11-07) they were German; games, setup files and snapshots written before are converted automatically
when the engine loads them (`tool/fof/migrate.py` holds the German words), and German command names, option names and
option values still work on the command line. Every key with its lifetime and meaning is listed in `tool/fof/keys.py`; this page
lists the ones an AI needs most when it reads a game state or writes a setup file.

## Game state / setup keys
| key | meaning |
|---|---|
| mission, type (offensive/defensive/patrol), target | mission title, mission type, objective text |
| turn, max_turns, phase | turn, last turn, current phase id (e.g. "3.3.2b") |
| sight (day/limited), light, weather | visibility (day or limited visibility turns), light level modifier, weather modifier |
| activity | Current Activity Level (No Contact, Contact, Engaged, Heavily Engaged) |
| units | units (dict by counter name) |
| cards | terrain cards (dict by card id = row+column, e.g. "34") |
| commands | Commands per HQ: available, saved, activated, done |
| active_hq | HQ of the current impulse |
| protocol | log of every booked step (number, turn, phase, text, rule) |
| packages, package_table | enemy packages, package table per PC letter |
| countermix | number of enemy counters in the box |
| counter_names | optional: the names printed on the enemy counters per countermix type, in the order you keep them; a new counter gets the first free name |
| enemy_prefix | optional: prefix of every enemy counter name (e.g. NKPA), so enemy and friendly names never clash |
| event_tables (friendly/enemy) | Higher HQ event tables |
| fire_missions, fm_values, fm_group, cff_table | fire missions left, VOF per mission type, battery per type, cards per observer |
| target_marker | Target/Concentration marker per firing agency |
| assets_pool, pyro_codes | assets not yet issued, pyrotechnic signal codes |
| objectives (primary, secondary, ap, ccp, cop, route, phaselines) | Tactical Controls (primary, secondary, attack position, CCP, combat outpost, route points, phase lines) |
| campaign (attempt, attempts_max, xp_table) | campaign data |
| xp | experience log (turn, attempt, points, reason) |
| prisoners, removed_from_play | prisoners, removed counters |
| patrol, patrol_mission | combat patrol state (platoon, members, route_index, success) |
| options | readings for open rules questions (see `fof.py options`) |
| reserve_units | units that are not on the board at the start |
| terrain_catalog, building_table, cover_values | terrain card values, building table, cover marker values |
| direction_table | direction table for package placement |
| illum_values | illumination marker values (top = card itself, bottom = adjacent cards) |

## Unit fields (`units[name]`)
| key | meaning |
|---|---|
| side (US/Enemy) | side |
| type | Squad, HQ, Staff, Weapons Team, FO, Fire Team, Assault Team, Paralyzed Team, Litter Team ... |
| level (BN/CO/PLT), platoon | command level, platoon number |
| experience | Green/Line/Veteran |
| card, area | card id, area on the card ("open", or a cover id "C1", "C2") |
| status | list: "Pinned", "Exposed", "Fire Team side", ... |
| steps | number of steps |
| target | card the unit is firing at |
| vof_rating, range | VOF (S, A, A/S, H, G, ...), range (P, C, L, V) |
| fire_team_side, ft_vof, ft_range | has a Fire Team side, its VOF and range |
| radio | radios: list of {type, net} (e.g. SCR536 on CO TAC) |
| ammo | ammo {type (MG/MTR/RKT), points, start} |
| assets, skills | carried assets, skill markers |
| spotted | enemy unit is spotted |
| stationary | unit may not move (e.g. not part of the current combat patrol) |
| attachment, attached_to | attachment flag, HQ it is attached to |

## Card fields (`cards[id]`)
| key | meaning |
|---|---|
| terrain, cc, cc2 | terrain type, Cover & Concealment value (cc2 = lower second value) |
| edges | card edges: "white" / "green" (dark), or per side {top, bottom, left, right, diagonal} |
| row, column | row, column |
| cover | cover markers [{id, type, value}] |
| external | markers like Incoming, Mines, Smoke, Pending [{type, value, source}] |
| pc | PC marker: "A", "B", "C", "?" or null |
| illum | illumination markers on the card |
| casualties, casualties_enemy | friendly / enemy casualty markers |
| assets_ground | assets lying on the card |
| outside | outside the map boundaries |

## Clarification ids in comments
E = player decision, K = rule clarification, V = procedure, L = tool change (see CHANGELOG), U = open rules question
(reading selectable in `options`).

## File names
`<game>/game_state.json` (game state), `<game>/history/` (snapshots for undo), `<game>/BRIEFING.md`, `.current_game`
(name of the current game folder); data/rulebook.txt, data/rulebook_compact.txt (rulebook), data/rule_index.json
(rule index), data/clarifications_2025_05_compact.txt, data/<name>_compact.txt (further texts for `search`),
data/action_cards.json (the player's action card archive). Folders and rule texts written by an earlier release under
their German names (spielstand.json, verlauf/, .aktuelle_partie, regelbuch*.txt, regelindex.json, karten.json) are still
read; a game folder is renamed to the English names when it is loaded.
