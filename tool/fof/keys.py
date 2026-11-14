"""Key register of the game state.

The game state is a nested dict saved as game_state.json. Its keys and values are English since (until they
were German; migrate.py translates older games and setup files on load). This module lists every key the engine writes
or the setup files bring in, with its lifetime and meaning, for six structures:

    GAME      the state itself (s)
    UNIT      a unit or vehicle (s["units"][name], also reserve_units / setup_units)
    CARD      a terrain card (s["cards"][id])
    COVER     a cover marker on a card (s["cards"][id]["cover"][i])
    RADIO     a radio or field phone carried by a unit (unit["radio"][i])
    COMMANDS  the command record of an HQ (s["commands"][name])

SUBKEYS names keys of smaller sub-structures (vehicle phase, patrol, events, ammo, protocol entries, ...); they are not
checked field by field, only listed so the source scan in tests/test_keys.py knows them.

Lifetimes:
    setup    from the mission setup file; changed only by setup or correction commands
    mission  built up during play, kept until the mission ends
    attempt  reset when a reattempt starts (3.9, campaign.start_reattempt)
    turn     cleared in Clean Up (3.8) or at the end of the turn
    phase    lives for one phase or segment
    action   lives for one action (an order, a vehicle action, a contact)
    command  one command only; popped before saving (never in game_state.json)
    legacy   written by older engine versions or present in old setup files; not read any more

Checks: with the environment variable FOF_KEY_CHECK=1 (set by tests/conftest.py and normandy/regression.sh)
state.save_state refuses a state that carries an unregistered key (check_state below). In normal play the check is off,
so a missing entry can never block a booking. tests/test_keys.py scans the source for every literal key written with
x["key"] = ..., setdefault("key"), update(key=...), unit dict literals and dict literals assigned to s[...] and fails if
it is not registered here.

Lifetime contract: every 'turn' key of GAME, UNIT, CARD and COMMANDS is gone or empty after the
end of the turn, and no 'command' key is ever saved; tests/test_keys.py checks both generically from this register,
so a new 'turn' key without a clean up fails a test at once.

Adding a key: put it into the right structure with lifetime and one line of meaning; for a working flag also say who
sets and who clears it (a flag that nobody clears is the most common bug class).
"""

import os

