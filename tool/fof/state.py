"""Game state: load/save, protocol, basic accessors for units and cards."""

import datetime
import json
import os
import pathlib
import sys

from . import briefing, rules


ROOT = pathlib.Path(__file__).resolve().parents[2]  # <project>/werkzeuge/fof/state.py -> <project>


DATA = ROOT / "data"


def game_dir():
    """Game folder: environment variable FOF_PARTIE (for tests, v3) before ROOT/.aktuelle_partie before 'partie1'."""

    if os.environ.get("FOF_PARTIE"):
        return ROOT / os.environ["FOF_PARTIE"]
    st = ROOT / ".aktuelle_partie"
    return ROOT / (st.read_text().strip() if st.exists() else "partie1")


def load_state():
    p = game_dir() / "spielstand.json"
    if not p.exists():
        sys.exit("No game state. First: fof.py new <aufbau.json>")
    return json.loads(p.read_text(encoding="utf-8"))


HISTORY_DIR = "verlauf"  # snapshots of the state after each protocol entry (for undo)
HISTORY_KEEP = 40


def save_snapshot(nr, text):
    """Keep the state after protocol entry nr as verlauf/<nr>.json; prune snapshots older than HISTORY_KEEP entries."""
    d = game_dir() / HISTORY_DIR
    try:
        d.mkdir(exist_ok=True)
        (d / f"{nr}.json").write_text(text, encoding="utf-8")
        for f in d.glob("*.json"):
            if f.stem.isdigit() and int(f.stem) < nr - HISTORY_KEEP:
                f.unlink()
    except OSError:
        pass  # history is a convenience; a read-only or no-delete folder must not block the game


def cmd_undo(s, args):
    """Back to the state after protocol entry N; the discarded entries are listed so the board can be reset."""
    from . import options

    if not args or not args[0].isdigit():
        raise rules.Violation("undo <entry no> --reason=..")
    nr = int(args[0])
    o = options.parse_opts(args[1:])
    last = len(s["protokoll"])
    if not 0 < nr < last:
        raise rules.Violation(f"Entry {nr} is not before the last entry {last}")
    snap = game_dir() / HISTORY_DIR / f"{nr}.json"
    if not snap.exists():
        raise rules.Violation(
            f"No snapshot for entry {nr} (kept: the last {HISTORY_KEEP} entries since the history started)"
        )
    old = json.loads(snap.read_text(encoding="utf-8"))
    dropped = s["protokoll"][nr:]
    reason = o.get("--grund", "")
    text = (
        f"Undo to entry {nr}"
        + (f" ({reason})" if reason else "")
        + "; discarded: "
        + "; ".join(f"{p['nr']} {p['text'][:80]}" for p in dropped)
    )
    save_state(old, text, None)
    print(f"Back to the state after entry {nr}. Discarded entries (reset these on the board):")
    for p in dropped:
        print(f"- {p['nr']} T{p['zug']} {p['phase']}: {p['text']}")
    print(briefing.check_stamp(old))


MARKER_NOTES = []  # VOF/Crossfire marker changes of the last save, printed before the CHECKSTAMP (L111)


def marker_summary(s):
    """Per card: the VOF marker on the board (strongest VOF, 6.2.2/FM1 p.44) and whether a Crossfire marker lies there."""
    from . import fire

    out = {}
    for k in s["karten"]:
        entries = fire.vof_entries(s, k)
        best = min(entries, key=lambda x: x[1]) if entries else None
        cf = fire.crossfire(s, k, "Feind") or fire.crossfire(s, k, "US")
        if best or cf:
            out[k] = ((best[0], best[1]) if best else None, cf)
    return out


def mutual_pdfs(s):
    """Pairs of cards whose units fire at each other along a PDF (V16)."""
    pdf = set()
    for e in s["einheiten"].values():
        z = e.get("ziel")
        if z and z != e.get("karte") and not e.get("indirekt"):
            pdf.add((e["karte"], z))
    return {tuple(sorted(p)) for p in pdf if (p[1], p[0]) in pdf}


