"""Game state: load/save, protocol, basic accessors for units and cards.

Import cycle: state imports briefing and rules at module level (briefing imports state back, used only at call time);
fire and history import state at module level, so state imports them inside the functions that need them
(marker_summary, cmd_undo)."""

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
    return ROOT / (st.read_text(encoding="utf-8").strip() if st.exists() else "partie1")


def check_new_game_folder(name, force=False):
    """Review M5: 'new' must not overwrite a game silently. Raises a Violation if the folder ROOT/name already holds a
    spielstand.json and force is not set; returns the folder path. Call it before .aktuelle_partie is switched."""
    folder = ROOT / name
    if (folder / "spielstand.json").exists() and not force:
        raise rules.Violation(
            f"Game folder {name} already holds a game (spielstand.json); choose another name or add --force to overwrite it"
        )
    return folder


# The state as last read from or written to disk (L344): save_state diffs the markers against the old file without
# reading it again, and needs no JSON parse at all for the phase/protocol bookkeeping of the Combat Effects segment.
_DISK = {}


def _remember_disk(path, text, s):
    _DISK.clear()
    try:
        st = path.stat()
    except OSError:
        return
    _DISK.update(
        path=str(path),
        stat=(st.st_mtime_ns, st.st_size),
        text=text,
        phase=s.get("phase"),
        entries=len(s["protokoll"]) if isinstance(s.get("protokoll"), list) else None,
    )


def _disk_before_save(path):
    """(phase, protocol length, loader of the full old state) of spielstand.json as it is on disk; None without a file.
    Uses the cached text when the file is unchanged since it was loaded or written; otherwise reads it (as before)."""
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    c = _DISK
    if (
        c.get("path") == str(path)
        and c.get("stat") == (st.st_mtime_ns, st.st_size)
        and c.get("phase") is not None
        and c.get("entries") is not None
    ):
        text = c["text"]
        return c["phase"], c["entries"], lambda: json.loads(text)
    old = json.loads(path.read_text(encoding="utf-8"))
    return old["phase"], len(old["protokoll"]), lambda: old


def load_state():
    p = game_dir() / "spielstand.json"
    if not p.exists():
        sys.exit("No game state. First: fof.py new <aufbau.json>")
    try:
        text = p.read_text(encoding="utf-8")
        s = json.loads(text)
        _remember_disk(p, text, s)
        return s
    except ValueError as err:  # L223: a damaged file names the latest snapshot instead of a traceback
        snaps = sorted(
            (int(f.stem) for f in (game_dir() / HISTORY_DIR).glob("*.json") if f.stem.isdigit()), reverse=True
        )
        hint = f" Latest snapshot: {HISTORY_DIR}/{snaps[0]}.json (copy it over spielstand.json)." if snaps else ""
        sys.exit(f"spielstand.json is not valid JSON ({err}).{hint}")


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
    except OSError as err:
        # history is a convenience; a read-only or no-delete folder must not block the game, but say so (L223)
        if not (d / f"{nr}.json").exists():
            print(f"NOTE: snapshot {HISTORY_DIR}/{nr}.json not written ({err}); undo to this entry is not possible")


def cmd_undo(s, args):
    """Moved to history.cmd_undo (review Struktur 10: a CLI handler, not state access); kept as an alias for old callers."""
    from . import history

    return history.cmd_undo(s, args)


MARKER_NOTES = []  # VOF/Crossfire marker changes of the last save, printed before the CHECKSTAMP (L111)


def marker_summary(s):
    """Per card the VOF markers on the board (6.2.1): the strongest VOF from outside or off-map at the top, the best friendly
    Point Blank VOF upper right and the best enemy Point Blank VOF lower left, each only if better than the top marker (L179);
    plus whether a Crossfire marker lies there."""
    from . import fire

    with fire.cached(s):  # read-only loop: one fire map for all cards (L349)
        return _marker_summary(s, fire)


def _marker_summary(s, fire):
    out = {}
    for k in s["karten"]:
        entries = fire.vof_entries(s, k)
        whole = [x for x in entries if x[3] is None]
        top = min(whole, key=lambda x: x[1]) if whole else None
        top_v = top[1] if top else 99
        # entry x[3] is the side that is hit: a friendly (US) Point Blank VOF hits the enemy, and vice versa
        by_us = [x for x in entries if x[3] == "Feind" and x[1] < top_v]
        by_enemy = [x for x in entries if x[3] == "US" and x[1] < top_v]
        us_b = min(by_us, key=lambda x: x[1]) if by_us else None
        en_b = min(by_enemy, key=lambda x: x[1]) if by_enemy else None
        cf = fire.crossfire(s, k, "Feind") or fire.crossfire(s, k, "US")
        if top or us_b or en_b or cf:
            out[k] = (
                (top[0], top[1]) if top else None,
                cf,
                (us_b[0], us_b[1]) if us_b else None,  # upper right: friendly Point Blank
                (en_b[0], en_b[1]) if en_b else None,  # lower left: enemy Point Blank
            )
    return out


