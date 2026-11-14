"""Korea / Naktong River Mission 1 building blocks (L477-L488): attempt plan, face-down cards, prisoners, Human Wave,
heat casualties, Naktong counter attack, enemy tank priorities. Synthetic boards only (no game data)."""

import pytest

from conftest import card, unit
from fof import fire_support  # L556: split from commands


@pytest.fixture
def quiet(monkeypatch):
    from fof import briefing, state

    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protocol"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)


# ---- L477 attempt plan
def test_attempt_plan_sets_turns_visibility_and_enemy_values(board):
    from fof import campaign

    s = board
    s["campaign"] = {"attempt": 1}
    s["attempt_plan"] = {
        "1": {
            "max_turns": 6,
            "sight": {"1-4": {"light": 0}, "5": {"light": 1}, "6": {"light": 4}},
            "enemy_experience": "Veteran",
            "package_ammo": {"HMG": 6, "Mortar": 4},
        }
    }
    s["units"]["NKPA HMG 1"] = unit(
        "33",
        side="Enemy",
        type="Weapons Team",
        type_name="NKPA HMG",
        tripod=True,
        ammo={"type": "MG", "points": 2, "start": 2},
    )
    prot = []
    campaign.apply_attempt_plan(s, prot)
    assert s["max_turns"] == 6 and s["enemy_experience_attempt"] == "Veteran"
    assert s["units"]["NKPA HMG 1"]["ammo"] == {"type": "MG", "points": 6, "start": 6}
    assert s["light"] == 0 and s["sight"] == "day"
    s["turn"] = 6
    campaign.apply_turn_visibility(s, prot)
    assert s["light"] == 4 and s["sight"] == "limited"
    assert any("Visibility turn 6" in p for p in prot)


# ---- L481 face-down cards
def test_face_down_cards_block_los_and_are_revealed_from_units(board):
    from fof import geometry

    s = board
    for k in ("21", "22", "23", "31", "32", "33"):
        s["cards"][k].update(face_down=True, edges="green", terrain="Face down (FD)")
    s["turn"], s["phase"], s["setup_done"] = 2, "3.3.1b", True
    s["units"]["1/1"] = unit("11")
    out = geometry.reveal_candidates(s)
    assert set(out) == {"21", "22"}  # adjacent cards always; row 3 hidden behind the dark face-down row 2
    s["cards"]["21"].update(face_down=False, edges="white")
    assert "31" in geometry.reveal_candidates(s)


def test_reveal_lock_stops_orders(board):
    from fof import contact, rules

    s = board
    s["cards"]["21"].update(face_down=True)
    s["turn"], s["phase"], s["setup_done"] = 2, "3.3.1b", True
    s["units"]["1/1"] = unit("11")
    with pytest.raises(rules.Violation, match="reveal the face-down cards"):
        contact.mine_lock(s)


# ---- L479 the North Koreans take no prisoners
def test_enemy_without_prisoners_converts_captured_us_teams(board, quiet):
    from fof import phase

    s = board
    s["take_prisoners"] = {"US": True, "Enemy": False}
    s["units"]["Paralyzed Team 1"] = unit("22", type="Paralyzed Team", steps=1, vof=None)
    s["units"]["NKPA Squad 1"] = unit("22", side="Enemy")
    prot = []
    phase.check_capture(s, prot)
    assert "Paralyzed Team 1" not in s["units"]
    assert s["cards"]["22"].get("casualties") == 1
    assert any("no prisoners" in p for p in prot)


# ---- L487 Human Wave
def test_human_wave_is_never_pinned_and_hits_are_casualties(board, quiet):
    from fof import combat, rules

    s = board
    s["units"]["NKPA Squad 1"] = unit("33", side="Enemy", human_wave=True, last_step="Fire Team")
    combat.cmd_hit(s, ["NKPA Squad 1", "PIN"])
    assert rules.PINNED not in s["units"]["NKPA Squad 1"]["status"]
    combat.cmd_hit(s, ["NKPA Squad 1", "HIT", "PL"])
    assert s["cards"]["33"]["casualties_enemy"] == 2  # "PL" read as "CC"
    # the last step becomes a Fire Team that keeps the Human Wave hit rule and is not Pinned
    ft = [e for e in s["units"].values() if e.get("type") == "Fire Team"]
    assert len(ft) == 1 and ft[0].get("human_wave") and rules.PINNED not in ft[0]["status"]