# ---------------------------------------------------------------- GAME (s)
GAME = {
    # mission data from the setup file
    "mission": ("setup", "mission title"),
    "type": ("setup", "mission type: offensive, defensive, patrol (selects the sequence of play, state.sop)"),
    "sight": ("mission", "visibility: day or limited (limited visibility turns)"),
    "light": ("mission", "light level modifier of limited visibility (Illumination)"),
    "weather": ("mission", "weather modifier"),
    "weather_this_turn_only": ("turn", "weather given with --this-turn-only: reset to 0 in this turn's Clean Up"),
    "visibility": ("mission", "visibility value for LOS (geometry.los)"),
    "activity": ("mission", "enemy activity level (No Contact, Contact, ...)"),
    "turn": ("mission", "current turn"),
    "max_turns": ("attempt", "turns of the current attempt"),
    "phase": ("mission", "current phase or segment id (3.1 ... 3.8)"),
    "target": ("setup", "mission objective text"),
    "objectives": ("setup", "objective cards (primary, secondary, route, phaselines)"),
    "objectives_note": ("setup", "note on the objectives"),
    "objectives_source": ("setup", "source of the objectives (mission book page)"),
    "objective_rows": ("setup", "objective rows per objective (Naktong)"),
    "objective_rules": ("setup", "objective rules: secure, clear_pcs, clear_rows, ..."),
    "ap_neighbours": ("setup", "which objectives count as neighbours of an Assembly Point"),
    "loa": ("legacy", "line of advance row (old setup files)"),
    "mlr_row": ("legacy", "main line of resistance row (old setup files)"),
    "card_layout": ("legacy", "card layout description (old setup files)"),
    "cards": ("mission", "terrain cards by id, see CARD"),
    "units": ("mission", "units on the board by name, see UNIT"),
    "reserve_units": ("setup", "units held back (patrol reserve, event units)"),
    "setup_units": ("mission", "units as set up at the start (for reattempt, experience, replacements)"),
    "removed_from_play": ("mission", "names of friendly units removed from play (new_name avoids them, 6.5.2)"),
    "rfp_data": ("mission", "level/platoon of removed HQs, for reconstitution (6.5.2)"),
    "commands": ("mission", "command records of the HQs, see COMMANDS"),
    "active_hq": ("phase", "HQ whose impulse is running, or GI; None between impulses"),
    "impulse_actions": ("phase", "actions per unit in the running impulse (one action per unit and impulse, 4.2)"),
    "impulse_spent": ("phase", "commands spent per HQ in the running impulse (cap 4.1.3)"),
    "protocol": (
        "mission",
        "protocol entries (number, turn, phase, text, rule, time); the entry number is the CHECKSTAMP",
    ),
    "protocol_entries": ("mission", "snapshots only: the number of protocol entries (the protocol is not copied)"),
    "options": ("setup", "chosen readings of open rules questions (U-options), state.option"),
    "campaign": ("mission", "campaign record: attempt, ... (12.x)"),
    "attempt_plan": ("setup", "turns, visibility and enemy values per attempt"),
    "mission_end": ("mission", "the mission has ended (campaign steps allowed)"),
    "reattempt_setup": ("attempt", "setup of a reattempt is running (3.9)"),
    "reattempt_secured": ("attempt", "cards secured at the end of the attempt, snapshot for reattempt step 5"),
    "setup_field": ("setup", "units set up on the field instead of the staging area (defensive missions)"),
    "setup_done": ("mission", "initial setup finished"),
    "single_platoon": ("setup", "single-platoon mission (GI halved, PLT HQ as CO)"),
    # command structure
    "co_hq": ("setup", "name of the CO HQ"),
    "bn_hq": ("setup", "name of the BN HQ"),
    "bn_unavailable": ("turn", "BN HQ not available this turn (event)"),
    "bn_reconstituting": ("mission", "turn in which the BN HQ gives no orders after its loss on the map (6.5.2 C)"),
    "co_always_in_comm": ("setup", "CO HQ always in communication (FM1 CAC)"),
    "co_always_in_comm_with": ("setup", "units the CO HQ is always in communication with"),
    "co_tac_medium": ("mission", "CO TAC net medium: radio or phone (CSR 1)"),
    "radio_active": ("setup", "radio rules in use (company and campaign games)"),
    "radio_free": ("mission", "radios in the pool, not yet carried by a unit"),
    "radio_destroyed": ("mission", "radios destroyed by radio damage checks"),
    "mtr_sec_radio_free": ("mission", "radios of the Mortar Section freed when it was split into teams (CSR 2)"),
    "phone_lines": ("setup", "phone lines available with field phones (CSR 1)"),
    "phone_note": ("setup", "note on field phones"),
    "lines_pool": ("mission", "phone lines not yet carried or laid"),
    "line_checks": ("phase", "pending phone line checks by card"),
    "runner_start": ("setup", "number of runners"),
    "runner_box": ("mission", "runners waiting in the CO HQ assets box (4.3.2)"),
    "runner_note": ("setup", "note on runners"),
    # fire support
    "fire_missions": ("mission", "fire missions left per agency"),
    "fm_start": ("mission", "fire missions at the start (for reattempt)"),
    "fm_values": ("setup", "fire mission values per agency and ammo"),
    "fm_value": ("setup", "default value of an enemy fire mission"),
    "fm_group": ("setup", "agency groups (one target marker per group)"),
    "fm_note": ("setup", "note on fire missions"),
    "fm_blocked": ("turn", "fire missions of one group blocked this turn (event)"),
    "battalion_fm": ("setup", "battalion fire missions"),
    "cff_observers": ("setup", "who may call for fire per agency (7.16.1 table)"),
    "cff_cards": ("setup", "cards to draw for Call for Fire"),
    "cff_table": ("setup", "Call for Fire table per observer type"),
    "target_marker": ("mission", "target marker card per agency"),
    "concentrations_placed": ("attempt", "concentrations placed before the attempt"),
    # assets, ammo, pyro
    "assets_pool": ("mission", "assets not yet given to a unit"),
    "assets_start": ("mission", "assets at the start (for reattempt)"),
    "assets_note": ("setup", "note on assets"),
    "pyro_codes": ("mission", "pyrotechnic signal meanings"),
    "pyro_note": ("setup", "note on pyrotechnics"),
    "rifle_grenade_range": ("setup", "rifle grenade range"),
    "rifle_grenade_note": ("setup", "note on rifle grenades"),
    "rifle_grenades_per_platoon": ("setup", "rifle grenade shots per platoon"),
    "hmg_spare_ammo": ("setup", "spare MG ammo of the HMG platoon (Naktong MSR 4)"),
    "mortar_choice": ("mission", "60mm mortar choice: section or teams (CSR 2)"),
    "mtr_team_de": ("setup", "German mortar team templates for the mortar breakdown"),
    "arty_jeep_possible": ("setup", "the mission offers the Arty Jeep (Normandy CSR 1)"),
    "arty_jeep_choice": ("mission", "Arty Jeep chosen: yes or no"),
    "fortifications_placed": ("attempt", "fortifications placed between attempts"),
    "fortify_between_attempts": ("setup", "fortifications allowed between attempts"),
    "ccp": ("mission", "Casualty Collection Point card"),
    "evacuated": ("mission", "casualties evacuated from the CCP"),
    "us_casualties_total": ("mission", "US casualties of the mission (12.x)"),
    "us_captured": ("mission", "US steps captured by the enemy (8.15)"),
    "prisoners": ("mission", "prisoners taken by the US side"),
    "take_prisoners": ("setup", "which side takes prisoners (8.15; NKPA none)"),
    "capture_open": ("phase", "units that may be captured in this phase"),
    # enemy
    "packages": ("mission", "enemy packages by number (units, place_vof, in_play)"),
    "package_table": ("setup", "R# table of enemy packages per PC letter"),
    "package_table_counterattack": ("setup", "package table of the planned counter attack"),
    "package_ammo": ("attempt", "ammo of package units per type"),
    "pc_start": ("mission", "PC markers at the start (for reattempt)"),
    "pc_markers_total": ("legacy", "PC marker count (old setup files)"),
    "pc_supply": ("legacy", "PC marker supply (old setup files)"),
    "pc_random": ("legacy", "random PC placement (old setup files)"),
    "countermix": ("setup", "enemy counters available per type"),
    "counter_names": (
        "setup",
        "counter names per countermix type in the order of the player's tray; new_name takes the first free",
    ),
    "lat_names": ("setup", "'card': generic teams are called by counter type and card, AT 45 (naming.relabel)"),
    "enemy_prefix": ("setup", "prefix of every enemy counter name, e.g. NKPA (commands.new_name)"),
    "countermix_note": ("setup", "note on the countermix"),
    "counter_vof": ("mission", "VOF rating learned per enemy counter type"),
    "direction_table": ("setup", "direction table for package placement (8.4)"),
    "enemy_tactic": ("attempt", "enemy tactic (Delay, Hasty Defense, Assault, ...)"),
    "enemy_experience_attempt": ("attempt", "enemy experience per attempt"),
    "enemy_target": ("mission", "target marker card of enemy fire missions per spotter"),
    "enemy_group": ("legacy", "enemy group (old setup files)"),
    "grenade_vof": ("setup", "VOF of enemy grenade attacks (Naktong -3)"),
    "grenade_responses": ("phase", "pending free grenade attack responses (7.10.5)"),
    "counterattack": ("mission", "planned counter attack: state and until which turn (Naktong)"),
    "rally_open": ("phase", "enemy units that owe an event Rally"),
    "sniper_targets": ("phase", "sniper targets chosen in this phase"),
    "sniper_open": ("phase", "pending sniper results"),
    "mine_checks": ("phase", "units that owe a mine check (7.9)"),
    "mine_check_info": ("phase", "card and reason per pending mine check"),
    "heat": (
        "mission",
        "heat condition {until_turn}: active up to that turn, removed by state.heat_check afterwards (Naktong M1)",
    ),
    "heat_open": ("phase", "units that owe a heat casualty check"),
    "hold_up": ("turn", "Hold Up event: turn in which it applies; removed in Clean Up"),
    # events
    "event_tables": ("setup", "friendly and enemy event tables"),
    "events_done": ("mission", "events already resolved (once-only events)"),
    "event_units": ("mission", "units that entered through an event"),
    "event_supply": ("mission", "event supplies (tank support, hmg50, ...)"),
    "event_task": ("attempt", "event with a mandatory task"),
    "event_flank": ("attempt", "flank event state"),
    "event_route": ("attempt", "route event state"),
    "event_ammo": ("attempt", "ammo event state"),
    "no_events": ("setup", "the mission has no events"),
    # patrol
    "patrol": ("mission", "patrol state (platoon, members, route_index, ...)"),
    "patrol_mission": ("setup", "this is a combat patrol mission (2.6)"),
    "patrol_reserve": ("mission", "units of the patrol reserve"),
    "patrol_change": ("mission", "patrol change pending"),
    "guards": ("mission", "guards left behind (patrol)"),
    # experience
    "xp": ("mission", "experience points entries (12.x)"),
    "xp_cards": ("mission", "cards drawn for experience"),
    "promoted": ("mission", "promotions made"),
    # tables and catalogues
    "terrain_catalog": ("setup", "terrain types with cover values, trafficability, ..."),
    "building_table": ("setup", "building tables (Seek Cover in buildings)"),
    "cover_values": ("setup", "cover values per marker type"),
    "cover_note": ("setup", "note on cover"),
    "illum_values": ("setup", "illumination values"),
    "vehicle_values": ("setup", "vehicle values of the mission"),
    "special_rules": ("setup", "special rules of the mission"),
    "note": ("setup", "note on the mission"),
    "_unverified": ("legacy", "list of unverified setup values (old setup files)"),
    "cancellations": ("legacy", "cancelled entries (old engine)"),
    # combat bookkeeping
    "combat_open": ("phase", "units that still owe Combat Effects in 3.7.4"),
    "combat_ncm": ("phase", "NCM rows per unit frozen at the start of 3.7.4"),
    "last_attempt": (
        "phase",
        "[unit, action, phase] of the last failed attempt (Exhort); cleared on success, by Exhort and at end of turn",
    ),
    "exhort_free": ("action", "[unit, action, phase] of a free follow-up attempt after Exhort; cleared by book_order"),
    "at36": ("phase", "AT Combat & Vehicle Movement phase: queue, action, next, choice (vehicles.py)"),
    "_ce_start": ("phase", "protocol entry at the start of 3.7.4 (marker changes announced when leaving)"),
    # never saved
    "_order_opts": ("command", "options of the running order; popped by book_order and save_state"),
    "_hints": ("command", "hint lines for this command's output; popped by save_state"),
    "_phase_before": ("command", "phase before phase next; popped by save_state"),
    "_engineer_check": ("command", "(unit, card, mine draws) of an Engineer move; popped by move_unit"),
    "_fj_r": ("command", "R# given for a FJ breakdown during the running hit"),
}

