from fof import geometry


def test_card_at_and_distance(board):
    assert geometry.card_at(board, 2, 3) == "23"
    assert geometry.card_at(board, 4, 1) is None
    assert geometry.distance(board, "11", "33") == 2
    assert geometry.adjacent(board, "11", "22")
    assert not geometry.adjacent(board, "11", "33")


def test_line_between_follows_the_eight_directions(board):
    assert geometry.line_between(board, "11", "13") == ["12"]
    assert geometry.line_between(board, "11", "33") == ["22"]
    assert geometry.line_between(board, "31", "13") == ["22"]
    assert geometry.line_between(board, "11", "23") is None  # knight's move: no straight line
    assert geometry.line_between(board, "12", "32") == ["22"]


def test_direction(board):
    assert geometry.direction(board, "11", "13") == (0, 1)
    assert geometry.direction(board, "33", "11") == (-1, -1)


def test_los_blocked_by_higher_card_between(board):
    ok, _ = geometry.los(board, "11", "13")
    assert ok
    board["karten"]["12"]["elevation"] = 2
    ok, reason = geometry.los(board, "11", "13")
    assert not ok and "5.2.2" in reason


def test_higher_observer_sees_over_lower_card(board):
    board["karten"]["11"]["elevation"] = 2
    board["karten"]["12"]["raender"] = "gruen"  # dark edges would block on the same level
    assert geometry.los(board, "11", "13")[0]
    assert not geometry.los(board, "31", "33")[0] or board["karten"]["32"]["raender"] == "weiss"


def test_incoming_blocks_los_out_and_through_but_not_into(board):
    board["karten"]["12"]["extern"].append({"typ": "Incoming", "wert": -3, "quelle": "test"})
    assert not geometry.los(board, "12", "13")[0]  # out of the card
    assert not geometry.los(board, "11", "13")[0]  # through the card
    assert geometry.los(board, "11", "12")[0]  # into the card


def test_limited_visibility_shortens_los_to_one_card(board):
    board["sicht"] = "eingeschraenkt"
    assert geometry.los(board, "11", "12")[0]
    assert not geometry.los(board, "11", "13")[0]