# ---- L483 heat casualties
def test_heat_casualties_open_a_draw_for_newly_exposed_units(board):
    from fof import commands, state

    s = board
    s["heat"] = {"until_turn": 2}
    s["units"]["1/1"] = unit("11")
    commands.mark(s["units"]["1/1"], "Exposed")
    state.heat_check(s)
    assert s["heat_open"] == ["1/1"]
    s["weather"] = 2
    s["heat_open"] = []
    commands.mark(s["units"]["1/1"], "Pinned")
    s["units"]["1/1"]["status"].remove("Exposed")
    commands.mark(s["units"]["1/1"], "Exposed")
    state.heat_check(s)
    assert s["heat_open"] == []  # ignored during Rain


# ---- L484 Naktong counter attack cards
def test_naktong_counter_attack_marks_the_right_us_cards(board, quiet):
    from fof import events

    s = board
    for c in (1, 2, 3):
        s["cards"][f"4{c}"] = card(4, c)
    s["special_rules"] = {"counterattack": {"mode": "naktong", "turns": 3}}
    s["enemy_tactic"] = "Hasty"
    s["cards"]["43"]["pc"] = "B"
    for k in ("11", "12", "13", "21", "22", "23", "31", "32"):
        s["units"][f"US {k}"] = unit(k)
    prot = []
    events.enemy_event(s, {"id": "counter_attack", "text": "Counter Attack"}, {}, prot)
    marked = {k for k, c in s["cards"].items() if c.get("pc") == "A"}
    # 32 next to the PC on 43 and to the empty 33/41/42; 31 next to empty 41/42; 22/23 next to the empty 33; 11-13 and 21 are inside
    assert marked == {"22", "23", "31", "32"}
    assert s["enemy_tactic"] == "Offensive Assault"


# ---- L488 enemy tank priorities
def _tank_board(board):
    s = board
    s["phase"] = "3.6"
    s["special_rules"] = {"tank_priorities": ["..."]}
    for k, c in s["cards"].items():
        c.update(cc=0, vehicles=True)
    s["cards"]["13"]["cc"] = 2
    s["units"]["T-34/85 1"] = unit(
        "31",
        side="Enemy",
        type="Vehicle",
        vehicle="T-34/85",
        vof="H",
        rng="V",
        steps=2,
        status=["Activated"],
        ammo={"type": "Tank", "points": 4, "start": 4},
    )
    return s


def test_tank_moves_to_the_closest_better_card(board, quiet):
    from fof import vehicles

    s = _tank_board(board)
    s["cards"]["22"]["cc"] = 1
    st = vehicles.at36(s)
    prot = vehicles.enemy_tank_action(s, st, "T-34/85 1", {})
    assert "priority 3" in prot[0] and "22" in prot[0]
    assert [x["card"] for x in st["action"]["plan"] if x["kind"] == "tankmove"] == ["22"]


def test_tank_without_better_card_stays(board, quiet):
    from fof import vehicles

    s = _tank_board(board)
    s["cards"]["13"]["cc"] = 0
    st = vehicles.at36(s)
    prot = vehicles.enemy_tank_action(s, st, "T-34/85 1", {})
    assert "stays" in prot[-1]
    assert "Moved/Fired" in s["units"]["T-34/85 1"]["status"]


def test_tank_concentrates_fire_on_a_bazooka_under_its_vof(board, quiet):
    from fof import rules, vehicles

    s = _tank_board(board)
    s["units"]["T-34/85 1"]["target"] = "21"
    s["units"]["2/W/1"] = unit(
        "21", type="Weapons Team", steps=1, at_weapon="M20 Bazooka", ammo={"type": "RKT", "points": 3, "start": 3}
    )
    st = vehicles.at36(s)
    with pytest.raises(rules.Violation, match="priority 2"):
        vehicles.enemy_tank_action(s, st, "T-34/85 1", {})


