"""L470: tool/step.py, the one-call probe/book/commit helper (parsing and output filter only; no game folder)."""

import importlib.util
import pathlib

SPEC = importlib.util.spec_from_file_location(
    "step", pathlib.Path(__file__).resolve().parent.parent / "tool" / "step.py"
)
step = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(step)


def test_read_commands_skips_comments_and_keeps_quotes():
    cmds = step.read_commands('# note\nhq "1st PLT HQ"\n\ncard ? 5\n')
    assert cmds == [["hq", "1st PLT HQ"], ["card", "?", "5"]]


def test_shorten_drops_only_allowed_headers():
    out = "ALLOWED [RULE 4.2.2a p.23]\nGI orders 1/3: Move; cost 1\nBoard: 1/3 to 43, Exposed\nCHECKSTAMP OK"
    assert step.shorten(out, False).splitlines() == [
        "GI orders 1/3: Move; cost 1",
        "Board: 1/3 to 43, Exposed",
        "CHECKSTAMP OK",
    ]
    assert step.shorten(out, True) == out


def test_parse_args():
    o = step.parse_args(["--probe", "--msg", "x y"])
    assert o["probe"] and o["msg"] == "x y" and not o["all"]


def test_verdict_uses_the_exit_code_not_the_text():
    """L529 (review K1/K8): exit 2 is a VIOLATION, any other non-zero exit or a traceback an error; the word in a
    help text, a note or an informational line is not a refusal."""
    assert step.verdict(0, "USAGE ... answers with VIOLATION and a rule citation") == "ok"
    assert step.verdict(0, "VIOLATION: radio check, informational") == "ok"
    assert step.verdict(2, "VIOLATION: 1/1 is Pinned") == "violation"
    assert step.verdict(1, "No game state. First: fof.py new <setup.json>") == "error"
    assert step.verdict(1, 'Traceback (most recent call last):\n  File "x"\nTypeError: ...') == "error"
    assert step.verdict(0, "Traceback (most recent call last):\nKeyError: 'x'") == "error"


def _main(monkeypatch, tmp_path, results, argv):
    game = tmp_path / "game"
    game.mkdir()
    (game / "game_state.json").write_text("{}", encoding="utf-8")
    calls = []

    def fake_run(cmd, game_dir):
        calls.append((cmd, game_dir))
        return results[len(calls) - 1]

    monkeypatch.setattr(step, "run", fake_run)
    monkeypatch.setattr(step, "commit", lambda partie, msg: "git: fake")
    monkeypatch.setattr(step.sys, "argv", ["step.py", "--game", str(game), *argv])
    monkeypatch.setattr(step.sys, "stdin", __import__("io").StringIO("note a\nnote b\n"))
    try:
        step.main()
        code = 0
    except SystemExit as e:
        code = e.code
    return code, calls, game


def test_traceback_in_the_probe_books_nothing(monkeypatch, tmp_path, capsys):
    code, calls, game = _main(monkeypatch, tmp_path, [(1, "Traceback (most recent call last):\nTypeError")], [])
    assert code == 1 and len(calls) == 1 and calls[0][1] != game
    assert "NOT BOOKED (probe, error exit 1)" in capsys.readouterr().out


def test_informational_violation_word_does_not_stop_the_batch(monkeypatch, tmp_path, capsys):
    ok = (0, "VIOLATION: informational")
    code, calls, game = _main(monkeypatch, tmp_path, [ok, ok, ok, ok], [])
    assert code == 0 and len(calls) == 4 and calls[2][1] == game and calls[3][1] == game
    assert "git: fake" in capsys.readouterr().out


def test_absolute_partie_probes_in_a_copy(monkeypatch, tmp_path):
    code, calls, game = _main(monkeypatch, tmp_path, [(0, "ok"), (0, "ok")], ["--probe"])
    assert code == 0 and all(d != game and d.name == "game" for _c, d in calls)


def test_error_in_the_real_run_names_what_is_booked(monkeypatch, tmp_path, capsys):
    code, _calls, _game = _main(
        monkeypatch, tmp_path, [(0, "ok"), (0, "ok"), (0, "ok"), (1, "Traceback (most recent call last):")], []
    )
    out = capsys.readouterr().out
    assert code == 1 and "command 2" in out and "commands 1-1 are booked but not committed" in out


def test_run_points_fof_at_the_given_folder(monkeypatch, tmp_path):
    """L565: run() hands fof.py the probe folder in FOF_GAME and drops only the variable name of earlier releases.
    L561 popped FOF_GAME itself, so the probe ran against the real game and every step was booked twice. subprocess.run
    is replaced, so this test never reaches a real game folder."""
    seen = {}

    class Done:
        returncode, stdout, stderr = 0, "ok", ""

    def fake(argv, **kw):
        seen.update(kw["env"])
        return Done()

    monkeypatch.setattr(step.subprocess, "run", fake)
    monkeypatch.setenv("FOF_GAME", "/somewhere/else")
    monkeypatch.setenv(step.migrate.ENV["FOF_GAME"], "/older/name")
    assert step.run(["status"], tmp_path / "probe") == (0, "ok")
    assert seen["FOF_GAME"] == str(tmp_path / "probe")
    assert step.migrate.ENV["FOF_GAME"] not in seen
