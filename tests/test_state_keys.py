"""Guard: the game state keeps its German keys. Keyword arguments of dict()/update()/setdefault()/get()/pop()
must not use English names (the identifier rename of 2026-10-12 once turned punkte=1 into points=1)."""

import ast
import pathlib

# English name the 2026-10-12 rename produced -> German JSON key the state uses
RENAMED = {
    "card": "karte",
    "area": "bereich",
    "target": "ziel",
    "side": "seite",
    "experience": "erfahrung",
    "type_name": "typname",
    "package": "paket",
    "pc_origin": "pc_herkunft",
    "points": "punkte",
    "range_": "reichweite",
    "available": "verfuegbar",
    "saved": "gespart",
    "done": "fertig",
    "activated": "aktiviert",
    "members": "mitglieder",
    "success": "erfolg",
    "primary_visited": "primaer_besucht",
    "unit": "einheit",
}
GERMAN_KEYS = set(RENAMED.values())
ENGLISH = set(RENAMED)


def package_dir():
    for folder in ("werkzeuge", "tool"):
        cand = pathlib.Path(__file__).resolve().parents[1] / folder / "fof"
        if cand.is_dir():
            return cand
    raise AssertionError("package fof not found")


def test_no_english_keyword_keys_in_state_writes():
    offenders, german_seen = [], set()
    for path in sorted(package_dir().glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
                if name in ("dict", "update", "setdefault", "get", "pop"):
                    for kw in node.keywords:
                        if kw.arg in ENGLISH:
                            offenders.append(f"{path.name}:{node.lineno} {name}({kw.arg}=...), use {RENAMED[kw.arg]}=")
                        elif kw.arg in GERMAN_KEYS:
                            german_seen.add(kw.arg)
    assert not offenders, offenders
    # the walk must actually see such calls, otherwise the guard passes vacuously (e.g. after a refactoring to dicts)
    assert len(german_seen) >= 3, sorted(german_seen)
