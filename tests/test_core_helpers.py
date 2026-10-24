"""Core helpers without game data (review 23.10.2026, Tests und Tooling): save/snapshot/undo, option parsing, the
English command line, phone net, multi-step experience (12.6), LOS asymmetry with Smoke (5.4)."""

import json

import pytest
from conftest import unit
from fof import campaign, cli, comms, geometry, options, rules, state


# ---- state.save_state / save_snapshot / cmd_undo


@pytest.fixture
def saving(board, isolated_game_dir, monkeypatch):
    """The synthetic board saved for real into the test folder (autouse FOF_PARTIE); marker notes start empty."""
    monkeypatch.setattr(state, "MARKER_NOTES", [])
    board.update(mission="synthetic", max_zuege=10)  # the briefing after each save needs these
    return board, isolated_game_dir


def snapshot(folder, n):
    return json.loads((folder / state.HISTORY_DIR / f"{n}.json").read_text(encoding="utf-8"))


def test_save_state_numbers_entries_and_keeps_a_snapshot_per_entry(saving):
    s, folder = saving
    for i in range(3):
        state.save_state(s, f"entry {i + 1}")
    assert [p["nr"] for p in s["protokoll"]] == [1, 2, 3]
    assert json.loads((folder / "spielstand.json").read_text(encoding="utf-8"))["protokoll"][-1]["text"] == "entry 3"
    assert [len(snapshot(folder, n)["protokoll"]) for n in (1, 2, 3)] == [1, 2, 3]
    assert not (folder / "spielstand.json.tmp").exists()


def test_save_snapshot_prunes_beyond_history_keep(isolated_game_dir, monkeypatch):
    monkeypatch.setattr(state, "HISTORY_KEEP", 3)
    for n in range(1, 7):
        state.save_snapshot(n, "{}")
    kept = sorted(int(f.stem) for f in (isolated_game_dir / state.HISTORY_DIR).glob("*.json"))
    assert kept == [3, 4, 5, 6]  # entry 6 and the HISTORY_KEEP entries before it


def test_undo_restores_the_snapshot_and_numbers_on(saving, capsys):
    s, folder = saving
    for i in range(4):
        s["zug"] = i + 1
        state.save_state(s, f"entry {i + 1}")
    capsys.readouterr()
    state.cmd_undo(s, ["2", "--reason=test"])
    out = capsys.readouterr().out
    assert "- 3 T3" in out and "- 4 T4" in out and "- 2 T2" not in out
    after = json.loads((folder / "spielstand.json").read_text(encoding="utf-8"))
    assert after["zug"] == 2 and [p["nr"] for p in after["protokoll"]] == [1, 2, 3]
    undo = after["protokoll"][-1]["text"]
    assert undo.startswith("Undo to entry 2 (test); discarded: 3 entry 3; 4 entry 4")
    assert len(snapshot(folder, 3)["protokoll"]) == 3  # the undo entry replaced the old snapshot 3
    state.save_state(after, "entry after undo")
    assert after["protokoll"][-1]["nr"] == 4


@pytest.mark.parametrize(
    "args, match",
    [([], "undo <entry no>"), (["x"], "undo <entry no>"), (["3"], "not before the last"), (["0"], "not before")],
)
def test_undo_refuses_bad_entry_numbers(saving, args, match):
    s, _ = saving
    for i in range(3):
        state.save_state(s, f"entry {i + 1}")
    with pytest.raises(rules.Violation, match=match):
        state.cmd_undo(s, args)


def test_undo_without_snapshot_is_a_violation(saving):
    s, folder = saving
    for i in range(3):
        state.save_state(s, f"entry {i + 1}")
    (folder / state.HISTORY_DIR / "1.json").unlink()
    with pytest.raises(rules.Violation, match="No snapshot for entry 1"):
        state.cmd_undo(s, ["1"])


def test_combat_effects_freeze_marker_notes_until_clean_up(saving):
    """L119 [RULE 3.7.4]: no marker notes during 3.7.4; leaving it compares with the state before 3.7.4 (_ce_start)."""
    s, _ = saving
    s["phase"] = "3.7.3"
    state.save_state(s, "before")
    s["einheiten"]["1/1"] = unit("11", ziel="13")
    state.save_state(s, "1/1 fires at 13")
    assert any(x.startswith("13: VOF marker") for x in state.MARKER_NOTES)
    state.MARKER_NOTES.clear()
    s["phase"] = "3.7.4"
    state.save_state(s, "enter 3.7.4")
    assert s["_ce_start"] == 2  # last entry before 3.7.4
    s["einheiten"]["1/1"]["ziel"] = None
    state.save_state(s, "1/1 ceases fire during 3.7.4")
    assert state.MARKER_NOTES == [] and s["_ce_start"] == 2
    s["phase"] = "3.8"
    state.save_state(s, "Clean Up")
    assert "_ce_start" not in s
    # base is snapshot 2 (VOF on 13), not the last 3.7.4 state (no VOF): the marker must be removed now
    assert any(x.startswith("13: remove the VOF marker") for x in state.MARKER_NOTES)


# ---- options.parse_opts


def test_parse_opts_bare_flag_equals_in_value_and_positionals():
    assert options.parse_opts(["3/AT", "--short", "--grund=a=b c"]) == {"--short": True, "--grund": "a=b c"}


