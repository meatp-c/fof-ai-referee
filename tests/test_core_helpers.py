"""Core helpers without game data (review 23.10.2026, tests and tooling): save/snapshot/undo, option parsing, the
English command line, phone net, multi-step experience (12.6), LOS asymmetry with Smoke (5.4)."""

import json

import pytest
from conftest import unit
from fof import campaign, cli, comms, geometry, options, rules, state


# ---- state.save_state / save_snapshot / cmd_undo


@pytest.fixture
def saving(board, isolated_game_dir, monkeypatch):
    """The synthetic board saved for real into the test folder (autouse FOF_GAME); marker notes start empty."""
    monkeypatch.setattr(state, "MARKER_NOTES", [])
    board.update(mission="synthetic", max_turns=10)  # the briefing after each save needs these
    return board, isolated_game_dir


def snapshot(folder, n):
    return json.loads((folder / state.HISTORY_DIR / f"{n}.json").read_text(encoding="utf-8"))


def test_save_state_numbers_entries_and_keeps_a_snapshot_per_entry(saving):
    s, folder = saving
    for i in range(3):
        state.save_state(s, f"entry {i + 1}")
    assert [p["number"] for p in s["protocol"]] == [1, 2, 3]
    assert json.loads((folder / "game_state.json").read_text(encoding="utf-8"))["protocol"][-1]["text"] == "entry 3"
    assert [snapshot(folder, n)["protocol_entries"] for n in (1, 2, 3)] == [1, 2, 3]
    assert all("protocol" not in snapshot(folder, n) for n in (1, 2, 3))  # the protocol is not copied per entry
    assert not (folder / "game_state.json.tmp").exists()


def test_save_snapshot_prunes_beyond_history_keep(isolated_game_dir, monkeypatch):
    monkeypatch.setattr(state, "HISTORY_KEEP", 3)
    for n in range(1, 7):
        state.save_snapshot(n, "{}")
    kept = sorted(int(f.stem) for f in (isolated_game_dir / state.HISTORY_DIR).glob("*.json"))
    assert kept == [3, 4, 5, 6]  # entry 6 and the HISTORY_KEEP entries before it


def test_undo_restores_the_snapshot_and_numbers_on(saving, capsys):
    s, folder = saving
    for i in range(4):
        s["turn"] = i + 1
        state.save_state(s, f"entry {i + 1}")
    capsys.readouterr()
    state.cmd_undo(s, ["2", "--reason=test"])
    out = capsys.readouterr().out
    assert "- 3 T3" in out and "- 4 T4" in out and "- 2 T2" not in out
    after = json.loads((folder / "game_state.json").read_text(encoding="utf-8"))
    assert after["turn"] == 2 and [p["number"] for p in after["protocol"]] == [1, 2, 3]
    undo = after["protocol"][-1]["text"]
    assert undo.startswith("Undo to entry 2 (test); discarded: 3 entry 3; 4 entry 4")
    assert snapshot(folder, 3)["protocol_entries"] == 3  # the undo entry replaced the old snapshot 3
    state.save_state(after, "entry after undo")
    assert after["protocol"][-1]["number"] == 4


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
    s["units"]["1/1"] = unit("11", target="13")
    state.save_state(s, "1/1 fires at 13")
    assert any(x.startswith("13: VOF marker") for x in state.MARKER_NOTES)
    state.MARKER_NOTES.clear()
    s["phase"] = "3.7.4"
    state.save_state(s, "enter 3.7.4")
    assert s["_ce_start"] == 2  # last entry before 3.7.4
    s["units"]["1/1"]["target"] = None
    state.save_state(s, "1/1 ceases fire during 3.7.4")
    assert state.MARKER_NOTES == [] and s["_ce_start"] == 2
    s["phase"] = "3.8"
    state.save_state(s, "Clean Up")
    assert "_ce_start" not in s
    # base is snapshot 2 (VOF on 13), not the last 3.7.4 state (no VOF): the marker must be removed now
    assert any(x.startswith("13: remove the VOF marker") for x in state.MARKER_NOTES)


# ---- options.parse_opts


def test_parse_opts_bare_flag_equals_in_value_and_positionals():
    assert options.parse_opts(["3/AT", "--short", "--reason=a=b c"]) == {"--short": True, "--reason": "a=b c"}


