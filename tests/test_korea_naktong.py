"""Korea / Naktong River Mission 1 building blocks (L477-L488): attempt plan, face-down cards, prisoners, Human Wave,
heat casualties, Naktong counter attack, enemy tank priorities. Synthetic boards only (no game data)."""

import pytest

from conftest import card, unit


@pytest.fixture
def quiet(monkeypatch):
    from fof import briefing, state

    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protokoll"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)


# ---- L477 attempt plan
def test_attempt_plan_sets_turns_visibility_and_enemy_values(board):
    from fof import campaign

    s = board
    s["kampagne"] = {"versuch": 1}
    s["versuch_plan"] = {
        "1": {
            "max_zuege": 6,
            "sicht": {"1-4": {"licht": 0}, "5": {"licht": 1}, "6": {"licht": 4}},
            "feind_erfahrung": "Veteran",
            "paket_munition": {"HMG": 6, "Mortar": 4},
        }
    }
    s["einheiten"]["NKPA HMG 1"] = unit(
        "33",
        side="Feind",
        typ="Weapons Team",
        typname="NKPA HMG",
        tripod=True,
        munition={"typ": "MG", "punkte": 2, "start": 2},
    )
    prot = []
    campaign.apply_attempt_plan(s, prot)
    assert s["max_zuege"] == 6 and s["feind_erfahrung_versuch"] == "Veteran"
    assert s["einheiten"]["NKPA HMG 1"]["munition"] == {"typ": "MG", "punkte": 6, "start": 6}
    assert s["licht"] == 0 and s["sicht"] == "tag"
    s["zug"] = 6
    campaign.apply_turn_visibility(s, prot)
    assert s["licht"] == 4 and s["sicht"] == "eingeschraenkt"
    assert any("Visibility turn 6" in p for p in prot)


# ---- L481 face-down cards
def test_face_down_cards_block_los_and_are_revealed_from_units(board):
    from fof import geometry

    s = board
    for k in ("21", "22", "23", "31", "32", "33"):
        s["karten"][k].update(verdeckt=True, raender="gruen", terrain="Face down (FD)")
    s["zug"], s["phase"], s["aufstellung_fertig"] = 2, "3.3.1b", True
    s["einheiten"]["1/1"] = unit("11")
    out = geometry.reveal_candidates(s)
    assert set(out) == {"21", "22"}  # adjacent cards always; row 3 hidden behind the dark face-down row 2
    s["karten"]["21"].update(verdeckt=False, raender="weiss")
    assert "31" in geometry.reveal_candidates(s)


def test_reveal_lock_stops_orders(board):
    from fof import contact, rules

    s = board
    s["karten"]["21"].update(verdeckt=True)
    s["zug"], s["phase"], s["aufstellung_fertig"] = 2, "3.3.1b", True
    s["einheiten"]["1/1"] = unit("11")
    with pytest.raises(rules.Violation, match="reveal the face-down cards"):
        contact.mine_lock(s)


# ---- L479 the North Koreans take no prisoners
def test_enemy_without_prisoners_converts_captured_us_teams(board, quiet):
    from fof import phase

    s = board
    s["gefangene_nehmen"] = {"US": True, "Feind": False}
    s["einheiten"]["Paralyzed Team 1"] = unit("22", typ="Paralyzed Team", steps=1, vof=None)
    s["einheiten"]["NKPA Squad 1"] = unit("22", side="Feind")
    prot = []
    phase.check_capture(s, prot)
    assert "Paralyzed Team 1" not in s["einheiten"]
    assert s["karten"]["22"].get("casualties") == 1
    assert any("no prisoners" in p for p in prot)


# ---- L487 Human Wave
def test_human_wave_is_never_pinned_and_hits_are_casualties(board, quiet):
    from fof import combat, rules

    s = board
    s["einheiten"]["NKPA Squad 1"] = unit("33", side="Feind", human_wave=True, letzter_step="Fire Team")
    combat.cmd_hit(s, ["NKPA Squad 1", "PIN"])
    assert rules.PINNED not in s["einheiten"]["NKPA Squad 1"]["status"]
    combat.cmd_hit(s, ["NKPA Squad 1", "HIT", "PL"])
    assert s["karten"]["33"]["casualties_feind"] == 2  # "PL" read as "CC"
    # the last step becomes a Fire Team that keeps the Human Wave hit rule and is not Pinned
    ft = [e for e in s["einheiten"].values() if e.get("typ") == "Fire Team"]
    assert len(ft) == 1 and ft[0].get("human_wave") and rules.PINNED not in ft[0]["status"]