@pytest.mark.parametrize(
    "args, match",
    [
        (["--ziel=12", "--ziel=13"], "given twice"),
        (["--target=12", "--ziel=13"], "given twice"),  # alias and German key are the same option
        (["--ziel="], "empty value"),
        (["--nonsense=1"], "Unknown option"),
    ],
)
def test_parse_opts_refuses(args, match):
    with pytest.raises(rules.Violation, match=match):
        options.parse_opts(args)


def test_move_target_marker_does_not_overwrite_the_target():
    """H7: --move-target-marker has its own key; aliases applied twice (CLI, then parse_opts) stay idempotent."""
    argv = ["order", "1st PLT HQ", "1/1", "4.2.2a", "--target=13", "--move-target-marker=no"]
    german = cli.argv_to_german(argv)
    assert options.parse_opts(german[1:]) == {"--ziel": "13", "--target_marker": "nein"}
    assert options.parse_opts(argv[1:]) == {"--ziel": "13", "--target_marker": "no"}


# ---- cli.argv_to_german


def test_argv_to_german_value_aliases_only_for_enumerated_options():
    out = cli.argv_to_german(["order", "3rd PLT HQ", "yes", "--success=yes", "--reason=no", "--what=open"])
    assert out == ["befehl", "3rd PLT HQ", "yes", "--erfolg=ja", "--grund=no", "--was=open"]


def test_argv_to_german_per_unit_lists_and_edges():
    assert cli.argv_to_german(["order", "--success=1/1:no,2/1:yes"])[1] == "--erfolg=1/1:nein,2/1:ja"
    assert cli.argv_to_german(["order", "--edges=white"])[1] == "--raender=weiss"
    assert cli.argv_to_german(["phase", "next"]) == ["phase", "weiter"]


def test_argv_to_german_passes_german_input_unchanged():
    argv = ["befehl", "3rd PLT HQ", "3/AT", "4.2.4d", "--ziel=62", "--erfolg=nein"]
    assert cli.argv_to_german(argv) == argv
    assert cli.argv_to_german([]) == []


# ---- comms.phone_net_connected


def line(board, *cards, cut=False):
    for k in cards:
        board["karten"][k]["leitungen"] = [{"cut": cut}]


def test_phone_net_orthogonal_line(board):
    line(board, "11", "12", "13")
    assert comms.phone_net_connected(board, "11", "13") is True
    board["karten"]["12"]["leitungen"][0]["cut"] = True
    assert comms.phone_net_connected(board, "11", "13") is False


def test_phone_net_diagonal_only_with_open_question_u14(board):
    line(board, "11", "22")
    assert comms.phone_net_connected(board, "11", "22") == "diagonal"  # U14 default: diagonal counts
    board["optionen"]["U14_telefon_diagonal"] = False
    assert comms.phone_net_connected(board, "11", "22") is False


def test_phone_net_staging_cards_are_integrated(board):
    board["karten"]["31"]["staging"] = True
    board["karten"]["33"]["staging"] = True
    assert comms.phone_net_connected(board, "31", "33") is True
    assert comms.phone_net_connected(board, "31", "11") is False  # 11 has no line


# ---- campaign.experience_from_steps (table 12.6 as read in the function's docstring, L152)


@pytest.mark.parametrize(
    "steps, expected",
    [
        ("VV", "Veteran"),
        ("VL", "Line"),
        ("VG", "Line"),
        ("LG", "Green"),
        ("VVG", "Line"),
        ("VVL", "Veteran"),
        ("LLV", "Line"),
        ("LLG", "Line"),
        ("GGV", "Line"),
        ("GGL", "Green"),
        ("VLG", "Line"),
        ("VVVG", "Veteran"),
        ("VVLG", "Line"),
        ("VVGG", "Line"),
        ("LLLG", "Line"),
        ("LLVG", "Line"),
        ("LLGG", "Green"),
        ("GGGV", "Green"),
        ("VLGG", None),
        ("VLGGL", None),
    ],
)
def test_experience_from_steps_table_12_6(steps, expected):
    name = {"V": "Veteran", "L": "Line", "G": "Green"}
    assert campaign.experience_from_steps([name[c] for c in steps]) == expected
    assert campaign.experience_from_steps([name[c] for c in reversed(steps)]) == expected  # order does not matter


def test_experience_from_steps_unknown_or_empty():
    assert campaign.experience_from_steps([]) is None
    assert campaign.experience_from_steps(["Line", "Elite"]) is None


# ---- geometry.los: Smoke/Incoming on the target vs on the firing card [RULE 5.4: 'LOS is not reciprocal']


@pytest.mark.parametrize("marker", ["Smoke", "Incoming"])
def test_los_into_a_blocked_card_but_not_out(board, marker):
    board["karten"]["12"]["extern"].append({"typ": marker, "wert": -2, "quelle": "test"})
    assert geometry.los(board, "11", "12")[0]  # marker on the target card: LOS into it
    ok, reason = geometry.los(board, "12", "11")  # marker on the firing card: no LOS out
    assert not ok and "no LOS out" in reason


def test_radio_los_ignores_smoke_but_not_incoming_by_default(board):
    """[RULE 4.3.5] SCR536 'ignoring smoke'; Incoming blocks radio LOS under the open question U3 (default)."""
    board["karten"]["12"]["extern"].append({"typ": "Smoke", "wert": -2, "quelle": "test"})
    assert geometry.los(board, "12", "11", radio=True)[0]
    board["karten"]["12"]["extern"] = [{"typ": "Incoming", "wert": -3, "quelle": "test"}]
    assert geometry.los(board, "12", "11", radio=True)[0] is not rules.DEFAULT_OPTIONS["U3_incoming_blockiert_funk"][0]