# ---------------------------------------------------------------- UNIT (s["units"][name])
UNIT = {
    "side": ("setup", "US or Enemy"),
    "type": ("setup", "Squad, HQ, Staff, Weapons Team, Fire Team, LAT types, FO, Vehicle, ..."),
    "type_name": ("setup", "display type name of a LAT or enemy counter"),
    "level": ("setup", "HQ level: PLT, CO, BN"),
    "rank": ("setup", "Staff rank order (Command Reference Table)"),
    "platoon": ("setup", "platoon of the unit (chain of command)"),
    "attached_to": ("mission", "HQs the unit is attached to"),
    "attachment": ("setup", "attached unit (no reconstitution)"),
    "experience": ("mission", "experience: Green, Line, Veteran; crewless jeep: highest on board (10.8.8)"),
    "steps": ("mission", "steps; crewless jeep 0"),
    "status": ("mission", "markers: Pinned, Exposed, Activated, Moved/Fired, Fire Team side, ..."),
    "card": ("mission", "card the unit is on (None before setup)"),
    "area": ("mission", "area on the card: open or a cover marker id"),
    "vof_rating": ("setup", "VOF rating of the front side (S, A, H, G!, ...)"),
    "range": ("setup", "range of the front side (P, C, L, V)"),
    "fire_team_side": ("setup", "the counter has a Fire Team back side"),
    "ft_vof": ("setup", "VOF rating of the Fire Team side"),
    "ft_range": ("setup", "range of the Fire Team side"),
    "last_step": ("setup", "what the last step becomes (Fire Team, ...)"),
    "last_step_values": ("setup", "values of the last step (Normandy p.48 A-rated Fire Team)"),
    "target": ("phase", "card the unit fires at (PDF); cleared by fire.cease_fire"),
    "target_open": ("phase", "the unit must choose a target; cleared by fire.cease_fire"),
    "cf_on": ("phase", "Concentrated Fire markers this unit placed: [target, card, area] each (7.11.5)"),
    "concentrated": ("phase", "Concentrated Fire on the target; cleared by fire.cease_fire"),
    "_smoke_target": ("phase", "old target while smoke/Incoming blocks LOS; cleared by fire.cease_fire"),
    "_vof_blocked": ("phase", "VOF blocked by LOS loss; cleared by fire.cease_fire"),
    "_range_vof": ("phase", "VOF limited by range; cleared by fire.cease_fire"),
    "pdf_only": ("turn", "PDF only, no VOF this turn; cleared in Clean Up"),
    "no_fire_until_clean_up": ("turn", "may not fire until Clean Up"),
    "cf": ("phase", "Concentrated Fire markers on the unit"),
    "cf_critical": ("phase", "Critical Hit of a Concentrated Fire"),
    "grenade": ("phase", "Grenade VOF values on the unit (7.10)"),
    "grenade_critical": ("phase", "Critical Hit of a grenade attack"),
    "grenade_ranged": ("setup", "may make ranged grenade attacks"),
    "spotted": ("mission", "enemy unit is spotted"),
    "radio": ("mission", "radios and phones carried, see RADIO"),
    "lines": ("mission", "phone lines carried"),
    "assets": ("mission", "assets carried (smoke, rifle grenades, ...)"),
    "ammo": ("mission", "ammo marker: type, points, start"),
    "ammo_empty": ("mission", "ammo used up"),
    "out_of_ammo": ("mission", "Out of Ammo (7.18)"),
    "ooa_flip": (
        "mission",
        "flipped to the Fire Team side by Out of Ammo; cleared by resupply and by a deliberate flip",
    ),
    "ooa_fallback": ("mission", "enemy unit falls back after its Out of Ammo flip"),
    "rkt_empty": ("mission", "rocket ammo used up"),
    "carries_ammo": ("mission", "carries ammo for another unit: type, points"),
    "carries_casualties": ("mission", "carries casualties (Litter Team)"),
    "ammo_carriers_abstract": ("setup", "ammo carriers are abstracted (mortar section)"),
    "rifle_grenades": ("mission", "rifle grenade shots"),
    "panzerfaust": ("setup", "carries a Panzerfaust"),
    "at_weapon": ("setup", "AT weapon (chart key)"),
    "tripod": ("setup", "tripod-mounted machine gun (+1 card for Concentrate Fire)"),
    "mortar": ("setup", "mortar unit"),
    "indirect": ("phase", "mortar in Indirect Lay"),
    "breakdown": ("setup", "breakdown rule (mtr_sec, ...)"),
    "breakdown_note": ("setup", "note on the breakdown"),
    "fj_breakdown": ("setup", "German FJ breakdown with R#"),
    "origin": ("mission", "unit a LAT came from"),
    "pc_origin": ("mission", "PC marker an enemy unit came from"),
    "package": ("mission", "enemy package number"),
    "source": ("setup", "source of the values (mission book page)"),
    "note": ("setup", "note on the unit"),
    "skills": ("mission", "skill markers (12.7)"),
    "skills_note": ("setup", "note on skills"),
    "observer": ("setup", "may act as observer for Call for Fire"),
    "spotter": ("setup", "enemy spotter of a fire mission"),
    "fm_value": ("mission", "fire mission value of an enemy spotter"),
    "missions": ("mission", "fire missions left for an enemy spotter"),
    "card_sequence": ("setup", "cards per enemy fire mission sequence"),
    "leader": ("setup", "enemy leader"),
    "human_wave": ("setup", "NKPA Human Wave unit, never Pinned (8.14)"),
    "ambush": ("mission", "AT ambush position (10.8.3)"),
    "immobile": ("setup", "enemy unit that does not move"),
    "step_levels": ("mission", "level of each step between missions, for promotions (12.6)"),
    "deep_bunker": ("mission", "unit in a Deep Bunker (id of the Cover marker): no VOF until it leaves"),
    "no_point_blank": (
        "mission",
        "enemy in a Bunker/Pillbox: no Point Blank fire (placement); derive from cover when the unit leaves",
    ),
    "bunker_direction": ("mission", "fire direction of a Bunker/Pillbox (placement)"),
    "check_open": (
        "phase",
        "enemy unit owes its Activity Check; set/cleared by enemy.prepare_enemy_check and cmd_enemy_action",
    ),
    "has_acted": ("phase", "vehicle has acted in 3.6; set by vehicles.end_action, cleared by vehicles.clean_up"),
    "in_motion": ("action", "vehicle moved in its current action; cleared by vehicles.end_action and clean_up"),
    "crew_hit_open": ("phase", "crew of a Knocked Out vehicle owes its HIT; cleared by combat.cmd_hit"),
    "mine_hit": ("turn", "unit was hit by a mine this turn: may not move (7.9.1)"),
    "stationary": ("mission", "not part of the patrol: no movement (Normandy M3 MSR 1)"),
    "attempt_only": ("attempt", "unit stays only until the end of the attempt (event unit)"),
    "engineer": ("setup", "engineer squad (CSR 10)"),
    "vehicle": ("setup", "vehicle type (chart key); makes the unit a vehicle"),
    "on_board": ("mission", "vehicle the unit is embarked on (10.8.1)"),
    "arty_jeep": ("setup", "the Arty Jeep (Normandy CSR 1)"),
    "company_jeep": ("setup", "the company jeep asset (Naktong p.12)"),
    "runner_target": ("mission", "HQ a runner carries a message to (4.3.2)"),
    "en_route_since": ("mission", "turn the runner set off (arrives the turn after)"),
    "until_turn": ("mission", "unit leaves play at the end of this turn (Bn Cmdr event unit)"),
    "_new_exposed": ("command", "became Exposed in this command (heat check); popped by save_state"),
    "tripod_legacy": ("legacy", "tripod (old name of tripod)"),
    "fd_net": ("legacy", "FD net (old radio model)"),
    "company_weapon": ("legacy", "company weapon (old setup files)"),
}