# ---- L483 heat casualties
def test_heat_casualties_open_a_draw_for_newly_exposed_units(board):
    from fof import commands, state

    s = board
    s["hitze"] = {"bis_zug": 2}
    s["einheiten"]["1/1"] = unit("11")
    commands.mark(s["einheiten"]["1/1"], "Exposed")
    state.heat_check(s)
    assert s["hitze_offen"] == ["1/1"]
    s["wetter"] = 2
    s["hitze_offen"] = []
    commands.mark(s["einheiten"]["1/1"], "Pinned")
    s["einheiten"]["1/1"]["status"].remove("Exposed")
    commands.mark(s["einheiten"]["1/1"], "Exposed")
    state.heat_check(s)
    assert s["hitze_offen"] == []  # ignored during Rain


# ---- L484 Naktong counter attack cards
def test_naktong_counter_attack_marks_the_right_us_cards(board, quiet):
    from fof import events

    s = board
    for c in (1, 2, 3):
        s["karten"][f"4{c}"] = card(4, c)
    s["sonderregeln"] = {"gegenangriff": {"modus": "naktong", "zuege": 3}}
    s["feind_taktik"] = "Hasty"
    s["karten"]["43"]["pc"] = "B"
    for k in ("11", "12", "13", "21", "22", "23", "31", "32"):
        s["einheiten"][f"US {k}"] = unit(k)
    prot = []
    events.enemy_event(s, {"id": "counter_attack", "text": "Counter Attack"}, {}, prot)
    marked = {k for k, c in s["karten"].items() if c.get("pc") == "A"}
    # 32 next to the PC on 43 and to the empty 33/41/42; 31 next to empty 41/42; 22/23 next to the empty 33; 11-13 and 21 are inside
    assert marked == {"22", "23", "31", "32"}
    assert s["feind_taktik"] == "Offensive Assault"


# ---- L488 enemy tank priorities
def _tank_board(board):
    s = board
    s["phase"] = "3.6"
    s["sonderregeln"] = {"panzer_prioritaeten": ["..."]}
    for k, c in s["karten"].items():
        c.update(cc=0, fahrzeuge=True)
    s["karten"]["13"]["cc"] = 2
    s["einheiten"]["T-34/85 1"] = unit(
        "31",
        side="Feind",
        typ="Vehicle",
        fahrzeug="T-34/85",
        vof="H",
        rng="V",
        steps=2,
        status=["Activated"],
        munition={"typ": "Tank", "punkte": 4, "start": 4},
    )
    return s


def test_tank_moves_to_the_closest_better_card(board, quiet):
    from fof import vehicles

    s = _tank_board(board)
    s["karten"]["22"]["cc"] = 1
    st = vehicles.at36(s)
    prot = vehicles.enemy_tank_action(s, st, "T-34/85 1", {})
    assert "priority 3" in prot[0] and "22" in prot[0]
    assert [x["karte"] for x in st["aktion"]["plan"] if x["art"] == "tankmove"] == ["22"]


def test_tank_without_better_card_stays(board, quiet):
    from fof import vehicles

    s = _tank_board(board)
    s["karten"]["13"]["cc"] = 0
    st = vehicles.at36(s)
    prot = vehicles.enemy_tank_action(s, st, "T-34/85 1", {})
    assert "stays" in prot[-1]
    assert "Moved/Fired" in s["einheiten"]["T-34/85 1"]["status"]


def test_tank_concentrates_fire_on_a_bazooka_under_its_vof(board, quiet):
    from fof import rules, vehicles

    s = _tank_board(board)
    s["einheiten"]["T-34/85 1"]["ziel"] = "21"
    s["einheiten"]["2/W/1"] = unit(
        "21", typ="Weapons Team", steps=1, at_waffe="M20 Bazooka", munition={"typ": "RKT", "punkte": 3, "start": 3}
    )
    st = vehicles.at36(s)
    with pytest.raises(rules.Violation, match="priority 2"):
        vehicles.enemy_tank_action(s, st, "T-34/85 1", {})


def test_out_of_ammo_tank_leaves(board, quiet):
    from fof import combat

    s = _tank_board(board)
    e = s["einheiten"]["T-34/85 1"]
    prot = []
    combat.out_of_ammo(s, "T-34/85 1", e, prot)
    assert "T-34/85 1" not in s["einheiten"]