def test_out_of_ammo_tank_leaves(board, quiet):
    from fof import combat

    s = _tank_board(board)
    e = s["units"]["T-34/85 1"]
    prot = []
    combat.out_of_ammo(s, "T-34/85 1", e, prot)
    assert "T-34/85 1" not in s["units"]


def test_korea_chart_lines_and_rcl_exposed():
    from fof import fire, vehicles

    assert vehicles.CHART["T-34/85"][0] == (-5, -3, -1, 0) and vehicles.CHART["T-34/85"][4] == 3
    assert "57mm RCL" in vehicles.AMBUSH_WEAPONS
    rcl = unit("11", type="Weapons Team", vof="H", at_weapon="75mm RCL", status=["Exposed"])
    assert not fire.can_fire(rcl)


# ---- L491 Rifle Grenades: Normandy one 1-shot counter per platoon, Naktong one 2-shot counter per platoon
def _rg_board(board, limit=None):
    s = board
    s["assets_pool"] = {"Rifle Grenade": 6}
    for n in ("1/1", "2/1", "1/2"):
        s["units"][n] = unit("11", platoon=n[-1])
    if limit:
        s["rifle_grenades_per_platoon"] = limit
    return s


def test_rifle_grenade_normandy_one_per_platoon(board):
    from fof import rules, setup

    s = _rg_board(board)
    setup.setup_assets(s, "1/1", s["units"]["1/1"], {"--asset": "Rifle Grenade"}, [])
    with pytest.raises(rules.Violation, match="at most 1 per platoon"):
        setup.setup_assets(s, "1/1", s["units"]["1/1"], {"--asset": "Rifle Grenade"}, [])


def test_rifle_grenade_naktong_two_shot_counter_on_one_unit(board):
    from fof import rules, setup

    s = _rg_board(board, limit=2)
    prot = []
    setup.setup_assets(s, "1/1", s["units"]["1/1"], {"--asset": "Rifle Grenade"}, prot)
    with pytest.raises(rules.Violation, match="stays with one unit"):
        setup.setup_assets(s, "2/1", s["units"]["2/1"], {"--asset": "Rifle Grenade"}, prot)
    setup.setup_assets(s, "1/1", s["units"]["1/1"], {"--asset": "Rifle Grenade"}, prot)
    assert s["units"]["1/1"]["assets"] == ["Rifle Grenade", "Rifle Grenade"]
    with pytest.raises(rules.Violation, match="at most 2 per platoon"):
        setup.setup_assets(s, "1/1", s["units"]["1/1"], {"--asset": "Rifle Grenade"}, prot)
    setup.setup_assets(s, "1/2", s["units"]["1/2"], {"--asset": "Rifle Grenade"}, prot)
    assert s["assets_pool"]["Rifle Grenade"] == 3


# ---- L492 free radio from the TO&E pool (Naktong p.12: six SCR536, one per HQ, the rest as desired)
def test_free_radio_from_pool_goes_to_one_unit_once(board):
    from fof import rules, setup

    s = board
    s["radio_free"] = [{"type": "SCR536", "net": "CO TAC"}]
    s["units"]["CO XO"] = unit("12", type="HQ", radio=[])
    s["units"]["CO 1 Sgt"] = unit("12", type="HQ", radio=[])
    prot = []
    setup.setup_device(s, "CO XO", s["units"]["CO XO"], {"--device": "SCR536"}, prot)
    assert s["units"]["CO XO"]["radio"] == [{"type": "SCR536", "net": "CO TAC"}]
    assert s["radio_free"] == []
    with pytest.raises(rules.Violation):
        setup.setup_device(s, "CO 1 Sgt", s["units"]["CO 1 Sgt"], {"--device": "SCR536"}, prot)


def test_free_radio_follows_phone_choice(board):
    from fof import setup

    s = board
    s["co_hq"] = "CO HQ"
    s["radio_free"] = [{"type": "SCR536", "net": "CO TAC"}]
    s["units"]["CO HQ"] = unit("12", type="HQ", radio=[{"type": "SCR536", "net": "CO TAC"}])
    setup.setup_net(s, "CO HQ", s["units"]["CO HQ"], {"--net": "phone"}, [])
    assert s["radio_free"] == [{"type": "EE8", "net": "CO TAC"}]


