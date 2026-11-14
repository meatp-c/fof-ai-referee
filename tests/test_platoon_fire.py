"""Platoon Concentrate Fire 4.2.4c and Platoon Grenade Attack 4.2.4h: one attempt per eligible unit of the platoon (L136)."""

import pytest
from conftest import unit

from fof import briefing, commands, rules, state


@pytest.fixture
def platoon(board, monkeypatch):
    s = board
    s.update(turn=2, active_hq="1st PLT HQ", xp=[])
    s["commands"]["1st PLT HQ"] = {"available": 6, "saved": 0, "activated": True, "done": False}
    s["units"]["1st PLT HQ"] = unit("22", vof=None, type="HQ", level="PLT", platoon="1", steps=1)
    s["units"]["1/1"] = unit("22", vof="S", platoon="1", target="23", experience="Veteran")
    s["units"]["2/1"] = unit("22", vof="S", platoon="1", target="23", experience="Green")
    s["units"]["MG"] = unit("22", vof="H", rng="V", type="Weapons Team", platoon="1", target="23", tripod=True, steps=1)
    s["units"]["1/2"] = unit("22", vof="S", platoon="2", target="23")  # other platoon, must not take part
    s["units"]["Enemy 1"] = unit("23", side="Enemy", vof="A", target="22", area="C1")
    s["cards"]["23"]["cover"] = [{"id": "C1", "type": "Foxholes", "value": 1}]
    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protocol"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)
    return s


def test_platoon_concentrate_fire_draws_per_unit_and_costs_two(platoon):
    s = platoon
    with pytest.raises(rules.Violation) as ex:
        commands.cmd_order(s, ["1st PLT HQ", "1st PLT HQ", "4.2.4c"])
    msg = str(ex.value)
    assert "1/1 3 cards (Veteran)" in msg and "2/1 1 cards (Green)" in msg and "MG 3 cards (Line, tripod +1)" in msg
    assert "1/2" not in msg
    commands.cmd_order(s, ["1st PLT HQ", "1st PLT HQ", "4.2.4c", "--success=1/1:yes,2/1:no,MG:yes", "--unit=Enemy 1"])
    assert s["units"]["Enemy 1"]["cf"] == 2
    assert s["commands"]["1st PLT HQ"]["available"] == 4


def test_platoon_grenade_attack_point_blank(platoon):
    s = platoon
    s["units"]["Enemy 2"] = unit("22", side="Enemy", vof="S", target="22")
    for n in ("1/1", "2/1", "MG", "1/2"):
        s["units"][n]["target"] = "22"
    commands.cmd_order(
        s,
        [
            "1st PLT HQ",
            "1st PLT HQ",
            "4.2.4h",
            "--success=1st PLT HQ:yes,1/1:yes,2/1:no,MG:no",
            "--unit=Enemy 2",
            "--critical=1/1",
        ],
    )
    assert s["units"]["Enemy 2"]["grenade"] == [-4, -4, -4]  # HQ, 1/1 and its Critical Hit
    assert s["cards"]["22"].get("grenade_miss") is True


def test_single_concentrate_fire_names_the_tripod_card(platoon):
    """L569: the extra card of a tripod MG (7.11.2) stands in the draw breakdown of a single Concentrate Fire too."""
    with pytest.raises(
        rules.Violation, match=r"draw 3 Action cards \(base 2, experience Line of the recipient, tripod MG \+1\)"
    ):
        commands.cmd_order(platoon, ["1st PLT HQ", "MG", "4.2.4b"])
