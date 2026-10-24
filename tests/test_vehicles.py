"""L187: vehicles and AT Combat (10.0-10.8, Normandy CSR 7) on the synthetic board."""

import pytest
from conftest import unit

from fof import fire, rules, vehicles


def sherman(kid, **extra):
    e = unit(kid, typ="Vehicle", fahrzeug="M4 Sherman 75mm", platoon="Tank", vof="H", rng="V", steps=2, ambush=True)
    e["munition"] = {"typ": "Tank", "punkte": 5, "start": 5}
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
    board["karten"]["22"]["cc"] = 1
    board["einheiten"]["Sherman 1"] = sherman("22", in_bewegung=True)
    board["einheiten"]["PAK"] = unit(
        "22", side="Feind", typ="AT Gun", vof="S", rng="C", at_waffe="75mm AT Gun", steps=1
    )
    rows = dict(vehicles.at_rows(board, "PAK", "Sherman 1"))
    assert rows["Gunnery 75mm AT Gun at range P"] == -4
    assert rows["Target is moving"] == 1
    assert rows["Tank Ambush [10.8.3]"] == -3
    assert sum(rows.values()) == -4 + 0 + 1 + 1 - 3


def test_ambush_needs_no_good_order_infantry(board):
    board["einheiten"]["Sherman 1"] = sherman("22")
    board["einheiten"]["1/1"] = unit("22")
    board["einheiten"]["PAK"] = unit(
        "23", side="Feind", typ="AT Gun", vof="S", rng="C", at_waffe="75mm AT Gun", steps=1
    )
    assert not vehicles.ambush(board, "Sherman 1", board["einheiten"]["PAK"])
    board["einheiten"]["1/1"]["status"] = ["Pinned"]
    assert vehicles.ambush(board, "Sherman 1", board["einheiten"]["PAK"])


def test_panzerfaust_and_rifle_grenade_shots(board):
    fj = unit("22", side="Feind", vof="A", panzerfaust=1)
    assert vehicles.weapon(fj) == "Panzerfaust" and vehicles.shots_left(fj) == 1
    fj["panzerfaust"] = 0
    assert not vehicles.at_capable(fj)
    sq = unit("21", assets=["Rifle Grenade"])
    assert vehicles.weapon(sq) == "Rifle Grenade" and vehicles.at_capable(sq)


def test_vof_against_vehicle_ignores_a_rated_at_capable(board):
    board["einheiten"]["Sherman 1"] = sherman("22")
    board["einheiten"]["FJ"] = unit("23", side="Feind", vof="A", rng="L", panzerfaust=1, ziel="22")
    assert vehicles.vof_on_vehicle(board, "Sherman 1") is None
    board["einheiten"]["FJ"]["panzerfaust"] = 0
    assert vehicles.vof_on_vehicle(board, "Sherman 1")[0] == "A"


def test_a_rated_at_capable_does_not_open_fire_on_vehicle_only_card(board):
    board["einheiten"]["Sherman 1"] = sherman("22")
    board["einheiten"]["FJ"] = unit("23", side="Feind", vof="A", rng="L", panzerfaust=1)
    assert "22" not in fire.fire_candidates(board, "FJ")
    board["einheiten"]["LMG"] = unit("23", side="Feind", vof="A", rng="L")
    assert "22" in fire.fire_candidates(board, "LMG")


def test_vehicle_orders_restricted(board):
    board["einheiten"]["Tank HQ"] = sherman("21", typ="HQ", ebene="PLT")
    board["einheiten"]["Sherman 1"] = sherman("21")
    board["einheiten"]["CO XO"] = unit("21", typ="Staff")
    board["einheiten"]["1/1"] = unit("21")
    assert vehicles.order_check(board, "Tank HQ", "Sherman 1", "4.2.1i")
    with pytest.raises(rules.Violation, match="10.1.2"):
        vehicles.order_check(board, "Tank HQ", "Sherman 1", "4.2.2a")
    with pytest.raises(rules.Violation, match="10.1.2"):
        vehicles.order_check(board, "CO XO", "Sherman 1", "4.2.4k")
    with pytest.raises(rules.Violation, match="10.1.1"):
        vehicles.order_check(board, "Tank HQ", "1/1", "4.2.2a")


def test_clean_up_burning_wreck_becomes_wreck_and_markers_go(board):
    board["einheiten"]["Sherman 1"] = sherman("21", status=["Activated", "Moved/Fired"], hat_gehandelt=True)
    board["karten"]["22"]["extern"].append({"typ": "Smoke", "wert": 2, "quelle": "Burning Wreck", "wrack": True})
    board["fahrzeug_werte"] = {"wreck_cover": 1}
    prot = []
    vehicles.clean_up(board, prot)
    assert board["einheiten"]["Sherman 1"]["status"] == []
    assert board["karten"]["22"]["cover"][0]["typ"] == "Wreck"


