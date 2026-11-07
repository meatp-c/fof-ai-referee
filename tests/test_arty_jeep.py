"""Arty Jeep, Normandy CSR 1 p.13 (L454): SCR610 mounted in a jeep that carries only the Arty FO."""

import types

import pytest

from conftest import unit
from fof import pickup  # L556: split from commands


def _board(board):
    s = board
    s["arty_jeep_moeglich"] = True
    s["einheiten"]["Arty FO"] = unit("21", typ="FO", vof=None, steps=1, funk=[{"typ": "SCR610", "netz": "Arty FD"}])
    return s


def _jeep(s):
    from fof import setup

    prot = []
    setup.setup_jeep(s, "Arty FO", s["einheiten"]["Arty FO"], {"--jeep": "ja"}, prot)
    return prot


def test_jeep_only_where_the_mission_offers_it(board):
    from fof import rules, setup

    s = _board(board)
    s["arty_jeep_moeglich"] = False
    with pytest.raises(rules.Violation, match="offers no Arty Jeep"):
        setup.setup_jeep(s, "Arty FO", s["einheiten"]["Arty FO"], {"--jeep": "ja"}, [])


def test_mounted_radio_works_only_on_board(board):
    from fof import comms

    s = _board(board)
    _jeep(s)
    fo = s["einheiten"]["Arty FO"]
    assert s["einheiten"]["Arty Jeep"]["karte"] == "21" and fo["an_bord"] == "Arty Jeep"
    assert comms.radios_of(fo, net="Arty FD")
    fo.pop("an_bord")
    assert not comms.radios_of(fo, net="Arty FD")


def test_choosing_no_removes_the_jeep(board):
    from fof import setup

    s = _board(board)
    _jeep(s)
    setup.setup_jeep(s, "Arty FO", s["einheiten"]["Arty FO"], {"--jeep": "nein"}, [])
    assert "Arty Jeep" not in s["einheiten"] and "an_bord" not in s["einheiten"]["Arty FO"]
    assert not any(g.get("eingebaut") for g in s["einheiten"]["Arty FO"]["funk"])


def test_jeep_with_fo_is_activated_automatically_in_3_6(board):
    from fof import rules, vehicles

    s = _board(board)
    _jeep(s)
    prot = []
    vehicles.enter_3_6(s, prot)
    assert rules.ACTIVATED in s["einheiten"]["Arty Jeep"]["status"]
    s2 = _board(board)
    _jeep(s2)
    s2["einheiten"]["Arty FO"].pop("an_bord")
    s2.pop("at36", None)
    s2["einheiten"]["Arty Jeep"]["status"] = []
    vehicles.enter_3_6(s2, [])
    assert rules.ACTIVATED not in s2["einheiten"]["Arty Jeep"]["status"]


def test_fo_rides_along_and_is_exposed(board):
    from fof import rules, vehicles

    s = _board(board)
    _jeep(s)
    vehicles.at36(s)["aktion"] = {"einheit": "Arty Jeep", "plan": [], "bewegt": False}
    prot = []
    vehicles.do_move(s, "Arty Jeep", "22", None, prot)
    fo = s["einheiten"]["Arty FO"]
    assert fo["karte"] == "22" and rules.EXPOSED in fo["status"]
    assert rules.EXPOSED not in s["einheiten"]["Arty Jeep"]["status"]


def test_fo_on_board_does_not_move_on_its_own(board):
    from fof import commands, rules

    s = _board(board)
    _jeep(s)
    with pytest.raises(rules.Violation, match="on board the Arty Jeep"):
        commands.check_move(s, s["einheiten"]["Arty FO"], "Arty FO", "22", "4.2.2a")


def test_get_off_and_on_only_the_arty_fo(board):
    from fof import rules

    s = _board(board)
    _jeep(s)
    fo = s["einheiten"]["Arty FO"]
    pickup.embark_jeep(s, types.SimpleNamespace(z=fo, target_name="Arty FO", prot=[]))
    assert "an_bord" not in fo
    s["einheiten"]["1/1"] = unit("21")
    with pytest.raises(rules.Violation, match="single step"):
        pickup.embark_jeep(s, types.SimpleNamespace(z=s["einheiten"]["1/1"], target_name="1/1", prot=[]))
    pickup.embark_jeep(s, types.SimpleNamespace(z=fo, target_name="Arty FO", prot=[]))
    assert fo["an_bord"] == "Arty Jeep"


def test_fo_dismounts_when_the_jeep_is_gone(board):
    from fof import combat

    s = _board(board)
    _jeep(s)
    combat.remove_from_play(s, "Arty Jeep", [], "Knocked Out")
    assert "an_bord" not in s["einheiten"]["Arty FO"] and s["einheiten"]["Arty FO"]["karte"] == "21"
