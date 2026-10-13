"""Command line: usage text, English command aliases, dispatch table, rule lookup."""

import importlib
import json
import re
import sys

from . import (
    briefing,
    messages,
    options,
    phase,
    rules,
    state,
)


USAGE = """fof.py - shadow board, sequence of play and rules check for Fields of Fire Deluxe (Series Rules 3rd Edition).

Usage:  python3 tool/fof.py <command> [arguments]   (run from the project folder)
Every change is saved only if the consistency check finds no error; an illegal step comes back as
VIOLATION with a rule citation and nothing is saved. VOF, PDF and Crossfire are derived from the units'
fire targets (6.1 to 6.3), not tracked by hand. Open rules questions are options in the setup JSON
("optionen") and appear in the output as [open Ux]. Action ids follow the Action Menus (4.2.2a Move,
4.2.2c Infiltrate, 4.2.3a Rally, 4.2.4a Spot, 4.2.4d Grenade Attack, 4.2.4i Call for Fire, ...).

Commands:"""


# One table for everything the command line knows about a command: English name, German name (the engine's
# dispatch key, still accepted on the command line), handler, usage and a one-line description.
# Handler None: handled directly in main() (needs no game state or prints the briefing).
COMMANDS = [
    # (english, german, handler, usage, description)
    ("new", "neu", None, "new <setup.json> [game]", "create a game from a mission setup file"),
    ("status", "stand", None, "status", "board briefing (also written to <game>/BRIEFING.md)"),
    ("check", "pruefung", None, "check", "consistency check of the game state (CHECKSTAMP line)"),
    ("help", "hilfe", None, "help [<command>]", "list the commands or show one command's usage"),
    ("rule", "regel", None, "rule <no>", "rule text from your own rule index (build_rules_index.py)"),
    ("search", "suche", None, "search <term>", "search the rule texts"),
    ("options", "optionen", "setup.cmd_options", "options", "open rules questions (Ux) and the chosen reading"),
    ("note", "notiz", "setup.cmd_note", "note <text>", "free-text protocol entry"),
    # setup before turn 1
    (
        "terrain",
        "terrain",
        "setup.cmd_terrain",
        "terrain <card> <type> [--no=..] [--hill=n] [--edges=top:white,..] [--cc=..]",
        "enter a random terrain card (2.2.1)",
    ),
    (
        "extend",
        "erweitern",
        "setup.cmd_extend",
        "extend <row> <column> <type> [...]",
        "map extension (8.4.5), off-limits to US units outside the boundaries",
    ),
    (
        "objective",
        "ziel",
        "setup.cmd_objective",
        "objective primary|secondary|ap|ccp|concentration|route|cop|phaseline ...",
        "Tactical Controls (2.4.1)",
    ),
    ("set", "werte", "setup.cmd_values", "set <unit> field=value ...", "enter unverified counter values before turn 1"),
    (
        "setup",
        "aufstellen",
        "setup.cmd_setup",
        "setup <unit> <card> [--area=C1|open] [--platoon=1|2|3|none] [--net=radio|phone] [--mortar=section|teams] [--asset=<type>] [--lines=n] [--pyro=<type>:<code>]",
        "starting setup, attachments and assets (2.3.3, 2.3.5)",
    ),
    (
        "multistory",
        "mehrstoeckig",
        "setup.cmd_multistory",
        "multistory <card>",
        "record the Multi-Story symbol of a card, add the Upper Story marker (5.3.3)",
    ),
    (
        "visibility",
        "sicht",
        "setup.cmd_visibility",
        "visibility [<light> [<weather>] [--this-turn-only=yes]]",
        "visibility modifier (9.0); +2 or more is Limited Visibility (9.1)",
    ),
    (
        "illum",
        "illum",
        "setup.cmd_illum",
        "illum <card> <top> [<bottom>] [--origin=..] | illum <card> remove",
        "illumination marker (9.2), removed in Clean Up",
    ),
    # sequence of play
    (
        "phase",
        "phase",
        "phase.cmd_phase",
        "phase next | phase <id>",
        "step through the sequence of play; segments with automation: 3.4.2, 3.5.x, 3.7.x",
    ),
    (
        "event",
        "ereignis",
        "events.cmd_event",
        "event <card no> yes <R#> [--who=..] | event <card no> no",
        "Higher HQ events (3.1, 3.4.1)",
    ),
    ("endturn", "rundenende", "phase.cmd_end_turn", "endturn", "3.8 Clean Up and the next turn"),
    # friendly command phase
    ("activate", "aktivieren", "commands.cmd_activate", "activate <hq>", "4.2.1a in the BN HQ / CO HQ impulse"),
    ("hq", "hq", "commands.cmd_hq", "hq <hq>", "choose the active HQ of the impulse"),
    (
        "card",
        "karte",
        "commands.cmd_card",
        "card <no> <helmet or star number> [--raw]",
        "Command draw (4.1.2); the tool says which number applies",
    ),
    ("gi", "gi", "commands.cmd_gi", "gi <no> <star number> [--skill-from=<HQ>]", "General Initiative (3.3.2d)"),
    (
        "order",
        "befehl",
        "commands.cmd_order",
        "order <hq|GI|BN> <unit> <action id> [--target=K] [--success=yes|no] [--area=<cover id|open>] [--unit=..] [--agency=..] [--skill=..] [--originator=<hq>] [--short=yes] [--critical=yes] [--place=K] [--what=..]",
        "one action of the action menu (4.2); the tool states how many cards to draw",
    ),
    (
        "lateorder",
        "nachtrag",
        "commands.cmd_late_order",
        "lateorder <hq> <unit> <action id> [...]",
        "forgotten order of an HQ whose impulse already ended this turn",
    ),
    ("done", "fertig", "commands.cmd_done", "done", "end the impulse, save Commands"),
    ("retreat", "rueckzug", "phase.cmd_retreat", "retreat <unit> [<card>]", "3.5.2 retreat of a Paralyzed/Litter Team"),
    (
        "undo",
        "zurueck",
        "state.cmd_undo",
        "undo <entry no> --reason=..",
        "back to the state after protocol entry <no> (snapshots of the last 40 entries); lists the discarded entries",
    ),
    (
        "fire",
        "feuer",
        "commands.cmd_fire",
        "fire <unit> <card|off>",
        "set a fire target by hand (random decision, correction)",
    ),
    (
        "correct",
        "korrektur",
        "commands.cmd_correct",
        "correct casualty <card> <+n|-n> [--side=Feind|US] --reason=.. | correct status <unit> <marker> remove|add --reason=.. | correct grenade <unit> expired <origin card> --reason=.. | correct ammo <unit> <+n|-n> --reason=.. | correct target <unit> <card> --reason=..",
        "fix a proven wrong booking (the board is the master)",
    ),
    # enemy
    (
        "enemycheck",
        "feindcheck",
        "enemy.cmd_enemy_check",
        "enemycheck",
        "3.4.2: hierarchy row and R# column for every enemy",
    ),
    (
        "enemyaction",
        "feindaktion",
        "enemy.cmd_enemy_action",
        'enemyaction <enemy> "<result>" [--target=K] [--success=yes|no] [--unit=<target>]',
        "carry out one enemy activity result",
    ),
    (
        "pc",
        "pc",
        "contact.cmd_pc",
        "pc [<card>] | pc reveal <card> <A|B|C> | pc set <card> <A|B|C|?> | pc clear <card> | pc contact <card> <package> [--direction=Front|Left|Right] [--place=K] [--type=..] [--variant=..]",
        "potential contact and enemy placement (8.2 to 8.4)",
    ),
    (
        "external",
        "extern",
        "contact.cmd_external",
        "external <card> Incoming|Mines|AirStrike|Smoke|Pending <value> | external <card> remove",
        "external VOF markers by hand",
    ),
    (
        "enemy",
        "feind",
        "contact.cmd_enemy",
        "enemy <name> spotted|unspotted|pinned|unpinned|remove|karte=K|cover=<id>|steps=n",
        "correct an enemy counter by hand",
    ),
    ("mine", "mine", "contact.cmd_mine", "mine <unit> yes|no", "result of a mine check (7.9.1)"),
    ("sniper", "sniper", "enemy.cmd_sniper", "sniper <sniper> <target>", "target of the sniper VOF in 3.7.4 (7.15)"),
    ("capture", "gefangen", "combat.cmd_capture", "capture <enemy> <guard>", "take prisoners (3.5.1, 8.15)"),
    # combat
    ("ncm", "ncm", "combat.cmd_ncm", "ncm <unit>", "net combat modifier of one unit (6.4)"),
    (
        "hit",
        "treffer",
        "combat.cmd_hit",
        "hit <unit> HIT|PIN|MISS [<effect letters>]",
        "combat result and hit effects (6.4.2, 6.4.3)",
    ),
    ("ammo", "munition", "combat.cmd_ammo", "ammo [depot <card> <type> <n>]", "ammunition overview and depots (7.18)"),
    # communication and assets
    (
        "radio",
        "funk",
        "setup.cmd_radio",
        "radio | radio check <hq> [<unit>] | radio damage <card> <device> intact|destroyed",
        "communication overview and checks (4.3, 4.3.5)",
    ),
    ("line", "leitung", "comms.cmd_line", "line <card> ok|cut | line lay <card>", "phone lines (4.3.4)"),
    ("runner", "runner", "comms.cmd_runner", "runner", "runner overview (4.3.2); orders 4.2.1f/g/h"),
    (
        "drop",
        "ablegen",
        "setup.cmd_drop",
        "drop <unit> <Casualty|asset|device|Leitung[:n]|AMMO:n>",
        "drop something without a Command (5.1.6B)",
    ),
    # campaign
    ("xp", "xp", "campaign.cmd_xp", "xp [add <n> <reason> | spend <n> <reason>]", "experience log (12.1)"),
    ("reattempt", "reattempt", "campaign.cmd_reattempt", "reattempt [done]", "mission reattempt (3.9)"),
    (
        "reconstitute",
        "rekon",
        "campaign.cmd_reconstitute",
        "reconstitute <unit> --from=<LAT,..> [--experience=..]",
        "reconstitute a unit from LATs between missions",
    ),
    ("campaign", "kampagne", "campaign.cmd_campaign", "campaign", "Mission Log (2.3.1, 12.2)"),
    (
        "patrol",
        "patrouille",
        "campaign.cmd_patrol",
        "patrol [start|next <platoon> [--with=a,b]]",
        "Combat Patrol (2.6, Normandy M3 MSR 1-4)",
    ),
]
CMD_ALIASES = {en: de for en, de, *_ in COMMANDS}
BY_GERMAN = {de: (en, de, handler, usage, desc) for en, de, handler, usage, desc in COMMANDS}


