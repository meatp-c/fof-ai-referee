from conftest import unit

from fof import fire


def test_vof_lands_on_the_closest_occupied_card_along_the_pdf(board):
    board["einheiten"]["1/1"] = unit("11", ziel="13")
    board["einheiten"]["Enemy 1"] = unit("13", side="Feind")
    assert fire.effective_fire_target(board, "1/1") == "13"
    board["einheiten"]["Enemy 2"] = unit("12", side="Feind")  # steps into the PDF
    assert fire.effective_fire_target(board, "1/1") == "12"


def test_vof_moves_back_to_a_blocking_incoming_card(board):
    board["einheiten"]["1/1"] = unit("11", ziel="13")
    board["einheiten"]["Enemy 1"] = unit("13", side="Feind")
    board["karten"]["12"]["extern"].append({"typ": "Incoming", "wert": -3, "quelle": "test"})
    assert fire.effective_fire_target(board, "1/1") == "12"  # [RULE 6.1.2 p.44]


def test_vof_against_takes_the_strongest_value(board):
    board["einheiten"]["1/1"] = unit("11", vof="S", ziel="13")
    board["einheiten"]["MG"] = unit("31", vof="A", ziel="13", tripod=True)
    board["einheiten"]["Enemy 1"] = unit("13", side="Feind")
    typ, value, sources = fire.vof_against(board, "13", "Feind")
    assert (typ, value) == ("A", -1) and set(sources) == {"1/1", "MG"}
    # fire from another card hits everybody on the target card (friendly fire incidents, 6.1.2) ...
    assert fire.vof_against(board, "13", "US")[:2] == ("A", -1)


def test_point_blank_fire_hits_only_the_opposing_side(board):
    board["einheiten"]["1/1"] = unit("12", vof="A", ziel="12")
    board["einheiten"]["Enemy 1"] = unit("12", side="Feind", vof="S", ziel="12")
    assert fire.vof_against(board, "12", "Feind")[:2] == ("A", -1)
    assert fire.vof_against(board, "12", "US")[:2] == ("S", 0)  # ... point blank only the other side (6.2.1b)


def test_pinned_unit_fires_pinned_vof(board):
    board["einheiten"]["1/1"] = unit("11", vof="A", ziel="12", status=["Pinned"])
    board["einheiten"]["Enemy 1"] = unit("12", side="Feind")
    assert fire.vof_against(board, "12", "Feind")[:2] == ("Pinned", 2)
