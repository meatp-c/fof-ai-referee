"""L461: moving away from a card names what happens to the PDF marker left behind."""

from conftest import unit


def test_pdf_stays_when_another_unit_on_origin_still_fires(board):
    from fof import fire

    s = board
    s["units"]["1/3"] = unit("23", target="22")
    s["units"]["2/3"] = unit("23", target="22")
    s["units"]["1/3"]["card"] = "13"
    msg = fire.pdf_left_behind(s, "1/3", s["units"]["1/3"], "23")
    assert "stays" in msg and "2/3" in msg


def test_pdf_removed_when_nobody_else_fires(board):
    from fof import fire

    s = board
    s["units"]["1/3"] = unit("13", target="22")
    msg = fire.pdf_left_behind(s, "1/3", s["units"]["1/3"], "23")
    assert "remove PDF marker 23 to 22" in msg


def test_mutual_pdf_turns_back_to_the_enemy_arrow(board):
    from fof import fire

    s = board
    s["units"]["1/3"] = unit("13", target="22")
    s["units"]["LMG"] = unit("22", side="Enemy", target="23")
    msg = fire.pdf_left_behind(s, "1/3", s["units"]["1/3"], "23")
    assert "single arrow from 22" in msg and "LMG" in msg
