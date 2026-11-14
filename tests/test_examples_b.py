"""Worked examples of the rulebook (Series Rules 3rd Ed.), part B: 5.1.6, 5.2, 5.3, 6.0 to 6.5.
Each test rebuilds the situation of the example on the synthetic board and checks the result of the tool
against the example. Line numbers refer to rulebook.txt. Row 1 is the row nearest to the player,
"forward" is row +1; column +1 is to the right."""

import pytest
from conftest import unit

from fof import briefing, combat, commands, enemy, fire, geometry, rules, state
from fof import pickup  # L556: split from commands


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protocol"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)


def hq(board, name, available=0, saved=0, activated=True):
    board["commands"][name] = {"available": available, "saved": saved, "activated": activated, "done": False}


def total(rows):
    return sum(v for _, v in rows)


def labels(rows):
    return [t for t, _ in rows]


# ---------------------------------------------------------------- 5.1.6 carrying capacity


def test_transport_capacity_demo_team_and_co_hq(board):
    """[RULE 5.1.6A p.33] Line 3757: a 1-step Demolition Team carries 3 RKT ammo (no more) plus any number of
    assets (Smoke, WP Smoke); a 1-step CO HQ carries two radios and four pyrotechnic assets. The tool does not know
    Demolition Charges as a load; checked are the ammo limit and the unlimited assets."""
    s = board
    s["cards"]["22"]["ammo"] = {"RKT": 4}
    s["cards"]["22"]["assets_ground"] = ["Smoke", "WP Smoke", "RSP", "GSP", "Red Smoke", "Green Smoke"]
    s["units"]["Demo Team"] = unit("22", vof="S", rng="C", type="Weapons Team", steps=1)
    s["units"]["CO HQ"] = unit(
        "22",
        vof=None,
        type="HQ",
        level="CO",
        steps=1,
        radio=[{"type": "SCR300", "net": "BN TAC"}, {"type": "SCR536", "net": "CO TAC"}],
    )
    demo, co = s["units"]["Demo Team"], s["units"]["CO HQ"]
    prot = []
    combat.ammo_pick_up(s, demo, "Demo Team", "RKT:3", prot)
    assert demo["carries_ammo"] == {"type": "RKT", "points": 3}
    with pytest.raises(rules.Violation, match="at most 3 RKT"):
        combat.ammo_pick_up(s, demo, "Demo Team", "RKT:1", prot)
    for a in ("Smoke", "WP Smoke"):
        pickup.pick_up(s, demo, "Demo Team", a, prot)
    assert demo["assets"] == ["Smoke", "WP Smoke"]
    for a in ("RSP", "GSP", "Red Smoke", "Green Smoke"):
        pickup.pick_up(s, co, "CO HQ", a, prot)
    assert len(co["assets"]) == 4 and len(co["radio"]) == 2


# ---------------------------------------------------------------- 5.2.1 / 5.2.2 Reciprocal LOS


def test_reciprocal_los_hedgerow_and_upper_story(board):
    """[RULE 5.2.1 p.34, 5.2.2 p.35] Line 3948, Fig 1 and Fig 2: the dark edges of the Hedgerow block the LOS
    between 1/1 and the German squad; as soon as the US LMG moves into the Upper Story (level 2), the LOS goes over
    the Hedgerow, in both directions (reciprocal): the enemy can place a VOF on the US card."""
    s = board
    s["cards"]["12"].update(terrain="Hedgerow", edges="dunkel")
    s["cards"]["11"]["cover"] = [
        {"id": "C1", "type": "Light Building", "value": 2},
        {"id": "U1", "type": "Upper Story", "value": 2},
    ]
    s["units"]["1/1"] = unit("11", vof="S")
    s["units"]["LMG"] = unit("11", vof="A", type="Weapons Team", steps=1)
    s["units"]["4/Gp"] = unit("13", side="Enemy", vof="S")
    assert not geometry.los(s, "11", "13")[0] and not geometry.los(s, "13", "11")[0]
    assert fire.fire_candidates(s, "1/1") == [] and fire.fire_candidates(s, "4/Gp") == []
    s["units"]["LMG"]["area"] = "U1"
    lmg = s["units"]["LMG"]
    assert geometry.los(s, "11", "13", ha=geometry.height_bonus(s, lmg))[0]
    assert geometry.los(s, "13", "11", hb=geometry.card_height_bonus(s, "11", "US"))[0]
    assert fire.fire_candidates(s, "LMG") == ["13"] and fire.fire_candidates(s, "4/Gp") == ["11"]
    assert fire.fire_candidates(s, "1/1") == []  # the squad on the ground floor still has no LOS of its own
    fire.open_fire(s, [])
    assert s["units"]["4/Gp"]["target"] == "11" and fire.vof_against(s, "11", "US")[:2] == ("S", 0)


