import pytest

from fof import cli, commands, messages, options, rules


def hq(board, name, available, saved=0):
    board["kommandos"][name] = {"verfuegbar": available, "gespart": saved, "aktiviert": True, "fertig": False}


def test_pay_commands_uses_available_before_saved(board):
    hq(board, "CO HQ", 2, 4)
    commands.pay_commands(board, "CO HQ", 3, "test")
    assert board["kommandos"]["CO HQ"]["verfuegbar"] == 0
    assert board["kommandos"]["CO HQ"]["gespart"] == 3
    assert board["impuls_ausgegeben"]["CO HQ"] == 3


def test_six_commands_per_impulse_by_day(board):
    hq(board, "CO HQ", 9)
    commands.pay_commands(board, "CO HQ", 6, "test")
    with pytest.raises(rules.Violation, match="4.1.3"):
        commands.pay_commands(board, "CO HQ", 1, "test")


def test_not_enough_commands(board):
    hq(board, "CO HQ", 1)
    with pytest.raises(rules.Violation):
        commands.pay_commands(board, "CO HQ", 2, "test")


def test_english_command_line_maps_to_the_engine_words():
    assert cli.argv_to_german(["order", "CO HQ", "1/1", "4.2.2a", "--target=22", "--area=open"]) == [
        "befehl",
        "CO HQ",
        "1/1",
        "4.2.2a",
        "--ziel=22",
        "--bereich=offen",
    ]
    assert cli.argv_to_german(["event", "?", "no"]) == ["ereignis", "?", "nein"]
    assert cli.argv_to_german(["befehl", "x"]) == ["befehl", "x"]  # German passes unchanged


def test_every_command_has_usage_and_description():
    for en, de, handler, usage, desc in cli.COMMANDS:
        assert usage.startswith(en), en
        assert desc
        if handler:
            assert callable(cli.resolve(handler)), handler


def test_unknown_option_is_refused():
    assert options.parse_opts(["--ziel=22"]) == {"--ziel": "22"}
    with pytest.raises(rules.Violation, match="Unknown option"):
        options.parse_opts(["--zeil=22"])


def test_rule_citation_format():
    assert messages.rule("6.1.2", 44) == "[RULE 6.1.2 p.44]"
    assert messages.rule("4.3 p.27") == "[RULE 4.3 p.27]"
    assert messages.rule("CSR 7 p.15") == "[CSR 7 p.15]"
    assert str(rules.Violation("no", rule="4.2 p.21")) == "no [RULE 4.2 p.21]"
