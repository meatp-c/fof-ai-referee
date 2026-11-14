"""generic team counters (Assault/Fire/Paralyzed/Litter Team) named by counter type and card.

A game with ``lat_names == "card"`` (command ``names lat card``) calls its generic teams 'AT 45', 'FT 33', 'P 55',
'L 42' (enemy teams with the setup's enemy_prefix in front). The name follows the counter: when the team changes
its type (a hit turns a Fire Team into a Paralyzed Team) or its card, it is renamed, and the rename is announced as
a board line. Several teams of one type on one card get 'b', 'c', ... in the order they arrive. Without the option
the numbered names ('Assault Team 3') stay as they are."""

from __future__ import annotations

from typing import Any

from . import state

ABBREVIATION = {"Assault Team": "AT", "Fire Team": "FT", "Paralyzed Team": "P", "Litter Team": "L"}
SUFFIXES = ("", "b", "c", "d", "e", "f", "g", "h")
# free text and the records of what happened keep the name the counter had at the time
KEEP = ("protocol", "xp", "setup_units", "removed_from_play", "terrain_catalog")


def base_label(s: state.GameState, e: state.Unit) -> str:
    prefix = s.get("enemy_prefix") if e["side"] == "Enemy" else None
    return f"{prefix + ' ' if prefix else ''}{ABBREVIATION[e['type']]} {e['card']}"


def _swap(x: Any, old: str, new: str) -> Any:
    """Replace the exact string old by new, in place: unit dicts stay the same objects for callers that still hold them."""
    if isinstance(x, str):
        return new if x == old else x
    if isinstance(x, list):
        x[:] = [_swap(i, old, new) for i in x]
    elif isinstance(x, dict):
        items = [(new if k == old else k, _swap(v, old, new)) for k, v in x.items()]
        x.clear()
        x.update(items)
    return x


def rename_unit(s: state.GameState, old: str, new: str) -> None:
    """Every reference to the unit (targets, attachments, Commands, NCM groups, ...) follows the new name."""
    for k in list(s):
        if k not in KEEP:
            s[k] = _swap(s[k], old, new)


def relabel(s: state.GameState) -> list[str]:
    """Rename every generic team whose name no longer fits its counter type and card; returns the board lines."""
    if s.get("lat_names") != "card":
        return []
    lines = []
    for n in list(s.get("units", {})):
        e = s["units"][n]
        if not state.is_lat(e) or not e.get("card"):
            continue
        base = base_label(s, e)
        if n in [base + x for x in SUFFIXES]:
            continue
        new = next(base + x for x in SUFFIXES if base + x not in s["units"])
        rename_unit(s, n, new)
        lines.append(f"{n} is now called {new} (counter type and card)")
    return lines