# ---------------------------------------------------------------- CARD (s["cards"][id])
CARD = {
    "row": ("setup", "row"),
    "column": ("setup", "column"),
    "card_number": ("mission", "number printed on the terrain card"),
    "terrain": ("mission", "terrain type (key of terrain_catalog)"),
    "elevation": ("mission", "elevation level"),
    "edges": ("mission", "card edges (white, ...) for LOS"),
    "cc": ("mission", "Cover and Concealment value"),
    "cc2": ("mission", "second C&C value (split card)"),
    "cover_draw": ("mission", "cover draw number (Seek Cover base)"),
    "cover_max": ("mission", "maximum number of cover markers"),
    "cover": ("mission", "cover markers on the card, see COVER"),
    "external": (
        "mission",
        "external markers: Incoming, Smoke, Mines, Indirect, Illum (type, value, source, side, active)",
    ),
    "face_down": ("mission", "card is face down"),
    "staging": ("setup", "staging area card"),
    "outside": ("setup", "outside the mission boundaries (extension card)"),
    "vehicles": ("mission", "trafficability for vehicles"),
    "building_table": ("mission", "building table of the card"),
    "multistory": ("mission", "multi-storey building"),
    "urban": ("mission", "urban card"),
    "op": ("mission", "observation post"),
    "mortar_banned": ("mission", "no mortar fire onto the card"),
    "burst": ("mission", "burst symbol value (Incoming, indirect mortar)"),
    "pc": ("mission", "PC marker letter (or ?)"),
    "pc2": ("mission", "second PC marker on the card"),
    "target": ("setup", "objective marker on the card"),
    "casualties": ("mission", "US casualties on the card"),
    "casualties_enemy": ("mission", "enemy casualties on the card"),
    "assets": ("mission", "assets dropped on the card"),
    "assets_ground": ("mission", "assets on the ground (dropped by removed units)"),
    "ammo": ("mission", "ammo dropped on the card per type"),
    "lines": ("mission", "phone lines laid on the card (cut)"),
    "line_assets": ("mission", "phone line assets lying on the card"),
    "grenade_miss": ("turn", "Grenade Miss modifier on the card (7.10.4)"),
    "illum": ("turn", "illumination on the card"),
    "pyro": ("turn", "pyrotechnic signals shown on the card (display only)"),
    "note": ("setup", "note on the card"),
    "verified": ("legacy", "values verified against the card (old setup files)"),
}

