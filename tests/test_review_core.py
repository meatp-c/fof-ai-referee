"""Review 23.10.2026, step 2a (setup, campaign, comms, cli, briefing, state, messages, rules, options): H10, H11, H12,
M5, M6, M38, LOW, efficiency and structure. CLI edge cases run in-process on a game created in tmp_path."""

import json
import pathlib

import pytest
from conftest import unit

from fof import briefing, campaign, cli, comms, history, messages, options, rules, setup, state

M1_SETUP = state.ROOT / "normandy" / "aufbau_normandy_m1.json"


@pytest.fixture
def cli_game(tmp_path, monkeypatch, capsys):
    """A fresh game from the M1 setup in tmp_path (FOF_PARTIE); run(argv) -> (exit code, output)."""
    if not M1_SETUP.exists():
        pytest.skip("mission setup normandy/aufbau_normandy_m1.json not available")
    game = tmp_path / "game"
    monkeypatch.setenv("FOF_PARTIE", str(game))

    def run(argv):
        try:
            cli.main(argv)
            code = 0
        except SystemExit as ex:
            code = ex.code if isinstance(ex.code, int) else 1
        return code, capsys.readouterr().out

    code, out = run(["new", str(M1_SETUP)])
    assert code == 0, out
    run.game = game
    return run


def saved(game):
    return json.loads((game / "spielstand.json").read_text(encoding="utf-8"))


# ---- H10: line


def test_h10_line_usage_is_one_text_and_names_the_unit():
    assert cli.usage("line") == cli.usage("leitung") == "line <card> ok|cut | line lay <card> <unit>"


@pytest.mark.parametrize("args", [["legen", "21"], ["legen"], ["21"]])
def test_h10_line_missing_arguments_are_violations(board, args):
    with pytest.raises(rules.Violation, match=r"Usage: line <card> ok\|cut \| line lay <card> <unit>"):
        comms.cmd_line(board, args)


def test_h10_line_wrong_result_word_names_the_usage(board):
    board["leitung_checks"] = {"21": "test"}
    with pytest.raises(rules.Violation, match="Usage: line"):
        comms.cmd_line(board, ["21", "maybe"])


# ---- H11: setup values and options


@pytest.fixture
def stub_save(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "save_state", lambda s, text=None, rule=None: calls.append(text))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)
    return calls


def test_h11_set_without_equals_and_bad_steps(board, stub_save):
    board["phase"] = "3.1"  # before turn 1: no --reason needed
    board["einheiten"]["1/1"] = unit("21")
    with pytest.raises(rules.Violation, match="field=value expected"):
        setup.cmd_values(board, ["1/1", "vof_rating", "A"])
    with pytest.raises(rules.Violation, match="whole number"):
        setup.cmd_values(board, ["1/1", "steps=x"])
    with pytest.raises(rules.Violation, match="at least 1 step"):
        setup.cmd_values(board, ["1/1", "steps=0"])
    with pytest.raises(rules.Violation, match="Usage: set"):
        setup.cmd_values(board, ["1/1"])
    setup.cmd_values(board, ["1/1", "steps=2", "vof_rating=A"])
    assert board["einheiten"]["1/1"]["steps"] == 2 and board["einheiten"]["1/1"]["vof_rating"] == "A"
    assert stub_save == ["1/1: steps = 2 (from the counter); 1/1: vof_rating = A (from the counter)"]


def test_h11_drop_phone_line_and_ammo_numbers(board, stub_save):
    board["einheiten"]["1/1"] = unit("21", leitungen=2)
    with pytest.raises(rules.Violation, match="whole number"):
        setup.cmd_drop(board, ["1/1", "Leitung:x"])
    with pytest.raises(rules.Violation, match="at least 1"):
        setup.cmd_drop(board, ["1/1", "Leitung:0"])
    with pytest.raises(rules.Violation, match="whole number"):
        setup.cmd_drop(board, ["1/1", "MG:x"])
    setup.cmd_drop(board, ["1/1", "Leitung:2"])
    assert board["einheiten"]["1/1"]["leitungen"] == 0 and board["karten"]["21"]["leitung_assets"] == 2


def test_h11_visibility_extend_illum_numbers(board, stub_save):
    with pytest.raises(rules.Violation, match="visibility <light>"):
        setup.cmd_visibility(board, ["x"])
    with pytest.raises(rules.Violation, match="weather"):
        setup.cmd_visibility(board, ["1", "y"])
    with pytest.raises(rules.Violation, match="extend <row>"):
        setup.cmd_extend(board, ["a", "b", "Woods"])
    with pytest.raises(rules.Violation, match="Usage: extend"):
        setup.cmd_extend(board, ["4", "2"])
    with pytest.raises(rules.Violation, match="illum <card> <top>"):
        setup.cmd_illum(board, ["21", "x"])
    with pytest.raises(rules.Violation, match="Usage: illum"):
        setup.cmd_illum(board, ["21"])
    assert stub_save == []


