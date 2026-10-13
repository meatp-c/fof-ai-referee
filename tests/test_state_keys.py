"""Guard: the game state keeps its German keys. Keyword arguments of dict()/update()/setdefault()/get()/pop()
must not use English names (the identifier rename of 2026-10-12 once turned punkte=1 into points=1)."""

import ast
import pathlib

GERMAN_KEYS = {
    "karte",
    "bereich",
    "ziel",
    "seite",
    "erfahrung",
    "typname",
    "paket",
    "pc_herkunft",
    "punkte",
    "reichweite",
    "verfuegbar",
    "gespart",
    "aktiviert",
    "fertig",
    "mitglieder",
    "erfolg",
    "primaer_besucht",
    "einheit",
}
ENGLISH = {
    "card",
    "area",
    "target",
    "side",
    "experience",
    "type_name",
    "package",
    "pc_origin",
    "points",
    "range_",
    "available",
    "saved",
    "done",
    "activated",
    "members",
    "success",
    "primary_visited",
    "unit",
}


def package_dir():
    for folder in ("werkzeuge", "tool"):
        cand = pathlib.Path(__file__).resolve().parents[1] / folder / "fof"
        if cand.is_dir():
            return cand
    raise AssertionError("package fof not found")


def test_no_english_keyword_keys_in_state_writes():
    offenders = []
    for path in sorted(package_dir().glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
                if name in ("dict", "update", "setdefault", "get", "pop"):
                    for kw in node.keywords:
                        if kw.arg in ENGLISH:
                            offenders.append(f"{path.name}:{node.lineno} {name}({kw.arg}=...)")
    assert not offenders, offenders
