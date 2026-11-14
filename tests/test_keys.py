"""L530 (code review 07.11.2026 S1/E1): the key register fof/keys.py.

1. Every literal key the engine writes (x["key"] = ..., setdefault("key", ...), update(key=...)) is registered.
2. Every saved state in the repository (games, history snapshots, setups, test fixtures) uses registered keys only.
3. With FOF_KEY_CHECK=1 (set for every test by conftest.py) save_state refuses an unregistered key.
"""

import ast
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def package_dir():
    for folder in ("tool",):
        cand = ROOT / folder / "fof"
        if cand.is_dir():
            return cand
    raise AssertionError("package fof not found")


def written_keys():
    """{key: [file:line, ..]} of every literal key written in the engine."""
    found = {}
    for f in sorted(package_dir().glob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            keys = []
            if isinstance(n, ast.Subscript) and isinstance(n.ctx, ast.Store) and isinstance(n.slice, ast.Constant):
                keys.append(n.slice.value)
            elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                if n.func.attr == "setdefault" and n.args and isinstance(n.args[0], ast.Constant):
                    keys.append(n.args[0].value)
                elif n.func.attr == "update":
                    keys += [kw.arg for kw in n.keywords if kw.arg]
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict):
                # dict literal stored on the state: s["counterattack"] = {"tactic_before": .., "until_turn": ..}
                if any(
                    isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id == "s"
                    for t in n.targets
                ):
                    keys += literal_keys(n.value)
            for k in keys:
                if isinstance(k, str) and not k.startswith("-"):
                    found.setdefault(k, []).append(f"{f.name}:{n.lineno}")
    return found


def literal_keys(d):
    return [k.value for k in d.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]


def unit_literal_keys():
    """{key: [file:line]} of dict literals that build a unit (keys side plus card, steps or status)."""
    found = {}
    for f in sorted(package_dir().glob("*.py")):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Dict):
                ks = literal_keys(n)
                if "side" in ks and {"card", "steps", "status"} & set(ks):
                    for k in ks:
                        found.setdefault(k, []).append(f"{f.name}:{n.lineno}")
    return found


def registered():
    from fof import keys

    out = set(keys.SUBKEYS)
    for st in keys.STRUCTURES.values():
        out |= set(st)
    return out


def test_every_written_key_is_registered():
    reg = registered()
    missing = {k: v for k, v in written_keys().items() if k not in reg}
    assert not missing, "register these keys in fof/keys.py: " + "; ".join(
        f"{k} ({', '.join(v[:3])})" for k, v in sorted(missing.items())
    )


def test_unit_dict_literals_use_unit_keys():
    from fof import keys

    missing = {k: v for k, v in unit_literal_keys().items() if k not in keys.UNIT}
    assert not missing, "register these unit keys in fof/keys.py UNIT: " + "; ".join(
        f"{k} ({', '.join(v[:3])})" for k, v in sorted(missing.items())
    )


def test_register_entries_are_well_formed():
    from fof import keys

    for name, st in keys.STRUCTURES.items():
        for k, v in st.items():
            assert isinstance(v, tuple) and len(v) == 2, (name, k)
            assert v[0] in keys.LIFETIMES, (name, k, v[0])
            assert v[1].strip(), (name, k)


def saved_states():
    """Games, setups and fixtures; of the history snapshots every 25th and the newest of each game (they differ little)."""
    for p in ("*/game_state.json", "normandy/setup_*.json", "korea/setup_*.json", "tests/fixtures/*.json"):
        yield from (f for f in sorted(ROOT.glob(p)) if ".stale." not in str(f))
    for d in sorted(ROOT.glob("*/history")):
        if ".stale." in str(d):
            continue
        snaps = sorted(d.glob("*.json"), key=lambda f: int(f.stem) if f.stem.isdigit() else 0)
        yield from snaps[::25] + snaps[-1:]


def test_every_saved_state_uses_registered_keys():
    from fof import keys, migrate

    files = list(saved_states())
    if not files:
        pytest.skip("no saved states in this copy")
    bad = {}
    for f in files:
        try:
            s = migrate.state(json.loads(f.read_text(encoding="utf-8")))  # L560: games saved before L560 are German
        except ValueError:
            continue
        if isinstance(s, dict) and ("cards" in s or "units" in s):
            u = keys.unknown_keys(s)
            if u:
                bad[str(f.relative_to(ROOT))] = u[:5]
    assert not bad, "; ".join(f"{f}: {u}" for f, u in list(bad.items())[:10])


def test_save_state_refuses_an_unregistered_key(cli_game, fof_cli):
    from conftest import saved_state
    from fof import rules, state

    cli_game()
    s = state.load_state()
    s["units"]["X"] = {
        "side": "US",
        "type": "Squad",
        "card": "11",
        "area": "open",
        "status": [],
        "kein_point_blnak": True,
    }
    with pytest.raises(rules.Violation, match="unregistered key.*kein_point_blnak"):
        state.save_state(s, "typo", None)
    assert "X" not in saved_state()["units"]


