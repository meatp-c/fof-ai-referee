"""Shared fixtures: a tiny synthetic board (no game data, no GMT text) for the engine's pure functions, the isolated
game folder for every test, the stripped M6 states under tests/fixtures/ and an in-process command line."""

import importlib.util
import json
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"

# pyproject.toml puts werkzeuge/ on the path (pytest pythonpath); the public kit (tool/fof, no pyproject) needs this
if importlib.util.find_spec("fof") is None:
    for folder in ("werkzeuge", "tool"):
        cand = ROOT / folder
        if (cand / "fof").is_dir():
            sys.path.insert(0, str(cand))
            break


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "game_data: uses the stripped Normandy M6 states in tests/fixtures (mission data, not for the kit)"
    )


def pytest_collection_modifyitems(config, items):
    """A copy without tests/fixtures (public kit: no mission data) skips the game_data tests instead of failing."""
    if (FIXTURES / "m6_base.json").exists():
        return
    skip = pytest.mark.skip(reason="tests/fixtures (Normandy M6 mission data) not in this copy")
    for item in items:
        if "game_data" in item.keywords:
            item.add_marker(skip)


def card(row, col, elevation=1, edges="weiss", **extra):
    c = {
        "reihe": row,
        "spalte": col,
        "elevation": elevation,
        "terrain": "Open Fields",
        "raender": edges,
        "cover": [],
        "extern": [],
    }
    c.update(extra)
    return c


def unit(kid, side="US", vof="S", rng="L", steps=3, **extra):
    e = {
        "karte": kid,
        "seite": side,
        "typ": "Squad",
        "steps": steps,
        "status": [],
        "bereich": "offen",
        "ziel": None,
        "vof_rating": vof,
        "reichweite": rng,
        "erfahrung": "Line",
        "spotted": True,
    }
    e.update(extra)
    return e


@pytest.fixture(autouse=True)
def isolated_game_dir(tmp_path, monkeypatch):
    """Every test plays in its own folder: nothing can reach the real game via .aktuelle_partie (incident 22.10., L209).
    Tests that need another folder set FOF_PARTIE themselves (monkeypatch.setenv wins, it runs later)."""
    monkeypatch.setenv("FOF_PARTIE", str(tmp_path))
    return tmp_path


@pytest.fixture
def board():
    """3 rows x 3 columns, card ids 11..33 (row, column), all open fields with white edges, day."""
    s = {
        "sicht": "tag",
        "typ": "offensiv",
        "zug": 1,
        "phase": "3.3.1b",
        "karten": {f"{r}{c}": card(r, c) for r in (1, 2, 3) for c in (1, 2, 3)},
        "einheiten": {},
        "kommandos": {},
        "impuls_ausgegeben": {},
        "impuls_aktionen": {},
        "protokoll": [],
        "optionen": {},
    }
    return s


def m6_state(n):
    """State after entry n of Normandy Mission 6 (tests/fixtures, built by make_m6_fixtures.py from normandy_m6/verlauf)."""
    s = json.loads((FIXTURES / "m6_base.json").read_text(encoding="utf-8"))
    s.update(json.loads((FIXTURES / f"m6_{n}.json").read_text(encoding="utf-8")))
    return s


@pytest.fixture
def m6_game(tmp_path, monkeypatch):
    """Factory m6_game(n): writes the M6 state n as tmp_path/spielstand.json, sets FOF_PARTIE, returns the state."""

    def load(n):
        s = m6_state(n)
        (tmp_path / "spielstand.json").write_text(json.dumps(s, indent=1, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setenv("FOF_PARTIE", str(tmp_path))
        return s

    return load


def saved_state():
    """The spielstand.json of the current test game (FOF_PARTIE)."""
    return json.loads((pathlib.Path(os.environ["FOF_PARTIE"]) / "spielstand.json").read_text(encoding="utf-8"))


@pytest.fixture
def fof_cli(capsys):
    """In-process command line: fof_cli("order", ...) -> (exit code, output). cli.main ends a Violation with
    sys.exit(2); load_state and a few usages end with sys.exit("text") (code 1, the text is part of the output)."""
    from fof import cli, state

    def run(*argv):
        state.MARKER_NOTES.clear()
        code, msg = 0, ""
        try:
            cli.main(list(argv))
        except SystemExit as e:
            if isinstance(e.code, str):
                code, msg = 1, e.code
            else:
                code = e.code or 0
        cap = capsys.readouterr()
        return code, cap.out + cap.err + msg

    return run


def fof_subprocess(*argv):
    """The real entry point (werkzeuge/fof.py or the kit's tool/fof.py) in a subprocess with the test's FOF_PARTIE."""
    tool = ROOT / "werkzeuge" / "fof.py"
    if not tool.exists():
        tool = ROOT / "tool" / "fof.py"
    return subprocess.run([sys.executable, str(tool), *argv], capture_output=True, text=True, env=dict(os.environ))
