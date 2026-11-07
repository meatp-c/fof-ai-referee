"""Key register of the game state (L530, code review 07.11.2026 S1/E1).

The game state is a nested dict saved as spielstand.json. Its keys are German (JSON compatibility with every saved game),
the code and messages are English. This module lists every key the engine writes or the setup files bring in, with its
lifetime and meaning, for six structures:

    GAME      the state itself (s)
    UNIT      a unit or vehicle (s["einheiten"][name], also reserve_einheiten / aufbau_einheiten)
    CARD      a terrain card (s["karten"][id])
    COVER     a cover marker on a card (s["karten"][id]["cover"][i])
    RADIO     a radio or field phone carried by a unit (unit["funk"][i])
    COMMANDS  the command record of an HQ (s["kommandos"][name])

SUBKEYS names keys of smaller sub-structures (vehicle phase, patrol, events, ammo, protocol entries, ...); they are not
checked field by field, only listed so the source scan in tests/test_keys.py knows them.

Lifetimes:
    setup    from the mission setup file; changed only by setup or correction commands
    mission  built up during play, kept until the mission ends
    attempt  reset when a reattempt starts (3.9, campaign.start_reattempt)
    turn     cleared in Clean Up (3.8) or at the end of the turn
    phase    lives for one phase or segment
    action   lives for one action (an order, a vehicle action, a contact)
    command  one command only; popped before saving (never in spielstand.json)
    legacy   written by older engine versions or present in old setup files; not read any more

Checks: with the environment variable FOF_KEY_CHECK=1 (set by tests/conftest.py and normandy/regression.sh)
state.save_state refuses a state that carries an unregistered key (check_state below). In normal play the check is off,
so a missing entry can never block a booking. tests/test_keys.py scans the source for every literal key written with
x["key"] = ..., setdefault("key"), update(key=...), unit dict literals and dict literals assigned to s[...] and fails if
it is not registered here.

Lifetime contract (L554, review E2): every 'turn' key of GAME, UNIT, CARD and COMMANDS is gone or empty after the
end of the turn, and no 'command' key is ever saved; tests/test_keys.py checks both generically from this register,
so a new 'turn' key without a clean up fails a test at once.

Adding a key: put it into the right structure with lifetime and one line of meaning; for a working flag also say who
sets and who clears it (a flag that nobody clears is the most common bug class of the 07.11.2026 review).
"""

import os