def test_check_is_off_in_normal_play(monkeypatch):
    from fof import keys

    monkeypatch.delenv("FOF_KEY_CHECK", raising=False)
    assert keys.check_state({"typo_key": 1}) == []
    monkeypatch.setenv("FOF_KEY_CHECK", "1")
    assert keys.check_state({"typo_key": 1})


# ---- L554 (review E2): the lifetime contract of the register, checked generically


DUMMY = {"fm_blocked": {"turn": 1, "group": "x"}, "illum": [{"value": 1}], "pyro": ["Red Smoke"]}


def test_every_turn_key_is_gone_after_the_end_of_the_turn(board, monkeypatch):
    """Set every 'turn' key of the register, run the end of the turn (campaign game, so the v4 clean up runs too) and
    check that none is left with a value: a new 'turn' key without a clean up fails here."""
    from conftest import unit
    from fof import briefing, keys, phase, state

    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protocol"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)
    s = board
    s.update(phase="3.8", mission="x", max_turns=6, campaign={})
    s["units"]["1/1"] = unit("22")
    s["commands"]["1st PLT HQ"] = {"available": 0, "saved": 0, "activated": False, "done": False}
    turn = {name: [k for k, (lt, _m) in st.items() if lt == "turn"] for name, st in keys.STRUCTURES.items()}
    for k in turn["GAME"]:
        s[k] = DUMMY.get(k, 1)
    for k in turn["UNIT"]:
        s["units"]["1/1"][k] = DUMMY.get(k, True)
    for k in turn["CARD"]:
        s["cards"]["22"][k] = DUMMY.get(k, True)
    for k in turn["COMMANDS"]:
        s["commands"]["1st PLT HQ"][k] = True
    phase.cmd_end_turn(s, [])
    left = (
        [f"state: {k}" for k in turn["GAME"] if s.get(k)]
        + [f"unit: {k}" for k in turn["UNIT"] if s["units"]["1/1"].get(k)]
        + [f"card: {k}" for k in turn["CARD"] if s["cards"]["22"].get(k)]
        + [f"commands: {k}" for k in turn["COMMANDS"] if s["commands"]["1st PLT HQ"].get(k)]
    )
    assert not left, (
        "'turn' keys survive the end of the turn (clean them up in 3.8 or change the lifetime): " + ", ".join(left)
    )


def test_no_command_key_is_ever_saved(cli_game, fof_cli):
    from conftest import saved_state
    from fof import keys

    cli_game()
    fof_cli("note", "x")
    s = saved_state()
    command = [k for k, (lt, _m) in keys.GAME.items() if lt == "command"]
    assert not [k for k in command if k in s]
    unit_cmd = [k for k, (lt, _m) in keys.UNIT.items() if lt == "command"]
    assert not [k for e in s["units"].values() for k in unit_cmd if k in e]


# ---- L554 (review E3/S4): one move path per side


# where a unit's card may be written: the two move paths, and placements (setup, entering units, a successor on the
# card of the unit it replaces, reconstitution, the reattempt reset)
PLACEMENT_WRITERS = {
    ("commands.py", "move_unit"),  # the US move path (and vehicles)
    ("enemy.py", "move_enemy"),  # the enemy move path
    ("setup.py", "place_unit"),
    ("setup.py", "place_mortar_teams"),
    ("setup.py", "setup_mortar"),
    ("setup.py", "setup_jeep"),
    ("events.py", "_friendly_tank_support"),  # L557: friendly_event split into one handler per event
    ("events.py", "_friendly_units_enter"),
    ("combat.py", "mortar_team"),
    ("combat.py", "mortar_team_de"),
    ("campaign.py", "cmd_reconstitute"),
    ("campaign.py", "remove_leaving_units"),
}


def test_a_units_card_changes_only_in_the_move_paths_or_placements():
    """A new direct write of unit['card'] outside the two move paths skips Grenade expiry, mines, ammo surplus,
    phone lines, patrol and fire after the move (review V9). Moves go through commands.move_unit or enemy.move_enemy."""
    found = set()
    for f in sorted(package_dir().glob("*.py")):
        for fn in [n for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))) if isinstance(n, ast.FunctionDef)]:
            for n in ast.walk(fn):
                store = (
                    isinstance(n, ast.Subscript)
                    and isinstance(n.ctx, ast.Store)
                    and isinstance(n.slice, ast.Constant)
                    and n.slice.value == "card"
                )
                upd = (
                    isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "update"
                    and any(k.arg == "card" for k in n.keywords)
                )
                if store or upd:
                    found.add((f.name, fn.name))
    assert found <= PLACEMENT_WRITERS, (
        f"move the unit through move_unit/move_enemy: {sorted(found - PLACEMENT_WRITERS)}"
    )
