"""Game state: load/save, protocol, basic accessors for units and cards.

Import cycle: state imports briefing and rules at module level (briefing imports state back, used only at call time);
fire and history import state at module level, so state imports them inside the functions that need them
(marker_summary, cmd_undo)."""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import sys
from typing import Any, Callable

from . import briefing, rules

# L555 (review E6/S8): names for the dict structures crossing module boundaries (keys and lifetimes: fof/keys.py)
GameState = dict[str, Any]  # the game state s (keys.GAME)
Unit = dict[str, Any]  # s["einheiten"][name] (keys.UNIT)
Card = dict[str, Any]  # s["karten"][id] (keys.CARD)
Prot = list[str]  # protocol lines of one command


ROOT = pathlib.Path(__file__).resolve().parents[2]  # <project>/werkzeuge/fof/state.py -> <project>


DATA = ROOT / "data"


def game_dir() -> pathlib.Path:
    """Game folder: environment variable FOF_PARTIE (for tests, v3) before ROOT/.aktuelle_partie before 'partie1'."""

    if os.environ.get("FOF_PARTIE"):
        return ROOT / os.environ["FOF_PARTIE"]
    st = ROOT / ".aktuelle_partie"
    return ROOT / (st.read_text(encoding="utf-8").strip() if st.exists() else "partie1")


def check_new_game_folder(name: str, force: bool = False) -> pathlib.Path:
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
_DISK: dict[str, Any] = {}


def _remember_disk(path: pathlib.Path, text: str, s: GameState) -> None:
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


def _disk_before_save(path: pathlib.Path) -> tuple[str, int, Callable[[], GameState]] | None:
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


def load_state() -> GameState:
    p = game_dir() / "spielstand.json"
    if not p.exists():
        sys.exit("No game state. First: fof.py new <aufbau.json>")
    try:
        text = p.read_text(encoding="utf-8")
        s = json.loads(text)
        _remember_disk(p, text, s)
        from . import vehicles

        vehicles.refresh_jeeps(s)  # L548: derived value, recomputed from the passengers
        return s
    except ValueError as err:  # L223: a damaged file names the latest snapshot instead of a traceback
        snaps = sorted(
            (int(f.stem) for f in (game_dir() / HISTORY_DIR).glob("*.json") if f.stem.isdigit()), reverse=True
        )
        hint = f" Latest snapshot: {HISTORY_DIR}/{snaps[0]}.json (copy it over spielstand.json)." if snaps else ""
        sys.exit(f"spielstand.json is not valid JSON ({err}).{hint}")


HISTORY_DIR = "verlauf"  # snapshots of the state after each protocol entry (for undo)
HISTORY_KEEP = 40


def save_snapshot(nr: int, text: str) -> None:
    """Keep the state after protocol entry nr as verlauf/<nr>.json; prune snapshots older than HISTORY_KEEP entries."""
    d = game_dir() / HISTORY_DIR
    try:
        d.mkdir(exist_ok=True)
        target = d / f"{nr}.json"
        oldest = d / f"{nr - HISTORY_KEEP - 1}.json"
        if not target.exists() and oldest.exists():
            # L471: reuse the snapshot that drops out of the window (rename + overwrite): the history stays at
            # HISTORY_KEEP files even where deleting is not allowed (sandboxed shell on a synced folder)
            oldest.rename(target)
        write_atomic(target, text)  # L551 (review K9): never a half-written snapshot
        for f in d.glob("*.json"):
            if f.stem.isdigit() and int(f.stem) < nr - HISTORY_KEEP:
                try:
                    f.unlink()
                except OSError:
                    pass  # no-delete folder: the rename above keeps the count bounded
    except OSError as err:
        # history is a convenience; a read-only or no-delete folder must not block the game, but say so (L223)
        # L551 (review K9): also when the reused (renamed) old file still sits under the new number; cmd_undo checks
        # the protocol length of a snapshot before using it
        print(f"NOTE: snapshot {HISTORY_DIR}/{nr}.json not written ({err}); undo to this entry is not possible")


def cmd_undo(s: GameState, args: list[str]) -> None:
    """Moved to history.cmd_undo (review Struktur 10: a CLI handler, not state access); kept as an alias for old callers."""
    from . import history

    return history.cmd_undo(s, args)


MARKER_NOTES: list[str] = []  # VOF/Crossfire marker changes of the last save, printed before the CHECKSTAMP (L111)


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


def pdf_pairs(s: GameState) -> set[tuple[str, str]]:
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