def test_reciprocal_los_concentrate_fire_only_on_the_upper_story(board, quiet):
    """[RULE 5.2.2 p.35] Line 3948, Fig 3: the enemy squad concentrates fire on the US card; only the LMG in the
    Upper Story is in true LOS and may be the target, the Basic VOF still covers the whole card.
    Tool since L150 (15.10.2026)."""
    s = board
    s.update(phase="3.4.2")
    s["cards"]["12"].update(terrain="Hedgerow", edges="dunkel")
    s["cards"]["11"]["cover"] = [
        {"id": "C1", "type": "Light Building", "value": 2},
        {"id": "U1", "type": "Upper Story", "value": 2},
    ]
    s["units"]["2/1"] = unit("11", vof="S")
    s["units"]["LMG"] = unit("11", vof="A", type="Weapons Team", steps=1, area="U1")
    s["units"]["4/Gp"] = unit("13", side="Enemy", vof="S", target="11")
    assert fire.vof_against(s, "11", "US")[:2] == ("S", 0)
    with pytest.raises(rules.Violation):
        enemy.cmd_enemy_action(s, ["4/Gp", "concentrate", "--success=yes", "--unit=2/1"])
    assert not s["units"]["2/1"].get("cf")
    enemy.cmd_enemy_action(s, ["4/Gp", "concentrate", "--success=yes", "--unit=LMG"])
    assert s["units"]["LMG"]["cf"] == 1
    assert total(combat.ncm_rows(s, "LMG")) == 0 + 2 - 1  # S +0, Upper Story +2, Concentrated Fire -1
    assert total(combat.ncm_rows(s, "2/1")) == 0  # Basic VOF on the whole card, no marker


def test_hill_sees_over_hedgerows_reciprocally(board):
    """[RULE 5.2.2A p.35] Line 4065: a German squad on a hill (level 2) has LOS over the Hedgerows to the
    US LMG Team behind them; the LOS is reciprocal, the LMG Team sees the squad on the hill. Without the hill the
    dark edges block."""
    s = board
    s["cards"]["12"].update(terrain="Hedgerow", edges="dunkel")
    s["cards"]["13"].update(terrain="Hill", elevation=2)
    s["units"]["LMG"] = unit("11", vof="A", type="Weapons Team", steps=1)
    s["units"]["4/Gp"] = unit("13", side="Enemy", vof="S")
    assert geometry.los(s, "13", "11")[0] and geometry.los(s, "11", "13")[0]
    assert fire.fire_candidates(s, "4/Gp") == ["11"] and fire.fire_candidates(s, "LMG") == ["13"]
    s["cards"]["13"]["elevation"] = 1
    ok, reason = geometry.los(s, "13", "11")
    assert not ok and "dark edges" in reason
    assert not geometry.los(s, "11", "13")[0]


# ---------------------------------------------------------------- 5.3 Cover


def test_canal_cover_potential_one_basic_cover_three_cards(board, quiet):
    """[RULE 5.3 p.36, 4.2.2e p.23] Line 4087: the Canal has Cover Potential 1, cover found is Basic +1 Cover,
    the Seek Cover attempt draws 3 cards. A second marker is not possible on the card."""
    s = board
    s.update(phase="3.3.1c", active_hq="1st PLT HQ")
    s["cards"]["22"].update(terrain="Canal", cc=0, cover_max=1, cover_draw=3)
    hq(s, "1st PLT HQ", available=3)
    s["units"]["1st PLT HQ"] = unit("22", vof=None, type="HQ", level="PLT", platoon="1", steps=1)
    s["units"]["1/1"] = unit("22", vof="S", platoon="1")
    s["units"]["2/1"] = unit("22", vof="S", platoon="1")
    with pytest.raises(rules.Violation, match="draw 3 Action cards"):
        commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.2e"])
    commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.2e", "--success=yes"])
    cover = s["cards"]["22"]["cover"]
    assert len(cover) == 1 and cover[0]["type"] == "Basic Cover" and cover[0]["value"] == 1
    assert s["units"]["1/1"]["area"] == cover[0]["id"] and "Exposed" in s["units"]["1/1"]["status"]
    with pytest.raises(rules.Violation, match="Cover Potential"):
        commands.cmd_order(s, ["1st PLT HQ", "2/1", "4.2.2e", "--success=yes"])
    assert len(s["cards"]["22"]["cover"]) == 1


