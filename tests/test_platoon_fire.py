"""Platoon Concentrate Fire 4.2.4c and Platoon Grenade Attack 4.2.4h: one attempt per eligible unit of the platoon (L136)."""

import pytest
from conftest import unit

from fof import briefing, commands, rules, state


@pytest.fixture
def platoon(board, monkeypatch):
    s = board
    s.update(zug=2, aktiver_hq="1st PLT HQ", xp=[])
    s["kommandos"]["1st PLT HQ"] = {"verfuegbar": 6, "gespart": 0, "aktiviert": True, "fertig": False}
    s["einheiten"]["1st PLT HQ"] = unit("22", vof=None, typ="HQ", ebene="PLT", platoon="1", steps=1)
    s["einheiten"]["1/1"] = unit("22", vof="S", platoon="1", ziel="23", erfahrung="Veteran")
    s["einheiten"]["2/1"] = unit("22", vof="S", platoon="1", ziel="23", erfahrung="Green")
    s["einheiten"]["MG"] = unit(
        "22", vof="H", rng="V", typ="Weapons Team", platoon="1", ziel="23", tripod=True, steps=1
    )
    s["einheiten"]["1/2"] = unit("22", vof="S", platoon="2", ziel="23")  # other platoon, must not take part
    s["einheiten"]["Enemy 1"] = unit("23", side="Feind", vof="A", ziel="22", bereich="C1")
    s["karten"]["23"]["cover"] = [{"id": "C1", "typ": "Foxholes", "wert": 1}]
    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protokoll"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)
    return s


def test_platoon_concentrate_fire_draws_per_unit_and_costs_two(platoon):
    s = platoon
    with pytest.raises(rules.Violation) as ex:
        commands.cmd_order(s, ["1st PLT HQ", "1st PLT HQ", "4.2.4c"])
    msg = str(ex.value)
    assert "1/1 3 cards (Veteran)" in msg and "2/1 1 cards (Green)" in msg and "MG 3 cards (Line, tripod +1)" in msg
    assert "1/2" not in msg
    commands.cmd_order(s, ["1st PLT HQ", "1st PLT HQ", "4.2.4c", "--success=1/1:ja,2/1:nein,MG:ja", "--unit=Enemy 1"])
    assert s["einheiten"]["Enemy 1"]["cf"] == 2
    assert s["kommandos"]["1st PLT HQ"]["verfuegbar"] == 4


def test_platoon_grenade_attack_point_blank(platoon):
    s = platoon
    s["einheiten"]["Enemy 2"] = unit("22", side="Feind", vof="S", ziel="22")
    for n in ("1/1", "2/1", "MG", "1/2"):
        s["einheiten"][n]["ziel"] = "22"
    commands.cmd_order(
        s,
        [
            "1st PLT HQ",
            "1st PLT HQ",
            "4.2.4h",
            "--success=1st PLT HQ:ja,1/1:ja,2/1:nein,MG:nein",
            "--unit=Enemy 2",
            "--critical=1/1",
        ],
    )
    assert s["einheiten"]["Enemy 2"]["grenade"] == [-4, -4, -4]  # HQ, 1/1 and its Critical Hit
    assert s["karten"]["22"].get("grenade_miss") is True