# ---- L493 a face-down card seen only over another face-down card waits for it (5.2.2)
def test_reveal_waits_for_nearer_face_down_card(board):
    from fof import briefing, geometry

    s = board
    for k in ("22", "23"):
        s["cards"][k].update(face_down=True, edges="green", terrain="Face down (FD)", elevation=1)
    s["cards"]["21"].update(elevation=2, edges="white")
    s["turn"], s["phase"], s["setup_done"] = 2, "3.3.1b", True
    s["units"]["1/1"] = unit("21")
    cand = geometry.reveal_candidates(s)
    assert {"22", "23"} <= set(cand)
    assert geometry.reveal_dependencies(s, cand) == {"23": ["22"]}
    lines = briefing.reveal_lines(s)
    assert any(z.startswith("Reveal face-down card 22") for z in lines)
    assert any(z.startswith("WAIT with face-down card 23") for z in lines)
    s["cards"]["22"].update(face_down=False, elevation=2, edges="green", terrain="Open on 1 Hill")
    assert "23" not in geometry.reveal_candidates(s)  # 2-2-1: the Hill closes the line


# ---- L494 building table column and source from the campaign table (Naktong CSR 6: R# column 5)
def test_building_table_reference_follows_campaign_table(board):
    from fof import contact

    s = board
    s["cards"]["22"]["building_table"] = "Village"
    s["building_table"] = {
        "_source": "CSR 6 S.14, R# Spalte 5",
        "Village": {"1-2": "Strong Building", "3-4": "Light Building", "5": "Basic Cover"},
    }
    assert contact.building_table_ref(s, "22") == (5, "CSR 6 p.14")
    s["building_table"] = {
        "_source": "CSR 8 S.15, R# Spalte 8",
        "Village": {"1-3": "Strong Building", "7-8": "Basic Cover"},
    }
    assert contact.building_table_ref(s, "22") == (8, "CSR 8 p.15")


# ---- L495 a firing Sniper also places the Sniper VOF marker (-3) on its target card (7.15)
def test_sniper_vof_marker_is_announced(board):
    import copy

    from fof import rules, state

    s = board
    s["units"]["Sniper 1"] = unit("33", side="Enemy", vof="S!", type="Sniper", steps=1)
    s["units"]["AT"] = unit("13", type="Assault Team", steps=1)
    old = copy.deepcopy(s)
    s["units"]["Sniper 1"]["target"] = "13"
    assert state.sniper_vof_cards(s) == {"13": ["Sniper 1"]}
    assert any("place the Sniper VOF marker" in z for z in state.marker_changes(old, s))
    pinned = copy.deepcopy(s)
    pinned["units"]["Sniper 1"]["status"].append(rules.PINNED)
    assert any("remove the Sniper VOF marker" in z for z in state.marker_changes(s, pinned))


# ---- L514 (replaces L496/E103) a team detached from an Exposed squad is NOT Exposed (Stead BGG 3727147)
def test_detached_team_not_exposed(board):
    from types import SimpleNamespace

    from fof import commands, rules

    s = board
    s["units"]["1/1"] = unit("12", status=[rules.EXPOSED], platoon="1")
    s["units"]["2/1"] = unit("12", platoon="1")
    for n in ("1/1", "2/1"):
        ctx = SimpleNamespace(recipient=s["units"][n], o={}, target_name=n, prot=[])
        commands._order_detach_team(s, ctx)
    teams = [e for e in s["units"].values() if e["type"] == "Assault Team"]
    assert [rules.EXPOSED in e["status"] for e in teams] == [False, False]
    assert rules.EXPOSED in s["units"]["1/1"]["status"]


# ---- L497 package infiltration attempt: 2 cards adjusted for Experience (Naktong CSR 3, Normandy CSR 6)
def test_package_infiltration_cards_follow_experience(b342):
    """L552 (review T3): behaviour instead of source text: the prompt names 2 cards adjusted for Experience."""
    import copy

    import pytest

    from fof import contact, rules

    s = b342
    s["campaign"] = {}
    s["cards"]["11"]["pc"] = "A"
    s["units"]["1/1"] = unit("11")
    pk = {
        "name": "Infiltrators",
        "spotted": True,
        "place_vof": True,
        "infiltration_rule": "Naktong CSR 3 p.13",
        "units": [
            {
                "unit": "NKPA Squad",
                "type": "Squad",
                "vof_rating": "S",
                "range": "L",
                "steps": 3,
                "place": "max",
                "infiltration": True,
                "experience": "Green",
            }
        ],
    }
    with pytest.raises(rules.Violation, match=r"1 Action cards \(2, experience Green\).*Naktong CSR 3 p.13"):
        contact.pc_contact_campaign(s, "11", "A1", copy.deepcopy(pk), {"--direction": "Front"})