def test_five_steps_under_cover_grenade_stacking_penalty(board):
    """[RULE 5.3 p.36] Line 4108: five steps under a +1 Cover marker get -2 Stacking against Grenade VOF
    (two steps over the limit of three), net -1 from cover and stacking; against direct VOF there is no
    stacking penalty."""
    s = board
    s["cards"]["22"]["cover"] = [{"id": "C1", "type": "Basic Cover", "value": 1}]
    s["units"]["1/1"] = unit("22", vof="S", steps=3, area="C1", grenade=[-4])
    s["units"]["2/1"] = unit("22", vof="S", steps=2, area="C1", grenade=[-4])
    for n in ("1/1", "2/1"):
        rows = combat.ncm_rows(s, n)
        assert ("Cover C1 Basic Cover", 1) in rows and ("Stacking 5 steps under cover", -2) in rows
        assert total(rows) == -4 + 1 - 2, rows
    for n in ("1/1", "2/1"):
        s["units"][n].pop("grenade")
    s["units"]["Enemy 1"] = unit("23", side="Enemy", vof="A", target="22")
    rows = combat.ncm_rows(s, "1/1")
    assert not any("Stacking" in t for t in labels(rows)) and total(rows) == -1 + 1


def test_hmg_in_bunker_keeps_firing_off_card_while_squad_shifts_to_point_blank(board):
    """[RULE 5.3.2 p.37, 6.2.1 p.41, 6.3.5 p.44] Line 4136: 2/1/HMG in the Bunker and 2/1 (without cover) fire forward
    at a German squad. A German Assault Team enters their card: 2/1 switches to Point Blank, the HMG Team in the
    Bunker keeps firing forward. When the Assault Team later withdraws into the Enclosed Field (to the side), the fire
    of 2/1 follows the Assault Team there (6.3.4 'in any direction', as in example 6.3.5, where 1/1 follows the squad
    into the Village although the PDF of 1/LMG lies on the card); the HMG in the Bunker keeps firing forward.
    Reading Claude 15.10.2026 (L149)."""
    s = board
    s["cards"]["22"]["cover"] = [{"id": "B1", "type": "Bunker", "value": 3, "capacity": 3, "direction": [1, 0]}]
    s["cards"]["23"]["terrain"] = "Enclosed Field"
    s["units"]["2/1/HMG"] = unit("22", vof="H", rng="V", type="Weapons Team", steps=1, tripod=True, area="B1")
    s["units"]["2/1"] = unit("22", vof="S")
    s["units"]["4/Gp"] = unit("32", side="Enemy", vof="S", target="22")
    fire.open_fire(s, [])
    assert s["units"]["2/1/HMG"]["target"] == "32" and s["units"]["2/1"]["target"] == "32"
    s["units"]["Assault Team"] = unit("12", side="Enemy", vof="A", rng="P", type="Assault Team", steps=1)
    prot = []
    commands.move_unit(s, "Assault Team", "22", None, exposed=False, prot=prot)
    assert s["units"]["2/1"]["target"] == "22"  # Point Blank against the Assault Team
    assert s["units"]["2/1/HMG"]["target"] == "32"  # the bunker keeps firing straight ahead
    assert fire.vof_against(s, "22", "Enemy")[:2] == ("S", 0)
    assert fire.vof_against(s, "32", "Enemy")[:2] == ("H", -3)
    commands.move_unit(s, "Assault Team", "23", None, exposed=False, prot=prot)
    assert s["units"]["2/1/HMG"]["target"] == "32"
    assert s["units"]["2/1"]["target"] == "23"  # fire follows the last Point Blank target (6.3.4), PDF 22 to 23
    assert fire.vof_against(s, "23", "Enemy")[:2] == ("S", 0)
    assert fire.vof_against(s, "32", "Enemy")[:2] == ("H", -3)


# ---------------------------------------------------------------- 6.0 Basic Combat Principle


def test_rain_stops_units_open_fire_at_long_range(board):
    """[RULE 6.0 p.39, 9.1 p.69, 6.1.1 p.39] Line 4292: 1/3 and the 2/W/3 MG Team look for the enemy in heavy rain
    (visibility only Close Range). The rain stops, the card is checked at once, both open fire on a North Korean
    Fire Team at Long Range."""
    s = board
    s.update(weather=2)
    geometry.update_visibility(s)
    assert s["sight"] == "limited"
    s["units"]["1/3"] = unit("11", vof="S", platoon="3")
    s["units"]["2/W/3"] = unit("11", vof="A", rng="V", type="Weapons Team", steps=1, tripod=True, platoon="3")
    s["units"]["NK Fire Team"] = unit("13", side="Enemy", vof="S", type="Fire Team", steps=1)
    fire.open_fire(s, [])
    assert s["units"]["1/3"]["target"] is None and s["units"]["2/W/3"]["target"] is None
    s["weather"] = 0
    geometry.update_visibility(s)
    prot = []
    fire.open_fire(s, prot)
    assert s["units"]["1/3"]["target"] == "13" and s["units"]["2/W/3"]["target"] == "13"
    assert fire.vof_against(s, "13", "Enemy")[:2] == ("A", -1)


