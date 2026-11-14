"""L187: vehicles and AT Combat (10.0-10.8, Normandy CSR 7) on the synthetic board."""

import pytest
from conftest import unit

from fof import fire, rules, vehicles


def sherman(card_id, **extra):
    e = unit(card_id, type="Vehicle", vehicle="M4 Sherman 75mm", platoon="Tank", vof="H", rng="V", steps=2, ambush=True)
    e["ammo"] = {"type": "Tank", "points": 5, "start": 5}
    e.update(extra)
    return e


def test_result_table_v():
    assert [vehicles.result_v(x) for x in (-3, -1, 0, 1, 2, 3, 4, 5, 6)] == [
        "Brewed Up",
        "Brewed Up",
        "Knocked Out",
        "Knocked Out",
        "Retreat",
        "Retreat",
        "Pinned",
        "Pinned",
        "Missed",
    ]


def test_at_rows_pak40_point_blank_ambush_moving(board):
    board["cards"]["22"]["cc"] = 1
    board["units"]["Sherman 1"] = sherman("22", in_motion=True)
    board["units"]["PAK"] = unit("22", side="Enemy", type="AT Gun", vof="S", rng="C", at_weapon="75mm AT Gun", steps=1)
    rows = dict(vehicles.at_rows(board, "PAK", "Sherman 1"))
    assert rows["Gunnery 75mm AT Gun at range P"] == -4
    assert rows["Target is moving"] == 1
    assert rows["Tank Ambush [10.8.3]"] == -3
    assert sum(rows.values()) == -4 + 0 + 1 + 1 - 3


def test_ambush_needs_no_good_order_infantry(board):
    board["units"]["Sherman 1"] = sherman("22")
    board["units"]["1/1"] = unit("22")
    board["units"]["PAK"] = unit("23", side="Enemy", type="AT Gun", vof="S", rng="C", at_weapon="75mm AT Gun", steps=1)
    assert not vehicles.ambush(board, "Sherman 1", board["units"]["PAK"])
    board["units"]["1/1"]["status"] = ["Pinned"]
    assert vehicles.ambush(board, "Sherman 1", board["units"]["PAK"])


def test_panzerfaust_and_rifle_grenade_shots(board):
    fj = unit("22", side="Enemy", vof="A", panzerfaust=1)
    assert vehicles.weapon(fj) == "Panzerfaust" and vehicles.shots_left(fj) == 1
    fj["panzerfaust"] = 0
    assert not vehicles.at_capable(fj)
    sq = unit("21", assets=["Rifle Grenade"])
    assert vehicles.weapon(sq) == "Rifle Grenade" and vehicles.at_capable(sq)


def test_vof_against_vehicle_ignores_a_rated_at_capable(board):
    board["units"]["Sherman 1"] = sherman("22")
    board["units"]["FJ"] = unit("23", side="Enemy", vof="A", rng="L", panzerfaust=1, target="22")
    assert vehicles.vof_on_vehicle(board, "Sherman 1") is None
    board["units"]["FJ"]["panzerfaust"] = 0
    assert vehicles.vof_on_vehicle(board, "Sherman 1")[0] == "A"


def test_a_rated_at_capable_does_not_open_fire_on_vehicle_only_card(board):
    board["units"]["Sherman 1"] = sherman("22")
    board["units"]["FJ"] = unit("23", side="Enemy", vof="A", rng="L", panzerfaust=1)
    assert "22" not in fire.fire_candidates(board, "FJ")
    board["units"]["LMG"] = unit("23", side="Enemy", vof="A", rng="L")
    assert "22" in fire.fire_candidates(board, "LMG")


def test_vehicle_orders_restricted(board):
    board["units"]["Tank HQ"] = sherman("21", type="HQ", level="PLT")
    board["units"]["Sherman 1"] = sherman("21")
    board["units"]["CO XO"] = unit("21", type="Staff")
    board["units"]["1/1"] = unit("21")
    assert vehicles.order_check(board, "Tank HQ", "Sherman 1", "4.2.1i")
    with pytest.raises(rules.Violation, match="10.1.2"):
        vehicles.order_check(board, "Tank HQ", "Sherman 1", "4.2.2a")
    with pytest.raises(rules.Violation, match="10.1.2"):
        vehicles.order_check(board, "CO XO", "Sherman 1", "4.2.4k")
    with pytest.raises(rules.Violation, match="10.1.1"):
        vehicles.order_check(board, "Tank HQ", "1/1", "4.2.2a")


def test_clean_up_burning_wreck_becomes_wreck_and_markers_go(board):
    board["units"]["Sherman 1"] = sherman("21", status=["Activated", "Moved/Fired"], has_acted=True)
    board["cards"]["22"]["external"].append({"type": "Smoke", "value": 2, "source": "Burning Wreck", "wreck": True})
    board["vehicle_values"] = {"wreck_cover": 1}
    prot = []
    vehicles.clean_up(board, prot)
    assert board["units"]["Sherman 1"]["status"] == []
    assert board["cards"]["22"]["cover"][0]["type"] == "Wreck"


