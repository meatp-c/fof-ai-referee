"""Shared fixtures: a tiny synthetic board (no game data, no GMT text) for the engine's pure functions, the isolated
game folder for every test, the stripped M6 states under tests/fixtures/ and an in-process command line."""

import copy
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
    monkeypatch.setenv("FOF_KEY_CHECK", "1")  # L530: every state a test saves must use registered keys (fof/keys.py)
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


@pytest.fixture
def cli_game(board, tmp_path, monkeypatch, fof_cli):
    """L529 (review T1): factory cli_game(**fields) creates a game with 'new' from the synthetic board (no mission data,
    runs in the public kit too) in tmp_path/game, sets FOF_PARTIE and returns the folder; drive it with fof_cli."""

    def make(**fields):
        s = copy.deepcopy(board)
        s.update(mission="synthetic", max_zuege=10)
        s.update(fields)
        setup_file = tmp_path / "aufbau.json"
        setup_file.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
        game = tmp_path / "game"
        monkeypatch.setenv("FOF_PARTIE", str(game))
        code, out = fof_cli("new", str(setup_file))
        assert code == 0, out
        return game

    return make


def fof_subprocess(*argv):
    """The real entry point (werkzeuge/fof.py or the kit's tool/fof.py) in a subprocess with the test's FOF_PARTIE."""
    tool = ROOT / "werkzeuge" / "fof.py"
    if not tool.exists():
        tool = ROOT / "tool" / "fof.py"
    return subprocess.run([sys.executable, str(tool), *argv], capture_output=True, text=True, env=dict(os.environ))


# ---- shared by tests/test_block_b.py and tests/test_block_c.py (review 07.11.2026, L531-)


@pytest.fixture
def b36(monkeypatch):
    """3x3 board in phase 3.6 with the Naktong tank priority list; save_state/print_board stubbed."""
    from fof import briefing, state

    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protokoll"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)
    return {
        "sicht": "tag",
        "typ": "offensiv",
        "zug": 1,
        "phase": "3.6",
        "karten": {f"{r}{c}": card(r, c) for r in (1, 2, 3) for c in (1, 2, 3)},
        "einheiten": {},
        "kommandos": {},
        "impuls_ausgegeben": {},
        "impuls_aktionen": {},
        "protokoll": [],
        "optionen": {},
        "mission": "x",
        "terrain_katalog": {"Open Fields": {"fahrzeuge": True}},
        "sonderregeln": {"panzer_prioritaeten": True},
    }


def t34(kid, **kw):
    from fof import rules

    kw.setdefault("fahrzeug", "T-34/85")
    return unit(
        kid,
        side="Feind",
        vof=kw.pop("vof", None),
        rng=kw.pop("rng", None),
        steps=1,
        typ="Vehicle",
        spotted=True,
        status=[rules.ACTIVATED],
        **kw,
    )


def bazooka(kid, **kw):
    return unit(kid, typ="Weapons Team", steps=1, at_waffe="M1A1 Bazooka", vof=kw.pop("vof", None), rng="C", **kw)


@pytest.fixture
def b342(monkeypatch):
    """4x3 board in the enemy segment 3.4.2; save_state/print_board stubbed (B6 uses the real consistency check)."""
    from fof import briefing, state

    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)
    s = {
        "sicht": "tag",
        "typ": "offensiv",
        "zug": 2,
        "phase": "3.4.2",
        "karten": {f"{r}{c}": card(r, c) for r in (1, 2, 3, 4) for c in (1, 2, 3)},
        "einheiten": {},
        "kommandos": {},
        "impuls_ausgegeben": {},
        "impuls_aktionen": {},
        "protokoll": [],
        "optionen": {},
        "feind_taktik": "Hasty",
        "aktivitaet": "Contact",
        "mission": "x",
    }
    saved = []

    def save(st, text, rule=None):
        from fof import briefing as b

        errors = b.consistency_check(st)
        if errors:
            from fof import rules

            raise rules.Violation("Check prevents saving: " + "; ".join(errors))
        st["protokoll"].append({"text": text})
        saved.append(text)

    monkeypatch.setattr(state, "save_state", save)
    return s


def german(kid, vof="A", **kw):
    kw.setdefault("typname", "German Squad")
    return unit(kid, side="Feind", vof=vof, **kw)


def _hq_board(board, monkeypatch, phase="3.3.1b"):
    from fof import briefing, state

    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protokoll"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)
    s = board
    s["phase"] = phase
    s["kommandos"]["1st PLT HQ"] = {"verfuegbar": 6, "gespart": 0, "aktiviert": True, "fertig": False}
    s["einheiten"]["1st PLT HQ"] = unit("22", vof=None, typ="HQ", ebene="PLT", platoon="1", steps=1)
    s["aktiver_hq"] = "1st PLT HQ"
    return s
