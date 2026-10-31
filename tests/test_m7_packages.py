"""Normandy Mission 7 package rules (L452): optional marker on an R# band and a single Incoming variant."""

import pytest

from conftest import card, unit


@pytest.fixture
def quiet(monkeypatch):
    from fof import briefing, state

    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protokoll"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)


def _sniper_board(board):
    s = board
    s["karten"]["11"]["pc"] = "A"
    s["einheiten"]["1/1"] = unit("11")
    pk = {
        "name": "Sniper! (Sniper in Basic +1 Cover; R#1/3 auch Mines)",
        "spotted": False,
        "marker": [{"typ": "Mines", "wert": -4, "platz": "trigger", "optional_r": "1/3"}],
        "einheiten": [
            {"einheit": "Sniper", "typ": "Sniper", "vof_rating": "S!", "reichweite": "L", "steps": 1, "platz": "max"}
        ],
    }
    return s, pk


def test_optional_mines_need_the_extra_draw(board, quiet):
    from fof import contact, rules

    s, pk = _sniper_board(board)
    with pytest.raises(rules.Violation, match="extra Mines on R# 1/3"):
        contact.pc_contact_v4(s, "11", "A3", pk, {"--richtung": "Front"})


def test_optional_mines_only_with_extra_yes(board, quiet):
    import copy

    from fof import contact

    s, pk = _sniper_board(board)
    s2 = copy.deepcopy(s)
    contact.pc_contact_v4(s, "11", "A3", pk, {"--richtung": "Front", "--zusatz": "nein"})
    assert not any(x["typ"] == "Mines" for x in s["karten"]["11"]["extern"])
    contact.pc_contact_v4(s2, "11", "A3", pk, {"--richtung": "Front", "--zusatz": "ja"})
    assert any(x["typ"] == "Mines" and x["wert"] == -4 for x in s2["karten"]["11"]["extern"])


def test_single_incoming_variant_needs_no_choice(board, quiet):
    from fof import contact

    s = board
    for c in (1, 2, 3):
        s["karten"][f"4{c}"] = card(4, c)
    s["karten"]["11"]["pc"] = "B"
    s["einheiten"]["1/1"] = unit("11")
    pk = {
        "name": "Incoming! (Mortar -3 mit Spotter in Foxholes)",
        "spotted": False,
        "marker": [{"typ": "Incoming", "wert": None, "platz": "trigger"}],
        "varianten": {"Mortar": {"wert": -3, "missionen": 2, "karten_folge": 3}},
        "einheiten": [
            {"einheit": "Spotter", "typ": "Spotter", "spotter": True, "platz": "max", "steps": 1, "reichweite": "L"}
        ],
    }
    contact.pc_contact_v4(s, "11", "B2", pk, {"--richtung": "Front"})
    assert any(x["typ"] == "Incoming" and x["wert"] == -3 for x in s["karten"]["11"]["extern"])


def test_terrain_without_second_cc_value(board):
    """L455: --cc2=none for a Hedgerow/Bocage card printed with only +2 (Normandy M7 card 52)."""
    from fof import setup

    s = board
    s["terrain_katalog"] = {"Hedgerow/Bocage": {"cc": 2, "cc2": 1, "cover_max": 2, "cover_draw": 4, "raender": None}}
    s["karten"]["22"]["terrain"] = None
    setup.set_terrain(s, "22", "Hedgerow/Bocage", {"--cc2": "none", "--hill": "1"})
    c = s["karten"]["22"]
    assert c["cc"] == 2 and c["cc2"] is None and c["elevation"] == 2


def test_mission_rows_for_objectives(board):
    """L456: Normandy M7 p.42, Secondary one row below the top, Attack Position next to the Secondary only."""
    from fof import rules, setup

    s = board
    s["ziele_reihen"] = {"primaer": 3, "sekundaer": 2, "ap": 1}
    s["ap_neben"] = ["sekundaer"]
    z = {"primaer": None, "sekundaer": None}
    setup.objective_card(s, z, "sekundaer", "23", [])
    with pytest.raises(rules.Violation, match="only on tool row 3"):
        setup.objective_card(s, z, "primaer", "23", [])
    z["sekundaer"], z["primaer"] = "23", "31"
    with pytest.raises(rules.Violation, match="adjacent to the Secondary"):
        setup.objective_card(s, z, "ap", "11", [])  # next to the Primary 31 is not enough
    setup.objective_card(s, z, "ap", "12", [])


def test_concentrate_fire_on_the_only_spotted_enemy_needs_no_unit(board, monkeypatch):
    """L457: with a single spotted enemy on the target card --unit is not required (E91)."""
    import types

    from fof import commands

    s = board
    s["einheiten"]["2/3"] = unit("22", ziel="32")
    s["einheiten"]["G"] = unit("32", side="Feind", spotted=True)
    ctx = types.SimpleNamespace(z=s["einheiten"]["2/3"], target_name="2/3", o={}, success="ja", prot=[], akt="4.2.4b")
    monkeypatch.setattr(commands, "cf_target_check", lambda *a: None)
    monkeypatch.setattr(commands.fire, "effective_fire_target", lambda s_, n: "32")
    try:
        commands._order_concentrate_fire(s, ctx)
    except Exception as x:  # later bookkeeping (ammo) is not the point here
        assert "--unit" not in str(x)
    assert s["einheiten"]["G"].get("cf") == 1


def test_extra_value_alias_is_translated():
    """L467: --extra=no reaches the engine as --zusatz=nein (it was refused as an unknown value)."""
    from fof import cli

    assert cli.argv_to_german(["pc", "contact", "32", "3", "--extra=no"])[-1] == "--zusatz=nein"
    assert cli.argv_to_german(["pc", "contact", "32", "3", "--extra=yes"])[-1] == "--zusatz=ja"
