"""Fixes collected during Naktong Mission 2 (V42, K54 and the gap list of that game)."""

from types import SimpleNamespace

import pytest

from conftest import unit

from fof import commands, enemy, fire, rules, setup


def test_casualty_carried_to_the_ccp_is_dropped_at_once(board):
    """V42: a unit bringing casualties onto the CCP drops them without a Command (5.1.6B), evacuation in Clean Up."""
    board["ccp"] = "12"
    board["units"]["L 22"] = unit("22", vof=None, type="Litter Team", steps=1, carries_casualties=1)
    prot = []
    commands.move_unit(board, "L 22", "12", "open", exposed=True, prot=prot)
    assert board["cards"]["12"]["casualties"] == 1 and "carries_casualties" not in board["units"]["L 22"]
    assert any("CCP 12" in p for p in prot)


def test_casualty_elsewhere_stays_with_the_carrier(board):
    board["ccp"] = "13"
    board["units"]["L 22"] = unit("22", vof=None, type="Litter Team", steps=1, carries_casualties=1)
    commands.move_unit(board, "L 22", "12", "open", exposed=True, prot=[])
    assert board["units"]["L 22"]["carries_casualties"] == 1 and not board["cards"]["12"].get("casualties")


def test_enemy_concentrate_fire_accepts_a_cover_id(board):
    """--unit=C1 names the stack beneath that Cover marker, as for the friendly side (commands.named_target)."""
    board["units"]["1/1"] = unit("22", area="C1")
    board["units"]["2/1"] = unit("22")
    assert enemy.stack_member(board, "22", "C1", "Enemy") == "1/1"
    assert enemy.stack_member(board, "22", "2/1", "Enemy") == "2/1"
    assert enemy.stack_member(board, "22", None, "Enemy") is None


def test_cease_fire_keeps_the_vof_marker_while_others_fire(board):
    """A unit losing its target only removes the VOF marker when no other unit of its side still fires there."""
    board["units"]["3/2"] = unit("11", target="33")
    board["units"]["2/W/2"] = unit("12", target="33", type="Weapons Team", steps=1)
    prot = []
    fire.apply_los_loss(board, "3/2", board["units"]["3/2"], ("lost", SimpleNamespace(text="too far")), prot)
    assert "its VOF stays (2/W/2 still fire there)" in prot[0]
    prot = []
    fire.apply_los_loss(board, "2/W/2", board["units"]["2/W/2"], ("lost", SimpleNamespace(text="too far")), prot)
    assert "remove the VOF marker from 33" in prot[0]


def test_staff_gets_a_patrol_hint_instead_of_a_platoon(board):
    board["units"]["CO XO"] = unit("11", type="Staff", steps=1)
    with pytest.raises(rules.Violation, match="--with=CO XO"):
        setup.assign_platoon(board, "CO XO", board["units"]["CO XO"], "2", [])


def test_observer_cards_per_firing_agency(board):
    """The board totals name the cards per observer for each firing agency when the mission has a table."""
    from fof import briefing

    board["cff_table"] = {"105mm HE": {"Arty FO": 3, "Mtr FO": 2}, "81mm HE": {"Arty FO": 2, "Mtr FO": 3}}
    assert briefing.observer_cards(board) == "; observer cards 105mm HE Arty FO 3/Mtr FO 2; 81mm HE Arty FO 2/Mtr FO 3"
    del board["cff_table"]
    board["cff_observers"] = {"Mtr FO": 3}
    assert briefing.observer_cards(board) == "; observers Mtr FO 3 card(s)"