# ---------------------------------------------------------------- GAME (s)
GAME = {
    # mission data from the setup file
    "mission": ("setup", "mission title"),
    "typ": ("setup", "mission type: offensiv, defensiv, patrouille (selects the sequence of play, state.sop)"),
    "sicht": ("mission", "visibility: tag or eingeschraenkt (limited visibility turns)"),
    "licht": ("mission", "light level modifier of limited visibility (Illumination)"),
    "wetter": ("mission", "weather modifier"),
    "wetter_nur_zug": ("turn", "weather given with --this-turn-only: reset to 0 in this turn's Clean Up"),
    "visibility": ("mission", "visibility value for LOS (geometry.los)"),
    "aktivitaet": ("mission", "enemy activity level (No Contact, Contact, ...)"),
    "zug": ("mission", "current turn"),
    "max_zuege": ("attempt", "turns of the current attempt"),
    "phase": ("mission", "current phase or segment id (3.1 ... 3.8)"),
    "ziel": ("setup", "mission objective text"),
    "ziele": ("setup", "objective cards (primaer, sekundaer, route, phaselines)"),
    "ziele_hinweis": ("setup", "note on the objectives"),
    "ziele_quelle": ("setup", "source of the objectives (mission book page)"),
    "ziele_reihen": ("setup", "objective rows per objective (Naktong)"),
    "ziel_regeln": ("setup", "objective rules: sichern, pc_klaeren, reihen_klaeren, ..."),
    "ap_neben": ("setup", "which objectives count as neighbours of an Assembly Point"),
    "loa": ("legacy", "line of advance row (old setup files)"),
    "mlr_reihe": ("legacy", "main line of resistance row (old setup files)"),
    "kartenschema": ("legacy", "card layout description (old setup files)"),
    "karten": ("mission", "terrain cards by id, see CARD"),
    "einheiten": ("mission", "units on the board by name, see UNIT"),
    "reserve_einheiten": ("setup", "units held back (patrol reserve, event units)"),
    "aufbau_einheiten": ("mission", "units as set up at the start (for reattempt, experience, replacements; L-v4)"),
    "removed_from_play": ("mission", "names of friendly units removed from play (new_name avoids them, 6.5.2)"),
    "rfp_daten": ("mission", "level/platoon of removed HQs, for reconstitution (6.5.2)"),
    "kommandos": ("mission", "command records of the HQs, see COMMANDS"),
    "aktiver_hq": ("phase", "HQ whose impulse is running, or GI; None between impulses"),
    "impuls_aktionen": ("phase", "actions per unit in the running impulse (one action per unit and impulse, 4.2)"),
    "impuls_ausgegeben": ("phase", "commands spent per HQ in the running impulse (cap 4.1.3)"),
    "protokoll": (
        "mission",
        "protocol entries (nr, zug, phase, text, regel, zeit); the entry number is the CHECKSTAMP",
    ),
    "optionen": ("setup", "chosen readings of open rules questions (U-options), state.option"),
    "kampagne": ("mission", "campaign record: versuch, ... (12.x)"),
    "versuch_plan": ("setup", "turns, visibility and enemy values per attempt (L477)"),
    "missionsende": ("mission", "the mission has ended (campaign steps allowed)"),
    "reattempt_setup": ("attempt", "setup of a reattempt is running (3.9)"),
    "reattempt_gesichert": ("attempt", "cards secured at the end of the attempt, snapshot for reattempt step 5 (L506)"),
    "aufstellung_feld": ("setup", "units set up on the field instead of the staging area (defensive missions)"),
    "aufstellung_fertig": ("mission", "initial setup finished"),
    "einzelzug": ("setup", "single-platoon mission (GI halved, PLT HQ as CO)"),
    # command structure
    "co_hq": ("setup", "name of the CO HQ"),
    "bn_hq": ("setup", "name of the BN HQ"),
    "bn_nicht_verfuegbar": ("turn", "BN HQ not available this turn (event)"),
    "co_immer_in_kommunikation": ("setup", "CO HQ always in communication (FM1 CAC)"),
    "co_immer_in_kommunikation_mit": ("setup", "units the CO HQ is always in communication with"),
    "co_tac_mittel": ("mission", "CO TAC net medium: funk or telefon (CSR 1)"),
    "funk_aktiv": ("setup", "radio rules in use (v3/v4)"),
    "funk_frei": ("mission", "radios in the pool, not yet carried by a unit"),
    "funk_zerstoert": ("mission", "radios destroyed by radio damage checks"),
    "mtr_sec_funk_frei": ("mission", "radios of the Mortar Section freed when it was split into teams (CSR 2)"),
    "telefon_leitungen": ("setup", "phone lines available with field phones (CSR 1)"),
    "telefon_hinweis": ("setup", "note on field phones"),
    "leitungen_pool": ("mission", "phone lines not yet carried or laid"),
    "leitung_checks": ("phase", "pending phone line checks by card"),
    "runner_start": ("setup", "number of runners"),
    "runner_box": ("mission", "runners waiting in the CO HQ assets box (4.3.2)"),
    "runner_hinweis": ("setup", "note on runners"),
    # fire support
    "feuermissionen": ("mission", "fire missions left per agency"),
    "fm_start": ("mission", "fire missions at the start (for reattempt)"),
    "fm_werte": ("setup", "fire mission values per agency and ammo"),
    "fm_wert": ("setup", "default value of an enemy fire mission"),
    "fm_gruppe": ("setup", "agency groups (one target marker per group)"),
    "fm_hinweis": ("setup", "note on fire missions"),
    "fm_gesperrt": ("turn", "fire missions of one group blocked this turn (event)"),
    "bataillon_fm": ("setup", "battalion fire missions"),
    "cff_beobachter": ("setup", "who may call for fire per agency (7.16.1 table)"),
    "cff_karten": ("setup", "cards to draw for Call for Fire"),
    "cff_tabelle": ("setup", "Call for Fire table per observer type"),
    "target_marker": ("mission", "target marker card per agency"),
    "konzentration_gesetzt": ("attempt", "concentrations placed before the attempt (L56)"),
    # assets, ammo, pyro
    "assets_pool": ("mission", "assets not yet given to a unit"),
    "assets_start": ("mission", "assets at the start (for reattempt)"),
    "assets_hinweis": ("setup", "note on assets"),
    "pyro_belegung": ("mission", "pyrotechnic signal meanings"),
    "pyro_hinweis": ("setup", "note on pyrotechnics"),
    "rifle_grenade_reichweite": ("setup", "rifle grenade range"),
    "rifle_grenade_hinweis": ("setup", "note on rifle grenades"),
    "rifle_grenade_je_platoon": ("setup", "rifle grenade shots per platoon (L491)"),
    "hmg_ersatzmunition": ("setup", "spare MG ammo of the HMG platoon (Naktong MSR 4)"),
    "moerser_wahl": ("mission", "60mm mortar choice: section or teams (CSR 2)"),
    "mtr_team_de": ("setup", "German mortar team templates for the mortar breakdown"),
    "arty_jeep_moeglich": ("setup", "the mission offers the Arty Jeep (Normandy CSR 1)"),
    "arty_jeep_wahl": ("mission", "Arty Jeep chosen: ja or nein"),
    "befestigung_gesetzt": ("attempt", "fortifications placed between attempts"),
    "befestigung_zwischen_versuchen": ("setup", "fortifications allowed between attempts"),
    "ccp": ("mission", "Casualty Collection Point card"),
    "evakuiert": ("mission", "casualties evacuated from the CCP"),
    "us_casualties_gesamt": ("mission", "US casualties of the mission (12.x)"),
    "us_gefangen": ("mission", "US steps captured by the enemy (8.15)"),
    "gefangene": ("mission", "prisoners taken by the US side"),
    "gefangene_nehmen": ("setup", "which side takes prisoners (8.15; NKPA none)"),
    "capture_offen": ("phase", "units that may be captured in this phase"),
    # enemy
    "pakete": ("mission", "enemy packages by number (units, place_vof, im_spiel)"),
    "paket_tabelle": ("setup", "R# table of enemy packages per PC letter"),
    "paket_tabelle_gegenangriff": ("setup", "package table of the planned counter attack"),
    "paket_munition": ("attempt", "ammo of package units per type"),
    "pc_start": ("mission", "PC markers at the start (for reattempt)"),
    "pc_marker_gesamt": ("legacy", "PC marker count (old setup files)"),
    "pc_vorrat": ("legacy", "PC marker supply (old setup files)"),
    "pc_zufall": ("legacy", "random PC placement (old setup files)"),
    "countermix": ("setup", "enemy counters available per type"),
    "countermix_hinweis": ("setup", "note on the countermix"),
    "counter_vof": ("mission", "VOF rating learned per enemy counter type"),
    "richtung_tabelle": ("setup", "direction table for package placement (8.4)"),
    "feind_taktik": ("attempt", "enemy tactic (Delay, Hasty Defense, Assault, ...)"),
    "feind_erfahrung_versuch": ("attempt", "enemy experience per attempt"),
    "feind_target": ("mission", "target marker card of enemy fire missions per spotter"),
    "feind_gruppe": ("legacy", "enemy group (old setup files)"),
    "granate_vof": ("setup", "VOF of enemy grenade attacks (Naktong -3)"),
    "granate_antworten": ("phase", "pending free grenade attack responses (7.10.5)"),
    "gegenangriff": ("mission", "planned counter attack: state and until which turn (Naktong)"),
    "rally_offen": ("phase", "enemy units that owe an event Rally"),
    "sniper_ziele": ("phase", "sniper targets chosen in this phase"),
    "sniper_offen": ("phase", "pending sniper results"),
    "minen_checks": ("phase", "units that owe a mine check (7.9)"),
    "minen_check_info": ("phase", "card and reason per pending mine check"),
    "hitze": (
        "mission",
        "heat condition {bis_zug}: active up to that turn, removed by state.heat_check afterwards (Naktong M1)",
    ),
    "hitze_offen": ("phase", "units that owe a heat casualty check (L483)"),
    "hold_up": ("turn", "Hold Up event: turn in which it applies; removed in Clean Up"),
    # events
    "ereignistabellen": ("setup", "friendly and enemy event tables"),
    "ereignis_erledigt": ("mission", "events already resolved (once-only events)"),
    "ereignis_einheiten": ("mission", "units that entered through an event"),
    "ereignis_vorrat": ("mission", "event supplies (tank support, hmg50, ...)"),
    "ereignis_pflicht": ("attempt", "event with a mandatory task"),
    "ereignis_flanke": ("attempt", "flank event state"),
    "ereignis_route": ("attempt", "route event state"),
    "ereignis_munition": ("attempt", "ammo event state"),
    "keine_ereignisse": ("setup", "the mission has no events"),
    # patrol
    "patrouille": ("mission", "patrol state (platoon, mitglieder, route_index, ...)"),
    "patrouille_mission": ("setup", "this is a combat patrol mission (2.6)"),
    "patrouille_reserve": ("mission", "units of the patrol reserve"),
    "patrouille_wechsel": ("mission", "patrol change pending"),
    "wachen": ("mission", "guards left behind (patrol)"),
    # experience
    "xp": ("mission", "experience points entries (12.x)"),
    "xp_karten": ("mission", "cards drawn for experience"),
    "befoerdert": ("mission", "promotions made"),
    # tables and catalogues
    "terrain_katalog": ("setup", "terrain types with cover values, trafficability, ..."),
    "gebaeude_tabelle": ("setup", "building tables (Seek Cover in buildings)"),
    "cover_werte": ("setup", "cover values per marker type"),
    "cover_hinweis": ("setup", "note on cover"),
    "illum_werte": ("setup", "illumination values"),
    "fahrzeug_werte": ("setup", "vehicle values of the mission"),
    "sonderregeln": ("setup", "special rules of the mission"),
    "hinweis": ("setup", "note on the mission"),
    "_unverifiziert": ("legacy", "list of unverified setup values (old setup files)"),
    "stornos": ("legacy", "cancelled entries (old engine)"),
    # combat bookkeeping
    "kampf_offen": ("phase", "units that still owe Combat Effects in 3.7.4"),
    "kampf_ncm": ("phase", "NCM rows per unit frozen at the start of 3.7.4"),
    "letzter_versuch": (
        "phase",
        "[unit, action, phase] of the last failed attempt (Exhort); cleared on success, by Exhort and at end of turn",
    ),
    "exhort_frei": ("action", "[unit, action, phase] of a free follow-up attempt after Exhort; cleared by book_order"),
    "at36": ("phase", "AT Combat & Vehicle Movement phase: queue, aktion, naechste, wahl (vehicles.py)"),
    "_ce_start": ("phase", "protocol entry at the start of 3.7.4 (marker changes announced when leaving)"),
    # never saved
    "_befehl_opts": ("command", "options of the running order; popped by book_order and save_state"),
    "_hinweise": ("command", "hint lines for this command's output; popped by save_state"),
    "_phase_alt": ("command", "phase before phase next; popped by save_state"),
    "_pionier_check": ("command", "(unit, card, mine draws) of an Engineer move; popped by move_unit"),
    "_fj_r": ("command", "R# given for a FJ breakdown during the running hit"),
}