def marker_changes(old, new):
    """Board lines for every card whose VOF marker or Crossfire marker changed between two states (L111)."""

    def name(v):
        return f"{rules.VOF_NAME.get(v[0], v[0])} {v[1]:+d}" if v else "none"

    a, b = marker_summary(old), marker_summary(new)
    lines = []
    ma, mb = mutual_pdfs(old), mutual_pdfs(new)
    for x, y in sorted(mb - ma):
        lines.append(f"PDF {x} and {y} fire at each other: turn the PDF marker to the double-arrow side [6.3.1, V16]")
    for x, y in sorted(ma - mb):
        lines.append(f"PDF between {x} and {y} no longer mutual: turn the PDF marker back to the single arrow [6.3.1]")
    for k in sorted(set(a) | set(b)):
        va, ca = a.get(k, (None, False))
        vb, cb = b.get(k, (None, False))
        if va != vb:
            if vb is None:
                lines.append(f"{k}: remove the VOF marker ({name(va)})")
            elif va is None:
                lines.append(f"{k}: VOF marker {name(vb)}")
            else:
                lines.append(f"{k}: VOF marker {name(va)} becomes {name(vb)} (strongest VOF counts) [6.2.2, FM1 p.44]")
        if ca != cb:
            lines.append(f"{k}: {'place' if cb else 'remove'} the Crossfire marker [6.2.4]")
    return lines


