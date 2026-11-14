"""Command-line option parsing (--key=value) with English aliases."""

from __future__ import annotations

import re

from typing import Any

from . import migrate, rules


# German option names and values (the engine's words until) are accepted as aliases
OPT_ALIASES = migrate.OPTION_WORDS

# German values of enumerated options (yes/no, open, Left/Right, none, radio/phone, section)
VALUE_ALIASES = {
    g: e
    for g, e in migrate.WORDS.items()
    if e in ("yes", "no", "open", "Left", "Right", "none", "radio", "phone", "section")
}

# German words in --edges values (top/bottom/left/right, white/green); 'dark' and 'corner' are English aliases
EDGE_ALIASES = {
    **{g: e for g, e in migrate.WORDS.items() if e in ("top", "bottom", "left", "right", "white", "green")},
    "dark": "green",
    "corner": "diagonal",
}


# Option keys the handlers read (an explicit registry: a scan of the source would
# accept every quoted word). English-only keys (--hq, --originator, --skill, --team, --squad, ...) are listed as well.
KNOWN_OPTIONS = frozenset(
    {
        "--plain",
        "--agency",
        "--asset",
        "--from",
        "--game",  # step.py only; cli.main refuses it with a hint
        "--battalion",
        "--at",
        "--area",
        "--burst",
        "--cc",
        "--cc2",
        "--cover_draw",
        "--cover_max",
        "--unit",
        "--experience",
        "--success",
        "--result",
        "--force",
        "--building",
        "--building-value",
        "--device",
        "--grenade",
        "--free",
        "--reason",
        "--hill",
        "--vehicles",
        "--elevation",
        "--hq",
        "--illum",
        "--jeep",
        "--jam",
        "--cost",
        "--critical",
        "--line",
        "--lines",
        "--with",
        "--mortar",
        "--to",
        "--net",
        "--no",
        "--this-turn-only",
        "--originator",
        "--platoon",
        "--place",
        "--pyro",
        "--origin",
        "--r",
        "--edges",
        "--range",
        "--direction",
        "--raw",
        "--side",
        "--short",
        "--skill",
        "--skill-from",
        "--squad",
        "--steps",
        "--move-target-marker",
        "--team",
        "--type",
        "--new-type",
        "--variant",
        "--leader-squad",
        "--ooa-flip",
        "--vof",
        "--source",
        "--weapon",
        "--choice",
        "--what",
        "--who",
        "--value",
        "--target",
        "--extra",
    }
)
assert not (set(OPT_ALIASES.values()) & set(OPT_ALIASES)), "an alias must not map onto another alias key"
assert set(OPT_ALIASES.values()) <= KNOWN_OPTIONS, "every alias target must be a known option"

# options whose values are enumerations and get the value aliases (yes/no/open/...) in parse_opts;
# free text (--reason, --what, --skill, --type, ...) is passed through untouched
ENUM_VALUE_OPTIONS = frozenset(
    {
        "--plain",
        "--success",
        "--jam",
        "--short",
        "--critical",
        "--free",
        "--this-turn-only",
        "--line",
        "--area",
        "--direction",
        "--net",
        "--mortar",
        "--platoon",
        "--raw",
        "--grenade",
        "--move-target-marker",
        "--new-type",
        "--jeep",
        "--vehicles",
        "--ooa-flip",
        "--cc2",  # --cc2=none, also with the German value aliases
        "--extra",  # --extra=yes|no needs the value alias too
    }
)


def parse_opts(args: list[str]) -> dict[str, Any]:
    """--key=value pairs. Unknown keys, empty values and repeated keys are refused; a bare --flag is stored as
    True. German option names are mapped to the English ones here, and the values of enumerated options (yes/no, open,
    ...) and of --edges as well, so the command line and in-process callers (the test suite calls cmd_order,
    cmd_grenade, ... directly) get the same English words."""
    o = {}
    for a in args:
        if not a.startswith("--"):
            continue
        k, eq, v = a.partition("=")
        k = OPT_ALIASES.get(k, k)
        if k not in KNOWN_OPTIONS:
            raise rules.Violation(f"Unknown option {k}; nothing booked")
        if eq and v == "":
            raise rules.Violation(f"Option {k} has an empty value; nothing booked")
        if k in o:
            raise rules.Violation(f"Option {k} given twice; nothing booked")
        o[k] = english_value(k, v) if eq else True
    return o


def _alias_item(x: str) -> str:
    head, sep, tail = x.rpartition(":")
    return head + sep + VALUE_ALIASES.get(tail, tail) if sep else VALUE_ALIASES.get(x, x)


def english_value(k: str, v: str) -> str:
    """English value of option k: enumerated values item by item ("1/1:yes,2/1:no"), --edges word by word; free text
    (--reason, --what, --skill, --type, ...) unchanged."""
    if k == "--edges":
        for de, en in EDGE_ALIASES.items():
            v = re.sub(rf"\b{de}\b", en, v)
        return v
    if k in ENUM_VALUE_OPTIONS:
        return ",".join(_alias_item(x) for x in v.split(","))
    return v


def int_opt(o: dict[str, Any], key: str, what: str, default: int | None = None) -> int | None:
    """Integer option with a Violation instead of a ValueError; a bare --flag without a number is a Violation as
    well."""
    v = o.get(key)
    if v is None:
        return default
    if v is True:
        raise rules.Violation(f"{what}: {key}=<whole number> expected, the value is missing")
    return rules.int_value(v, what)


def text_opt(o: dict[str, Any], key: str, usage: str | None = None, default: str | None = None) -> str | None:
    """Option that needs a text value (canonical version of the local text_opt helpers in commands.py and vehicles.py): a bare --flag (stored as True by parse_opts) is a Violation naming the usage; missing: default."""
    v = o.get(key)
    if v is True:
        raise rules.Violation(f"Option {key} needs a value: " + (usage or f"{key}=.."))
    return default if v is None else v


def list_option(o: dict[str, Any], key: str) -> list[str]:
    v = o.get(key)
    if v is True:  # a bare flag where a list is expected
        raise rules.Violation(f"Option {key} needs a value: {key}=<a>[,<b>..]")
    return [x.strip() for x in v.split(",")] if v else []