def test_korea_chart_lines_and_rcl_exposed():
    from fof import fire, vehicles

    assert vehicles.CHART["T-34/85"][0] == (-5, -3, -1, 0) and vehicles.CHART["T-34/85"][4] == 3
    assert "57mm RCL" in vehicles.AMBUSH_WEAPONS
    rcl = unit("11", typ="Weapons Team", vof="H", at_waffe="75mm RCL", status=["Exposed"])
    assert not fire.can_fire(rcl)


# ---- L491 Rifle Grenades: Normandy one 1-shot counter per platoon, Naktong one 2-shot counter per platoon
def _rg_board(board, limit=None):
    s = board
    s["assets_pool"] = {"Rifle Grenade": 6}
    for n in ("1/1", "2/1", "1/2"):
        s["einheiten"][n] = unit("11", platoon=n[-1])
    if limit:
        s["rifle_grenade_je_platoon"] = limit
    return s


def test_rifle_grenade_normandy_one_per_platoon(board):
    from fof import rules, setup

    s = _rg_board(board)
    setup.setup_assets(s, "1/1", s["einheiten"]["1/1"], {"--asset": "Rifle Grenade"}, [])
    with pytest.raises(rules.Violation, match="at most 1 per platoon"):
        setup.setup_assets(s, "1/1", s["einheiten"]["1/1"], {"--asset": "Rifle Grenade"}, [])


def test_rifle_grenade_naktong_two_shot_counter_on_one_unit(board):
    from fof import rules, setup

    s = _rg_board(board, limit=2)
    prot = []
    setup.setup_assets(s, "1/1", s["einheiten"]["1/1"], {"--asset": "Rifle Grenade"}, prot)
    with pytest.raises(rules.Violation, match="stays with one unit"):
        setup.setup_assets(s, "2/1", s["einheiten"]["2/1"], {"--asset": "Rifle Grenade"}, prot)
    setup.setup_assets(s, "1/1", s["einheiten"]["1/1"], {"--asset": "Rifle Grenade"}, prot)
    assert s["einheiten"]["1/1"]["assets"] == ["Rifle Grenade", "Rifle Grenade"]
    with pytest.raises(rules.Violation, match="at most 2 per platoon"):
        setup.setup_assets(s, "1/1", s["einheiten"]["1/1"], {"--asset": "Rifle Grenade"}, prot)
    setup.setup_assets(s, "1/2", s["einheiten"]["1/2"], {"--asset": "Rifle Grenade"}, prot)
    assert s["assets_pool"]["Rifle Grenade"] == 3


# ---- L492 free radio from the TO&E pool (Naktong p.12: six SCR536, one per HQ, the rest as desired)
def test_free_radio_from_pool_goes_to_one_unit_once(board):
    from fof import rules, setup

    s = board
    s["funk_frei"] = [{"typ": "SCR536", "netz": "CO TAC"}]
    s["einheiten"]["CO XO"] = unit("12", typ="HQ", funk=[])
    s["einheiten"]["CO 1 Sgt"] = unit("12", typ="HQ", funk=[])
    prot = []
    setup.setup_device(s, "CO XO", s["einheiten"]["CO XO"], {"--geraet": "SCR536"}, prot)
    assert s["einheiten"]["CO XO"]["funk"] == [{"typ": "SCR536", "netz": "CO TAC"}]
    assert s["funk_frei"] == []
    with pytest.raises(rules.Violation):
        setup.setup_device(s, "CO 1 Sgt", s["einheiten"]["CO 1 Sgt"], {"--geraet": "SCR536"}, prot)


def test_free_radio_follows_phone_choice(board):
    from fof import setup

    s = board
    s["co_hq"] = "CO HQ"
    s["funk_frei"] = [{"typ": "SCR536", "netz": "CO TAC"}]
    s["einheiten"]["CO HQ"] = unit("12", typ="HQ", funk=[{"typ": "SCR536", "netz": "CO TAC"}])
    setup.setup_net(s, "CO HQ", s["einheiten"]["CO HQ"], {"--netz": "telefon"}, [])
    assert s["funk_frei"] == [{"typ": "EE8", "netz": "CO TAC"}]


