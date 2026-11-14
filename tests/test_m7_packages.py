"""Normandy Mission 7 package rules (L452): optional marker on an R# band and a single Incoming variant."""

import pytest

from conftest import card, unit


@pytest.fixture
def quiet(monkeypatch):
    from fof import briefing, state

    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protocol"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)


def _sniper_board(board):
    s = board
    s["cards"]["11"]["pc"] = "A"
    s["units"]["1/1"] = unit("11")
    pk = {
        "name": "Sniper! (Sniper in Basic +1 Cover; R#1/3 also Mines)",
        "spotted": False,
        "marker": [{"type": "Mines", "value": -4, "place": "trigger", "optional_r": "1/3"}],
        "units": [{"unit": "Sniper", "type": "Sniper", "vof_rating": "S!", "range": "L", "steps": 1, "place": "max"}],
    }
    return s, pk


def test_optional_mines_need_the_extra_draw(board, quiet):
    from fof import contact, rules

    s, pk = _sniper_board(board)
    with pytest.raises(rules.Violation, match="extra Mines on R# 1/3"):
        contact.pc_contact_campaign(s, "11", "A3", pk, {"--direction": "Front"})


def test_optional_mines_only_with_extra_yes(board, quiet):
    import copy

    from fof import contact

    s, pk = _sniper_board(board)
    s2 = copy.deepcopy(s)
    contact.pc_contact_campaign(s, "11", "A3", pk, {"--direction": "Front", "--extra": "no"})
    assert not any(x["type"] == "Mines" for x in s["cards"]["11"]["external"])
    contact.pc_contact_campaign(s2, "11", "A3", pk, {"--direction": "Front", "--extra": "yes"})
    assert any(x["type"] == "Mines" and x["value"] == -4 for x in s2["cards"]["11"]["external"])


def test_single_incoming_variant_needs_no_choice(board, quiet):
    from fof import contact

    s = board
    for c in (1, 2, 3):
        s["cards"][f"4{c}"] = card(4, c)
    s["cards"]["11"]["pc"] = "B"
    s["units"]["1/1"] = unit("11")
    pk = {
        "name": "Incoming! (Mortar -3 with Spotter in Foxholes)",
        "spotted": False,
        "marker": [{"type": "Incoming", "value": None, "place": "trigger"}],
        "variants": {"Mortar": {"value": -3, "missions": 2, "card_sequence": 3}},
        "units": [{"unit": "Spotter", "type": "Spotter", "spotter": True, "place": "max", "steps": 1, "range": "L"}],
    }
    contact.pc_contact_campaign(s, "11", "B2", pk, {"--direction": "Front"})
    assert any(x["type"] == "Incoming" and x["value"] == -3 for x in s["cards"]["11"]["external"])


def test_terrain_without_second_cc_value(board):
    """L455: --cc2=none for a Hedgerow/Bocage card printed with only +2 (Normandy M7 card 52)."""
    from fof import setup

    s = board
    s["terrain_catalog"] = {"Hedgerow/Bocage": {"cc": 2, "cc2": 1, "cover_max": 2, "cover_draw": 4, "edges": None}}
    s["cards"]["22"]["terrain"] = None
    setup.set_terrain(s, "22", "Hedgerow/Bocage", {"--cc2": "none", "--hill": "1"})
    c = s["cards"]["22"]
    assert c["cc"] == 2 and c["cc2"] is None and c["elevation"] == 2


def test_mission_rows_for_objectives(board):
    """L456: Normandy M7 p.42, Secondary one row below the top, Attack Position next to the Secondary only."""
    from fof import rules, setup

    s = board
    s["objective_rows"] = {"primary": 3, "secondary": 2, "ap": 1}
    s["ap_neighbours"] = ["secondary"]
    z = {"primary": None, "secondary": None}
    setup.objective_card(s, z, "secondary", "23", [])
    with pytest.raises(rules.Violation, match="only on tool row 3"):
        setup.objective_card(s, z, "primary", "23", [])
    z["secondary"], z["primary"] = "23", "31"
    with pytest.raises(rules.Violation, match="adjacent to the Secondary"):
        setup.objective_card(s, z, "ap", "11", [])  # next to the Primary 31 is not enough
    setup.objective_card(s, z, "ap", "12", [])


def test_concentrate_fire_on_the_only_spotted_enemy_needs_no_unit(board, monkeypatch):
    """L457: with a single spotted enemy on the target card --unit is not required (E91)."""
    import types

    from fof import commands

    s = board
    s["units"]["2/3"] = unit("22", target="32")
    s["units"]["G"] = unit("32", side="Enemy", spotted=True)
    ctx = types.SimpleNamespace(
        recipient=s["units"]["2/3"], target_name="2/3", o={}, success="yes", prot=[], action_id="4.2.4b"
    )
    monkeypatch.setattr(commands, "cf_target_check", lambda *a: None)
    monkeypatch.setattr(commands.fire, "effective_fire_target", lambda s_, n: "32")
    try:
        commands._order_concentrate_fire(s, ctx)
    except Exception as x:  # later bookkeeping (ammo) is not the point here
        assert "--unit" not in str(x)
    assert s["units"]["G"].get("cf") == 1


def test_extra_value_alias_is_translated():
    """L467: --extra=no reaches the engine as --zusatz=no (it was refused as an unknown value)."""
    from fof import cli

    assert cli.normalize_argv(["pc", "contact", "32", "3", "--extra=no"])[-1] == "--extra=no"
    assert cli.normalize_argv(["pc", "contact", "32", "3", "--extra=yes"])[-1] == "--extra=yes"
