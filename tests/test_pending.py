"""L475: rules.Pending, a saved step that stops at an open draw: OPEN instead of VIOLATION, exit code 0."""

import pytest

from fof import cli, messages, rules  # L552 (review T6): conftest/pyproject put the package on the path


def test_pending_is_a_violation():
    assert issubclass(rules.Pending, rules.Violation)


def test_cli_prints_open_and_exits_zero(monkeypatch, capsys):
    def boom(*_a, **_k):
        raise rules.Pending("VOF against vehicles still to resolve: x")

    monkeypatch.setattr(cli.state, "load_state", lambda: {})
    monkeypatch.setattr(cli, "resolve", lambda _name: boom)
    try:
        cli.main(["note", "x"])
    except SystemExit as e:
        pytest.fail(f"exit {e.code}")
    out = capsys.readouterr().out
    assert out.startswith(f"{messages.OPEN}: ") and messages.VIOLATION not in out


def test_cli_refuses_zug_options(monkeypatch, capsys):
    """L501: 'fof.py done --probe' booked the step; zug.py options are a VIOLATION now, before the state loads."""

    def no_load():
        pytest.fail("state loaded")

    monkeypatch.setattr(cli.state, "load_state", no_load)
    with pytest.raises(SystemExit) as e:
        cli.main(["done", "--probe"])
    assert e.value.code == 2
    out = capsys.readouterr().out
    assert out.startswith(f"{messages.VIOLATION}: --probe is an option of zug.py") and "nothing booked" in out
