"""L464: a second failed Grenade Attack on the same card places no second Miss Modifier."""


def test_second_grenade_miss_says_already_there(board):
    from fof import commands

    s = board
    first = commands.place_grenade_miss(s, "22")
    second = commands.place_grenade_miss(s, "22")
    assert "(-1) on 22" in first and "already on 22" in second
    assert s["karten"]["22"]["grenade_miss"] is True