# ---------------------------------------------------------------- 6.1 Opening Fire / Continuing to Fire


def test_opening_fire_example_1_wp_smoke_on_the_firing_card(board):
    """[RULE 6.1.2 p.40, 5.4 p.38] Line 4402, Example 1: 1/Gp (A VOF) on 23 and a US squad (S VOF) in the Village 22
    fire at each other. A WP mission puts smoke on 23: 1/Gp loses the LOS, the PDF is removed, its Automatic VOF
    stays on its own card and hits US units that enter it. The US squad has LOS into the smoke, its Small Arms VOF
    on 23 stays.
    Tool since L148 (15.10.2026)."""
    s = board
    s["cards"]["22"].update(terrain="Village", cc=3)
    s["units"]["1/1"] = unit("22", vof="S", target="23")
    s["units"]["1/Gp"] = unit("23", side="Enemy", vof="A", target="22")
    assert fire.vof_against(s, "22", "US")[:2] == ("A", -1)
    s["cards"]["23"]["external"].append({"type": "Smoke", "value": 1, "source": "WP"})
    prot = []
    fire.cease_fire_on_los_loss(s, prot)
    assert s["units"]["1/1"]["target"] == "23" and fire.vof_against(s, "23", "Enemy")[:2] == ("S", 0)
    assert fire.vof_against(s, "22", "US") is None  # no PDF from 23 any more
    assert fire.is_firing(s["units"]["1/Gp"]) and fire.effective_fire_target(s, "1/Gp") == "23"
    assert fire.vof_against(s, "23", "US")[:2] == ("A", -1)  # the German VOF waits on its own card


def test_opening_fire_example_2_no_fire_past_own_litter_team(board):
    """[RULE 6.1.1 p.40] Line 4417, Example 2: 1/1 enters the left card; an NKPA HMG is in LOS, but the VOF would
    stay on the nearest occupied card with its own Litter Team, so 1/1 does not open fire. Thanks to Grazing Fire the
    HMG hits both US units."""
    s = board
    s["units"]["Litter Team"] = unit("12", vof=None, type="Litter Team", steps=1)
    s["units"]["NKPA HMG"] = unit(
        "13", side="Enemy", vof="A", rng="V", type="Weapons Team", steps=1, tripod=True, target="12"
    )
    s["units"]["1/1"] = unit("11", vof="S")
    assert geometry.los(s, "11", "13")[0]
    assert "13" not in fire.fire_candidates(s, "1/1")
    prot = []
    fire.open_fire(s, prot, only=["1/1"])
    assert s["units"]["1/1"]["target"] is None
    assert fire.grazing_cards(s, "NKPA HMG") == ["12", "11"]
    assert fire.vof_against(s, "12", "US")[:2] == ("A", -1) and fire.vof_against(s, "11", "US")[:2] == ("A", -1)


def test_opening_fire_example_3_vof_moves_to_the_closer_card(board):
    """[RULE 6.1.2 p.40, 7.2.2 p.51] Line 4411, Example 3: 1/1 fires over an Open Field at a Litter Team in the
    Farm (S VOF on the Farm). An Exposed LMG Team appears in the field: the VOF moves from the Farm to the field. With
    Grazing Fire 1/1 would hit both; an Unspotted LMG Team would be fired through."""
    s = board
    s["cards"]["23"]["terrain"] = "Farm"
    s["units"]["1/1"] = unit("21", vof="S", target="23")
    s["units"]["Litter Team"] = unit("23", side="Enemy", vof=None, type="Litter Team", steps=1)
    assert fire.effective_fire_target(s, "1/1") == "23" and fire.vof_against(s, "23", "Enemy")[:2] == ("S", 0)
    s["units"]["LMG Team"] = unit(
        "22", side="Enemy", vof="A", type="Weapons Team", steps=1, tripod=True, status=["Exposed"], spotted=True
    )
    assert fire.effective_fire_target(s, "1/1") == "22"
    assert fire.vof_against(s, "22", "Enemy")[:2] == ("S", 0) and fire.vof_against(s, "23", "Enemy") is None
    s["units"]["1/1"].update(vof_rating="A", range="V", tripod=True)  # with Grazing Fire: both cards
    assert fire.grazing_cards(s, "1/1") == ["22", "23"]
    assert fire.vof_against(s, "23", "Enemy")[:2] == ("A", -1)
    s["units"]["1/1"].update(vof_rating="S", range="L", tripod=False)
    s["units"]["LMG Team"]["spotted"] = False  # Unspotted: fired through, the VOF stays on the farm
    assert fire.effective_fire_target(s, "1/1") == "23" and fire.vof_against(s, "22", "Enemy") is None