# ---------------------------------------------------------------- UNIT (s["einheiten"][name])
UNIT = {
    "seite": ("setup", "US or Feind"),
    "typ": ("setup", "Squad, HQ, Staff, Weapons Team, Fire Team, LAT types, FO, Vehicle, ..."),
    "typname": ("setup", "display type name of a LAT or enemy counter"),
    "ebene": ("setup", "HQ level: PLT, CO, BN"),
    "rang": ("setup", "Staff rank order (Command Reference Table)"),
    "platoon": ("setup", "platoon of the unit (chain of command)"),
    "attached_an": ("mission", "HQs the unit is attached to"),
    "attachment": ("setup", "attached unit (no reconstitution)"),
    "erfahrung": ("mission", "experience: Green, Line, Veteran; crewless jeep: highest on board (10.8.8)"),
    "steps": ("mission", "steps; crewless jeep 0"),
    "status": ("mission", "markers: Pinned, Exposed, Activated, Moved/Fired, Fire Team side, ..."),
    "karte": ("mission", "card the unit is on (None before setup)"),
    "bereich": ("mission", "area on the card: offen or a cover marker id"),
    "vof_rating": ("setup", "VOF rating of the front side (S, A, H, G!, ...)"),
    "reichweite": ("setup", "range of the front side (P, C, L, V)"),
    "fire_team_seite": ("setup", "the counter has a Fire Team back side"),
    "ft_vof": ("setup", "VOF rating of the Fire Team side"),
    "ft_reichweite": ("setup", "range of the Fire Team side"),
    "letzter_step": ("setup", "what the last step becomes (Fire Team, ...)"),
    "letzter_step_werte": ("setup", "values of the last step (Normandy p.48 A-rated Fire Team)"),
    "ziel": ("phase", "card the unit fires at (PDF); cleared by fire.cease_fire"),
    "ziel_offen": ("phase", "the unit must choose a target; cleared by fire.cease_fire"),
    "konzentriert": ("phase", "Concentrated Fire on the target; cleared by fire.cease_fire"),
    "_rauch_ziel": ("phase", "old target while smoke/Incoming blocks LOS; cleared by fire.cease_fire"),
    "_vof_sperre": ("phase", "VOF blocked by LOS loss; cleared by fire.cease_fire"),
    "_reichweite_vof": ("phase", "VOF limited by range; cleared by fire.cease_fire"),
    "nur_pdf": ("turn", "PDF only, no VOF this turn; cleared in Clean Up"),
    "kein_feuer_bis_clean_up": ("turn", "may not fire until Clean Up"),
    "cf": ("phase", "Concentrated Fire markers on the unit"),
    "cf_critical": ("phase", "Critical Hit of a Concentrated Fire"),
    "grenade": ("phase", "Grenade VOF values on the unit (7.10)"),
    "grenade_critical": ("phase", "Critical Hit of a grenade attack"),
    "grenade_ranged": ("setup", "may make ranged grenade attacks"),
    "spotted": ("mission", "enemy unit is spotted"),
    "funk": ("mission", "radios and phones carried, see RADIO"),
    "leitungen": ("mission", "phone lines carried"),
    "assets": ("mission", "assets carried (smoke, rifle grenades, ...)"),
    "munition": ("mission", "ammo marker: typ, punkte, start"),
    "munition_leer": ("mission", "ammo used up"),
    "out_of_ammo": ("mission", "Out of Ammo (7.18)"),
    "ooa_flip": (
        "mission",
        "flipped to the Fire Team side by Out of Ammo; cleared by resupply and by a deliberate flip (L228)",
    ),
    "ooa_fallback": ("mission", "enemy unit falls back after its Out of Ammo flip"),
    "rkt_leer": ("mission", "rocket ammo used up"),
    "traegt_munition": ("mission", "carries ammo for another unit: typ, punkte"),
    "traegt_casualties": ("mission", "carries casualties (Litter Team)"),
    "munition_traeger_abstrakt": ("setup", "ammo carriers are abstracted (mortar section)"),
    "rifle_grenades": ("mission", "rifle grenade shots"),
    "panzerfaust": ("setup", "carries a Panzerfaust"),
    "at_waffe": ("setup", "AT weapon (chart key)"),
    "tripod": ("setup", "tripod-mounted machine gun (+1 card for Concentrate Fire)"),
    "moerser": ("setup", "mortar unit"),
    "indirekt": ("phase", "mortar in Indirect Lay"),
    "breakdown": ("setup", "breakdown rule (mtr_sec, ...)"),
    "breakdown_hinweis": ("setup", "note on the breakdown"),
    "fj_breakdown": ("setup", "German FJ breakdown with R#"),
    "herkunft": ("mission", "unit a LAT came from"),
    "pc_herkunft": ("mission", "PC marker an enemy unit came from"),
    "paket": ("mission", "enemy package number"),
    "quelle": ("setup", "source of the values (mission book page)"),
    "hinweis": ("setup", "note on the unit"),
    "skills": ("mission", "skill markers (12.7)"),
    "skills_hinweis": ("setup", "note on skills"),
    "beobachter": ("setup", "may act as observer for Call for Fire"),
    "spotter": ("setup", "enemy spotter of a fire mission"),
    "fm_wert": ("mission", "fire mission value of an enemy spotter"),
    "missionen": ("mission", "fire missions left for an enemy spotter"),
    "karten_folge": ("setup", "cards per enemy fire mission sequence"),
    "leader": ("setup", "enemy leader"),
    "human_wave": ("setup", "NKPA Human Wave unit, never Pinned (8.14)"),
    "ambush": ("mission", "AT ambush position (10.8.3)"),
    "unbeweglich": ("setup", "enemy unit that does not move"),
    "deep_bunker": ("mission", "enemy unit in a Deep Bunker: no VOF until it leaves"),
    "kein_point_blank": (
        "mission",
        "enemy in a Bunker/Pillbox: no Point Blank fire (placement); derive from cover when the unit leaves",
    ),
    "bunker_richtung": ("mission", "fire direction of a Bunker/Pillbox (placement)"),
    "check_offen": (
        "phase",
        "enemy unit owes its Activity Check; set/cleared by enemy.prepare_enemy_check and cmd_enemy_action",
    ),
    "hat_gehandelt": ("phase", "vehicle has acted in 3.6; set by vehicles.end_action, cleared by vehicles.clean_up"),
    "in_bewegung": ("action", "vehicle moved in its current action; cleared by vehicles.end_action and clean_up"),
    "crew_hit_offen": ("phase", "crew of a Knocked Out vehicle owes its HIT; cleared by combat.cmd_hit"),
    "mine_hit": ("turn", "unit was hit by a mine this turn: may not move (7.9.1)"),
    "stationaer": ("mission", "not part of the patrol: no movement (Normandy M3 MSR 1)"),
    "nur_versuch": ("attempt", "unit stays only until the end of the attempt (event unit)"),
    "engineer": ("setup", "engineer squad (CSR 10)"),
    "fahrzeug": ("setup", "vehicle type (chart key); makes the unit a vehicle"),
    "an_bord": ("mission", "vehicle the unit is embarked on (10.8.1)"),
    "arty_jeep": ("setup", "the Arty Jeep (Normandy CSR 1, L454)"),
    "kompanie_jeep": ("setup", "the company jeep asset (Naktong p.12, L528)"),
    "runner_ziel": ("mission", "HQ a runner carries a message to (4.3.2)"),
    "unterwegs_seit": ("mission", "turn the runner set off (arrives the turn after)"),
    "bis_zug": ("mission", "unit leaves play at the end of this turn (Bn Cmdr event unit)"),
    "_neu_exposed": ("command", "became Exposed in this command (heat check); popped by save_state"),
    "dreifuss": ("legacy", "tripod (old name of tripod)"),
    "fd_netz": ("legacy", "FD net (old radio model)"),
    "kompanie_waffe": ("legacy", "company weapon (old setup files)"),
}