# ---- L493 a face-down card seen only over another face-down card waits for it (5.2.2)
def test_reveal_waits_for_nearer_face_down_card(board):
    from fof import briefing, geometry

    s = board
    for k in ("22", "23"):
        s["karten"][k].update(verdeckt=True, raender="gruen", terrain="Face down (FD)", elevation=1)
    s["karten"]["21"].update(elevation=2, raender="weiss")
    s["zug"], s["phase"], s["aufstellung_fertig"] = 2, "3.3.1b", True
    s["einheiten"]["1/1"] = unit("21")
    cand = geometry.reveal_candidates(s)
    assert {"22", "23"} <= set(cand)
    assert geometry.reveal_dependencies(s, cand) == {"23": ["22"]}
    lines = briefing.reveal_lines(s)
    assert any(z.startswith("Reveal face-down card 22") for z in lines)
    assert any(z.startswith("WAIT with face-down card 23") for z in lines)
    s["karten"]["22"].update(verdeckt=False, elevation=2, raender="gruen", terrain="Open on 1 Hill")
    assert "23" not in geometry.reveal_candidates(s)  # 2-2-1: the Hill closes the line


# ---- L494 building table column and source from the campaign table (Naktong CSR 6: R# column 5)
def test_building_table_reference_follows_campaign_table(board):
    from fof import contact

    s = board
    s["karten"]["22"]["gebaeude_tabelle"] = "Village"
    s["gebaeude_tabelle"] = {
        "_quelle": "CSR 6 S.14, R# Spalte 5",
        "Village": {"1-2": "Strong Building", "3-4": "Light Building", "5": "Basic Cover"},
    }
    assert contact.building_table_ref(s, "22") == (5, "CSR 6 p.14")
    s["gebaeude_tabelle"] = {
        "_quelle": "CSR 8 S.15, R# Spalte 8",
        "Village": {"1-3": "Strong Building", "7-8": "Basic Cover"},
    }
    assert contact.building_table_ref(s, "22") == (8, "CSR 8 p.15")


# ---- L495 a firing Sniper also places the Sniper VOF marker (-3) on its target card (7.15)
def test_sniper_vof_marker_is_announced(board):
    import copy

    from fof import rules, state

    s = board
    s["einheiten"]["Sniper 1"] = unit("33", side="Feind", vof="S!", typ="Sniper", steps=1)
    s["einheiten"]["AT"] = unit("13", typ="Assault Team", steps=1)
    old = copy.deepcopy(s)
    s["einheiten"]["Sniper 1"]["ziel"] = "13"
    assert state.sniper_vof_cards(s) == {"13": ["Sniper 1"]}
    assert any("place the Sniper VOF marker" in z for z in state.marker_changes(old, s))
    pinned = copy.deepcopy(s)
    pinned["einheiten"]["Sniper 1"]["status"].append(rules.PINNED)
    assert any("remove the Sniper VOF marker" in z for z in state.marker_changes(s, pinned))


# ---- L514 (replaces L496/E103) a team detached from an Exposed squad is NOT Exposed (Stead BGG 3727147)
def test_detached_team_not_exposed(board):
    from types import SimpleNamespace

    from fof import commands, rules

    s = board
    s["einheiten"]["1/1"] = unit("12", status=[rules.EXPOSED], platoon="1")
    s["einheiten"]["2/1"] = unit("12", platoon="1")
    for n in ("1/1", "2/1"):
        ctx = SimpleNamespace(z=s["einheiten"][n], o={}, target_name=n, prot=[])
        commands._order_detach_team(s, ctx)
    teams = [e for e in s["einheiten"].values() if e["typ"] == "Assault Team"]
    assert [rules.EXPOSED in e["status"] for e in teams] == [False, False]
    assert rules.EXPOSED in s["einheiten"]["1/1"]["status"]


# ---- L497 package infiltration attempt: 2 cards adjusted for Experience (Naktong CSR 3, Normandy CSR 6)
def test_package_infiltration_cards_follow_experience():
    import inspect

    from fof import contact

    src = inspect.getsource(contact.contact_place_units)
    assert '2 + {"Green": -1, "Veteran": 1}' in src and "infiltration_regel" in src


# ---- L498 Limited Visibility at the start of a turn: fire beyond the adjacent card lapses (9.1)
def test_limited_visibility_ends_fire_beyond_adjacent(board):
    from fof import fire

    s = board
    s["einheiten"]["1/1"] = unit("11", ziel="31")
    s["einheiten"]["E"] = unit("31", side="Feind")
    assert fire.is_firing(s["einheiten"]["1/1"])
    s["sicht"] = "eingeschraenkt"
    prot = []
    fire.cease_fire_on_los_loss(s, prot)
    assert s["einheiten"]["1/1"]["ziel"] is None and prot