def pdf_pairs(s):
    """(from card, to card) of every direct PDF on the board."""
    pdf = set()
    for e in s["einheiten"].values():
        z = e.get("ziel")
        if z and z != e.get("karte") and not e.get("indirekt"):
            pdf.add((e["karte"], z))
    return pdf


def mutual_pdfs(s):
    """Pairs of cards whose units fire at each other along a PDF (V16)."""
    pdf = pdf_pairs(s)
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
    left = pdf_pairs(new)
    for x, y in sorted(ma - mb):
        if (x, y) in left or (y, x) in left:
            lines.append(
                f"PDF between {x} and {y} no longer mutual: turn the PDF marker back to the single arrow [6.3.1]"
            )
        else:  # L198: nobody fires along this PDF any more
            lines.append(
                f"PDF between {x} and {y}: nobody fires along it any more, remove the PDF marker [6.1.2, 6.3.1]"
            )
    for x, y in sorted(pdf_pairs(old) - left):  # L206: a one-way PDF disappeared
        if tuple(sorted((x, y))) in ma or (y, x) in left:
            continue
        lines.append(f"PDF from {x} to {y}: nobody fires along it any more, remove the PDF marker [6.1.2]")
    for k in sorted(set(a) | set(b)):
        va, ca, ua, ea = a.get(k, (None, False, None, None))
        vb, cb, ub, eb = b.get(k, (None, False, None, None))
        for where, x, y in (
            ("", va, vb),
            (" upper right (friendly Point Blank)", ua, ub),
            (" lower left (enemy Point Blank)", ea, eb),
        ):
            if x == y:
                continue
            rule = " [6.2.1b]" if where else " (strongest VOF counts) [6.2.2, FM1 p.44]"
            if y is None:
                lines.append(f"{k}: remove the VOF marker{where} ({name(x)})")
            elif x is None:
                lines.append(f"{k}: VOF marker{where} {name(y)}" + (" [6.2.1b]" if where else ""))
            else:
                lines.append(f"{k}: VOF marker{where} {name(x)} becomes {name(y)}{rule}")
        if ca != cb:
            lines.append(f"{k}: {'place' if cb else 'remove'} the Crossfire marker [6.2.4]")
    return lines


def write_atomic(path, text):
    """Write text to path via a temporary file and os.replace, so a crash mid-write keeps the old file intact (L223)."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


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
    path = game_dir() / "spielstand.json"
    try:
        old = _disk_before_save(path)  # L344: the file as loaded, without reading and parsing it a second time
        if old is not None:
            old_phase, old_entries, old_state = old
            if s["phase"] == "3.7.4":
                # [RULE 3.7.4] VOF, PDF and level stay frozen until 3.8: announce the changes only when leaving (L119)
                if old_phase != "3.7.4":
                    s["_ce_start"] = old_entries
            else:
                base = None
                if old_phase == "3.7.4" and s.get("_ce_start"):
                    snap = game_dir() / HISTORY_DIR / f"{s['_ce_start']}.json"
                    if snap.exists():
                        base = json.loads(snap.read_text(encoding="utf-8"))
                s.pop("_ce_start", None)
                MARKER_NOTES.extend(marker_changes(base if base is not None else old_state(), s))
    except (ValueError, KeyError):
        pass  # announcement only; never blocks saving
    text = json.dumps(s, indent=1, ensure_ascii=False)  # L344: serialized once, after the bookkeeping above
    write_atomic(path, text)  # L223: never leave a half-written spielstand.json behind
    _remember_disk(path, text, s)
    save_snapshot(len(s["protokoll"]), text)
    if h:
        s["_hinweise"] = h  # v3: hints (e.g. radio path) are kept for output, not saved
    briefing.briefing(s, errors)  # L344: the consistency check above is not run a second time


def free_cover(s, kid, side="US"):
    """Cover markers on card kid not occupied by units of the opposing side of `side` (L224: one helper for the six copies).
    For an enemy unit pass side="Feind": markers with US units under them are taken."""
    other = opponent_of_side(side)
    return [
        c
        for c in card(s, kid).get("cover", [])
        if not any(
            s["einheiten"][m]["seite"] == other and s["einheiten"][m].get("bereich") == c["id"]
            for m in units_on(s, kid)
        )
    ]


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
    return rules.PINNED in e["status"]


def fire_team_side(e):
    return rules.FIRE_TEAM_SIDE in e["status"]


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
    """Card id of row r, column c: '23'; negative columns (map extension to the left) get an 'm': row 2, column -1 is
    '2m1'. Columns from 10 on are plain digits ('210'), they used to become '2m10' as if negative (L346)."""
    return f"{r}{c}" if c >= 0 else f"{r}m{abs(c)}"


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