# ---------------------------------------------------------------- CARD (s["karten"][id])
CARD = {
    "reihe": ("setup", "row"),
    "spalte": ("setup", "column"),
    "kartennummer": ("mission", "number printed on the terrain card"),
    "terrain": ("mission", "terrain type (key of terrain_katalog)"),
    "elevation": ("mission", "elevation level"),
    "raender": ("mission", "card edges (weiss, ...) for LOS"),
    "cc": ("mission", "Cover and Concealment value"),
    "cc2": ("mission", "second C&C value (split card)"),
    "cover_draw": ("mission", "cover draw number (Seek Cover base)"),
    "cover_max": ("mission", "maximum number of cover markers"),
    "cover": ("mission", "cover markers on the card, see COVER"),
    "extern": (
        "mission",
        "external markers: Incoming, Smoke, Mines, Indirect, Illum (typ, wert, quelle, seite, aktiv)",
    ),
    "verdeckt": ("mission", "card is face down"),
    "staging": ("setup", "staging area card"),
    "ausserhalb": ("setup", "outside the mission boundaries (extension card)"),
    "fahrzeuge": ("mission", "trafficability for vehicles"),
    "gebaeude_tabelle": ("mission", "building table of the card"),
    "mehrstoeckig": ("mission", "multi-storey building"),
    "urban": ("mission", "urban card"),
    "op": ("mission", "observation post"),
    "moerser_verbot": ("mission", "no mortar fire onto the card"),
    "burst": ("mission", "burst symbol value (Incoming, indirect mortar)"),
    "pc": ("mission", "PC marker letter (or ?)"),
    "pc2": ("mission", "second PC marker on the card"),
    "ziel": ("setup", "objective marker on the card"),
    "casualties": ("mission", "US casualties on the card"),
    "casualties_feind": ("mission", "enemy casualties on the card"),
    "assets": ("mission", "assets dropped on the card"),
    "assets_boden": ("mission", "assets on the ground (dropped by removed units)"),
    "munition": ("mission", "ammo dropped on the card per type"),
    "leitungen": ("mission", "phone lines laid on the card (cut)"),
    "leitung_assets": ("mission", "phone line assets lying on the card"),
    "grenade_miss": ("turn", "Grenade Miss modifier on the card (7.10.4)"),
    "illum": ("turn", "illumination on the card"),
    "pyro": ("turn", "pyrotechnic signals shown on the card (display only)"),
    "hinweis": ("setup", "note on the card"),
    "verifiziert": ("legacy", "values verified against the card (old setup files)"),
}