def test_base_type_card_without_terrain():
    """L191: 'vehicle traffic' with cards still lacking terrain (terrain None) must not crash."""
    assert vehicles.base_type(None) == ""
    assert vehicles.base_type("Woods on 1 Hill") == "Woods"
    assert vehicles.base_type("Cemetery on 1 Hill") == "Cemetery"


def test_stacking_16_steps_ignores_vehicle_crews(board, monkeypatch):
    """L193 [RULE 5.1.5 p.32, BGG 1881833]: 16 steps of infantry and 4 vehicles per card; Sherman crews are no infantry
    steps, so a 3-step squad may still join 13 infantry steps and two tanks."""
    from fof import briefing, commands, state

    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protocol"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)
    s = board
    s.update(phase="3.3.1c", co_hq="CO HQ")
    s["units"]["CO HQ"] = unit("11", vof=None, type="HQ", level="CO", steps=1)
    s["units"]["1st PLT HQ"] = unit("12", vof=None, type="HQ", level="PLT", platoon="1", steps=1)
    s["units"]["1/1"] = unit("12", platoon="1", steps=3)
    s["commands"]["1st PLT HQ"] = {"available": 3, "saved": 0, "activated": True, "done": False}
    s["commands"]["CO HQ"] = {"available": 0, "saved": 0, "activated": True, "done": True}
    for i in range(4):
        s["units"][f"Sq {i}"] = unit("22", steps=3 if i < 3 else 4, platoon="2")
    s["units"]["Sherman 1"] = sherman("22")
    s["units"]["Sherman 2"] = sherman("22")
    commands.cmd_hq(s, ["1st PLT HQ"])
    with pytest.raises(rules.Violation, match="17 US steps"):
        commands.cmd_order(s, ["1st PLT HQ", "1st PLT HQ", "4.2.2b", "--target=22"])
    s["units"]["Sq 3"]["steps"] = 2
    commands.cmd_order(s, ["1st PLT HQ", "1st PLT HQ", "4.2.2b", "--target=22"])
    assert s["units"]["1/1"]["card"] == "22"


def test_staging_card_is_trafficable(board):
    """L194: Staging Area cards have no terrain card; vehicle movement there is normal."""
    board["cards"]["11"].update(staging=True, terrain=None)
    assert vehicles.traffic(board, "11") is True


def test_msr2_tanks_act_before_at_guns(board):
    """L201 [Normandy M6 MSR 2]: with the group order the enemy AT gun gets no own action while tanks are still to act."""
    board["special_rules"] = {"vehicle_order": "MSR 2"}
    board["units"]["Sherman 1"] = sherman("21", status=["Activated"])
    board["units"]["PAK"] = unit(
        "31", side="Enemy", type="AT Gun", vof="S", rng="C", at_weapon="75mm AT Gun", steps=1, status=["Activated"]
    )
    assert vehicles.current_group(board) == 1
    assert vehicles.enemy_actors(board) == []
    assert vehicles.us_actors(board) == ["Sherman 1"]
    board["units"]["Sherman 1"]["status"] = ["Moved/Fired"]
    assert vehicles.current_group(board) == 3
    del board["special_rules"]
    assert vehicles.current_group(board) is None


@pytest.mark.game_data
def test_m6_package_templates_have_unit_type():
    """L202: every unit template of the M6 enemy packages carries 'type' (package 7 held the two-team dict).
    Checks the real setup file when present, else its packages in tests/fixtures (kit layout)."""
    import json
    import pathlib

    p = pathlib.Path(__file__).resolve().parent.parent / "normandy" / "setup_normandy_m6.json"
    if not p.exists():
        p = pathlib.Path(__file__).resolve().parent / "fixtures" / "setup_normandy_m6_packages.json"
    m = json.loads(p.read_text(encoding="utf-8"))
    for k, pk in m["packages"].items():
        units = list(pk.get("units", [])) + [u for v in pk.get("choice", {}).values() for u in v]
        for u in units:
            assert "type" in u, f"package {k}: {u.get('unit')}"


def test_grenade_vof_on_vehicle_counts(board):
    """L205 [RULE 10.5.3]: a Grenade VOF on a vehicle is resolved with the AT modifier Grenade -2."""
    board["units"]["Sherman 1"] = sherman("22", grenade=[-4])
    b = vehicles.vof_on_vehicle(board, "Sherman 1")
    assert b[0] == "G"
    assert vehicles.VOF_AT_MOD[b[0]] == -2


@pytest.mark.game_data
def test_friendly_incoming_hits_own_vehicle():
    """L214 [RULE 10.5.3, 6.2]: own Incoming! on the card is resolved against an own vehicle (friendly fire)."""
    from conftest import m6_state

    s = m6_state(569)
    s["units"]["M4 Sherman 13"]["card"] = "53"
    best = vehicles.vof_on_vehicle(s, "M4 Sherman 13")
    assert best and best[0] == "Incoming" and best[2] == "Mtr FO"