def test_opening_fire_example_4_grazing_fire_stops_at_wp_smoke(board):
    """[RULE 6.1.2 p.41, 7.2.2 p.51, 5.4 p.38] Line 4445, Example 4: an NVA HMG in a Bunker fires over open ground at
    US units and with Grazing Fire places Heavy Weapons VOF on all cards in LOS. After a WP mission on the card in
    between its fire reaches only up to the smoke."""
    s = board
    s["cards"]["13"]["cover"] = [{"id": "B1", "type": "Bunker", "value": 3, "capacity": 3, "direction": [0, -1]}]
    s["units"]["NVA HMG"] = unit(
        "13", side="Enemy", vof="H", rng="V", type="Weapons Team", steps=1, tripod=True, area="B1"
    )
    s["units"]["1/1"] = unit("11", vof="S", target="13")
    s["units"]["2/1"] = unit("11", vof="S", target="13")
    fire.open_fire(s, [])
    assert s["units"]["NVA HMG"]["target"] == "11"
    assert fire.grazing_cards(s, "NVA HMG") == ["12", "11"]
    assert fire.vof_against(s, "11", "US")[:2] == ("H", -3) and fire.vof_against(s, "12", "US")[:2] == ("H", -3)
    s["cards"]["12"]["external"].append({"type": "Smoke", "value": 1, "source": "WP"})
    assert fire.grazing_cards(s, "NVA HMG") == ["12"]
    assert fire.effective_fire_target(s, "NVA HMG") == "12"
    assert fire.vof_against(s, "11", "US") is None and fire.vof_against(s, "12", "US")[:2] == ("H", -3)


# ---------------------------------------------------------------- 6.2.1 Placing VOF Markers


def test_vof_example_1_best_vof_from_outside_and_crossfire(board):
    """[RULE 6.2.1a p.41, 6.2.4 p.42] Line 4488, Example 1: 1st PLT HQ, 2/1 and 1/W/1 MG Team are fired at from the
    left with Small Arms (+0) and from the right by an HMG with Automatic Weapons (-1); only the Automatic VOF applies,
    plus Crossfire -1."""
    s = board
    s["units"]["1st PLT HQ"] = unit("22", vof=None, type="HQ", level="PLT", platoon="1", steps=1)
    s["units"]["2/1"] = unit("22", vof="S", platoon="1")
    s["units"]["1/W/1"] = unit("22", vof="A", rng="V", type="Weapons Team", steps=1, tripod=True, platoon="1")
    s["units"]["Squad L"] = unit("21", side="Enemy", vof="S", target="22")
    s["units"]["HMG R"] = unit(
        "23", side="Enemy", vof="A", rng="V", type="Weapons Team", steps=1, tripod=True, target="22"
    )
    type_, value, sources = fire.vof_against(s, "22", "US")
    assert (type_, value) == ("A", -1) and set(sources) == {"Squad L", "HMG R"}
    assert fire.crossfire(s, "22", "US") is True
    for n in ("1st PLT HQ", "2/1", "1/W/1"):
        rows = combat.ncm_rows(s, n)
        assert rows[0] == ("VOF Automatic Weapons from HMG R", -1)
        assert ("Crossfire (two PDF directions)", -1) in rows and total(rows) == -2, rows


def test_vof_example_2_artillery_beats_panzerschreck(board):
    """[RULE 6.2.1 p.41, 6.4 p.45] Line 4502, Example 2: artillery (-5) hits the card with 1st PLT HQ, 2/1 and
    1/Mtr Team; 2/1 is also the target of a successful Panzerschreck attack (-4). All three are resolved with
    Artillery -5, the Panzerschreck VOF is ignored."""
    s = board
    s["cards"]["22"]["external"].append({"type": "Incoming", "value": -5, "source": "Arty"})
    s["units"]["1st PLT HQ"] = unit("22", vof=None, type="HQ", level="PLT", platoon="1", steps=1)
    s["units"]["2/1"] = unit("22", vof="S", platoon="1", grenade=[-4])
    s["units"]["1/Mtr"] = unit("22", vof="G", rng="C-L", type="Weapons Team", steps=1, mortar=True, platoon="1")
    assert fire.vof_against(s, "22", "US")[:2] == ("Incoming", -5)
    for n in ("1st PLT HQ", "2/1", "1/Mtr"):
        rows = combat.ncm_rows(s, n)
        assert rows[0] == ("VOF Incoming! (Arty)", -5) and total(rows) == -5, rows