# ---------------------------------------------------------------- COVER (card["cover"][i])
COVER = {
    "id": ("mission", "marker id on the card (C1, C2, ...)"),
    "typ": ("mission", "marker type (Basic Cover, Foxholes, Bunker, ...)"),
    "wert": ("mission", "cover value"),
    "feld": ("mission", "field fortification, not a terrain cover marker"),
    "kapazitaet": ("mission", "steps the marker holds"),
    "richtung": ("mission", "fire direction of a Bunker/Pillbox"),
}

# ---------------------------------------------------------------- RADIO (unit["funk"][i])
RADIO = {
    "typ": ("setup", "device: SCR300, SCR536, SCR610, EE8"),
    "netz": ("setup", "net: BN TAC, CO TAC, Arty FD, Mtr FD"),
    "eingebaut": ("mission", "mounted in this vehicle; works only on board (L454)"),
    "schaden_offen": ("phase", "radio damage check pending"),
}

# ---------------------------------------------------------------- COMMANDS (s["kommandos"][hq])
COMMANDS = {
    "verfuegbar": ("phase", "commands available in this impulse"),
    "gespart": ("mission", "commands saved (4.1.3)"),
    "aktiviert": ("turn", "HQ activated this turn"),
    "fertig": ("turn", "HQ has ended its impulse"),
    "gezogen": ("turn", "card drawn for the HQ's commands"),
}

