"""L466: moving onto a card under the VOF of own units names those shooters (friendly fire, 6.3.3)."""

from conftest import unit


def test_friendly_fire_on_lists_own_shooters(board):
    from fof import commands

    s = board
    s["units"]["A"] = unit("21", target="23")
    s["units"]["B"] = unit("22")
    s["units"]["B"]["card"] = "23"
    s["units"]["G"] = unit("23", side="Enemy")
    assert commands.friendly_fire_on(s, "B", "23") == ["A"]
