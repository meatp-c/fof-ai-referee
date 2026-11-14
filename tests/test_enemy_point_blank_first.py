"""L472: an enemy unit with opposing units on its own card opens fire Point Blank (6.2.1b), even if another card in view
holds more US steps."""

from conftest import unit


def test_enemy_opens_point_blank_before_most_steps(board):
    from fof import fire

    s = board
    s["units"]["FT"] = unit("22", side="Enemy", rng="C", steps=1)
    s["units"]["US1"] = unit("22", steps=1)
    s["units"]["US2"] = unit("23", steps=3)
    s["units"]["US3"] = unit("23", steps=3)
    prot = []
    fire.open_fire(s, prot, only=["FT"])
    assert s["units"]["FT"]["target"] == "22", prot
