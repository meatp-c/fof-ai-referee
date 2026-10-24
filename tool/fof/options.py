"""Command-line option parsing (--key=value) with English aliases."""

from . import rules


OPT_ALIASES = {
    "--target": "--ziel",
    "--success": "--erfolg",
    "--unit": "--einheit",
    "--net": "--netz",
    "--area": "--bereich",
    "--value": "--wert",
    "--critical": "--kritisch",
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
    "--move-target-marker": "--target_marker",
    "--skill-from": "--skill-von",
    "--no": "--nr",
    "--to": "--nach",
    "--with": "--mit",
    "--lines": "--leitungen",
    "--device": "--geraet",
    "--from": "--aus",
    "--result": "--ergebnis",
    "--cost": "--kosten",
    "--extra": "--zusatz",
    "--what": "--was",
    "--weapon": "--waffe",
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


# German option keys the handlers read (review 23.10.2026, L222: an explicit registry replaces the source scan that
# accepted every quoted word). English-only keys (--hq, --originator, --skill, --team, --squad, ...) are listed as well.
KNOWN_OPTIONS = frozenset(
    {
        "--agentur",
        "--asset",
        "--aus",
        "--bataillon",
        "--bei",
        "--bereich",
        "--burst",
        "--cc",
        "--cc2",
        "--cover_draw",
        "--cover_max",
        "--einheit",
        "--erfahrung",
        "--erfolg",
        "--ergebnis",
        "--force",
        "--gebaeude",
        "--gebaeude_wert",
        "--geraet",
        "--granate",
        "--gratis",
        "--grund",
        "--hill",
        "--hq",
        "--illum",
        "--jam",
        "--kosten",
        "--kritisch",
        "--leitung",
        "--leitungen",
        "--mit",
        "--moerser",
        "--nach",
        "--netz",
        "--nr",
        "--nur_zug",
        "--originator",
        "--platoon",
        "--platz",
        "--pyro",
        "--quelle",
        "--r",
        "--raender",
        "--reichweite",
        "--richtung",
        "--roh",
        "--seite",
        "--short",
        "--skill",
        "--skill-von",
        "--squad",
        "--steps",
        "--target_marker",
        "--team",
        "--typ",
        "--typ-neu",
        "--variante",
        "--vof",
        "--von",
        "--waffe",
        "--wahl",
        "--was",
        "--wer",
        "--wert",
        "--ziel",
        "--zusatz",
    }
)
assert not (set(OPT_ALIASES.values()) & set(OPT_ALIASES)), "an alias must not map onto another alias key"
assert set(OPT_ALIASES.values()) <= KNOWN_OPTIONS, "every alias target must be a known option"

# options whose values are enumerations and get the English value aliases (yes/no/open/...) in cli.argv_to_german;
# free text (--grund, --was, --skill, --typ, ...) is passed through untouched (L222)
ENUM_VALUE_OPTIONS = frozenset(
    {
        "--erfolg",
        "--jam",
        "--short",
        "--kritisch",
        "--gratis",
        "--nur_zug",
        "--leitung",
        "--bereich",
        "--richtung",
        "--netz",
        "--moerser",
        "--platoon",
        "--roh",
        "--granate",
        "--target_marker",
        "--typ-neu",
    }
)


def parse_opts(args):
    """--key=value pairs. Unknown keys, empty values and repeated keys are refused (L72, L222); a bare --flag is stored as
    True. English key aliases are accepted here too (idempotent: no alias target is itself an alias key).

    Kept on purpose (review Struktur 8): the command line is translated once in cli.argv_to_german, but in-process
    callers skip it (the test suite calls cmd_order, cmd_grenade, ... with --target=, --success=, --unit= around a
    hundred times). Only keys are mapped here; value aliases (yes/no, open, ...) exist only in cli.argv_to_german, so
    in-process callers pass German values ("ja"/"nein")."""
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
        o[k] = v if eq else True
    return o


def int_opt(o, key, what, default=None):
    """Integer option with a Violation instead of a ValueError (L221); a bare --flag without a number is a Violation as
    well (L333), it used to fall back to the default silently."""
    v = o.get(key)
    if v is None:
        return default
    if v is True:
        raise rules.Violation(f"{what}: {key}=<whole number> expected, the value is missing")
    return rules.int_value(v, what)


def text_opt(o, key, usage=None, default=None):
    """Option that needs a text value (canonical version of the local text_opt helpers in commands.py and vehicles.py,
    review H12): a bare --flag (stored as True by parse_opts) is a Violation naming the usage; missing: default."""
    v = o.get(key)
    if v is True:
        raise rules.Violation(f"Option {key} needs a value: " + (usage or f"{key}=.."))
    return default if v is None else v


def list_option(o, key):
    v = o.get(key)
    if v is True:  # L323: a bare flag where a list is expected
        raise rules.Violation(f"Option {key} needs a value: {key}=<a>[,<b>..]")
    return [x.strip() for x in v.split(",")] if v else []