def save_state(s, entry=None, rule=None):
    errors = briefing.consistency_check(s)
    if errors:
        raise rules.Violation("Check prevents saving: " + "; ".join(errors))
    if entry:
        s["protokoll"].append(
            {
                "nr": len(s["protokoll"]) + 1,
                "zug": s["zug"],
                "phase": s["phase"],
                "text": entry,
                "regel": rule,
                "zeit": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
        )
    h = s.pop("_hinweise", None)
    for k in ("_befehl_opts", "_phase_alt"):
        s.pop(k, None)
    text = json.dumps(s, indent=1, ensure_ascii=False)
    path = game_dir() / "spielstand.json"
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            if s["phase"] == "3.7.4":
                # [RULE 3.7.4] VOF, PDF and level stay frozen until 3.8: announce the changes only when leaving (L119)
                if old["phase"] != "3.7.4":
                    s["_ce_start"] = len(old["protokoll"])
            else:
                base = old
                if old["phase"] == "3.7.4" and s.get("_ce_start"):
                    snap = game_dir() / HISTORY_DIR / f"{s['_ce_start']}.json"
                    if snap.exists():
                        base = json.loads(snap.read_text(encoding="utf-8"))
                s.pop("_ce_start", None)
                MARKER_NOTES.extend(marker_changes(base, s))
            text = json.dumps(s, indent=1, ensure_ascii=False)
        except (ValueError, KeyError):
            pass  # announcement only; never blocks saving
    path.write_text(text, encoding="utf-8")
    save_snapshot(len(s["protokoll"]), text)
    if h:
        s["_hinweise"] = h  # v3: hints (e.g. radio path) are kept for output, not saved
    briefing.briefing(s)


def sop(s):
    return rules.SOP_DEFENSIVE if s["typ"] == "defensiv" else rules.SOP_OFFENSIVE


def phase_name(s, row_id=None):
    return dict(sop(s)).get(row_id or s["phase"], "?")


def unit(s, name):
    if name not in s["einheiten"]:
        raise rules.Violation(f"Unit '{name}' unknown. Known: {', '.join(s['einheiten'])}")
    return s["einheiten"][name]


def card(s, kid):
    if kid not in s["karten"]:
        raise rules.Violation(f"Card '{kid}' unknown. Known: {', '.join(s['karten'])}")
    return s["karten"][kid]


def is_hq(e):
    return e["typ"] in ("HQ", "Staff")


def is_lat(e):
    return e["typ"] in ("Paralyzed Team", "Litter Team", "Fire Team", "Assault Team")


def pinned(e):
    return "Pinned" in e["status"]


def fire_team_side(e):
    return "Fire Team side" in e["status"]


def good_order(e):
    return not pinned(e) and not is_lat(e) and not fire_team_side(e)


def steps(e):
    return e.get("steps", 1)


def units_on(s, kid, side=None):
    return [n for n, e in s["einheiten"].items() if e["karte"] == kid and (side is None or e["seite"] == side)]


def opponent_of_side(side):
    return "Feind" if side == "US" else "US"


def option(s, key):
    """Value of an open rules question: setup 'optionen' before OPTIONEN_STANDARD."""
    return s.get("optionen", {}).get(key, rules.DEFAULT_OPTIONS[key][0])


def open_reading(s, key):
    """Tag '[open Ux]' for output, only if the mission tracks open questions (setup 'optionen')."""
    return f" [open {key.split('_')[0]}]" if "optionen" in s else ""


def company(s):
    """CO HQ is a unit on the board (CAC, campaign; also after its loss); PAC: co_hq = 'off-map'."""
    return s.get("co_hq") not in (None, "off-map")


def radio_active(s):
    return bool(s.get("funk_aktiv"))


def is_mortar(e):
    return bool(e.get("moerser"))


def range_limits(s, e):
    """[RULE 1.2.6 p.7] Range P/C/L/V; 'C-L' (Mtr Sec) = minimum and maximum range [open U12]."""
    r = e.get("reichweite", "V") or "V"
    if e.get("out_of_ammo"):
        return 0, 1  # [RULE 7.18.2 p.61] Out of Ammo: range Close
    if fire_team_side(e) and e.get("ft_reichweite"):
        r = e["ft_reichweite"]  # E10: Fire Team side with its own range (German LMG: A/C)
    if "-" in r:
        a, b = r.split("-", 1)
        return rules.RANGE_CARDS.get(a, 0), rules.RANGE_CARDS.get(b, 3)
    return (1 if e.get("min_reichweite") == "C" else 0), rules.RANGE_CARDS.get(r, 3)


def is_visible(e):
    """US units always count as Spotted (8.5); enemies only with the flag."""
    return True if e["seite"] == "US" else bool(e.get("spotted"))


def valid_target(s, kid, shooter_side):
    """Visible unit of the opposing side on the card (6.1.1)."""
    return [n for n in units_on(s, kid, opponent_of_side(shooter_side)) if is_visible(s["einheiten"][n])]


def is_v4(s):
    return "kampagne" in s


def in_setup(s):
    """Before the first 'phase next' (turn 1, phase 3.1) or during Reattempt preparation (3.9)."""
    return (s["zug"] == 1 and s["phase"] == sop(s)[0][0] and not s.get("aufstellung_fertig")) or bool(
        s.get("reattempt_setup")
    )


def countermix_count(s, name):
    """Countermix count; if missing (null in the setup data = UNVERIFIED), 1 is assumed and reported."""
    v = s.get("countermix", {}).get(name, 1)
    if v is None:
        s.setdefault("_hinweise", []).append(f"Countermix {name}: count not recorded (UNVERIFIED), 1 assumed")
        return 1
    return v


def card_id(r, c):
    return f"{r}{c}" if 0 <= c <= 9 else f"{r}m{abs(c)}"


def us_front(s):
    """Row of the foremost US unit (Staging = row 1)."""
    rs = [
        card(s, e["karte"])["reihe"]
        for e in s["einheiten"].values()
        if e["seite"] == "US" and e.get("karte") in s["karten"]
    ]
    return max(rs) if rs else 1


def top_row(s):
    return max(c["reihe"] for c in s["karten"].values() if not c.get("ausserhalb"))
