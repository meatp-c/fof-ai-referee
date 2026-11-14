"""Guard (L560): the game state uses English keys. No German key of migrate.WORDS may appear as a keyword argument of
dict()/update()/setdefault()/make_step()/make_item() or as a whole string literal in the engine (outside migrate.py
and the alias tables), otherwise an old German key would be written next to the English one."""

import ast
import pathlib

from fof import migrate

# places where a German word stands on purpose: the alias tables and input words accepted from the command line
# migrate.py holds the German words; every alias table (cli.DE_COMMANDS, options.VALUE_ALIASES, YES_WORDS, ...) is
# built from it, so no other module needs a German literal
ALLOWED = {"migrate.py"}


def package_dir():
    for folder in ("tool",):
        cand = pathlib.Path(__file__).resolve().parents[1] / folder / "fof"
        if cand.is_dir():
            return cand
    raise AssertionError("package fof not found")


GERMAN = (
    set(migrate.WORDS)
    | set(migrate.COMMANDS_DE)
    | set(migrate.OPTION_WORDS)
    | set(migrate.FILES.values())
    | set(migrate.DATA_FILES.values())
    | set(migrate.ENV.values())
)


def test_no_german_keys_in_the_engine():
    """L560/L561: also the German command, option, file and variable names of earlier releases, in tool/ as well."""
    offenders, calls_seen = [], 0
    for path in sorted(package_dir().glob("*.py")) + sorted(package_dir().parent.glob("*.py")):
        if path.name in ALLOWED:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
                if name in ("dict", "update", "setdefault", "make_step", "make_item"):
                    calls_seen += 1
                    offenders += [f"{path.name}:{node.lineno} {kw.arg}=" for kw in node.keywords if kw.arg in GERMAN]
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in GERMAN:
                    offenders.append(f"{path.name}:{node.lineno} {node.value!r}")
    assert not offenders, offenders
    assert calls_seen >= 20, calls_seen  # the walk must see such calls, otherwise the guard passes vacuously