SUBWORD_ALIASES = {  # per (German) command: English positional word -> German word
    "phase": {"next": "weiter"},
    "patrouille": {"next": "naechste"},
    "reattempt": {"done": "fertig"},
    "xp": {"add": "plus", "spend": "ausgeben"},
    "pc": {"reveal": "aufdecken", "set": "setzen", "clear": "frei", "contact": "kontakt"},
    "ziel": {"primary": "primaer", "secondary": "sekundaer", "concentration": "konzentration"},
    "leitung": {"lay": "legen"},
    "funk": {"check": "pruefen", "damage": "schaden", "intact": "heil", "destroyed": "zerstoert"},
    "feuer": {"off": "aus"},
    "extern": {"remove": "weg"},
    "feind": {"remove": "weg"},
    "illum": {"remove": "weg"},
    "munition": {"depot": "lager"},
    "ereignis": {"yes": "ja", "no": "nein"},
    "mine": {"yes": "ja", "no": "nein"},
    "korrektur": {
        "grenade": "granate",
        "ammo": "munition",
        "target": "ziel",
        "expired": "verfallen",
        "remove": "weg",
        "add": "dazu",
    },
}


def argv_to_german(argv):
    """Translate an English command line into the engine's German command line (German input passes unchanged)."""
    if not argv:
        return argv
    cmd = CMD_ALIASES.get(argv[0], argv[0])
    sub = SUBWORD_ALIASES.get(cmd, {})
    out = [cmd]
    for a in argv[1:]:
        if a.startswith("--"):
            k, eq, v = a.partition("=")
            k = options.OPT_ALIASES.get(k, k)
            if eq and k == "--raender":
                for en_, de_ in (
                    ("top", "oben"),
                    ("bottom", "unten"),
                    ("left", "links"),
                    ("right", "rechts"),
                    ("white", "weiss"),
                    ("green", "gruen"),
                    ("dark", "gruen"),
                    ("corner", "diagonal"),
                ):
                    v = v.replace(en_, de_)
            elif eq:
                v = (
                    ",".join(options.VALUE_ALIASES.get(x, x) for x in v.split(","))
                    if k in ("--richtung",)
                    else options.VALUE_ALIASES.get(v, v)
                )
            out.append(k + eq + v)
        else:
            out.append(sub.get(a, a))
    return out


