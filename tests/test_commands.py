import pytest
from conftest import saved_state

from fof import cli, commands, messages, options, rules


def hq(board, name, available, saved=0):
    board["commands"][name] = {"available": available, "saved": saved, "activated": True, "done": False}


def test_pay_commands_uses_available_before_saved(board):
    hq(board, "CO HQ", 2, 4)
    commands.pay_commands(board, "CO HQ", 3, "test")
    assert board["commands"]["CO HQ"]["available"] == 0
    assert board["commands"]["CO HQ"]["saved"] == 3
    assert board["impulse_spent"]["CO HQ"] == 3


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
    assert cli.normalize_argv(["order", "CO HQ", "1/1", "4.2.2a", "--target=22", "--area=open"]) == [
        "order",
        "CO HQ",
        "1/1",
        "4.2.2a",
        "--target=22",
        "--area=open",
    ]
    assert cli.normalize_argv(["event", "?", "no"]) == ["event", "?", "no"]
    assert cli.normalize_argv(["order", "x"]) == ["order", "x"]  # German passes unchanged


def test_every_command_has_usage_and_description():
    for en, handler, usage, desc in cli.COMMANDS:
        assert usage.startswith(en), en
        assert desc
        if handler:
            assert callable(cli.resolve(handler)), handler


def test_unknown_option_is_refused():
    assert options.parse_opts(["--target=22"]) == {"--target": "22"}
    with pytest.raises(rules.Violation, match="Unknown option"):
        options.parse_opts(["--zeil=22"])


def test_rule_citation_format():
    assert messages.rule("6.1.2", 44) == "[RULE 6.1.2 p.44]"
    assert messages.rule("4.3 p.27") == "[RULE 4.3 p.27]"
    assert messages.rule("CSR 7 p.15") == "[CSR 7 p.15]"
    assert str(rules.Violation("no", rule="4.2 p.21")) == "no [RULE 4.2 p.21]"


def test_correct_number_fixes_the_printed_card_number(cli_game, fof_cli):
    """L578: 'correct number <card> <no>' changes only the recorded number of a terrain card."""
    cli_game()
    code, out = fof_cli("correct", "number", "22", "36", "--reason=photo")
    assert code == 0 and "card number - becomes 36" in out, out
    assert saved_state()["cards"]["22"]["card_number"] == "36"
    code, out = fof_cli("correct", "number", "22", "36")
    assert code == 2 and "--reason" in out


def test_status_lists_dropped_assets(board):
    """L580: Assets dropped on a card by a removed unit (assets_ground) appear in its card line."""
    from fof import briefing

    card_id = next(iter(board["cards"]))
    board["cards"][card_id]["assets_ground"] = ["Rifle Grenade", "HC Smoke"]
    assert "lying here: Rifle Grenade, HC Smoke" in briefing.card_markers(board, card_id, board["cards"][card_id])
