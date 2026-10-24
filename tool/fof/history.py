"""Undo: back to a snapshot of the protocol history (verlauf/<n>.json). A CLI handler, kept out of state.py (review
Struktur 10); the snapshots themselves are written by state.save_snapshot."""

import json

from . import briefing, options, rules, state


def cmd_undo(s, args):
    """Back to the state after protocol entry N; the discarded entries are listed so the board can be reset."""
    from . import cli  # lazy: the usage text lives in the command table (cli imports the handlers lazily as well)

    if not args or not args[0].isdigit():
        raise rules.Violation(cli.usage("undo"))
    nr = int(args[0])
    o = options.parse_opts(args[1:])
    last = len(s["protokoll"])
    if not 0 < nr < last:
        raise rules.Violation(f"Entry {nr} is not before the last entry {last}")
    snap = state.game_dir() / state.HISTORY_DIR / f"{nr}.json"
    if not snap.exists():
        raise rules.Violation(
            f"No snapshot for entry {nr} (kept: the last {state.HISTORY_KEEP} entries since the history started)"
        )
    old = json.loads(snap.read_text(encoding="utf-8"))
    dropped = s["protokoll"][nr:]
    reason = options.text_opt(o, "--grund", cli.usage("undo"), "")
    text = (
        f"Undo to entry {nr}"
        + (f" ({reason})" if reason else "")
        + "; discarded: "
        + "; ".join(f"{p['nr']} {p['text'][:80]}" for p in dropped)
    )
    state.save_state(old, text, None)
    print(f"Back to the state after entry {nr}. Discarded entries (reset these on the board):")
    for p in dropped:
        print(f"- {p['nr']} T{p['zug']} {p['phase']}: {p['text']}")
    print(briefing.check_stamp(old))