# ---------------------------------------------------------------- keys of smaller sub-structures (not field-checked)
SUBKEYS = {
    # at36 (vehicles.py)
    "aktion": "at36: running vehicle action",
    "plan": "at36 action: remaining plan steps",
    "queue": "at36: pending AT draws",
    "naechste": "at36: side that acts next",
    "wahl": "at36: open target choice",
    "bewegt": "at36 action: vehicle has moved",
    "slow": "at36 action: SLOW terrain stops the move",
    "gefeuert": "at36 action: vehicle has fired",
    "ende": "at36 action: action ends after the queue",
    "angegriffen": "at36: vehicles attacked this phase",
    "reaction": "at36 queue item: reaction fire",
    "reaktion_offen": "at36: open US Reaction Fire window {ziel, schuetzen}; closed by vehicle react / react pass (L531)",
    "schuetzen": "at36 reaktion_offen: US units that may still react",
    "typ_nach": "at36 wahl: kind of the draw queued after the choice (quick, action; L543)",
    "g_karten": "at36 queue item: cards of the G! grenade attempt",
    # patrol (campaign.py)
    "mitglieder": "patrouille: member units",
    "route_index": "patrouille: next route card",
    "primaer_besucht": "patrouille: primary objective visited",
    "erfolg": "patrouille: patrol succeeded",
    "erledigt": "patrouille: route cards done",
    "teilgenommen": "patrouille: units that took part",
    # objectives (setup.py)
    "primaer": "ziele: primary objective card",
    "route": "ziele: patrol route",
    "phaselines": "ziele: phase lines by name",
    # events and counter attack (events.py)
    "bis_zug": "gegenangriff/hitze: until which turn",
    "bezahlt": "event: cost paid",
    "erfuellt": "event: task fulfilled",
    "geprueft": "event: checked",
    "tank_support": "ereignis_vorrat: tank support event",
    "commands": "ereignis_pflicht: commands the task costs",
    "stern": "ereignis_pflicht/flanke/route: star number of the event card",
    "gruppe": "fm_gesperrt: blocked agency group",
    "taktik_vorher": "gegenangriff: enemy tactic before the counter attack",
    # campaign record
    "versuch": "kampagne: current attempt",
    # ammo marker
    "punkte": "munition: ammo points left",
    "start": "munition: ammo points at the start",
    # card markers
    "aktiv": "extern Mines marker: flipped to the explosion side",
    "cut": "card leitungen: phone line cut",
    # enemy packages (contact.py)
    "im_spiel": "pakete: package is on the board",
    "platz": "package unit: placement rule",
    "_ref": "package unit: reference unit for mit_zufaelligem placement (L522)",
    # dynamic unit names written as keys
    "GI": "kommandos: General Initiative pseudo HQ",
    "Mtr Sec": "einheiten: 60mm Mortar Section (CSR 2)",
    # state.py disk cache (_DISK), not game state
    "path": "state._DISK: file path",
    "stat": "state._DISK: file mtime and size",
    "entries": "state._DISK: protocol length",
    "text": "state._DISK: serialized state",
}