def cmd_rule(args):
    idx = json.loads((state.DATA / "regelindex.json").read_text(encoding="utf-8"))
    company_ = (state.DATA / "regelbuch_kompakt.txt").read_text(encoding="utf-8").split("\n")
    nr = args[0]
    if nr not in idx:
        sys.exit(f"Rule {nr} not in the index. Example: 4.2.2a is part of 4.2.2.")
    start = idx[nr]["zeile_kompakt"]
    following = sorted(
        (v["zeile_kompakt"], k) for k, v in idx.items() if v["zeile_kompakt"] and v["zeile_kompakt"] > start
    )
    end = following[0][0] if following else start + 40
    print(f"[RULE {nr} p.{idx[nr]['seite']}] {idx[nr]['titel']}")
    print("\n".join(company_[start - 1 : min(end - 1, start + 80)]))
    cl = (state.DATA / "clarifications_2025_05_kompakt.txt").read_text(encoding="utf-8")
    main_ = ".".join(nr.split(".")[:2])
    if re.search(r"\b" + re.escape(nr) + r"\b", cl) or re.search(r"\b" + re.escape(main_) + r"\b", cl):
        print(f"\nNOTE: Clarifications May 2025 mention {main_}/{nr}; see data/clarifications_2025_05_kompakt.txt")