def test_base_type_card_without_terrain():
    """L191: 'vehicle traffic' with cards still lacking terrain (terrain None) must not crash."""
    assert vehicles.base_type(None) == ""
    assert vehicles.base_type("Woods on 1 Hill") == "Woods"
    assert vehicles.base_type("Cemetery auf 1 Hill") == "Cemetery"


def test_stacking_16_steps_ignores_vehicle_crews(board, monkeypatch):
    """L193 [RULE 5.1.5 p.32, BGG 1881833]: 16 steps of infantry and 4 vehicles per card; Sherman crews are no infantry
    steps, so a 3-step squad may still join 13 infantry steps and two tanks."""
    from fof import briefing, commands, state

    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protokoll"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)
    s = board
    s.update(phase="3.3.1c", co_hq="CO HQ")
    s["einheiten"]["CO HQ"] = unit("11", vof=None, typ="HQ", ebene="CO", steps=1)
    s["einheiten"]["1st PLT HQ"] = unit("12", vof=None, typ="HQ", ebene="PLT", platoon="1", steps=1)
    s["einheiten"]["1/1"] = unit("12", platoon="1", steps=3)
    s["kommandos"]["1st PLT HQ"] = {"verfuegbar": 3, "gespart": 0, "aktiviert": True, "fertig": False}
    s["kommandos"]["CO HQ"] = {"verfuegbar": 0, "gespart": 0, "aktiviert": True, "fertig": True}
    for i in range(4):
        s["einheiten"][f"Sq {i}"] = unit("22", steps=3 if i < 3 else 4, platoon="2")
    s["einheiten"]["Sherman 1"] = sherman("22")
    s["einheiten"]["Sherman 2"] = sherman("22")
    commands.cmd_hq(s, ["1st PLT HQ"])
    with pytest.raises(rules.Violation, match="17 US steps"):
        commands.cmd_order(s, ["1st PLT HQ", "1st PLT HQ", "4.2.2b", "--target=22"])
    s["einheiten"]["Sq 3"]["steps"] = 2
    commands.cmd_order(s, ["1st PLT HQ", "1st PLT HQ", "4.2.2b", "--target=22"])
    assert s["einheiten"]["1/1"]["karte"] == "22"


def test_staging_card_is_trafficable(board):
    """L194: Staging Area cards have no terrain card; vehicle movement there is normal."""
    board["karten"]["11"].update(staging=True, terrain=None)
    assert vehicles.traffic(board, "11") is True


def test_msr2_tanks_act_before_at_guns(board):
    """L201 [Normandy M6 MSR 2]: with the group order the enemy AT gun gets no own action while tanks are still to act."""
    board["sonderregeln"] = {"fahrzeug_reihenfolge": "MSR 2"}
    board["einheiten"]["Sherman 1"] = sherman("21", status=["Activated"])
    board["einheiten"]["PAK"] = unit(
        "31", side="Feind", typ="AT Gun", vof="S", rng="C", at_waffe="75mm AT Gun", steps=1, status=["Activated"]
    )
    assert vehicles.current_group(board) == 1
    assert vehicles.enemy_actors(board) == []
    assert vehicles.us_actors(board) == ["Sherman 1"]
    board["einheiten"]["Sherman 1"]["status"] = ["Moved/Fired"]
    assert vehicles.current_group(board) == 3
    del board["sonderregeln"]
    assert vehicles.current_group(board) is None


@pytest.mark.game_data
def test_m6_package_templates_have_unit_type():
    """L202: every unit template of the M6 enemy packages carries 'typ' (package 7 held the two-team dict).
    Checks the real setup file when present, else its packages in tests/fixtures (kit layout)."""
    import json
    import pathlib

    p = pathlib.Path(__file__).resolve().parent.parent / "normandy" / "aufbau_normandy_m6.json"
    if not p.exists():
        p = pathlib.Path(__file__).resolve().parent / "fixtures" / "aufbau_normandy_m6_pakete.json"
    m = json.loads(p.read_text(encoding="utf-8"))
    for k, pk in m["pakete"].items():
        units = list(pk.get("einheiten", [])) + [u for v in pk.get("wahl", {}).values() for u in v]
        for u in units:
            assert "typ" in u, f"package {k}: {u.get('einheit')}"


def test_grenade_vof_on_vehicle_counts(board):
    """L205 [RULE 10.5.3]: a Grenade VOF on a vehicle is resolved with the AT modifier Grenade -2."""
    board["einheiten"]["Sherman 1"] = sherman("22", grenade=[-4])
    b = vehicles.vof_on_vehicle(board, "Sherman 1")
    assert b[0] == "G"
    assert vehicles.VOF_AT_MOD[b[0]] == -2


@pytest.mark.game_data
def test_friendly_incoming_hits_own_vehicle():
    """L214 [RULE 10.5.3, 6.2]: own Incoming! on the card is resolved against an own vehicle (friendly fire)."""
    from conftest import m6_state

    s = m6_state(569)
    s["einheiten"]["M4 Sherman 13"]["karte"] = "53"
    best = vehicles.vof_on_vehicle(s, "M4 Sherman 13")
    assert best and best[0] == "Incoming" and best[2] == "Mtr FO"