# ---------------------------------------------------------------- COVER (card["cover"][i])
COVER = {
    "id": ("mission", "marker id on the card (C1, C2, ...)"),
    "type": ("mission", "marker type (Basic Cover, Foxholes, Bunker, ...)"),
    "value": ("mission", "cover value"),
    "field": ("mission", "field fortification, not a terrain cover marker"),
    "capacity": ("mission", "steps the marker holds"),
    "direction": ("mission", "fire direction of a Bunker/Pillbox"),
    "wreck": ("mission", "cover from a vehicle wreck (10.7)"),
}

# ---------------------------------------------------------------- RADIO (unit["radio"][i])
RADIO = {
    "type": ("setup", "device: SCR300, SCR536, SCR610, EE8"),
    "net": ("setup", "net: BN TAC, CO TAC, Arty FD, Mtr FD"),
    "mounted": ("mission", "mounted in this vehicle; works only on board"),
    "damage_open": ("phase", "radio damage check pending"),
}

# ---------------------------------------------------------------- COMMANDS (s["commands"][hq])
COMMANDS = {
    "available": ("phase", "commands available in this impulse"),
    "saved": ("mission", "commands saved (4.1.3)"),
    "activated": ("turn", "HQ activated this turn"),
    "done": ("turn", "HQ has ended its impulse"),
    "drawn": ("turn", "card drawn for the HQ's commands"),
    "skill_for": ("turn", "GI only: holders of the General Initiative skills whose extra Command is still unspent"),
}

