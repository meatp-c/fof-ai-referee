"""Company Jeep asset, Naktong p.12 'Company Vehicle Assets: Jeep (no crew) (10.8.1)' (L528): rules 10.8.1 and 10.8.8."""

import json
import pathlib
import types

import pytest

from conftest import unit
from fof import pickup  # L556: split from commands


def _board(board):
    from fof import vehicles

    s = board
    s["units"]["Jeep"] = vehicles.company_jeep_unit("21")
    s["units"]["1st PLT HQ"] = unit("21", type="HQ", level="PLT", platoon="1", steps=1, experience="Green")
    s["units"]["2nd PLT HQ"] = unit("21", type="HQ", level="PLT", platoon="2", steps=1)
    s["units"]["1/W/1"] = unit("21", type="Weapons Team", platoon="1", steps=1, experience="Veteran")
    s["units"]["2/W/1"] = unit("21", type="Weapons Team", platoon="1", steps=1)
    s["units"]["1/1"] = unit("21", platoon="1", steps=3)
    return s


def _embark(s, n):

    prot = []
    pickup.embark_jeep(s, types.SimpleNamespace(recipient=s["units"][n], target_name=n, prot=prot))
    return prot


def test_jeep_carries_two_steps_of_infantry(board):
    from fof import rules, vehicles

    s = _board(board)
    with pytest.raises(rules.Violation, match="does not fit"):
        _embark(s, "1/1")
    _embark(s, "1/W/1")
    _embark(s, "2/W/1")
    assert vehicles.passengers(s, "Jeep") == ["1/W/1", "2/W/1"]
    with pytest.raises(rules.Violation, match="carries 2 steps"):
        _embark(s, "1st PLT HQ")


def test_experience_as_per_driver_and_passenger(board):
    s = _board(board)
    _embark(s, "1st PLT HQ")
    assert s["units"]["Jeep"]["experience"] == "Green"
    _embark(s, "1/W/1")
    assert s["units"]["Jeep"]["experience"] == "Veteran"
    _embark(s, "1/W/1")  # gets off again
    assert "on_board" not in s["units"]["1/W/1"] and s["units"]["Jeep"]["experience"] == "Green"


def test_no_activation_without_a_driver(board):
    from fof import rules, vehicles

    s = _board(board)
    ctx = types.SimpleNamespace(recipient=s["units"]["Jeep"], target_name="Jeep", prot=[])
    with pytest.raises(rules.Violation, match="nobody on board"):
        vehicles.order_4_2_1i(s, ctx)
    _embark(s, "2/W/1")
    vehicles.order_4_2_1i(s, ctx)
    assert rules.ACTIVATED in s["units"]["Jeep"]["status"]


def test_embarked_hq_activates_itself_others_need_an_eligible_hq(board):
    from fof import comms, rules, vehicles

    s = _board(board)
    _embark(s, "1st PLT HQ")
    assert vehicles.order_check(s, "1st PLT HQ", "Jeep", "4.2.1i")
    assert comms.chain_of_command(s, "1st PLT HQ", "Jeep")
    _embark(s, "1st PLT HQ")
    _embark(s, "1/W/1")
    assert comms.chain_of_command(s, "1st PLT HQ", "Jeep")
    with pytest.raises(rules.Violation, match="none of the units on board"):
        comms.chain_of_command(s, "2nd PLT HQ", "Jeep")


def test_activation_by_an_hq_off_board_needs_visual_verbal(board):
    from fof import rules, vehicles

    s = _board(board)
    _embark(s, "1/W/1")
    assert vehicles.order_check(s, "1st PLT HQ", "Jeep", "4.2.1i")
    s["units"]["1st PLT HQ"]["card"] = "22"
    with pytest.raises(rules.Violation, match="Visual-Verbal"):
        vehicles.order_check(s, "1st PLT HQ", "Jeep", "4.2.1i")


def test_passengers_ride_along_exposed(board):
    from fof import rules, vehicles

    s = _board(board)
    _embark(s, "1/W/1")
    vehicles.at36(s)["action"] = {"unit": "Jeep", "plan": [], "moved": False}
    vehicles.do_move(s, "Jeep", "22", None, [])
    assert s["units"]["1/W/1"]["card"] == "22" and rules.EXPOSED in s["units"]["1/W/1"]["status"]
    assert s["units"]["2/W/1"]["card"] == "21"


def test_naktong_setup_has_the_company_jeep():
    p = pathlib.Path(__file__).resolve().parents[1] / "korea" / "setup_naktong_m1.json"
    if not p.exists():
        pytest.skip("Naktong setup not in this copy")
    j = json.load(open(p, encoding="utf-8"))["units"]["Jeep"]
    assert j["company_jeep"] and j["vehicle"] == "Jeep" and j["steps"] == 0


@pytest.mark.game_data
def test_embark_and_activate_through_the_command_line(m6_game, fof_cli, tmp_path):
    from conftest import saved_state
    from fof import rules, vehicles

    s = m6_game(622)
    s["units"]["Jeep"] = vehicles.company_jeep_unit("53")
    (tmp_path / "game_state.json").write_text(json.dumps(s, indent=1, ensure_ascii=False), encoding="utf-8")
    code, out = fof_cli("order", "3rd PLT HQ", "Jeep", "4.2.1i")
    assert code == 2 and "nobody on board" in out
    code, out = fof_cli("order", "3rd PLT HQ", "3/AT", "4.2.2h", "--what=jeep")
    assert code == 0, out
    assert saved_state()["units"]["3/AT"]["on_board"] == "Jeep"
    code, out = fof_cli("order", "3rd PLT HQ", "Jeep", "4.2.1i")
    assert code == 0, out
    assert rules.ACTIVATED in saved_state()["units"]["Jeep"]["status"]