def test_vof_example_3_mortar_heavy_weapons_hits_both_sides(board):
    """[RULE 6.2.1a/b p.41] Line 4517, Example 3: 1st PLT HQ, 1/LMG and 2/1 share the card with 4/Gp and 5/Gp. A
    German 81mm Mortar Section fires Heavy Weapons (-3) from outside onto the card; it hits all units of both
    sides. The US Automatic VOF (-1) and the German Small Arms VOF (+0) are not placed."""
    s = board
    s["units"]["1st PLT HQ"] = unit("22", vof=None, type="HQ", level="PLT", platoon="1", steps=1)
    s["units"]["1/LMG"] = unit("22", vof="A", type="Weapons Team", steps=1, platoon="1", target="22")
    s["units"]["2/1"] = unit("22", vof="S", platoon="1", target="22")
    s["units"]["4/Gp"] = unit("22", side="Enemy", vof="S", target="22")
    s["units"]["5/Gp"] = unit("22", side="Enemy", vof="S", target="22")
    s["units"]["81mm Mtr"] = unit(
        "32", side="Enemy", vof="H", rng="C-L", type="Weapons Team", steps=3, mortar=True, target="22"
    )
    assert fire.vof_against(s, "22", "US")[:2] == ("H", -3) and fire.vof_against(s, "22", "Enemy")[:2] == ("H", -3)
    for n in ("1st PLT HQ", "1/LMG", "2/1", "4/Gp", "5/Gp"):
        rows = combat.ncm_rows(s, n)
        assert rows[0] == ("VOF Heavy Weapons from 81mm Mtr", -3) and total(rows) == -3, rows


def test_vof_example_4_point_blank_vof_better_than_outside_vof(board):
    """[RULE 6.2.1b p.41, 6.3.6 p.45] Line 4534, Example 4: 1st PLT HQ, 2/AT Bazooka Team and 2/1 share the card with
    a German 88. 1/LMG fires Automatic (-1) from outside onto the card. The US Small Arms VOF (+0) is not
    placed; the 88 fires Heavy Weapons (-3), which hits the US units, the 88 itself only the Automatic VOF."""
    s = board
    s["units"]["1st PLT HQ"] = unit("22", vof=None, type="HQ", level="PLT", platoon="1", steps=1)
    s["units"]["2/AT"] = unit("22", vof="S", rng="C", type="Weapons Team", steps=1, platoon="2", target="22")
    s["units"]["2/1"] = unit("22", vof="S", platoon="1", target="22")
    s["units"]["88mm"] = unit("22", side="Enemy", vof="H", rng="V", type="Weapons Team", steps=1, target="22")
    s["units"]["1/LMG"] = unit("32", side="Enemy", vof="A", type="Weapons Team", steps=1, target="22")
    type_, value, sources = fire.vof_against(s, "22", "US")
    assert (type_, value) == ("H", -3) and set(sources) == {"88mm", "1/LMG"}
    type_, value, sources = fire.vof_against(s, "22", "Enemy")
    assert (type_, value) == ("A", -1) and "1/LMG" in sources  # the US Small Arms VOF (+0) is not the marker placed
    assert "88mm" not in sources  # Point Blank fire hits only the opposing side
    for n in ("1st PLT HQ", "2/AT", "2/1"):
        assert total(combat.ncm_rows(s, n)) == -3
    assert total(combat.ncm_rows(s, "88mm")) == -1


# ---------------------------------------------------------------- 6.3 PDF


def test_out_of_ammo_vof_moves_to_the_adjacent_card_pdf_stays(board):
    """[RULE 6.3.2 p.43, 7.18.2 p.61] Line 4717: the 2/W/3 MG Team (A VOF, L range) fires at an enemy two cards
    to the right. Out of ammo its VOF drops to Small Arms (+0) and its range to Close; the PDF stays to the right,
    the VOF moves to the neighbouring card.
    Tool since L147 (15.10.2026)."""
    s = board
    s["units"]["2/W/3"] = unit(
        "11",
        vof="A",
        rng="L",
        type="Weapons Team",
        steps=1,
        tripod=True,
        target="13",
        platoon="3",
        ammo={"type": "MG", "points": 1, "start": 6},
    )
    s["units"]["Enemy 1"] = unit("13", side="Enemy", vof="S", target="11")
    assert fire.vof_against(s, "13", "Enemy")[:2] == ("A", -1)
    mg = s["units"]["2/W/3"]
    prot = []
    combat.ammo_use(s, "2/W/3", mg, 1, "fire", prot)
    assert mg["out_of_ammo"] and fire.current_vof_rating(mg, False) == "S"
    assert state.range_limits(s, mg) == (0, 1)
    assert fire.is_firing(mg) and mg["target"] == "13"  # the PDF marker stays (right)
    assert fire.effective_fire_target(s, "2/W/3") == "12"
    assert fire.vof_against(s, "13", "Enemy") is None and fire.vof_against(s, "12", "Enemy")[:2] == ("S", 0)


