"""L563: counters keep the name printed on them; a new counter takes the first free one in the player's tray order."""

from fof import commands


def test_first_free_counter_name_in_tray_order(board):
    board["counter_names"] = {"82mm Mtr Sec": ["1/82mm Mtr", "3/82mm Mtr", "2/82mm Mtr"]}
    assert commands.new_name(board, "82mm Mtr Sec", reuse_removed=True) == "1/82mm Mtr"
    board["units"]["1/82mm Mtr"] = {"side": "Enemy"}
    assert commands.new_name(board, "82mm Mtr Sec", reuse_removed=True) == "3/82mm Mtr"
    board["units"]["3/82mm Mtr"] = {"side": "Enemy"}
    del board["units"]["1/82mm Mtr"]  # left the map: back to its place in the tray
    board["removed_from_play"] = ["1/82mm Mtr"]
    assert commands.new_name(board, "82mm Mtr Sec", reuse_removed=True) == "1/82mm Mtr"


def test_types_without_counter_names_keep_the_numbering(board):
    board["counter_names"] = {"NKPA Squad": ["1/1/1"]}
    assert commands.new_name(board, "Fire Team") == "Fire Team 1"
    board["units"]["1/1/1"] = {"side": "Enemy"}
    assert commands.new_name(board, "NKPA Squad", reuse_removed=True) == "NKPA Squad 1"  # all named counters in play


def test_enemy_prefix_for_counters_without_a_printed_name(board):
    board["enemy_prefix"] = "NKPA"
    assert commands.new_name(board, "Sniper", reuse_removed=True) == "NKPA Sniper 1"
    assert commands.new_name(board, "NKPA Leader", reuse_removed=True) == "NKPA Leader 1"  # no double prefix
    assert commands.new_name(board, "Fire Team", side="Enemy") == "NKPA Fire Team 1"
    assert commands.new_name(board, "Fire Team", side="US") == "Fire Team 1"
