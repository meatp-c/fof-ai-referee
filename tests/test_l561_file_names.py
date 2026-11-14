"""L561: English file, folder and variable names; games and rule texts of earlier releases are read and renamed."""

import importlib.util
import json
import pathlib

from fof import cli, state

STEP = importlib.util.spec_from_file_location("step", pathlib.Path(__file__).resolve().parents[1] / "tool" / "step.py")
step = importlib.util.module_from_spec(STEP)
STEP.loader.exec_module(step)


def test_game_folder_of_an_earlier_release_is_adopted(cli_game, fof_cli, monkeypatch):
    game = cli_game()
    (game / "game_state.json").rename(game / "spielstand.json")
    (game / "history").rename(game / "verlauf")
    monkeypatch.delenv("FOF_GAME")
    monkeypatch.setenv("FOF_PARTIE", str(game))  # the environment variable of earlier releases
    code, out = fof_cli("note", "after the rename")
    assert code == 0, out
    assert (game / "game_state.json").exists() and not (game / "spielstand.json").exists()
    assert (game / "history").is_dir() and not (game / "verlauf").exists()
    s = json.loads((game / "game_state.json").read_text(encoding="utf-8"))
    assert s["protocol"][-1]["text"].endswith("after the rename")
    assert (game / "history" / f"{len(s['protocol'])}.json").exists()


def test_pointer_file_of_an_earlier_release(tmp_path, monkeypatch):
    monkeypatch.delenv("FOF_GAME")
    monkeypatch.setattr(state, "ROOT", tmp_path)
    (tmp_path / ".aktuelle_partie").write_text("old_game", encoding="utf-8")
    assert state.game_dir() == tmp_path / "old_game"
    (tmp_path / ".current_game").write_text("new_game", encoding="utf-8")
    assert state.game_dir() == tmp_path / "new_game"
    (tmp_path / ".current_game").unlink()
    (tmp_path / ".aktuelle_partie").unlink()
    assert state.game_dir() == tmp_path / "game1"


def test_rule_texts_of_an_earlier_release(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(state, "DATA", tmp_path)
    (tmp_path / "regelindex.json").write_text(
        json.dumps({"9.9": {"titel": "Test", "seite": 9, "zeile_txt": 1, "zeile_kompakt": 1}}), encoding="utf-8"
    )
    (tmp_path / "regelbuch_kompakt.txt").write_text("9.9 Test\nsecond line\n", encoding="utf-8")
    (tmp_path / "clarifications_2025_05_kompakt.txt").write_text("", encoding="utf-8")
    (tmp_path / "campaign_x_kompakt.txt").write_text("old searchable text\n", encoding="utf-8")
    (tmp_path / "campaign_y_compact.txt").write_text("new searchable text\n", encoding="utf-8")
    assert state.data_file("rule_index.json") == tmp_path / "regelindex.json"
    cli.cmd_rule(["9.9"])
    assert "[RULE 9.9 p.9] Test" in capsys.readouterr().out
    cli.cmd_search(["searchable"])
    out = capsys.readouterr().out
    assert "campaign_x_kompakt.txt" in out and "campaign_y_compact.txt" in out
    (tmp_path / "rule_index.json").write_text("{}", encoding="utf-8")
    assert state.data_file("rule_index.json") == tmp_path / "rule_index.json"  # the new name wins


def test_step_accepts_the_option_name_of_earlier_releases():
    assert step.parse_args(["--partie", "game7"])["game"] == "game7"
    assert step.parse_args(["--game", "game8", "--probe"])["game"] == "game8"


def test_terrain_on_a_hill_written_before_l561():
    from fof import migrate

    old = {"karten": {"34": {"terrain": "Woods auf 1 Hill"}}, "einheiten": {}}
    assert migrate.state(old)["cards"]["34"]["terrain"] == "Woods on 1 Hill"