def test_vof_follows_the_squad_that_leaves_the_card(board):
    """[RULE 6.3.4 p.44, 6.3.5 p.44, 6.1.1 p.39, 6.2.4 p.42] Line 4774: 1/1 and 1/LMG fire in the Woods; the German
    squad on the card of 1/1 (Point Blank) moves into the Village. The Small Arms VOF of 1/1 follows it with a PDF from
    the Woods to the Village; 1/LMG keeps firing in its direction. The squad ceases fire and opens fire again on the
    Woods (most steps), so 1/1 lies in a Crossfire.
    Tool since L149 (15.10.2026)."""
    s = board
    s["cards"]["22"].update(terrain="Woods", cc=2)
    s["cards"]["23"].update(terrain="Village", cc=3)
    s["units"]["1/1"] = unit("22", vof="S", platoon="1", target="22")
    s["units"]["1/LMG"] = unit("22", vof="A", type="Weapons Team", steps=1, platoon="1", target="32")
    s["units"]["4/Gp"] = unit("22", side="Enemy", vof="S", target="22")
    s["units"]["5/Gp"] = unit("32", side="Enemy", vof="S", target="22")
    assert fire.vof_against(s, "22", "Enemy")[:2] == ("S", 0) and fire.vof_against(s, "32", "Enemy")[:2] == ("A", -1)
    assert fire.crossfire(s, "22", "US") is False
    prot = []
    commands.move_unit(s, "4/Gp", "23", None, exposed=True, prot=prot)
    assert s["units"]["4/Gp"]["target"] == "22"  # cease fire, then open fire on the Woods (most steps)
    assert s["units"]["1/LMG"]["target"] == "32"  # not along its PDF: keeps firing in the same direction
    assert s["units"]["1/1"]["target"] == "23"  # Small Arms VOF follows, PDF Woods to Village
    assert fire.vof_against(s, "23", "Enemy")[:2] == ("S", 0)
    assert fire.crossfire(s, "22", "US") is True
    assert ("Crossfire (two PDF directions)", -1) in combat.ncm_rows(s, "1/1")


# ---------------------------------------------------------------- 6.4 Combat Resolution


def test_combat_example_1_fog_grenade_crossfire(board):
    """[RULE 6.4 p.45, 9.0 p.69, 7.10 p.54] Line 4937, Example 1: fog (+2) on an Open Field. 1/LMG and the Assault
    Team under +1 Basic Cover, 1/1 Pinned in the open. An 88 (H) fires from the right, a Pinned German squad from the
    left, a Panzerschreck team hits the covered stack with Grenade -4. NCM 1/LMG and Assault Team -4 (Grenade without
    the visibility modifier, Cover +1, Crossfire -1); NCM 1/1 -1 (H -3, fog +2, Pinned +1, Crossfire -1)."""
    s = board
    s.update(weather=2)
    geometry.update_visibility(s)
    s["cards"]["22"]["cover"] = [{"id": "C1", "type": "Basic Cover", "value": 1}]
    s["units"]["1/1"] = unit("22", vof="S", platoon="1", status=["Pinned"])
    s["units"]["1/LMG"] = unit("22", vof="A", type="Weapons Team", steps=1, platoon="1", area="C1", grenade=[-4])
    s["units"]["Assault Team"] = unit(
        "22", vof="A", rng="P", type="Assault Team", steps=1, platoon="1", area="C1", grenade=[-4]
    )
    s["units"]["88 Flak"] = unit("23", side="Enemy", vof="H", rng="V", type="Weapons Team", steps=1, target="22")
    s["units"]["Pzschreck"] = unit("23", side="Enemy", vof="S", rng="C", type="Weapons Team", steps=1, target="22")
    s["units"]["Squad L"] = unit("21", side="Enemy", vof="A", target="22", status=["Pinned"])
    assert fire.vof_against(s, "22", "US")[:2] == ("H", -3) and fire.crossfire(s, "22", "US") is True
    for n in ("1/LMG", "Assault Team"):
        rows = combat.ncm_rows(s, n)
        assert rows[0] == ("Grenade VOF (cumulative)", -4)
        assert not any("Visibility" in t for t in labels(rows))
        assert ("Cover C1 Basic Cover", 1) in rows and ("Crossfire (two PDF directions)", -1) in rows
        assert total(rows) == -4, rows
    rows = combat.ncm_rows(s, "1/1")
    assert rows[0] == ("VOF Heavy Weapons from 88 Flak", -3)
    assert ("Pinned", 1) in rows and ("Crossfire (two PDF directions)", -1) in rows
    assert any(t.startswith("Visibility") and v == 2 for t, v in rows)
    assert total(rows) == -1, rows