def test_h11_pyro_without_colon_and_bare_option_values(board):
    e = unit("21")
    with pytest.raises(rules.Violation, match="--pyro=<type>:<code>"):
        setup.setup_pyro(board, "1/1", e, {"--pyro": "RSP"}, [])
    with pytest.raises(rules.Violation, match="needs a value"):
        setup.setup_pyro(board, "1/1", e, {"--pyro": True}, [])
    prot = []
    setup.setup_pyro(board, "1/1", e, {"--pyro": "RSP:CF"}, prot)
    assert board["pyro_belegung"] == {"RSP": "CF"}
    board["co_tac_mittel"] = "telefon"
    with pytest.raises(rules.Violation, match="--lines"):
        setup.setup_lines(board, "1/1", e, {"--leitungen": "x"}, [])
    with pytest.raises(rules.Violation, match="value is missing"):
        setup.setup_lines(board, "1/1", e, {"--leitungen": True}, [])


def test_h11_edges_without_colour_is_a_violation():
    with pytest.raises(rules.Violation, match="--edges"):
        setup.parse_edges("oben")
    assert setup.parse_edges("oben:weiss")["oben"] == "weiss"


# ---- H12: missing arguments through the CLI and in the handlers


@pytest.mark.parametrize(
    "argv, usage",
    [
        (["setup"], "setup <unit>"),
        (["terrain", "21"], "terrain <card> <type>"),
        (["extend", "4", "2"], "extend <row> <column> <type>"),
        (["objective", "route"], "objective primary"),
        (["set", "1/1"], "set <unit>"),
        (["multistory"], "multistory <card>"),
        (["illum", "21"], "illum <card>"),
        (["note"], "note <text>"),
        (["undo"], "undo <entry no>"),
        (["line", "21"], "line <card>"),
        (["drop", "1/1"], "drop <unit>"),
        (["reconstitute", "--from=x"], "reconstitute <unit>"),
        (["rule"], "rule <no>"),
        (["search"], "search <term>"),
    ],
)
def test_h12_cli_minimum_arguments(cli_game, argv, usage):
    code, out = cli_game(argv)
    assert code == 2
    assert f"{messages.VIOLATION}: Usage: {usage}" in out


@pytest.mark.parametrize(
    "argv, text",
    [
        (["radio", "check"], "Usage: radio"),
        (["radio", "damage", "21"], "Usage: radio"),
        (["radio", "nonsense"], "Usage: radio"),
        (["objective", "route", "1"], "objective route <1-4>"),
        (["objective", "phaseline", "1"], "objective phaseline <n> <row>"),
        (["objective", "phaseline", "1", "x"], "whole number"),
        (["objective", "concentration", "21"], "objective concentration"),
        (["objective", "nonsense", "21"], "Usage: objective"),
        (["xp", "add"], "Usage: xp"),
        (["xp", "add", "x"], "whole number"),
        (["xp", "skill", "CO HQ"], "Usage: xp"),
        (["xp", "promote"], "Usage: xp"),
        (["patrol", "start"], "Not a Combat Patrol mission"),
        (["reattempt", "now"], "Usage: reattempt"),
        (["set", "CO HQ", "steps"], "field=value expected"),
        (["setup", "CO HQ", "--platoon"], "needs a value"),
        (["terrain", "21", "Woods", "--hill"], "value is missing"),
    ],
)
def test_h12_cli_handler_arguments(cli_game, argv, text):
    before = (cli_game.game / "spielstand.json").read_text(encoding="utf-8")
    code, out = cli_game(argv)
    assert code == 2 and text in out, out
    assert "Traceback" not in out
    assert (cli_game.game / "spielstand.json").read_text(encoding="utf-8") == before  # nothing saved


def test_h12_xp_promote_and_skill_numbers(board):
    board["kampagne"] = {}
    board["missionsende"] = True
    board["einheiten"]["1/1"] = unit("21")
    board["einheiten"]["CO HQ"] = unit("21", typ="HQ")
    with pytest.raises(rules.Violation, match="whole number"):
        campaign.cmd_xp(board, ["promote", "1/1", "--from=Green", "--steps=x"])
    with pytest.raises(rules.Violation, match="at least one step"):
        campaign.cmd_xp(board, ["promote", "1/1", "--from=Green", "--steps=0"])
    skill = next(iter(rules.SKILL_COST))
    with pytest.raises(rules.Violation, match="whole number"):
        campaign.cmd_xp(board, ["skill", "CO HQ", skill, "--cost=x"])