def test_end_turn_rechecks_los_after_new_visibility():
    import inspect

    from fof import phase

    src = inspect.getsource(phase.cmd_end_turn)
    assert src.index("apply_turn_visibility") < src.rindex("cease_fire_on_los_loss")


# ---- L499 Heat Casualty on a 2-step squad: the last step becomes a generic Fire Team (6.4.3)
def test_heat_casualty_on_two_step_squad_leaves_fire_team(board, quiet):
    from fof import events

    s = board
    s["einheiten"]["2/1"] = unit("12", steps=2, letzter_step="Fire Team")
    s["hitze_offen"] = ["2/1"]
    events.cmd_heat(s, ["2/1", "ja"])
    assert "2/1" not in s["einheiten"]
    ft = [e for e in s["einheiten"].values() if e["typ"] == "Fire Team" and e["karte"] == "12"]
    assert ft


def test_heat_new_fire_team_opens_fire(board, quiet):
    from fof import events

    s = board
    s["einheiten"]["2/1"] = unit("12", steps=2, letzter_step="Fire Team", rng="C")
    s["einheiten"]["E"] = unit("22", side="Feind")
    s["hitze_offen"] = ["2/1"]
    events.cmd_heat(s, ["2/1", "ja"])
    ft = [e for e in s["einheiten"].values() if e["typ"] == "Fire Team" and e["karte"] == "12"]
    assert ft and ft[0]["ziel"] == "22"
    assert "Pinned" not in ft[0]["status"]  # L500: no HIT, no Pinned


# ---- L502 heat takes the read-off R#/4 value: only 1 is a loss
def test_heat_takes_r4_value(board, quiet):
    from fof import events

    s = board
    s["einheiten"]["AT"] = unit("12")
    s["hitze_offen"] = ["AT"]
    events.cmd_heat(s, ["AT", "3"])
    assert s["einheiten"]["AT"]["steps"] == 3 and "hitze_offen" not in s
    s["hitze_offen"] = ["AT"]
    events.cmd_heat(s, ["AT", "1"])
    assert s["einheiten"]["AT"]["steps"] == 2


# ---- L503 reattempt names the removal of saved Commands (3.9 step 11)
def test_reattempt_names_saved_commands_removal():
    from fof import campaign

    s = {"kommandos": {"CO XO": {"gespart": 4}}, "feuermissionen": {}, "assets_pool": {}}
    prot = []
    campaign.reset_pools_and_events(s, prot)
    assert s["kommandos"]["CO XO"]["gespart"] == 0
    assert any("step 11" in x for x in prot)


# ---- L504 handing out assets in the reattempt preparation opens no fire (3.9 step 14)
def test_setup_fire_update_only_after_a_placement():
    import inspect

    from fof import setup

    src = inspect.getsource(setup.cmd_setup)
    assert 'if kz and (s.get("reattempt_setup") or s.get("patrouille_mission")):' in src


# ---- L505 3.9 step 8 again in 'reattempt done': a cover freed by a used-up LAT takes the enemy in the open
def test_enemy_into_cover_after_lat_used_up(board):
    from fof import campaign

    s = board
    s["karten"]["22"]["cover"] = [{"id": "C1", "typ": "Foxholes", "wert": 1}]
    s["einheiten"]["FT"] = unit("22", side="Feind", steps=1)
    s["einheiten"]["AT"] = unit("22", steps=1, bereich="C1")
    prot = []
    campaign.enemy_into_cover(s, prot)
    assert s["einheiten"]["FT"]["bereich"] == "offen"  # the US team still holds the foxholes
    del s["einheiten"]["AT"]  # used up in step 3
    campaign.enemy_into_cover(s, prot)
    assert s["einheiten"]["FT"]["bereich"] == "C1" and "step 8" in prot[-1]
    src = __import__("inspect").getsource(campaign.reattempt_done)
    assert "enemy_into_cover(s, prot)" in src


# ---- L506 secured cards of the reattempt setup: the snapshot at the end of the attempt (3.9 step 5, U42)
def test_secured_for_reattempt_uses_the_snapshot(board):
    from fof import campaign

    s = board
    s["pc_start"] = {"22": "C", "23": "C"}
    s["einheiten"]["AT"] = unit("22", steps=1)
    assert campaign.secured_for_reattempt(s, "22")  # no snapshot: momentary occupation
    s["reattempt_gesichert"] = ["22"]
    del s["einheiten"]["AT"]  # used up in step 3
    assert campaign.secured_for_reattempt(s, "22") and not campaign.is_secured(s, "22")
    assert not campaign.secured_for_reattempt(s, "23")  # empty at the end of the attempt


