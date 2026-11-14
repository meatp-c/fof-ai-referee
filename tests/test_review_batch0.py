"""Review 23.10.2026, batch 0 (L221-L228): shared helpers and the core fixes that depend on them."""

import json

import pytest

from conftest import unit


def test_need_and_int_value_raise_violations():
    """L221: missing arguments and non-numbers are Violations, not IndexError/ValueError."""
    from fof import rules

    with pytest.raises(rules.Violation):
        rules.need([], 1, "x <a>")
    rules.need(["a"], 1, "x <a>")
    with pytest.raises(rules.Violation):
        rules.int_value("abc", "R#")
    assert rules.int_value("7", "R#") == 7


def test_parse_opts_registry_flags_empty_and_repeated():
    """L222: unknown keys, empty values and repeated keys are refused; a bare flag is True."""
    from fof import options, rules

    assert options.parse_opts(["--raw"]) == {"--raw": True}
    assert options.parse_opts(["--target=21"]) == {"--target": "21"}
    for bad in (["--karte=1"], ["--target="], ["--target=21", "--target=22"]):
        with pytest.raises(rules.Violation):
            options.parse_opts(bad)
    assert options.int_opt({"--r": "5"}, "--r", "R#") == 5
    with pytest.raises(rules.Violation):
        options.int_opt({"--r": "x"}, "--r", "R#")


def test_move_target_marker_no_longer_overwrites_the_target():
    """Review H7: --move-target-marker had become --target and then --ziel, overwriting the Call for Fire target."""
    from fof import cli, options

    argv = cli.normalize_argv(["order", "HQ", "FO", "4.2.4i", "--target=A3", "--move-target-marker=no"])
    o = options.parse_opts(argv[4:])
    assert o["--target"] == "A3" and o["--move-target-marker"] == "no"


def test_value_aliases_only_for_enumerations():
    """L222 (review M3): free text keeps its words; per-unit lists translate item by item (review H8)."""
    from fof import cli

    out = cli.normalize_argv(["set", "1/1", "--reason=no", "--what=radio", "--success=1/1:yes,2/1:no", "--area=open"])
    assert "--reason=no" in out and "--what=radio" in out
    assert "--success=1/1:yes,2/1:no" in out and "--area=open" in out


def test_save_is_atomic_and_damaged_file_names_snapshot(tmp_path, monkeypatch):
    """L223 (review M1): write via .tmp + os.replace; a damaged game_state.json names the latest snapshot."""
    from fof import state

    monkeypatch.setenv("FOF_GAME", str(tmp_path))
    p = tmp_path / "game_state.json"
    state.write_atomic(p, '{"a": 1}')
    assert json.loads(p.read_text()) == {"a": 1} and not (tmp_path / "game_state.json.tmp").exists()
    (tmp_path / "history").mkdir()
    (tmp_path / "history" / "12.json").write_text("{}")
    p.write_text('{"a": ')
    with pytest.raises(SystemExit) as err:
        state.load_state()
    assert "history/12.json" in str(err.value)


def test_cease_fire_clears_all_working_fields():
    """L225 (review H6): a stale _smoke_target must not survive a Cease Fire."""
    from fof import fire

    e = {"target": "31", "concentrated": True, "_smoke_target": "31", "_vof_blocked": "21", "_range_vof": "22"}
    fire.cease_fire(e)
    assert e == {"target": None}


def test_free_cover_respects_the_occupying_side(board):
    """L224: markers under units of the opposing side are not free."""
    from fof import state

    board["cards"]["22"]["cover"] = [
        {"id": "C1", "type": "Foxholes", "value": 1},
        {"id": "C2", "type": "Basic Cover", "value": 1},
    ]
    board["units"]["G"] = unit("22", side="Enemy", area="C1")
    assert [c["id"] for c in state.free_cover(board, "22", side="US")] == ["C2"]
    assert [c["id"] for c in state.free_cover(board, "22", side="Enemy")] == ["C1", "C2"]


def test_resupply_undoes_only_the_out_of_ammo_flip():
    """L228 (review H4): a Fire-Team flip caused by a HIT stays after picking up ammo."""
    from fof import combat

    s = {"cards": {"21": {"ammo": {"MG": 4}}}, "units": {}}
    hit = {
        "card": "21",
        "type": "Weapons Team",
        "steps": 1,
        "status": ["Fire Team side"],
        "fire_team_side": True,
        "ammo": {"type": "MG", "points": 0, "start": 6},
    }
    combat.ammo_pick_up(s, hit, "1/LMG", "MG:2", [])
    assert "Fire Team side" in hit["status"]
    ooa = dict(hit, status=["Fire Team side"], ooa_flip=True, ammo={"type": "MG", "points": 0, "start": 6})
    combat.ammo_pick_up(s, ooa, "2/LMG", "MG:2", [])
    assert "Fire Team side" not in ooa["status"]


def test_enemy_segments_follow_the_sequence_of_play():
    """L320 (review H2): defensive missions use 3.2.1/3.2.2 for the enemy segments, also in phase.py."""
    from fof import enemy

    assert enemy.enemy_segments({"type": "offensive"}) == ("3.4.1", "3.4.2")
    assert enemy.enemy_segments({"type": "defensive"}) == ("3.2.1", "3.2.2")


def test_list_option_bare_flag_is_a_violation():
    """L323: --with without a value is refused instead of crashing in str.split."""
    from fof import options, rules

    with pytest.raises(rules.Violation):
        options.list_option({"--with": True}, "--with")
    assert options.list_option({"--with": "a, b"}, "--with") == ["a", "b"]
