"""L529, review block A (07.11.2026): 'new' without a dangling .current_game (K2), damaged setup files (K5), and the
command line on the synthetic board (T1: these paths had no test that runs in the public kit)."""

import json

from conftest import saved_state, unit


def test_new_with_damaged_json_is_a_violation(fof_cli, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    code, out = fof_cli("new", str(bad))
    assert code == 2 and "VIOLATION" in out and "not valid JSON" in out


def test_new_with_a_file_that_is_no_setup(fof_cli, tmp_path):
    f = tmp_path / "x.json"
    f.write_text('{"mission": "x"}', encoding="utf-8")
    code, out = fof_cli("new", str(f))
    assert code == 2 and "missing units, cards" in out


def _root(tmp_path, monkeypatch, board):
    from fof import state

    root = tmp_path / "root"
    root.mkdir()
    (root / ".current_game").write_text("game1", encoding="utf-8")
    monkeypatch.setattr(state, "ROOT", root)
    monkeypatch.delenv("FOF_GAME", raising=False)
    s = dict(board, mission="synthetic", max_turns=10)
    setup_file = tmp_path / "setup.json"
    setup_file.write_text(json.dumps(s), encoding="utf-8")
    return root, setup_file


def test_new_in_a_nested_folder_creates_it_and_switches_the_pointer(fof_cli, tmp_path, monkeypatch, board):
    root, setup_file = _root(tmp_path, monkeypatch, board)
    code, out = fof_cli("new", str(setup_file), "games/m1")
    assert code == 0, out
    assert (root / "games" / "m1" / "game_state.json").exists()
    assert (root / ".current_game").read_text(encoding="utf-8") == "games/m1"


def test_failed_save_switches_the_pointer_back(fof_cli, tmp_path, monkeypatch, board):
    from fof import rules, state

    root, setup_file = _root(tmp_path, monkeypatch, board)

    def refuse(*a, **k):
        raise rules.Violation("disk full (test)")

    monkeypatch.setattr(state, "save_state", refuse)
    code, out = fof_cli("new", str(setup_file), "m2")
    assert code == 2 and "disk full" in out
    assert (root / ".current_game").read_text(encoding="utf-8") == "game1"


def test_cli_game_runs_status_and_refuses_with_exit_2(cli_game, fof_cli):
    cli_game()
    code, out = fof_cli("status")
    assert code == 0 and "synthetic" in out
    code, out = fof_cli("order")
    assert code == 2 and "VIOLATION" in out
    code, out = fof_cli("nonsense-command")
    assert code != 0


def test_cli_game_books_and_undoes(cli_game, fof_cli, board):
    cli_game(units={"1/1": unit("11", platoon="1")})
    assert fof_cli("note", "first")[0] == 0
    assert fof_cli("note", "second")[0] == 0
    n = len(saved_state()["protocol"])
    code, out = fof_cli("undo", str(n - 1))
    assert code == 0, out
    prot = saved_state()["protocol"]
    assert len(prot) == n and prot[-1]["text"].startswith(f"Undo to entry {n - 1}")
    assert not any("second" in p["text"] for p in prot[:-1])


# ---- A3: argument checks (review K3, K4, C7, C8): a Violation instead of a traceback or a silently wrong value


def _cmd_board(board, monkeypatch, phase="3.3.1b"):
    from fof import briefing, state

    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protocol"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)
    s = board
    s["phase"] = phase
    s["commands"]["1st PLT HQ"] = {"available": 6, "saved": 0, "activated": True, "done": False}
    s["units"]["1st PLT HQ"] = unit("22", vof=None, type="HQ", level="PLT", platoon="1", steps=1)
    s["active_hq"] = "1st PLT HQ"
    return s


def test_steps_cannot_be_cleared(board, monkeypatch):
    import pytest
    from fof import rules, setup

    s = _cmd_board(board, monkeypatch, phase="3.1")
    s["units"]["1/1"] = unit("11")
    with pytest.raises(rules.Violation, match="steps cannot be cleared"):
        setup.cmd_values(s, ["1/1", "steps=null"])
    assert s["units"]["1/1"]["steps"] == 3


def test_reconstitute_refuses_a_lat_named_twice_and_a_wrong_experience(board, monkeypatch):
    import pytest
    from fof import campaign, rules

    s = _cmd_board(board, monkeypatch)
    s.update(campaign={"attempt": 1}, mission_end=True, setup_units={"1/1": unit("11", steps=3)})
    s["units"]["LT1"] = unit("11", type="Fire Team", steps=1)
    s["units"]["LT2"] = unit("11", type="Fire Team", steps=1)
    with pytest.raises(rules.Violation, match="more than once"):
        campaign.cmd_reconstitute(s, ["1/1", "--from=LT1,LT1"])
    with pytest.raises(rules.Violation, match="Green, Line, Veteran"):
        campaign.cmd_reconstitute(s, ["1/1", "--from=LT1,LT2", "--experience=elite"])
    assert "LT1" in s["units"] and "LT2" in s["units"]


def _squad_board(board, monkeypatch):
    s = _cmd_board(board, monkeypatch)
    s["removed_from_play"] = ["1/1"]
    s["units"]["Fire Team 1"] = unit("22", type="Fire Team", steps=1, platoon="1")
    s["units"]["Fire Team 2"] = unit("22", type="Fire Team", steps=1, platoon="1")
    return s


def test_reconstitute_squad_argument_checks(board, monkeypatch):
    import pytest
    from fof import commands, rules

    base = ["1st PLT HQ", "Fire Team 1", "4.2.3i", "--squad=1/1", "--success=yes"]
    s = _squad_board(board, monkeypatch)
    with pytest.raises(rules.Violation, match="named twice"):
        commands.cmd_order(s, [*base, "--with=Fire Team 1"])
    s = _squad_board(board, monkeypatch)
    with pytest.raises(rules.Violation, match="needs a value"):
        commands.cmd_order(s, [*base, "--with"])
    s = _squad_board(board, monkeypatch)
    with pytest.raises(rules.Violation, match="Green, Line, Veteran"):
        commands.cmd_order(s, [*base, "--with=Fire Team 2", "--experience=elite"])
    s = _squad_board(board, monkeypatch)
    commands.cmd_order(s, [*base, "--with=Fire Team 2", "--experience=veteran"])
    assert s["units"]["1/1"]["experience"] == "Veteran"


def test_bare_success_flag_is_a_violation(board, monkeypatch):
    import pytest
    from fof import commands, rules

    s = _cmd_board(board, monkeypatch)
    s["units"]["1/1"] = unit("22", platoon="1")
    with pytest.raises(rules.Violation, match="needs a value"):
        commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.2a", "--target=32", "--success"])
    assert s["units"]["1/1"]["card"] == "22"