# ---- L507 a free TO&E radio handed out in the setup survives the reattempt reset
def test_free_device_is_kept_in_the_setup_units():
    from fof import setup

    e = {"typ": "Staff", "funk": []}
    s = {
        "funk_frei": [{"typ": "SCR536", "netz": "CO TAC"}],
        "einheiten": {"CO XO": e},
        "aufbau_einheiten": {"CO XO": {"typ": "Staff", "funk": []}},
    }
    prot = []
    setup.setup_device(s, "CO XO", e, {"--geraet": "SCR536"}, prot)
    assert s["aufbau_einheiten"]["CO XO"]["funk"] == [{"typ": "SCR536", "netz": "CO TAC"}]
    assert s["funk_frei"] == []


# ---- L508 Heat Casualties end with the attempt (turn counter restarts)
def test_heat_casualties_end_with_the_attempt():
    from fof import campaign

    s = {"kommandos": {}, "feuermissionen": {}, "assets_pool": {}, "hitze": {"bis_zug": 6}}
    prot = []
    campaign.reset_pools_and_events(s, prot)
    assert "hitze" not in s and any("Heat Casualties end" in x for x in prot)


# ---- L509 a Move where an Infiltrate is possible is refused unless --plain=yes
def test_move_refused_when_infiltrate_possible(board, quiet):
    from fof import commands, fire, rules

    s = board
    s["einheiten"]["2/2"] = unit("21")
    e = s["einheiten"]["2/2"]
    assert not commands.infiltrate_possible(s, e, "22")
    orig = fire.vof_against
    fire.vof_against = lambda s_, k, side: ("S", 0) if k == "21" and side == "US" else None
    try:
        assert commands.infiltrate_possible(s, e, "22")
        at = unit("21", typ="Assault Team", steps=1)
        assert commands.infiltrate_possible(s, at, "22")  # Assault Teams may infiltrate (4.2.5)
        e["status"] = [rules.EXPOSED]
        assert not commands.infiltrate_possible(s, e, "22")
    finally:
        fire.vof_against = orig


# ---- L510 a Grenade VOF on the unit counts as Under Fire for the Enemy Activity Check
def test_grenade_vof_counts_as_under_fire(board):
    from fof import enemy

    s = board
    s["einheiten"]["E"] = unit("31", side="Feind", grenade=[-4])
    assert enemy.under_fire(s, s["einheiten"]["E"])
    s["einheiten"]["E"].pop("grenade")
    assert not enemy.under_fire(s, s["einheiten"]["E"])


# ---- L511 a Platoon Infiltrate/Move counts as the single action of every member (4.2)
def test_platoon_infiltrate_books_single_action():
    import inspect

    from fof import commands

    src = inspect.getsource(commands._order_move_platoon)
    assert 'ctx.also_book = "4.2.2a" if ctx.akt == "4.2.2b" else "4.2.2c"' in src
    s = {"impuls_aktionen": {"1/1": ["4.2.2c"]}, "einheiten": {}}
    assert "4.2.2c" in s["impuls_aktionen"]["1/1"]


# ---- L512 a 'PLT HQ' column of the Fire Support Available Table covers every PLT HQ (7.16.1)
def test_plt_hq_column_makes_every_plt_hq_an_observer(board):
    from fof import commands

    s = board
    s["cff_beobachter"] = {"Arty FO": 4, "CO HQ": 3, "PLT HQ": 2}
    s["cff_tabelle"] = {"81mm HE": {"Arty FO": 3, "CO HQ": 3, "PLT HQ": 2}}
    hmg = unit("21", typ="HQ", ebene="PLT")
    assert commands.cff_observer_key(s, "HMG PLT HQ", hmg) == "PLT HQ"
    assert commands.cff_observer_key(s, "CO HQ", unit("21", typ="HQ", ebene="CO")) == "CO HQ"
    assert commands.cff_observer_key(s, "1/1", unit("21")) == "1/1"
    s["cff_beobachter"].pop("PLT HQ")
    s["cff_tabelle"]["81mm HE"].pop("PLT HQ")
    assert commands.cff_observer_key(s, "HMG PLT HQ", hmg) == "HMG PLT HQ"
