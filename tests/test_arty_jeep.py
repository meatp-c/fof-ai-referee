"""Arty Jeep, Normandy CSR 1 p.13 (L454): SCR610 mounted in a jeep that carries only the Arty FO."""

import types

import pytest

from conftest import unit
from fof import pickup  # L556: split from commands


def _board(board):
    s = board
    s["arty_jeep_possible"] = True
    s["units"]["Arty FO"] = unit("21", type="FO", vof=None, steps=1, radio=[{"type": "SCR610", "net": "Arty FD"}])
    return s


def _jeep(s):
    from fof import setup

    prot = []
    setup.setup_jeep(s, "Arty FO", s["units"]["Arty FO"], {"--jeep": "yes"}, prot)
    return prot


def test_jeep_only_where_the_mission_offers_it(board):
    from fof import rules, setup

    s = _board(board)
    s["arty_jeep_possible"] = False
    with pytest.raises(rules.Violation, match="offers no Arty Jeep"):
        setup.setup_jeep(s, "Arty FO", s["units"]["Arty FO"], {"--jeep": "yes"}, [])


def test_mounted_radio_works_only_on_board(board):
    from fof import comms

    s = _board(board)
    _jeep(s)
    fo = s["units"]["Arty FO"]
    assert s["units"]["Arty Jeep"]["card"] == "21" and fo["on_board"] == "Arty Jeep"
    assert comms.radios_of(fo, net="Arty FD")
    fo.pop("on_board")
    assert not comms.radios_of(fo, net="Arty FD")


def test_choosing_no_removes_the_jeep(board):
    from fof import setup

    s = _board(board)
    _jeep(s)
    setup.setup_jeep(s, "Arty FO", s["units"]["Arty FO"], {"--jeep": "no"}, [])
    assert "Arty Jeep" not in s["units"] and "on_board" not in s["units"]["Arty FO"]
    assert not any(g.get("mounted") for g in s["units"]["Arty FO"]["radio"])


def test_jeep_with_fo_is_activated_automatically_in_3_6(board):
    from fof import rules, vehicles

    s = _board(board)
    _jeep(s)
    prot = []
    vehicles.enter_3_6(s, prot)
    assert rules.ACTIVATED in s["units"]["Arty Jeep"]["status"]
    s2 = _board(board)
    _jeep(s2)
    s2["units"]["Arty FO"].pop("on_board")
    s2.pop("at36", None)
    s2["units"]["Arty Jeep"]["status"] = []
    vehicles.enter_3_6(s2, [])
    assert rules.ACTIVATED not in s2["units"]["Arty Jeep"]["status"]


def test_fo_rides_along_and_is_exposed(board):
    from fof import rules, vehicles

    s = _board(board)
    _jeep(s)
    vehicles.at36(s)["action"] = {"unit": "Arty Jeep", "plan": [], "moved": False}
    prot = []
    vehicles.do_move(s, "Arty Jeep", "22", None, prot)
    fo = s["units"]["Arty FO"]
    assert fo["card"] == "22" and rules.EXPOSED in fo["status"]
    assert rules.EXPOSED not in s["units"]["Arty Jeep"]["status"]


def test_fo_on_board_does_not_move_on_its_own(board):
    from fof import commands, rules

    s = _board(board)
    _jeep(s)
    with pytest.raises(rules.Violation, match="on board the Arty Jeep"):
        commands.check_move(s, s["units"]["Arty FO"], "Arty FO", "22", "4.2.2a")


def test_get_off_and_on_only_the_arty_fo(board):
    from fof import rules

    s = _board(board)
    _jeep(s)
    fo = s["units"]["Arty FO"]
    pickup.embark_jeep(s, types.SimpleNamespace(recipient=fo, target_name="Arty FO", prot=[]))
    assert "on_board" not in fo
    s["units"]["1/1"] = unit("21")
    with pytest.raises(rules.Violation, match="single step"):
        pickup.embark_jeep(s, types.SimpleNamespace(recipient=s["units"]["1/1"], target_name="1/1", prot=[]))
    pickup.embark_jeep(s, types.SimpleNamespace(recipient=fo, target_name="Arty FO", prot=[]))
    assert fo["on_board"] == "Arty Jeep"


def test_fo_dismounts_when_the_jeep_is_gone(board):
    from fof import combat

    s = _board(board)
    _jeep(s)
    combat.remove_from_play(s, "Arty Jeep", [], "Knocked Out")
    assert "on_board" not in s["units"]["Arty FO"] and s["units"]["Arty FO"]["card"] == "21"
