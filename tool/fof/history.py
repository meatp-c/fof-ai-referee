"""Undo: back to a snapshot of the protocol history (history/<n>.json). A CLI handler, kept out of state.py;
the snapshots themselves are written by state.save_snapshot and read by state.load_snapshot."""

from . import briefing, options, rules, state


def cmd_undo(s, args):
    """Back to the state after protocol entry N; the discarded entries are listed so the board can be reset."""
    from . import cli  # lazy: the usage text lives in the command table (cli imports the handlers lazily as well)

    if not args or not args[0].isdigit():
        raise rules.Violation(cli.usage("undo"))
    num = int(args[0])
    o = options.parse_opts(args[1:])
    last = len(s["protocol"])
    if not 0 < num < last:
        raise rules.Violation(f"Entry {num} is not before the last entry {last}")
    try:
        old = state.load_snapshot(num, s["protocol"])
    except ValueError:
        raise rules.Violation(f"Snapshot {num} is damaged (not valid JSON); choose an earlier entry") from None
    if old is None:
        raise rules.Violation(
            f"No snapshot for entry {num} (kept: the last {state.HISTORY_KEEP} entries since the history started)"
        )
    if len(old.get("protocol", [])) != num:  # a reused old file under this number is not the state after entry number
        raise rules.Violation(
            f"Snapshot {num} holds the state after entry {len(old.get('protocol', []))}, not {num}; choose another entry"
        )
    dropped = s["protocol"][num:]
    reason = options.text_opt(o, "--reason", cli.usage("undo"), "")
    text = (
        f"Undo to entry {num}"
        + (f" ({reason})" if reason else "")
        + "; discarded: "
        + "; ".join(f"{p['number']} {p['text'][:80]}" for p in dropped)
    )
    state.save_state(old, text, None)
    print(f"Back to the state after entry {num}. Discarded entries (reset these on the board):")
    for p in dropped:
        print(f"- {p['number']} T{p['turn']} {p['phase']}: {p['text']}")
    print(briefing.check_stamp(old))
