"""L475: rules.Pending, a saved step that stops at an open draw: OPEN instead of VIOLATION, exit code 0."""

import sys

import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "tool"))
from fof import cli, messages, rules  # noqa: E402


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