def sniper_vof_cards(s):
    """L495 [RULE 7.15 p.57]: cards that carry a Sniper VOF marker (-3): a firing S! unit that is not Pinned and not on
    its Fire Team side places it on its target card, next to the Small Arms VOF. {card: [snipers]}."""
    out = {}
    for n, e in s.get("einheiten", {}).items():
        if e.get("vof_rating") != "S!" or not e.get("ziel") or pinned(e) or fire_team_side(e):
            continue
        out.setdefault(e["ziel"], []).append(n)
    return out


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
    sa, sb = sniper_vof_cards(old), sniper_vof_cards(new)
    for k in sorted(set(sa) | set(sb)):
        if k in sb and k not in sa:
            lines.append(
                f"{k}: place the Sniper VOF marker (-3) from {', '.join(sb[k])} next to the Small Arms VOF [7.15 p.57]"
            )
        elif k in sa and k not in sb:
            lines.append(f"{k}: remove the Sniper VOF marker (-3) [7.15 p.57]")
    return lines


def write_atomic(path: pathlib.Path, text: str) -> None:
    """Write text to path via a temporary file and os.replace, so a crash mid-write keeps the old file intact (L223)."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def heat_check(s: GameState) -> None:
    """L483 [Naktong M1 p.17 Heat Casualties]: friendly units newly marked Exposed while the event runs get a draw."""
    heat: dict[str, Any] = s.get("hitze") or {}
    active = bool(heat) and s.get("zug", 0) <= heat["bis_zug"] and (s.get("wetter") or 0) < 2
    for n, e in s.get("einheiten", {}).items():
        if e.pop("_neu_exposed", None) and active:
            s.setdefault("hitze_offen", []).append(n)
            s.setdefault("_hinweise", []).append(
                f'Heat Casualties: {n} marked Exposed, draw a card, R#/4 = 1 (only 1) = one step Casualty: fof.py heat "{n}" <R#/4 value> [Naktong M1 p.17]'
            )
    if heat and s.get("zug", 0) > heat["bis_zug"]:
        s.pop("hitze")


def save_state(s: GameState, entry: str | None = None, rule: str | None = None) -> None:
    from . import keys

    errors = briefing.consistency_check(s) + keys.check_state(s)  # L530: register check only with FOF_KEY_CHECK=1
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
    heat_check(s)  # L483
    from . import vehicles

    vehicles.refresh_jeeps(s)  # L548
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


def clear_pc(c: Card, promote: bool = True) -> None:
    """L550 (review E12): the PC marker of card c is resolved or removed. promote=True: a second marker on the card
    (pc2, a face-down one waiting for 8.2.3) becomes the card's marker; promote=False removes both (fired over, COP,
    defensive clean up)."""
    c["pc"] = c.pop("pc2", None) if promote else None
    c.pop("pc2", None)


PENDING_LISTS = ("minen_checks", "rally_offen", "hitze_offen", "capture_offen")
PENDING_DICTS = ("minen_check_info", "sniper_offen")


def forget_pending(s: GameState, name: str) -> None:
    """L538 (review E5): a counter that leaves the board owes no mine check, event Rally, heat check, capture or sniper
    result any more; otherwise its name blocks phase next for good (cmd_mine: 'Unit unknown')."""
    for k in PENDING_LISTS:
        if name in (s.get(k) or []):
            s[k].remove(name)
    for k in PENDING_DICTS:
        (s.get(k) or {}).pop(name, None)


def free_cover(s: GameState, kid: str, side: str = "US", steps: int = 0) -> list[dict[str, Any]]:
    """Cover markers on card kid not occupied by units of the opposing side of `side` (L224: one helper for the six copies).
    For an enemy unit pass side="Feind": markers with US units under them are taken. steps > 0: only markers with room for
    that many more steps (capacity, 5.3.2; L534, review E2)."""
    other = opponent_of_side(side)
    out = []
    for c in card(s, kid).get("cover", []):
        under = [s["einheiten"][m] for m in units_on(s, kid) if s["einheiten"][m].get("bereich") == c["id"]]
        if any(x["seite"] == other for x in under):
            continue
        if steps and c.get("kapazitaet") and sum(_steps(x) for x in under) + steps > c["kapazitaet"]:
            continue
        out.append(c)
    return out


def _steps(e: Unit) -> int:
    return e.get("steps", 1)


def sop(s: GameState) -> list[tuple[str, str]]:
    return rules.SOP_DEFENSIVE if s["typ"] == "defensiv" else rules.SOP_OFFENSIVE


def phase_name(s: GameState, row_id: str | None = None) -> str:
    return dict(sop(s)).get(row_id or s["phase"], "?")


def unit(s: GameState, name: str) -> Unit:
    if name not in s["einheiten"]:
        raise rules.Violation(f"Unit '{name}' unknown. Known: {', '.join(s['einheiten'])}")
    return s["einheiten"][name]


def card(s: GameState, kid: str) -> Card:
    if kid not in s["karten"]:
        raise rules.Violation(f"Card '{kid}' unknown. Known: {', '.join(s['karten'])}")
    return s["karten"][kid]


def is_hq(e: Unit) -> bool:
    return e["typ"] in ("HQ", "Staff")


def is_lat(e: Unit) -> bool:
    return e["typ"] in ("Paralyzed Team", "Litter Team", "Fire Team", "Assault Team")


def pinned(e: Unit) -> bool:
    return rules.PINNED in e["status"]


def fire_team_side(e: Unit) -> bool:
    return rules.FIRE_TEAM_SIDE in e["status"]


def good_order(e: Unit) -> bool:
    return not pinned(e) and not is_lat(e) and not fire_team_side(e)


def steps(e: Unit) -> int:
    return e.get("steps", 1)


def units_on(s: GameState, kid: str | None, side: str | None = None) -> list[str]:
    return [n for n, e in s["einheiten"].items() if e["karte"] == kid and (side is None or e["seite"] == side)]


def opponent_of_side(side: str) -> str:
    return "Feind" if side == "US" else "US"


def option(s: GameState, key: str) -> Any:
    """Value of an open rules question: setup 'optionen' before OPTIONEN_STANDARD."""
    return s.get("optionen", {}).get(key, rules.DEFAULT_OPTIONS[key][0])


def open_reading(s: GameState, key: str) -> str:
    """Tag '[open Ux]' for output, only if the mission tracks open questions (setup 'optionen')."""
    return f" [open {key.split('_')[0]}]" if "optionen" in s else ""


def company(s: GameState) -> bool:
    """CO HQ is a unit on the board (CAC, campaign; also after its loss); PAC: co_hq = 'off-map'."""
    return s.get("co_hq") not in (None, "off-map")


def radio_active(s: GameState) -> bool:
    return bool(s.get("funk_aktiv"))


def is_mortar(e: Unit) -> bool:
    return bool(e.get("moerser"))


def range_limits(s: GameState, e: Unit) -> tuple[int, int]:
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


def is_visible(e: Unit) -> bool:
    """US units always count as Spotted (8.5); enemies only with the flag."""
    return True if e["seite"] == "US" else bool(e.get("spotted"))


def valid_target(s: GameState, kid: str, shooter_side: str) -> list[str]:
    """Visible unit of the opposing side on the card (6.1.1)."""
    return [n for n in units_on(s, kid, opponent_of_side(shooter_side)) if is_visible(s["einheiten"][n])]


def is_v4(s: GameState) -> bool:
    return "kampagne" in s


def in_setup(s: GameState) -> bool:
    """Before the first 'phase next' (turn 1, phase 3.1) or during Reattempt preparation (3.9)."""
    return (s["zug"] == 1 and s["phase"] == sop(s)[0][0] and not s.get("aufstellung_fertig")) or bool(
        s.get("reattempt_setup")
    )


def countermix_count(s: GameState, name: str) -> int:
    """Countermix count; if missing (null in the setup data = UNVERIFIED), 1 is assumed and reported."""
    v = s.get("countermix", {}).get(name, 1)
    if v is None:
        s.setdefault("_hinweise", []).append(f"Countermix {name}: count not recorded (UNVERIFIED), 1 assumed")
        return 1
    return v


def card_id(r: int, c: int) -> str:
    """Card id of row r, column c: '23'; negative columns (map extension to the left) get an 'm': row 2, column -1 is
    '2m1'. Columns from 10 on are plain digits ('210'), they used to become '2m10' as if negative (L346)."""
    return f"{r}{c}" if c >= 0 else f"{r}m{abs(c)}"


def us_front(s: GameState) -> int:
    """Row of the foremost US unit (Staging = row 1)."""
    rs = [
        card(s, e["karte"])["reihe"]
        for e in s["einheiten"].values()
        if e["seite"] == "US" and e.get("karte") in s["karten"]
    ]
    return max(rs) if rs else 1


def top_row(s: GameState) -> int:
    return max(c["reihe"] for c in s["karten"].values() if not c.get("ausserhalb"))