# ---------------------------------------------------------------- keys of smaller sub-structures (not field-checked)
SUBKEYS = {
    # at36 (vehicles.py)
    "action": "at36: running vehicle action",
    "plan": "at36 action: remaining plan steps",
    "queue": "at36: pending AT draws",
    "next": "at36: side that acts next",
    "choice": "at36: open target choice",
    "moved": "at36 action: vehicle has moved",
    "slow": "at36 action: SLOW terrain stops the move",
    "fired": "at36 action: vehicle has fired",
    "end": "at36 action: action ends after the queue",
    "attacked": "at36: vehicles attacked this phase",
    "reaction": "at36 queue item: reaction fire",
    "reaction_open": "at36: open US Reaction Fire window {objective, shooters}; closed by vehicle react / react pass",
    "shooters": "at36 reaction_open: US units that may still react",
    "type_after": "at36 choice: kind of the draw queued after the choice (quick, action)",
    "g_cards": "at36 queue item: cards of the G! grenade attempt",
    # patrol (campaign.py)
    "members": "patrol: member units",
    "route_index": "patrol: next route card",
    "primary_visited": "patrol: primary objective visited",
    "success": "patrol: patrol succeeded",
    "completed": "patrol: route cards done",
    "took_part": "patrol: units that took part",
    # objectives (setup.py)
    "primary": "objectives: primary objective card",
    "route": "objectives: patrol route",
    "phaselines": "objectives: phase lines by name",
    # events and counter attack (events.py)
    "until_turn": "counterattack/heat: until which turn",
    "paid": "event: cost paid",
    "fulfilled": "event: task fulfilled",
    "checked": "event: checked",
    "tank_support": "event_supply: tank support event",
    "commands": "event_task: commands the task costs",
    "star": "event_task/flanke/route: star number of the event card",
    "group": "fm_blocked: blocked agency group",
    "tactic_before": "counterattack: enemy tactic before the counter attack",
    # campaign record
    "attempt": "campaign: current attempt",
    # ammo marker
    "points": "ammo: ammo points left",
    "start": "ammo: ammo points at the start",
    # card markers
    "active": "external Mines marker: flipped to the explosion side",
    "cut": "card lines: phone line cut",
    # enemy packages (contact.py)
    "in_play": "packages: package is on the board",
    "place": "package unit: placement rule",
    "_ref": "package unit: reference unit for with_random placement",
    # dynamic unit names written as keys
    "GI": "commands: General Initiative pseudo HQ",
    "Mtr Sec": "units: 60mm Mortar Section (CSR 2)",
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
    for coll in ("units", "reserve_units", "setup_units"):
        for n, e in (s.get(coll) or {}).items():
            if not isinstance(e, dict):
                continue
            bad += [f"{coll}[{n}]: {k}" for k in e if k not in UNIT]
            for g in e.get("radio") or []:
                if isinstance(g, dict):
                    bad += [f"{coll}[{n}].radio: {k}" for k in g if k not in RADIO]
    for card_id, c in (s.get("cards") or {}).items():
        if not isinstance(c, dict):
            continue
        bad += [f"cards[{card_id}]: {k}" for k in c if k not in CARD]
        for m in c.get("cover") or []:
            if isinstance(m, dict):
                bad += [f"cards[{card_id}].cover: {k}" for k in m if k not in COVER]
    for hq, k in (s.get("commands") or {}).items():
        if isinstance(k, dict):
            bad += [f"commands[{hq}]: {x}" for x in k if x not in COMMANDS]
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
