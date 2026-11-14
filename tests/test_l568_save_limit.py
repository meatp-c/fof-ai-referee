"""L568: the Command lines name the save limit of 4.1.3 (Green 3/2, Line 6/4, Veteran 9/6 by day/limited visibility)."""

from fof import commands


def test_save_limit_by_experience_and_visibility(board):
    board["units"]["1st PLT HQ"] = {
        "side": "US",
        "type": "HQ",
        "level": "PLT",
        "experience": "Green",
        "card": "11",
        "status": [],
        "steps": 1,
    }
    board["units"]["CO 1 Sgt"] = {
        "side": "US",
        "type": "Staff",
        "level": "CO",
        "experience": "Veteran",
        "card": "11",
        "status": [],
        "steps": 1,
    }
    assert commands.save_limit(board, "1st PLT HQ") == 3
    assert commands.save_limit(board, "CO 1 Sgt") == 9
    assert commands.save_limit(board, "GI") == 0
    board["sight"] = "limited"
    assert commands.save_limit(board, "1st PLT HQ") == 2
    assert commands.save_limit(board, "CO 1 Sgt") == 6