# ---- L498 Limited Visibility at the start of a turn: fire beyond the adjacent card lapses (9.1)
def test_limited_visibility_ends_fire_beyond_adjacent(board):
    from fof import fire

    s = board
    s["units"]["1/1"] = unit("11", target="31")
    s["units"]["E"] = unit("31", side="Enemy")
    assert fire.is_firing(s["units"]["1/1"])
    s["sight"] = "limited"
    prot = []
    fire.cease_fire_on_los_loss(s, prot)
    assert s["units"]["1/1"]["target"] is None and prot


def test_end_turn_rechecks_los_after_new_visibility(board, quiet):
    """L552 (review T3): turn 2 of the attempt plan is a night turn: the PDF two cards away lapses at the turn change."""
    from fof import phase

    s = board
    s.update(phase="3.8", mission="x", max_turns=6, campaign={})
    s["attempt_plan"] = {"1": {"sight": {"1": {"light": 0, "weather": 0}, "2-6": {"light": 3, "weather": 0}}}}
    s["units"]["1/1"] = unit("11", target="31")
    s["units"]["E"] = unit("31", side="Enemy")
    phase.cmd_end_turn(s, [])
    assert s["turn"] == 2 and s["sight"] == "limited" and s["units"]["1/1"]["target"] is None


# ---- L499 Heat Casualty on a 2-step squad: the last step becomes a generic Fire Team (6.4.3)
def test_heat_casualty_on_two_step_squad_leaves_fire_team(board, quiet):
    from fof import events

    s = board
    s["units"]["2/1"] = unit("12", steps=2, last_step="Fire Team")
    s["heat_open"] = ["2/1"]
    events.cmd_heat(s, ["2/1", "yes"])
    assert "2/1" not in s["units"]
    ft = [e for e in s["units"].values() if e["type"] == "Fire Team" and e["card"] == "12"]
    assert ft


def test_heat_new_fire_team_opens_fire(board, quiet):
    from fof import events

    s = board
    s["units"]["2/1"] = unit("12", steps=2, last_step="Fire Team", rng="C")
    s["units"]["E"] = unit("22", side="Enemy")
    s["heat_open"] = ["2/1"]
    events.cmd_heat(s, ["2/1", "yes"])
    ft = [e for e in s["units"].values() if e["type"] == "Fire Team" and e["card"] == "12"]
    assert ft and ft[0]["target"] == "22"
    assert "Pinned" not in ft[0]["status"]  # L500: no HIT, no Pinned


# ---- L502 heat takes the read-off R#/4 value: only 1 is a loss
def test_heat_takes_r4_value(board, quiet):
    from fof import events

    s = board
    s["units"]["AT"] = unit("12")
    s["heat_open"] = ["AT"]
    events.cmd_heat(s, ["AT", "3"])
    assert s["units"]["AT"]["steps"] == 3 and "heat_open" not in s
    s["heat_open"] = ["AT"]
    events.cmd_heat(s, ["AT", "1"])
    assert s["units"]["AT"]["steps"] == 2


# ---- L503 reattempt names the removal of saved Commands (3.9 step 11)
def test_reattempt_names_saved_commands_removal():
    from fof import campaign

    s = {"commands": {"CO XO": {"saved": 4}}, "fire_missions": {}, "assets_pool": {}}
    prot = []
    campaign.reset_pools_and_events(s, prot)
    assert s["commands"]["CO XO"]["saved"] == 0
    assert any("step 11" in x for x in prot)


