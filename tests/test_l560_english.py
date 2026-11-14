"""L560: the engine is English inside; German words of older games, setup files and command lines are aliases."""

import json

import pytest

from fof import cli, migrate, options, state


def test_german_command_line_becomes_english():
    n = cli.normalize_argv
    assert n(["befehl", "CO HQ", "1/1", "4.2.2a", "--ziel=22", "--bereich=offen"]) == [
        "order",
        "CO HQ",
        "1/1",
        "4.2.2a",
        "--target=22",
        "--area=open",
    ]
    assert n(["phase", "weiter"]) == ["phase", "next"]
    assert n(["fahrzeug", "bewegen", "T-34"]) == ["vehicle", "move", "T-34"]
    assert n(["ziel", "primaer", "34"]) == ["objective", "primary", "34"]
    assert n(["sicht", "tag"]) == ["visibility", "day"]
    assert n(["zurueck", "12", "--grund=Tippfehler"]) == ["undo", "12", "--reason=Tippfehler"]
    assert n(["aufstellen", "CO HQ", "12", "--netz=telefon"]) == ["setup", "CO HQ", "12", "--net=phone"]
    # free text keeps its words, also German ones
    assert n(["xp", "plus", "2", "ja", "weiter"]) == ["xp", "add", "2", "ja", "weiter"]
    assert n(["notiz", "ja", "nein"]) == ["note", "ja", "nein"]


def test_german_option_values_per_unit_and_edges():
    assert cli.normalize_argv(["befehl", "--erfolg=1/1:ja,2/1:nein"])[1] == "--success=1/1:yes,2/1:no"
    assert cli.normalize_argv(["terrain", "22", "Woods", "--raender=oben:weiss,links:gruen"])[-1] == (
        "--edges=top:white,left:green"
    )
    # in-process callers get the same translation from parse_opts
    assert options.parse_opts(["--erfolg=ja", "--netz=telefon", "--grund=ja"]) == {
        "--success": "yes",
        "--net": "phone",
        "--reason": "ja",  # free text
    }


def test_every_german_command_name_is_an_alias_of_a_command():
    assert all(en in cli.BY_NAME for en in migrate.COMMANDS_DE.values())
    assert not set(migrate.COMMANDS_DE) & set(cli.BY_NAME)
    assert cli.usage("zurueck") == cli.usage("undo")


def test_old_state_is_translated_names_untouched():
    old = {
        "zug": 1,
        "sicht": "tag",
        "einheiten": {"1/1": {"karte": "34", "seite": "Feind", "bereich": "offen", "status": ["Pinned"]}},
        "karten": {"34": {"reihe": 3, "spalte": 4, "raender": {"oben": "weiss"}}},
        "kommandos": {"1st PLT HQ": {"verfuegbar": 2, "gespart": 0, "fertig": False}},
        "protokoll": [{"nr": 1, "zug": 1, "regel": "4.2", "text": "ja"}],
    }
    new = migrate.state(old)
    assert new == {
        "turn": 1,
        "sight": "day",
        "units": {"1/1": {"card": "34", "side": "Enemy", "area": "open", "status": ["Pinned"]}},
        "cards": {"34": {"row": 3, "column": 4, "edges": {"top": "white"}}},
        "commands": {"1st PLT HQ": {"available": 2, "saved": 0, "done": False}},
        "protocol": [{"number": 1, "turn": 1, "rule": "4.2", "text": "yes"}],
    }
    assert migrate.state(new) == new  # an English state passes unchanged
    with pytest.raises(ValueError, match="German and English key"):
        migrate.state({"einheiten": {}, "zug": 1, "turn": 1})


def test_a_game_saved_before_l560_loads_and_saves_in_english(cli_game, fof_cli):
    cli_game()
    s = state.load_state()
    unique = {}
    for g, e in migrate.WORDS.items():
        unique.setdefault(e, []).append(g)
    inverse = {e: gs[0] for e, gs in unique.items() if len(gs) == 1}

    def to_german(o, names=False):
        if isinstance(o, dict):
            return {
                (k if names else inverse.get(k, k)): to_german(v, k in migrate.NAME_KEYED)
                if isinstance(v, dict)
                else to_german(v)
                for k, v in o.items()
            }
        if isinstance(o, list):
            return [to_german(v) for v in o]
        return inverse.get(o, o) if isinstance(o, str) else o

    old = to_german(s)
    assert "einheiten" in old and "units" not in old
    (state.game_dir() / "game_state.json").write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    assert state.load_state() == s
    code, _ = fof_cli("notiz", "nach dem Umbau")
    assert code == 0
    saved = json.loads((state.game_dir() / "game_state.json").read_text(encoding="utf-8"))
    assert "units" in saved and "einheiten" not in saved and saved["protocol"][-1]["text"].endswith("nach dem Umbau")


def test_rule_index_built_before_l560(tmp_path, monkeypatch, capsys):
    (tmp_path / "rule_index.json").write_text(
        json.dumps({"9.9": {"titel": "Test", "seite": 99, "zeile_txt": 1, "zeile_kompakt": 1}}), encoding="utf-8"
    )
    (tmp_path / "rulebook_compact.txt").write_text("9.9 Test\nline two\n", encoding="utf-8")
    (tmp_path / "clarifications_2025_05_compact.txt").write_text("", encoding="utf-8")
    monkeypatch.setattr(state, "DATA", tmp_path)
    cli.cmd_rule(["9.9"])
    assert "[RULE 9.9 p.99] Test" in capsys.readouterr().out