def cmd_search(args):
    rx = re.compile(re.escape(" ".join(args)), re.I)
    for f in sorted(state.DATA.glob("*_kompakt.txt")):
        for i, l in enumerate(f.read_text(encoding="utf-8").split("\n"), 1):
            if rx.search(l):
                print(f"{f.name}:{i}: {l.strip()[:140]}")


def resolve(handler):
    """'module.function' -> callable (modules are imported lazily, so the table stays plain data)."""
    mod, _, fn = handler.partition(".")
    return getattr(importlib.import_module("." + mod, __package__), fn)


def cmd_help(args):
    if args:
        key = CMD_ALIASES.get(args[0], args[0])
        if key not in BY_GERMAN:
            raise rules.Violation(f"Unknown command {args[0]}; fof.py help lists the commands")
        en, de, _, usage, desc = BY_GERMAN[key]
        print(f"{en}" + (f" (German: {de})" if de != en else ""))
        print(f"  {usage}")
        print(f"  {desc}")
        return
    print(USAGE)
    width = max(len(en) for en, *_ in COMMANDS)
    for en, de, _, usage, desc in COMMANDS:
        print(f"  {en:<{width}}  {desc}")
    print("\nfof.py help <command> shows the usage of one command. German command names work too.")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        cmd_help([])
        return
    cmd, *args = argv_to_german(argv)
    try:
        if cmd == "hilfe":
            return cmd_help(args)
        if cmd == "neu":
            return phase.cmd_new(args)
        if cmd == "regel":
            return cmd_rule(args)
        if cmd == "suche":
            return cmd_search(args)
        if cmd not in BY_GERMAN:
            raise rules.Violation(f"Unknown command {cmd}; fof.py help lists the commands")
        s = state.load_state()
        if cmd == "stand":
            print(briefing.briefing(s))
        elif cmd == "pruefung":
            print(briefing.check_stamp(s))
        else:
            resolve(BY_GERMAN[cmd][2])(s, args)
    except rules.Violation as v:
        print(f"{messages.VIOLATION}: " + str(v))
        sys.exit(2)
    except FileNotFoundError as e:
        print(f"{messages.VIOLATION}: file not found: {e.filename}")
        sys.exit(2)
    except BrokenPipeError:
        pass