# ---- L504 handing out assets in the reattempt preparation opens no fire (3.9 step 14)
def test_setup_fire_update_only_after_a_placement(board, quiet):
    """L552 (review T3): handing out an asset in the reattempt preparation opens no fire on either side."""
    from fof import setup

    s = board
    s.update(phase="3.1", mission="x", max_turns=6, campaign={}, reattempt_setup=True, assets_pool={"HC Smoke": 2})
    s["units"]["1/1"] = unit("11")
    s["units"]["E"] = unit("31", side="Enemy")
    setup.cmd_setup(s, ["1/1", "--asset=HC Smoke"])
    assert s["units"]["1/1"]["assets"] == ["HC Smoke"]
    assert s["units"]["1/1"]["target"] is None and s["units"]["E"]["target"] is None


# ---- L505 3.9 step 8 again in 'reattempt done': a cover freed by a used-up LAT takes the enemy in the open
def test_enemy_into_cover_after_lat_used_up(board):
    from fof import campaign

    s = board
    s["cards"]["22"]["cover"] = [{"id": "C1", "type": "Foxholes", "value": 1}]
    s["units"]["FT"] = unit("22", side="Enemy", steps=1)
    s["units"]["AT"] = unit("22", steps=1, area="C1")
    prot = []
    campaign.enemy_into_cover(s, prot)
    assert s["units"]["FT"]["area"] == "open"  # the US team still holds the foxholes
    del s["units"]["AT"]  # used up in step 3
    campaign.enemy_into_cover(s, prot)
    assert s["units"]["FT"]["area"] == "C1" and "step 8" in prot[-1]


def test_reattempt_done_puts_enemies_into_free_cover(board, quiet):
    """L552 (review T3): 'reattempt done' itself runs step 8 again (behaviour instead of source text)."""
    from fof import campaign

    s = board
    s.update(phase="3.1", mission="x", max_turns=6, campaign={"attempt": 2}, reattempt_setup=True)
    s["cards"]["11"]["staging"] = True
    s["cards"]["22"]["cover"] = [{"id": "C1", "type": "Foxholes", "value": 1}]
    s["units"]["1/1"] = unit("11")
    s["units"]["FT"] = unit("22", side="Enemy", steps=1)
    campaign.reattempt_done(s)
    assert s["units"]["FT"]["area"] == "C1" and not s.get("reattempt_setup")


# ---- L506 secured cards of the reattempt setup: the snapshot at the end of the attempt (3.9 step 5, U42)
def test_secured_for_reattempt_uses_the_snapshot(board):
    from fof import campaign

    s = board
    s["pc_start"] = {"22": "C", "23": "C"}
    s["units"]["AT"] = unit("22", steps=1)
    assert campaign.secured_for_reattempt(s, "22")  # no snapshot: momentary occupation
    s["reattempt_secured"] = ["22"]
    del s["units"]["AT"]  # used up in step 3
    assert campaign.secured_for_reattempt(s, "22") and not campaign.is_secured(s, "22")
    assert not campaign.secured_for_reattempt(s, "23")  # empty at the end of the attempt


# ---- L507 a free TO&E radio handed out in the setup survives the reattempt reset
def test_free_device_is_kept_in_the_setup_units():
    from fof import setup

    e = {"type": "Staff", "radio": []}
    s = {
        "radio_free": [{"type": "SCR536", "net": "CO TAC"}],
        "units": {"CO XO": e},
        "setup_units": {"CO XO": {"type": "Staff", "radio": []}},
    }
    prot = []
    setup.setup_device(s, "CO XO", e, {"--device": "SCR536"}, prot)
    assert s["setup_units"]["CO XO"]["radio"] == [{"type": "SCR536", "net": "CO TAC"}]
    assert s["radio_free"] == []


# ---- L508 Heat Casualties end with the attempt (turn counter restarts)
def test_heat_casualties_end_with_the_attempt():
    from fof import campaign

    s = {"commands": {}, "fire_missions": {}, "assets_pool": {}, "heat": {"until_turn": 6}}
    prot = []
    campaign.reset_pools_and_events(s, prot)
    assert "heat" not in s and any("Heat Casualties end" in x for x in prot)


