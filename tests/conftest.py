"""Shared fixtures: a tiny synthetic board (no game data, no GMT text) for the engine's pure functions."""

import pathlib
import sys

import pytest

for folder in ("werkzeuge", "tool"):  # project layout (werkzeuge/fof) and kit layout (tool/fof)
    cand = pathlib.Path(__file__).resolve().parents[1] / folder
    if (cand / "fof").is_dir():
        sys.path.insert(0, str(cand))


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
