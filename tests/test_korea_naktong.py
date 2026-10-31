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