def test_combat_example_2_point_blank_orchard_grenades_and_concentrated_fire(board):
    """[RULE 6.4 p.45, 7.10.4 p.55, 7.11 p.56] Line 4969, Example 2: Point Blank in the Orchard (+1). 2/1 and 3/1 under
    +1 Basic Cover, 2/LMG Pinned in the open, against an A- and an S-rated German squad. The S squad misses its
    Grenade Attack (Grenade Miss), 2/1 misses in return, 3/1 hits (-4). 2/1 concentrates fire on the A squad, 3/1
    on the S squad. NCM: 2/1 and 3/1 +0, 2/LMG +0, A squad -1, S squad -5."""
    s = board
    s["cards"]["22"].update(terrain="Orchard", cc=1, grenade_miss=True)
    s["cards"]["22"]["cover"] = [{"id": "C1", "type": "Basic Cover", "value": 1}]
    s["units"]["2/1"] = unit("22", vof="S", platoon="1", area="C1", target="22")
    s["units"]["3/1"] = unit("22", vof="S", platoon="1", area="C1", target="22")
    s["units"]["2/LMG"] = unit("22", vof="A", type="Weapons Team", steps=1, platoon="1", target="22", status=["Pinned"])
    s["units"]["Squad A"] = unit("22", side="Enemy", vof="A", target="22", cf=1)
    s["units"]["Squad S"] = unit("22", side="Enemy", vof="S", target="22", cf=1, grenade=[-4])
    assert fire.vof_against(s, "22", "US")[:2] == ("A", -1)
    assert fire.vof_against(s, "22", "Enemy")[:2] == ("S", 0)
    for n in ("2/1", "3/1"):
        rows = combat.ncm_rows(s, n)
        assert rows[0] == ("VOF Automatic Weapons from Squad A", -1) and ("Grenade Miss", -1) in rows
        assert total(rows) == 0, rows
    rows = combat.ncm_rows(s, "2/LMG")
    assert ("Pinned", 1) in rows and total(rows) == 0, rows
    rows = combat.ncm_rows(s, "Squad A")
    assert rows[0][1] == 0 and rows[0][0].startswith("VOF Small Arms")
    assert ("Concentrated Fire", -1) in rows and ("Grenade Miss", -1) in rows and total(rows) == -1, rows
    rows = combat.ncm_rows(s, "Squad S")
    assert rows[0] == ("Grenade VOF (cumulative)", -4)
    assert ("Concentrated Fire", -1) in rows and ("Grenade Miss", -1) in rows and total(rows) == -5, rows


def test_hit_effects_cf_on_japanese_squad_and_lc_on_bazooka_team(board, quiet):
    """[RULE 6.4.3 p.47] Line 5214: a 3-step Japanese squad takes a CF hit: step 1 Casualty, step 2 Fire
    Team, the last step becomes a Fire Team as well; both Fire Teams are Pinned. A 1-step Bazooka Team takes
    LC: the only step becomes a Litter Team (Pinned), the C is not applied any more."""
    s = board
    s.update(phase="3.7.4")
    s["units"]["Jap Squad"] = unit("22", side="Enemy", vof="S", steps=3, last_step="Fire Team")
    s["units"]["1/1"] = unit("12", vof="S", target="22")
    s["units"]["Bazooka"] = unit("12", vof="S", rng="C", type="Weapons Team", steps=1)
    s["units"]["Enemy 2"] = unit("13", side="Enemy", vof="S", target="12")
    combat.cmd_hit(s, ["Jap Squad", "HIT", "CF"])
    assert "Jap Squad" not in s["units"] and s["cards"]["22"]["casualties_enemy"] == 1
    teams = [n for n, e in s["units"].items() if e["side"] == "Enemy" and e["card"] == "22"]
    assert len(teams) == 2
    for n in teams:
        e = s["units"][n]
        assert e["type"] == "Fire Team" and e["steps"] == 1 and "Pinned" in e["status"]
    combat.cmd_hit(s, ["Bazooka", "HIT", "LC"])
    assert "Bazooka" not in s["units"] and not s["cards"]["12"].get("casualties")
    lats = [e for e in s["units"].values() if e["side"] == "US" and e["card"] == "12" and state.is_lat(e)]
    assert len(lats) == 1 and lats[0]["type"] == "Litter Team" and "Pinned" in lats[0]["status"]


# ---------------------------------------------------------------- 6.5.2 Reconstitution


# L552 (review T2): the example of 6.5.2 (German A and S Fire Teams reconstitute into a squad) was an unconditional
# skip, a test that could never fail. The gap is recorded in normandy/luecken_fof_v4.md instead.