def test_h12_rule_lookup_without_compact_line_and_empty_search(tmp_path, monkeypatch):
    (tmp_path / "regelindex.json").write_text(
        json.dumps({"9.9": {"titel": "Test", "seite": 99, "zeile_kompakt": None}}), encoding="utf-8"
    )
    (tmp_path / "regelbuch_kompakt.txt").write_text("line one\n", encoding="utf-8")
    monkeypatch.setattr(state, "DATA", tmp_path)
    with pytest.raises(rules.Violation, match="no line in the compact rule text"):
        cli.cmd_rule(["9.9"])
    with pytest.raises(rules.Violation, match="Usage: search"):
        cli.cmd_search(["  "])


# ---- M5: new does not overwrite a game


def test_m5_new_refuses_an_existing_game_unless_force(cli_game):
    game = cli_game.game
    (game / "marker.txt").write_text("x", encoding="utf-8")
    code, out = cli_game(["note", "first entry"])
    assert code == 0
    entries = len(saved(game)["protokoll"])
    code, out = cli_game(["new", str(M1_SETUP)])
    assert code == 2 and "already holds a game" in out and "--force" in out
    assert len(saved(game)["protokoll"]) == entries
    code, out = cli_game(["new", str(M1_SETUP), "--force"])
    assert code == 0, out
    assert len(saved(game)["protokoll"]) == 1


def test_m5_helpers(tmp_path, board):
    folder = tmp_path / "g"
    assert state.check_new_game_folder(str(folder)) == folder  # absolute path: ROOT / abs is abs
    folder.mkdir()
    (folder / "spielstand.json").write_text("{}", encoding="utf-8")
    with pytest.raises(rules.Violation, match="already holds a game"):
        state.check_new_game_folder(str(folder))
    assert state.check_new_game_folder(str(folder), force=True) == folder
    board["optionen"] = {"U99_nonsense": True}
    with pytest.raises(rules.Violation, match="Unknown options in setup: U99_nonsense"):
        setup.check_new_game(board)
    board["optionen"] = {}
    board["einheiten"]["1/1"] = unit("99")
    with pytest.raises(rules.Violation, match="unknown card 99"):
        setup.check_new_game(board)


# ---- M6: patrol next checks platoon and --with before the reset is saved


def patrol_board(board):
    board["kampagne"] = {"versuch": 1}
    board["patrouille_mission"] = True
    board["missionsende"] = True
    board["patrouille"] = {"platoon": "1", "erledigt": ["1"]}
    board["einheiten"]["1st PLT HQ"] = unit("11", typ="HQ", ebene="PLT", platoon="1")
    board["einheiten"]["2nd PLT HQ"] = unit("11", typ="HQ", ebene="PLT", platoon="2")
    board["einheiten"]["1/2"] = unit("11", platoon="2")
    board["einheiten"]["1/1"] = unit("11", platoon="1")
    return board


@pytest.mark.parametrize(
    "args, text",
    [
        (["naechste", "7"], "Platoon 7 unknown"),
        (["naechste", "2", "--mit=Nobody"], "Unit 'Nobody' unknown"),
        (["naechste", "2", "--mit=1/1"], "only Weapons Teams"),
        (["naechste", "2", "--mit"], "needs a value"),
        (["naechste"], "Usage: patrol"),
    ],
)
def test_m6_patrol_next_checks_before_saving(board, stub_save, args, text):
    s = patrol_board(board)
    with pytest.raises(rules.Violation, match=text):
        campaign.cmd_patrol(s, args)
    assert stub_save == []  # the reattempt reset was not saved
    assert "patrouille_wechsel" not in s and s["kampagne"]["versuch"] == 1


def test_m6_platoon_hq_in_the_patrol_reserve_counts(board):
    s = patrol_board(board)
    s["patrouille_reserve"] = {"3rd PLT HQ": {"einheit": unit(None, typ="HQ", ebene="PLT", platoon="3")}}
    s["einheiten"]["BN HQ"] = unit("11", typ="HQ", ebene="BN")
    units = campaign.units_after_reattempt(s)
    assert "3rd PLT HQ" in units and "BN HQ" not in units
    campaign.check_patrol_choice(units, "3", [])
    with pytest.raises(rules.Violation, match="BN HQ"):
        campaign.check_patrol_choice(units, "3", ["BN HQ"])


# ---- M38: unknown vehicle type or AT weapon fails the consistency check


