# Glossary: German names inside the engine

The engine was written in German. All output and the command line are English (German command names still work),
but **internal identifiers, JSON keys and stored values are German**. An AI reading the code or the game state
JSON needs this table. Do not translate these keys in your setup files, the engine looks them up literally.

## Game state / setup keys (`spielstand.json`, setup JSON)
| key | meaning |
|---|---|
| mission, typ (offensiv/defensiv), ziel | mission title, mission type, objective text |
| zug, max_zuege, phase | turn, last turn, current phase id (e.g. "3.3.2b") |
| sicht (tag/eingeschraenkt), licht, wetter | visibility (day/limited), light level modifier, weather modifier |
| aktivitaet | Current Activity Level (No Contact, Contact, Engaged, Heavily Engaged) |
| einheiten | units (dict by counter name) |
| karten | terrain cards (dict by card id = row+column, e.g. "34") |
| kommandos | Commands per HQ: verfuegbar (available), gespart (saved), aktiviert (activated), fertig (done) |
| aktiver_hq | HQ of the current impulse |
| protokoll | log of every booked step (nr, zug, phase, text, regel) |
| pakete, paket_tabelle | enemy packages, package table per PC letter |
| countermix | number of enemy counters in the box |
| ereignistabellen (freund/feind) | Higher HQ event tables (friendly/enemy) |
| feuermissionen, fm_werte, fm_gruppe, cff_tabelle | fire missions left, VOF per mission type, battery per type, cards per observer |
| target_marker | Target/Concentration marker per firing agency |
| assets_pool, pyro_belegung | assets not yet issued, pyrotechnic signal codes |
| ziele (primaer, sekundaer, ap, ccp, cop, route, phaselines) | Tactical Controls (primary, secondary, attack position, CCP, combat outpost, route points, phase lines) |
| kampagne (versuch, versuche_max, xp_tabelle) | campaign data (attempt, max attempts, experience table) |
| xp | experience log (zug, versuch, punkte = points, grund = reason) |
| gefangene, removed_from_play | prisoners, removed counters |
| patrouille, patrouille_mission | combat patrol state (platoon, mitglieder = members, route_index, erfolg = success) |
| optionen | readings for open rules questions (see `fof.py options`) |
| reserve_einheiten | units that are not on the board at the start |
| terrain_katalog, gebaeude_tabelle, cover_werte | terrain card values, building table, cover marker values |
| richtung_tabelle | direction table for package placement |
| illum_werte | illumination marker values (oben = card itself, unten = adjacent cards) |

## Unit fields (`einheiten[name]`)
| key | meaning |
|---|---|
| seite (US/Feind) | side (US/enemy) |
| typ | Squad, HQ, Staff, Weapons Team, FO, Fire Team, Assault Team, Paralyzed Team, Litter Team ... |
| ebene (BN/CO/PLT), platoon | command level, platoon number |
| erfahrung | experience (Green/Line/Veteran) |
| karte, bereich | card id, area on the card ("offen" = open, or cover id "C1", "C2") |
| status | list: "Pinned", "Exposed", "Fire Team side", ... |
| steps | number of steps |
| ziel | card the unit is firing at (fire target) |
| vof_rating, reichweite | VOF (S, A, A/S, H, G, ...), range (P, C, L, V) |
| fire_team_seite, ft_vof, ft_reichweite | has a Fire Team side, its VOF and range |
| funk | radios: list of {typ, netz} (e.g. SCR536 on CO TAC) |
| munition | ammo {typ (MG/MTR/RKT), punkte = points, start} |
| assets, skills | carried assets, skill markers |
| spotted | enemy unit is spotted |
| stationaer | unit may not move (e.g. not part of the current combat patrol) |
| attachment, attached_an | attachment flag, HQ it is attached to |

## Card fields (`karten[id]`)
| key | meaning |
|---|---|
| terrain, cc, cc2 | terrain type, Cover & Concealment value (cc2 = lower second value) |
| raender | card edges: "weiss" (white) / "gruen" (dark), or per side {oben, unten, links, rechts, diagonal} = top, bottom, left, right, corners |
| reihe, spalte | row, column |
| cover | cover markers [{id, typ, wert}] |
| extern | markers like Incoming, Mines, Smoke, Pending [{typ, wert, quelle}] |
| pc | PC marker: "A", "B", "C", "?" or null |
| illum | illumination markers on the card |
| casualties, casualties_feind | friendly / enemy casualty markers |
| assets_boden | assets lying on the card |
| ausserhalb | outside the map boundaries |

## Values used in commands (English alias = German value)
yes = ja, no = nein, open = offen, Left = Links, Right = Rechts, none = keiner, radio = funk, phone = telefon,
section = sektion; edges: top/bottom/left/right/white/green(dark)/corner = oben/unten/links/rechts/weiss/gruen/diagonal.

## Code terms
Verstoss = violation (exception class), prot = list of board instructions for the current step, speichern = save,
laden = load, befehl = order, aktion = action, karte = card, einheit = unit, feind = enemy, treffer = hit,
rundenende = end of turn, aufstellen = setup, ziehen = draw, Erfolg = success, Lesart = reading of an unclear rule.
Clarification ids in comments: E = player decision, K = rule clarification, V = procedure, L = tool gap fixed,
U = open rules question (reading selectable in `optionen`).

## Data file names (kept German)
data/regelbuch.txt, data/regelbuch_kompakt.txt (rulebook), data/regelindex.json (rule index),
data/clarifications_2025_05_kompakt.txt, data/karten.json (player's action card archive), `.aktuelle_partie`
(name of the current game folder), `<game>/spielstand.json` (game state), `<game>/BRIEFING.md`.
