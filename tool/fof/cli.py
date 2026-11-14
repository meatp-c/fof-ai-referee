"""Command line: usage text, English command aliases, dispatch table, rule lookup."""

import importlib
import json
import os
import re
import shlex
import sys

from . import (
    briefing,
    messages,
    migrate,
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
("options") and appear in the output as [open Ux]. Action ids follow the Action Menus (4.2.2a Move,
4.2.2c Infiltrate, 4.2.3a Rally, 4.2.4a Spot, 4.2.4d Grenade Attack, 4.2.4i Call for Fire, ...).

Commands:"""


# One table for everything the command line knows about a command: name (the dispatch key), handler, usage and a
# one-line description. The German names are aliases in migrate.COMMANDS_DE.
# Handler None: handled directly in main() (needs no game state or prints the briefing).
COMMANDS = [
    # (name, handler, usage, description)
    ("new", None, "new <setup.json> [game] [--force]", "create a game from a mission setup file"),
    ("status", None, "status", "board briefing (also written to <game>/BRIEFING.md)"),
    ("check", None, "check", "consistency check of the game state (CHECKSTAMP line)"),
    ("help", None, "help [<command>]", "list the commands or show one command's usage"),
    ("rule", None, "rule <no>", "rule text from your own rule index (build_rules_index.py)"),
    ("search", None, "search <term>", "search the rule texts"),
    ("options", "setup.cmd_options", "options", "open rules questions (Ux) and the chosen reading"),
    ("note", "setup.cmd_note", "note <text>", "free-text protocol entry"),
    (
        "names",
        "setup.cmd_names",
        "names lat card|numbered",
        "generic teams by counter type and card (AT 45, FT 33, P 55, L 42) or numbered (Assault Team 3)",
    ),
    # setup before turn 1
    (
        "terrain",
        "setup.cmd_terrain",
        "terrain <card> <type> [--no=..] [--hill=n] [--edges=top:white,..] [--cc=..]",
        "enter a random terrain card (2.2.1)",
    ),
    (
        "extend",
        "setup.cmd_extend",
        "extend <row> <column> <type> [--hill=n] [--edges=..] [--no=..]",
        "map extension (8.4.5), off-limits to US units outside the boundaries",
    ),
    (
        "objective",
        "setup.cmd_objective",
        "objective primary|secondary|ap|ccp|cop <card> | objective route <1-4> <card> | objective concentration <card> <fire asset> | objective phaseline <n> <row> | objective fortify <card> foxholes|deepbunker",
        "Tactical Controls (2.4.1)",
    ),
    (
        "set",
        "setup.cmd_values",
        "set <unit> field=value ... [--reason=..]",
        "enter counter values (before turn 1, during play only with --reason)",
    ),
    (
        "setup",
        "setup.cmd_setup",
        "setup <unit> <card> [--area=C1|open] [--platoon=1|2|3|none] [--net=radio|phone] [--mortar=section|teams] [--jeep=yes|no] [--asset=<type>] [--lines=n] [--pyro=<type>:<code>]",
        "starting setup, attachments and assets (2.3.3, 2.3.5)",
    ),
    (
        "multistory",
        "setup.cmd_multistory",
        "multistory <card>",
        "record the Multi-Story symbol of a card, add the Upper Story marker (5.3.3)",
    ),
    (
        "visibility",
        "setup.cmd_visibility",
        "visibility [<light> [<weather>] [--this-turn-only=yes]]",
        "visibility modifier (9.0); +2 or more is Limited Visibility (9.1)",
    ),
    (
        "illum",
        "setup.cmd_illum",
        "illum <card> <top> [<bottom>] [--origin=..] | illum <card> remove",
        "illumination marker (9.2), removed in Clean Up",
    ),
    # sequence of play
    (
        "phase",
        "phase.cmd_phase",
        "phase next | phase <id>",
        "step through the sequence of play; segments with automation: 3.4.2, 3.5.x, 3.7.x",
    ),
    (
        "event",
        "events.cmd_event",
        "event <card no> yes <R#> [--who=..] | event <card no> no",
        "Higher HQ events (3.1, 3.4.1)",
    ),
    ("endturn", "phase.cmd_end_turn", "endturn", "3.8 Clean Up and the next turn"),
    (
        "heat",
        "events.cmd_heat",
        "heat <unit> <R#/4 1-4>|yes|no",
        "Heat Casualties draw, R#/4 = 1 is a loss (Naktong M1 event)",
    ),
    # friendly command phase
    ("activate", "commands.cmd_activate", "activate <hq>", "4.2.1a in the BN HQ / CO HQ impulse"),
    ("hq", "commands.cmd_hq", "hq <hq>", "choose the active HQ of the impulse"),
    (
        "card",
        "commands.cmd_card",
        "card <no> <helmet or star number> [--raw]",
        "Command draw (4.1.2); the tool says which number applies",
    ),
    (
        "gi",
        "commands.cmd_gi",
        "gi <no> <star number> [--skill-from=<HQ>] | gi skill <HQ>",
        "General Initiative (3.3.2d)",
    ),
    (
        "order",
        "commands.cmd_order",
        "order <hq|GI|BN> <unit> <action id> [--target=K] [--success=yes|no] [--area=<cover id|open>] [--unit=..] [--agency=..] [--skill=..] [--originator=<hq>] [--short=yes] [--critical=yes] [--place=K] [--what=..]",
        "one action of the action menu (4.2); the tool states how many cards to draw",
    ),
    (
        "lateorder",
        "commands.cmd_late_order",
        "lateorder <hq> <unit> <action id> [...]",
        "forgotten order of an HQ whose impulse already ended this turn",
    ),
    ("done", "commands.cmd_done", "done", "end the impulse, save Commands"),
    ("retreat", "phase.cmd_retreat", "retreat <unit> [<card>]", "3.5.2 retreat of a Paralyzed/Litter Team"),
    (
        "undo",
        "history.cmd_undo",
        "undo <entry no> --reason=..",
        "back to the state after protocol entry <no> (snapshots of the last 40 entries); lists the discarded entries",
    ),
    (
        "fire",
        "commands.cmd_fire",
        "fire <unit> <card|off>",
        "set a fire target by hand (random decision, correction)",
    ),
    (
        "correct",
        "commands.cmd_correct",
        "correct casualty <card> <+n|-n> [--side=Enemy|US] --reason=.. | correct status <unit> <marker> remove|add --reason=.. | correct grenade <unit> expired <origin card> --reason=.. | correct ammo <unit> <+n|-n> --reason=.. | correct target <unit> <card> --reason=.. | correct number <card> <card number> --reason=..",
        "fix a proven wrong booking (the board is the master)",
    ),
    # enemy
    (
        "enemycheck",
        "enemy.cmd_enemy_check",
        "enemycheck",
        "3.4.2: hierarchy row and R# column for every enemy",
    ),
    (
        "enemyaction",
        "enemy.cmd_enemy_action",
        'enemyaction <enemy> "<result>" [--target=K] [--success=yes|no] [--unit=<target>]',
        "carry out one enemy activity result",
    ),
    (
        "pc",
        "contact.cmd_pc",
        "pc [<card>] | pc reveal <card> <A|B|C> | pc set <card> <A|B|C|?> | pc clear <card> | pc contact <card> <package> [--direction=Front|Left|Right] [--place=K] [--type=..] [--variant=..]",
        "potential contact and enemy placement (8.2 to 8.4)",
    ),
    (
        "external",
        "contact.cmd_external",
        "external <card> Incoming|Mines|AirStrike|Smoke|Pending <value> | external <card> remove",
        "external VOF markers by hand",
    ),
    (
        "enemy",
        "contact.cmd_enemy",
        "enemy <name> spotted|unspotted|pinned|unpinned|remove|card=K|cover=<id>|steps=n",
        "correct an enemy counter by hand",
    ),
    ("mine", "contact.cmd_mine", "mine <unit> yes|no", "result of a mine check (7.9.1)"),
    ("sniper", "enemy.cmd_sniper", "sniper <sniper> <target>", "target of the sniper VOF in 3.7.4 (7.15)"),
    ("capture", "combat.cmd_capture", "capture <enemy> <guard>", "take prisoners (3.5.1, 8.15)"),
    (
        "grenade",
        "grenades.cmd_grenade",
        "grenade response <responder> --success=yes|no [--critical=yes]",
        "7.10.5 free Grenade Attack response after a Point Blank attack (no Command)",
    ),
    # combat
    (
        "ncm",
        "combat.cmd_ncm",
        "ncm <unit> | ncm next",
        "net combat modifier of one unit (6.4); 'next' = next Combat Effects group as a numbered list (3.7.4)",
    ),
    (
        "hit",
        "combat.cmd_hit",
        "hit <unit> HIT|PIN|MISS [<effect letters>]",
        "combat result and hit effects (6.4.2, 6.4.3)",
    ),
    ("ammo", "combat.cmd_ammo", "ammo [depot <card> <type> <n>]", "ammunition overview and depots (7.18)"),
    # communication and assets
    (
        "radio",
        "setup.cmd_radio",
        "radio | radio check <hq> [<unit>] | radio damage <card> <device> intact|destroyed",
        "communication overview and checks (4.3, 4.3.5)",
    ),
    ("line", "comms.cmd_line", "line <card> ok|cut | line lay <card> <unit>", "phone lines (4.3.4)"),
    ("runner", "comms.cmd_runner", "runner", "runner overview (4.3.2); orders 4.2.1f/g/h"),
    (
        "drop",
        "setup.cmd_drop",
        "drop <unit> <Casualty|asset|device|Line[:n]|MG:n|MTR:n|RKT:n|RCL:n>",
        "drop something without a Command (5.1.6B)",
    ),
    # campaign
    (
        "xp",
        "campaign.cmd_xp",
        "xp [add <n> <reason> | spend <n> <reason> | promote <unit> --from=Green|Line --steps=n | skill <HQ> <skill>]",
        "experience log (12.1)",
    ),
    ("reattempt", "campaign.cmd_reattempt", "reattempt [done]", "mission reattempt (3.9)"),
    (
        "reconstitute",
        "campaign.cmd_reconstitute",
        "reconstitute <unit> --from=<LAT,..> [--experience=..]",
        "reconstitute a unit from LATs between missions",
    ),
    ("campaign", "campaign.cmd_campaign", "campaign", "Mission Log (2.3.1, 12.2)"),
    (
        "vehicle",
        "vehicles.cmd_vehicle",
        "vehicle [status] | move <v> <card> [--area=] | fire <unit> <target> | cf <v> --unit= --success= | spot <v> --target= --success= | done <unit> | enemy [--unit=] [--target=] | target <R#> | react <unit> <target> | traffic <terrain> normal|slow|no",
        "vehicle actions in the AT Combat & Vehicle Movement Phase 3.6 (10.5)",
    ),
    (
        "at",
        "vehicles.cmd_at",
        "at <AT number>|:<card no>|grenade yes|no|again|stop",
        "resolve the open AT draw (10.5.3, 10.6)",
    ),
    (
        "patrol",
        "campaign.cmd_patrol",
        "patrol [start|next <platoon> [--with=a,b]]",
        "Combat Patrol (2.6, Normandy M3 MSR 1-4)",
    ),
]
BY_NAME = {en: (en, handler, usage, desc) for en, handler, usage, desc in COMMANDS}
DE_COMMANDS = migrate.COMMANDS_DE  # German command names, accepted as aliases

# Minimum number of positional (non --option) arguments, checked once in main() against the usage of the table.
# Only commands whose every form needs these arguments; forms that depend on a sub-word are checked in
# their handlers, with the same usage text (usage()).
MIN_ARGS = {
    "new": 1,
    "rule": 1,
    "search": 1,
    "note": 1,
    "terrain": 2,
    "extend": 3,
    "objective": 2,
    "set": 2,
    "setup": 1,
    "multistory": 1,
    "illum": 2,
    "undo": 1,
    "line": 2,
    "drop": 2,
    "reconstitute": 1,
}
assert set(MIN_ARGS) <= set(BY_NAME), "MIN_ARGS keys are English command names"


def usage(command):
    """Usage text of a command (English or German name) from the command table: the one source for handlers."""
    return BY_NAME[DE_COMMANDS.get(command, command)][2]


def check_min_args(cmd, args):
    """cmd: English command name; a Violation with the usage if positional arguments are missing."""
    rules.need([a for a in args if not a.startswith("--")], MIN_ARGS.get(cmd, 0), usage(cmd))


# positions (among the positional arguments) where a sub-word may stand; everything else is free
# text or a name and is passed unchanged ('xp add 2 we did spend ...' keeps its reason)
SUBWORD_POSITIONS = {"xp": {0}, "correct": {0, 2, 3}, "note": set(), "search": set(), "rule": set()}
SUBWORD_POSITIONS_DEFAULT = {0, 1}


def normalize_argv(argv):
    """Command line in the engine's words: German command names, sub-command words (migrate.WORDS), option names and
    option values (options.parse_opts) become English; English input passes unchanged."""
    if not argv:
        return argv
    cmd = DE_COMMANDS.get(argv[0], argv[0])
    out = [cmd]
    where = SUBWORD_POSITIONS.get(cmd, SUBWORD_POSITIONS_DEFAULT)
    pos = 0
    for a in argv[1:]:
        if a.startswith("--"):
            k, eq, v = a.partition("=")
            k = options.OPT_ALIASES.get(k, k)
            out.append(k + eq + (options.english_value(k, v) if eq else ""))
        else:
            out.append(migrate.WORDS.get(a, a) if pos in where else a)
            pos += 1
    return out


def cmd_rule(args):
    rules.need(args, 1, usage("rule"))
    idx = migrate.rule_index(json.loads(state.data_file("rule_index.json").read_text(encoding="utf-8")))
    compact_text = state.data_file("rulebook_compact.txt").read_text(encoding="utf-8").split("\n")
    num = args[0]
    if num not in idx:
        sys.exit(f"Rule {num} not in the index. Example: 4.2.2a is part of 4.2.2.")
    start = idx[num].get("line_compact")
    if not start:  # an index entry without a line in the compact text (line_compact null)
        raise rules.Violation(
            f"Rule {num} ({idx[num].get('title', '?')}, p.{idx[num].get('page', '?')}) has no line in the compact rule text; "
            "look it up in the rulebook or with fof.py search"
        )
    following = sorted(
        (v["line_compact"], k) for k, v in idx.items() if v["line_compact"] and v["line_compact"] > start
    )
    end = following[0][0] if following else start + 40
    print(f"[RULE {num} p.{idx[num]['page']}] {idx[num]['title']}")
    print("\n".join(compact_text[start - 1 : min(end - 1, start + 80)]))
    cl_file = state.data_file("clarifications_2025_05_compact.txt")
    cl = cl_file.read_text(encoding="utf-8")
    main_ = ".".join(num.split(".")[:2])
    if re.search(r"\b" + re.escape(num) + r"\b", cl) or re.search(r"\b" + re.escape(main_) + r"\b", cl):
        print(f"\nNOTE: Clarifications May 2025 mention {main_}/{num}; see data/{cl_file.name}")


def cmd_search(args):
    if not " ".join(args).strip():  # an empty term matched every line of the corpus
        raise rules.Violation(f"Usage: {usage('search')}")
    rx = re.compile(re.escape(" ".join(args)), re.I)
    files = {}
    for suffix in reversed(migrate.COMPACT_SUFFIX):  # a text under the new name wins over the old one
        for f in state.DATA.glob("*" + suffix):
            files[f.name[: -len(suffix)]] = f
    for f in sorted(files.values()):
        for i, l in enumerate(f.read_text(encoding="utf-8").split("\n"), 1):
            if rx.search(l):
                print(f"{f.name}:{i}: {l.strip()[:140]}")


def cmd_new(args):
    """'new' refuses a game folder that already holds a game state unless --force is given;
    phase.cmd_new gets the positional arguments only."""
    o = options.parse_opts(args)
    pos = [a for a in args if not a.startswith("--")]
    name = migrate.env("FOF_GAME", os.environ) or (pos[1] if len(pos) > 1 else state.DEFAULT_GAME)  # as phase.cmd_new
    state.check_new_game_folder(name, bool(o.get("--force")))
    return phase.cmd_new(pos)


def resolve(handler):
    """'module.function' -> callable (modules are imported lazily, so the table stays plain data)."""
    mod, _, fn = handler.partition(".")
    return getattr(importlib.import_module("." + mod, __package__), fn)


def cmd_help(args):
    if args:
        key = DE_COMMANDS.get(args[0], args[0])
        if key not in BY_NAME:
            raise rules.Violation(f"Unknown command {args[0]}; fof.py help lists the commands")
        en, _, usage, desc = BY_NAME[key]
        de = [g for g, e in DE_COMMANDS.items() if e == en]
        print(f"{en}" + (f" (German: {', '.join(de)})" if de else ""))
        print(f"  {usage}")
        print(f"  {desc}")
        return
    print(USAGE)
    width = max(len(en) for en, *_ in COMMANDS)
    for en, _, usage, desc in COMMANDS:
        print(f"  {en:<{width}}  {desc}")
    print("\nfof.py help <command> shows the usage of one command. German command names work too.")


def _state_stamp():
    try:
        st = state.state_path().stat()
        return st.st_mtime_ns, st.st_size
    except OSError:
        return None


def log_command(argv, before):
    """A command that changed the game goes into <game>/commands.txt as typed, one line each: the game can be
    replayed from it (python3 tool/fof.py <line>). Never blocks the game."""
    after = _state_stamp()
    if after is None or after == before:
        return
    try:
        with (state.game_dir() / state.COMMAND_LOG).open("a", encoding="utf-8") as f:
            f.write(shlex.join(argv) + "\n")
    except OSError:
        pass


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        cmd_help([])
        return
    before = _state_stamp()
    try:
        _dispatch(argv)
    finally:
        log_command(argv, before)


def _dispatch(argv):
    cmd, *args = normalize_argv(argv)
    try:
        if cmd not in BY_NAME:
            raise rules.Violation(f"Unknown command {cmd}; fof.py help lists the commands")
        # step.py options given to fof.py were silently ignored and the step was booked for real
        runner_opts = [
            a
            for a in args
            if options.OPT_ALIASES.get(*[a.partition("=")[0]] * 2) in ("--probe", "--all", "--msg", "--game")
        ]
        if runner_opts:
            raise rules.Violation(
                f"{', '.join(runner_opts)} is an option of step.py, not of fof.py (fof.py books directly); "
                "nothing booked. Probe with: python3 tool/step.py --probe <<'EOF' ... EOF"
            )
        check_min_args(cmd, args)
        if cmd == "help":
            return cmd_help(args)
        if cmd == "new":
            return cmd_new(args)
        if cmd == "rule":
            return cmd_rule(args)
        if cmd == "search":
            return cmd_search(args)
        s = state.load_state()
        if cmd == "status":
            print(briefing.briefing(s))
        elif cmd == "check":
            print(briefing.check_stamp(s))
        else:
            resolve(BY_NAME[cmd][1])(s, args)
    except rules.Pending as v:
        print(f"{messages.OPEN}: " + str(v))
    except rules.Violation as v:
        print(f"{messages.VIOLATION}: " + str(v))
        sys.exit(2)
    except FileNotFoundError as e:
        print(f"{messages.VIOLATION}: file not found: {e.filename}")
        sys.exit(2)
    except BrokenPipeError:
        pass
