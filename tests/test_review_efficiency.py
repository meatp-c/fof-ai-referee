"""Review 24.10.2026, last efficiency items (L450): check_move and the Platoon Move."""

from conftest import unit


def test_check_move_computes_each_vof_once(board, monkeypatch):
    """Infiltration of a Pinned unit onto a friendly card without VOF: the destination VOF was looked up twice."""
    from fof import commands, fire

    s = board
    s["einheiten"]["1/1"] = unit("22", status=["Pinned"])
    s["einheiten"]["2/1"] = unit("23")
    calls = []
    real = fire.vof_against
    monkeypatch.setattr(fire, "vof_against", lambda s_, kid, side, **kw: calls.append(kid) or real(s_, kid, side, **kw))
    try:
        commands.check_move(s, s["einheiten"]["1/1"], "1/1", "23", "4.2.2c")
    except Exception:  # legality is not the point here
        pass
    assert sorted(calls) == sorted(set(calls)), calls


def test_platoon_move_runs_the_board_wide_fire_check_once(board, monkeypatch):
    """move_unit(open_all=False) skips the board-wide open_fire; the Platoon Move runs it once after the last member."""
    from fof import commands, fire

    s = board
    for n in ("1/1", "2/1", "3/1"):
        s["einheiten"][n] = unit("21")
    full = []
    real = fire.open_fire
    monkeypatch.setattr(fire, "open_fire", lambda s_, prot, only=None: full.append(only) or real(s_, prot, only=only))
    for n in ("1/1", "2/1", "3/1"):
        commands.move_unit(s, n, "22", None, True, [], open_all=False)
    assert None not in full  # only the per-unit calls (only=[n])
    commands.move_unit(s, "1/1", "23", None, True, [])
    assert None in full  # a single move still checks the whole board
    assert all(s["einheiten"][n]["karte"] in ("22", "23") for n in ("1/1", "2/1", "3/1"))