@pytest.mark.parametrize(
    "args, match",
    [
        (["--target=12", "--target=13"], "given twice"),
        (["--target=12", "--target=13"], "given twice"),  # alias and German key are the same option
        (["--target="], "empty value"),
        (["--nonsense=1"], "Unknown option"),
    ],
)
def test_parse_opts_refuses(args, match):
    with pytest.raises(rules.Violation, match=match):
        options.parse_opts(args)


def test_move_target_marker_does_not_overwrite_the_target():
    """H7: --move-target-marker has its own key; aliases applied twice (CLI, then parse_opts) stay idempotent."""
    argv = ["order", "1st PLT HQ", "1/1", "4.2.2a", "--target=13", "--move-target-marker=no"]
    german = cli.normalize_argv(argv)
    assert options.parse_opts(german[1:]) == {"--target": "13", "--move-target-marker": "no"}
    assert options.parse_opts(argv[1:]) == {"--target": "13", "--move-target-marker": "no"}


# ---- cli.normalize_argv


def test_normalize_argv_value_aliases_only_for_enumerated_options():
    out = cli.normalize_argv(["order", "3rd PLT HQ", "yes", "--success=yes", "--reason=no", "--what=open"])
    assert out == ["order", "3rd PLT HQ", "yes", "--success=yes", "--reason=no", "--what=open"]


def test_normalize_argv_per_unit_lists_and_edges():
    assert cli.normalize_argv(["order", "--success=1/1:no,2/1:yes"])[1] == "--success=1/1:no,2/1:yes"
    assert cli.normalize_argv(["order", "--edges=white"])[1] == "--edges=white"
    assert cli.normalize_argv(["phase", "next"]) == ["phase", "next"]


def test_normalize_argv_passes_german_input_unchanged():
    argv = ["order", "3rd PLT HQ", "3/AT", "4.2.4d", "--target=62", "--success=no"]
    assert cli.normalize_argv(argv) == argv
    assert cli.normalize_argv([]) == []


# ---- comms.phone_net_connected


def line(board, *cards, cut=False):
    for k in cards:
        board["cards"][k]["lines"] = [{"cut": cut}]


def test_phone_net_orthogonal_line(board):
    line(board, "11", "12", "13")
    assert comms.phone_net_connected(board, "11", "13") is True
    board["cards"]["12"]["lines"][0]["cut"] = True
    assert comms.phone_net_connected(board, "11", "13") is False


def test_phone_net_diagonal_only_with_open_question_u14(board):
    line(board, "11", "22")
    assert comms.phone_net_connected(board, "11", "22") == "diagonal"  # U14 default: diagonal counts
    board["options"]["U14_phone_diagonal"] = False
    assert comms.phone_net_connected(board, "11", "22") is False


def test_phone_net_staging_cards_are_integrated(board):
    board["cards"]["31"]["staging"] = True
    board["cards"]["33"]["staging"] = True
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
    board["cards"]["12"]["external"].append({"type": marker, "value": -2, "source": "test"})
    assert geometry.los(board, "11", "12")[0]  # marker on the target card: LOS into it
    ok, reason = geometry.los(board, "12", "11")  # marker on the firing card: no LOS out
    assert not ok and "no LOS out" in reason


def test_radio_los_ignores_smoke_but_not_incoming_by_default(board):
    """[RULE 4.3.5] SCR536 'ignoring smoke'; Incoming blocks radio LOS under the open question U3 (default)."""
    board["cards"]["12"]["external"].append({"type": "Smoke", "value": -2, "source": "test"})
    assert geometry.los(board, "12", "11", radio=True)[0]
    board["cards"]["12"]["external"] = [{"type": "Incoming", "value": -3, "source": "test"}]
    assert geometry.los(board, "12", "11", radio=True)[0] is not rules.DEFAULT_OPTIONS["U3_incoming_blocks_radio"][0]


def test_undo_reads_a_snapshot_that_still_holds_its_protocol(saving, capsys):
    """Snapshots of earlier releases carry the whole protocol; they stay usable."""
    s, folder = saving
    for i in range(3):
        s["turn"] = i + 1
        state.save_state(s, f"entry {i + 1}")
    old = json.loads((folder / "game_state.json").read_text(encoding="utf-8"))
    old["turn"], old["protocol"] = 2, old["protocol"][:2]
    (folder / state.HISTORY_DIR / "2.json").write_text(json.dumps(old), encoding="utf-8")
    state.cmd_undo(s, ["2"])
    after = json.loads((folder / "game_state.json").read_text(encoding="utf-8"))
    assert after["turn"] == 2 and [p["number"] for p in after["protocol"]] == [1, 2, 3]
    assert "protocol_entries" not in after