STRUCTURES = {"GAME": GAME, "UNIT": UNIT, "CARD": CARD, "COVER": COVER, "RADIO": RADIO, "COMMANDS": COMMANDS}
LIFETIMES = {"setup", "mission", "attempt", "turn", "phase", "action", "command", "legacy"}


def unknown_keys(s):
    """Keys of the state that are not registered, as 'structure path: key' strings (empty list: all registered)."""
    bad = [f"state: {k}" for k in s if k not in GAME]
    for coll in ("einheiten", "reserve_einheiten", "aufbau_einheiten"):
        for n, e in (s.get(coll) or {}).items():
            if not isinstance(e, dict):
                continue
            bad += [f"{coll}[{n}]: {k}" for k in e if k not in UNIT]
            for g in e.get("funk") or []:
                if isinstance(g, dict):
                    bad += [f"{coll}[{n}].funk: {k}" for k in g if k not in RADIO]
    for kid, c in (s.get("karten") or {}).items():
        if not isinstance(c, dict):
            continue
        bad += [f"karten[{kid}]: {k}" for k in c if k not in CARD]
        for m in c.get("cover") or []:
            if isinstance(m, dict):
                bad += [f"karten[{kid}].cover: {k}" for k in m if k not in COVER]
    for hq, k in (s.get("kommandos") or {}).items():
        if isinstance(k, dict):
            bad += [f"kommandos[{hq}]: {x}" for x in k if x not in COMMANDS]
    return bad


def check_state(s):
    """FOF_KEY_CHECK=1 (tests, regression): list of unregistered keys as error strings for state.save_state."""
    if not os.environ.get("FOF_KEY_CHECK"):
        return []
    bad = unknown_keys(s)
    return (
        [f"unregistered key(s), add them to fof/keys.py: {', '.join(bad[:8])}" + (" ..." if len(bad) > 8 else "")]
        if bad
        else []
    )