def test_m38_unknown_vehicle_type_is_a_consistency_error(board):
    board["einheiten"]["Tank"] = unit("21", typ="Vehicle", fahrzeug="M4 Sherman")
    board["einheiten"]["Gun"] = unit("31", side="Feind", typ="AT Gun", at_waffe="77mm")
    errors = briefing.consistency_check(board)
    assert any(x.startswith("Tank: Unknown vehicle type 'M4 Sherman'") and "M4 Sherman 75mm" in x for x in errors)
    assert any(x.startswith("Gun: Unknown AT weapon '77mm'") and "75mm AT Gun" in x for x in errors)
    board["einheiten"]["Tank"]["fahrzeug"] = "M4 Sherman 75mm"
    board["einheiten"]["Gun"]["at_waffe"] = "75mm AT Gun"
    assert briefing.vehicle_type_errors(board) == []


# ---- LOW


def test_low_card_id_columns_from_ten():
    assert state.card_id(2, 3) == "23"
    assert state.card_id(2, 10) == "210"
    assert state.card_id(2, -1) == "2m1"


def test_low_messages_board_removed_and_gi_exceptions_consistent():
    assert not hasattr(messages, "board")
    assert rules.HQ_REQUIRED_UNDER_GI <= set(rules.ACTIONS)
    assert "4.2.4m" in rules.HQ_REQUIRED_UNDER_GI_NOT_IMPLEMENTED and "4.2.4m" not in rules.ACTIONS


def test_low_marker_summary_friendly_point_blank_upper_right(board):
    board["einheiten"]["1/1"] = unit("22", ziel="22")
    board["einheiten"]["G1"] = unit("22", side="Feind", ziel="22")
    board["einheiten"]["G1"]["vof_rating"] = "H"
    out = state.marker_summary(board)["22"]
    top, cf, friendly_pb, enemy_pb = out
    assert top is None and not cf
    assert friendly_pb is not None and enemy_pb is not None
    assert friendly_pb[1] > enemy_pb[1]  # the German H (-3) is the enemy (lower left) marker, the US S/A the other


# ---- options


def test_options_text_opt_and_int_opt_bare_flags():
    assert options.text_opt({}, "--ziel") is None
    assert options.text_opt({}, "--ziel", default="x") == "x"
    assert options.text_opt({"--ziel": "21"}, "--ziel") == "21"
    with pytest.raises(rules.Violation, match="--ziel needs a value: fire <unit>"):
        options.text_opt({"--ziel": True}, "--ziel", "fire <unit> --target=..")
    with pytest.raises(rules.Violation, match="value is missing"):
        options.int_opt({"--wert": True}, "--wert", "cover value", 1)
    assert options.parse_opts(["--force"]) == {"--force": True}


# ---- efficiency: one read, one parse-free bookkeeping, one consistency check per save


def test_save_state_uses_the_loaded_text_and_checks_once(cli_game, monkeypatch):
    game = cli_game.game
    s = state.load_state()
    calls = []
    real_check = briefing.consistency_check
    monkeypatch.setattr(briefing, "consistency_check", lambda st: calls.append(1) or real_check(st))
    real_read = pathlib.Path.read_text

    def no_state_read(self, *a, **k):
        assert self.name != "spielstand.json", "spielstand.json read again by save_state"
        return real_read(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "read_text", no_state_read)
    state.save_state(s, "cached", None)
    assert calls == [1]
    monkeypatch.setattr(pathlib.Path, "read_text", real_read)
    assert saved(game)["protokoll"][-1]["text"] == "cached"
    # changed on disk behind our back: the old file is read again, as before
    on_disk = saved(game)
    on_disk["phase"] = "3.7.4"
    (game / "spielstand.json").write_text(json.dumps(on_disk) + "\n\n", encoding="utf-8")
    phase, entries, loader = state._disk_before_save(game / "spielstand.json")
    assert phase == "3.7.4" and entries == len(on_disk["protokoll"]) and loader()["phase"] == "3.7.4"


# ---- structure: undo lives in history.py


def test_undo_moved_to_history_and_still_works(cli_game):
    assert cli.BY_GERMAN["zurueck"][2] == "history.cmd_undo"
    assert state.cmd_undo.__doc__.startswith("Moved to history.cmd_undo")
    for i in range(3):
        assert cli_game(["note", f"n{i}"])[0] == 0
    entries = len(saved(cli_game.game)["protokoll"])
    code, out = cli_game(["undo", "2", "--reason=test"])
    assert code == 0, out
    s = saved(cli_game.game)
    assert len(s["protokoll"]) == 3 and s["protokoll"][-1]["text"].startswith("Undo to entry 2 (test)")
    assert entries == 4
    with pytest.raises(rules.Violation, match="undo <entry no>"):
        history.cmd_undo(s, ["x"])
    with pytest.raises(rules.Violation, match="--grund needs a value"):
        history.cmd_undo(s, ["1", "--reason"])
