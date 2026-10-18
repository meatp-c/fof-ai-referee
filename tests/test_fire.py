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


def test_grazing_fire_lays_the_vof_on_every_card_along_the_pdf(board):
    """[RULE 7.2.2 p.51] tripod MG at range: VOF on all cards along the PDF up to max range, friendly cards included (L128)."""
    board["einheiten"]["MG"] = unit("11", vof="A", rng="V", ziel="12", tripod=True)
    board["einheiten"]["Enemy 1"] = unit("12", side="Feind")
    board["einheiten"]["2/1"] = unit("13")  # friendly unit behind the target
    assert fire.grazing_cards(board, "MG") == ["12", "13"]
    assert fire.vof_against(board, "13", "US")[:2] == ("A", -1)
    assert fire.pdfs_to(board, "13", "Feind") == {"11"}  # the grazing PDF counts for Crossfire on that card


def test_grazing_fire_stops_at_an_elevation_change_and_at_smoke(board):
    board["einheiten"]["MG"] = unit("11", vof="A", rng="V", ziel="12", tripod=True)
    board["einheiten"]["Enemy 1"] = unit("12", side="Feind")
    board["karten"]["13"]["elevation"] = 2  # level then uphill: no longer the same elevation
    assert fire.grazing_cards(board, "MG") == ["12"]
    board["karten"]["13"]["elevation"] = 1
    board["karten"]["11"]["elevation"] = 2  # MG on a hill, 2-1-1: shoots down at the nearest card only (BGG 3535366)
    board["einheiten"]["MG"]["ziel"] = "13"
    board["einheiten"]["Enemy 1"]["karte"] = "13"
    assert fire.grazing_cards(board, "MG") == []
    board["karten"]["11"]["elevation"] = 1
    board["karten"]["13"]["elevation"] = 1
    board["karten"]["12"]["extern"].append({"typ": "Smoke", "wert": 0, "quelle": "test"})
    assert fire.grazing_cards(board, "MG") == ["12"]  # the blocking card is the last one (6.1.2 p.44)


def test_no_grazing_fire_when_pinned_point_blank_or_without_tripod(board):
    board["einheiten"]["Enemy 1"] = unit("12", side="Feind")
    board["einheiten"]["MG"] = unit("11", vof="A", rng="V", ziel="12", tripod=True, status=["Pinned"])
    assert fire.grazing_cards(board, "MG") == []
    board["einheiten"]["MG"] = unit("12", vof="A", rng="V", ziel="12", tripod=True)
    assert fire.grazing_cards(board, "MG") == []
    board["einheiten"]["LMG"] = unit("11", vof="A", rng="L", ziel="12")
    assert fire.grazing_cards(board, "LMG") == []
    assert fire.vof_against(board, "13", "US") is None


def test_ncm_picks_the_strongest_effect_after_modifiers_at_night(board):
    """[RULE 6.4 p.45, Clarification 3] a Grenade VOF ignores the visibility modifier, so at night it beats an equal direct VOF (L129)."""
    from fof import combat

    board["sicht"] = "eingeschraenkt"
    board["licht"] = 2
    board["einheiten"]["MG"] = unit("11", vof="H", rng="V", ziel="12", tripod=True)
    board["einheiten"]["Enemy 1"] = unit("12", side="Feind", grenade=[-3])
    rows = combat.ncm_rows(board, "Enemy 1")
    assert rows[0][0].startswith("Grenade VOF") and sum(v for _, v in rows) == -3
    board["einheiten"]["Enemy 1"].pop("grenade")
    rows = combat.ncm_rows(board, "Enemy 1")
    assert rows[0][0].startswith("VOF Heavy") and sum(v for _, v in rows) == -1
