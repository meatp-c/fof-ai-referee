"""L466: moving onto a card under the VOF of own units names those shooters (friendly fire, 6.3.3)."""

from conftest import unit


def test_friendly_fire_on_lists_own_shooters(board):
    from fof import commands

    s = board
    s["einheiten"]["A"] = unit("21", ziel="23")
    s["einheiten"]["B"] = unit("22")
    s["einheiten"]["B"]["karte"] = "23"
    s["einheiten"]["G"] = unit("23", side="Feind")
    assert commands.friendly_fire_on(s, "B", "23") == ["A"]