# ---- L509 a Move where an Infiltrate is possible is refused unless --plain=yes
def test_move_refused_when_infiltrate_possible(board, quiet):
    from fof import commands, fire, rules

    s = board
    s["units"]["2/2"] = unit("21")
    e = s["units"]["2/2"]
    assert not commands.infiltrate_possible(s, e, "22")
    orig = fire.vof_against
    fire.vof_against = lambda s_, k, side: ("S", 0) if k == "21" and side == "US" else None
    try:
        assert commands.infiltrate_possible(s, e, "22")
        at = unit("21", type="Assault Team", steps=1)
        assert commands.infiltrate_possible(s, at, "22")  # Assault Teams may infiltrate (4.2.5)
        e["status"] = [rules.EXPOSED]
        assert not commands.infiltrate_possible(s, e, "22")
    finally:
        fire.vof_against = orig


# ---- L510 a Grenade VOF on the unit counts as Under Fire for the Enemy Activity Check
def test_grenade_vof_counts_as_under_fire(board):
    from fof import enemy

    s = board
    s["units"]["E"] = unit("31", side="Enemy", grenade=[-4])
    assert enemy.under_fire(s, s["units"]["E"])
    s["units"]["E"].pop("grenade")
    assert not enemy.under_fire(s, s["units"]["E"])


# ---- L511 a Platoon Infiltrate/Move counts as the single action of every member (4.2)
def test_platoon_infiltrate_books_single_action(board, monkeypatch):
    """L552 (review T3): every member of a Platoon Infiltrate has used its single action (4.2.2c) in this impulse."""
    from conftest import _hq_board
    from fof import commands

    s = _hq_board(board, monkeypatch)
    s["units"]["1/1"] = unit("22", platoon="1")
    s["units"]["2/1"] = unit("22", platoon="1")
    s["units"]["E"] = unit("33", side="Enemy", target="22")
    commands.cmd_order(
        s, ["1st PLT HQ", "1st PLT HQ", "4.2.2d", "--target=12", "--success=1st PLT HQ:yes,1/1:yes,2/1:yes"]
    )
    for n in ("1st PLT HQ", "1/1", "2/1"):
        assert "4.2.2c" in s["impulse_actions"][n]


# ---- L512 a 'PLT HQ' column of the Fire Support Available Table covers every PLT HQ (7.16.1)
def test_plt_hq_column_makes_every_plt_hq_an_observer(board):

    s = board
    s["cff_observers"] = {"Arty FO": 4, "CO HQ": 3, "PLT HQ": 2}
    s["cff_table"] = {"81mm HE": {"Arty FO": 3, "CO HQ": 3, "PLT HQ": 2}}
    hmg = unit("21", type="HQ", level="PLT")
    assert fire_support.cff_observer_key(s, "HMG PLT HQ", hmg) == "PLT HQ"
    assert fire_support.cff_observer_key(s, "CO HQ", unit("21", type="HQ", level="CO")) == "CO HQ"
    assert fire_support.cff_observer_key(s, "1/1", unit("21")) == "1/1"
    s["cff_observers"].pop("PLT HQ")
    s["cff_table"]["81mm HE"].pop("PLT HQ")
    assert fire_support.cff_observer_key(s, "HMG PLT HQ", hmg) == "HMG PLT HQ"


def test_reattempt_clears_dropped_assets(board):
    """L581: 3.9 step 6 also removes Assets dropped on a card (assets_ground); the pool is refilled."""
    from fof import campaign

    card_id = next(iter(board["cards"]))
    board["cards"][card_id]["assets_ground"] = ["Rifle Grenade"]
    campaign.reset_cards(board, [])
    assert "assets_ground" not in board["cards"][card_id]


def test_reattempt_enemy_into_deep_bunker_places_no_vof(board, quiet):
    """L582: an enemy put into a Deep Bunker by 3.9 step 8 exerts no VOF (Naktong CSR 7)."""
    from fof import campaign, fire

    s = board
    s["cards"]["22"]["cover"] = [
        {"id": "C1", "type": "Deep Bunker", "value": 5, "field": True},
        {"id": "C2", "type": "Basic Cover", "value": 1},
    ]
    s["units"]["FT"] = unit("22", side="Enemy", steps=1)
    campaign.enemy_into_cover(s, [])
    assert s["units"]["FT"]["area"] == "C1" and s["units"]["FT"]["deep_bunker"] == "C1"
    assert not fire.can_fire(s["units"]["FT"])
