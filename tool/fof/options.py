"""Command-line option parsing (--key=value) with English aliases."""

import pathlib

from . import rules


OPT_ALIASES = {
    "--target": "--ziel",
    "--success": "--erfolg",
    "--unit": "--einheit",
    "--net": "--netz",
    "--area": "--bereich",
    "--value": "--wert",
    "--mortar": "--moerser",
    "--place": "--platz",
    "--free": "--gratis",
    "--agency": "--agentur",
    "--edges": "--raender",
    "--building": "--gebaeude",
    "--building-value": "--gebaeude_wert",
    "--experience": "--erfahrung",
    "--who": "--wer",
    "--type": "--typ",
    "--move-target-marker": "--target",
    "--skill-from": "--skill-von",
    "--no": "--nr",
    "--to": "--nach",
    "--with": "--mit",
    "--lines": "--leitungen",
    "--device": "--geraet",
    "--from": "--aus",
    "--extra": "--zusatz",
    "--what": "--was",
    "--choice": "--wahl",
    "--source": "--von",
    "--variant": "--variante",
    "--raw": "--roh",
    "--direction": "--richtung",
    "--range": "--reichweite",
    "--origin": "--quelle",
    "--this-turn-only": "--nur_zug",
    "--line": "--leitung",
    "--grenade": "--granate",
    "--at": "--bei",
    "--battalion": "--bataillon",
    "--reason": "--grund",
    "--side": "--seite",
}


VALUE_ALIASES = {
    "yes": "ja",
    "no": "nein",
    "open": "offen",
    "Left": "Links",
    "Right": "Rechts",
    "none": "keiner",
    "radio": "funk",
    "phone": "telefon",
    "section": "sektion",
}


_KNOWN_OPTIONS = None


def parse_opts(args):
    """L72: never ignore unknown options silently (M3 turn 5: --agency instead of --agentur led to a wrong LOS check)."""
    global _KNOWN_OPTIONS
    if _KNOWN_OPTIONS is None:
        import re as _re

        _src = "\n".join(f.read_text(encoding="utf-8") for f in sorted(pathlib.Path(__file__).parent.glob("*.py")))
        _KNOWN_OPTIONS = (
            set(_re.findall(r"(--[a-z_0-9]+)", _src))
            | {"--" + w for w in _re.findall(r'"([a-z_0-9]+)"', _src)}
            | set(OPT_ALIASES.values())
        )  # also options assembled as f"--{field}"
    o = {}
    for a in args:
        if not a.startswith("--"):
            continue
        k, v = (a.split("=", 1) + [None])[:2] if "=" in a else (a, None)
        k = OPT_ALIASES.get(k, k)
        if k not in _KNOWN_OPTIONS:
            raise rules.Violation(f"Unknown option {k}; nothing booked")
        if v is not None:
            o[k] = v
    return o


def list_option(o, key):
    v = o.get(key)
    return [x.strip() for x in v.split(",")] if v else []
