"""Game state: load/save, protocol, basic accessors for units and cards.

Import cycle: state imports briefing and rules at module level (briefing imports state back, used only at call time);
fire and history import state at module level, so state imports them inside the functions that need them
(marker_summary, cmd_undo)."""

from __future__ import annotations

import copy
import datetime
import json
import os
import pathlib
import sys
from typing import Any, Callable

from . import briefing, migrate, rules

# (S8): names for the dict structures crossing module boundaries (keys and lifetimes: fof/keys.py)
GameState = dict[str, Any]  # the game state s (keys.GAME)
Unit = dict[str, Any]  # s["units"][name] (keys.UNIT)
Card = dict[str, Any]  # s["cards"][id] (keys.CARD)
Prot = list[str]  # protocol lines of one command


ROOT = pathlib.Path(__file__).resolve().parents[2]  # <project>/tool/fof/state.py -> <project>


DATA = ROOT / "data"
STATE_FILE = "game_state.json"  # the game state in the game folder
HISTORY_DIR = "history"  # snapshots of the state after each protocol entry (for undo)
COMMAND_LOG = "commands.txt"  # every command line that changed the game, in order (replayable)
POINTER = ".current_game"  # in ROOT: name of the current game folder
DEFAULT_GAME = "game1"
# the names of earlier releases (spielstand.json, verlauf/, .aktuelle_partie, FOF_PARTIE) are read too, see
# migrate.FILES; a game folder is renamed to the English names when it is loaded


def game_dir() -> pathlib.Path:
    """Game folder: environment variable FOF_GAME (tests, step.py) before ROOT/.current_game before 'game1'."""
    name = migrate.env("FOF_GAME", os.environ)
    if name:
        return ROOT / name
    pointer = migrate.path(ROOT, POINTER)
    return ROOT / (pointer.read_text(encoding="utf-8").strip() if pointer.exists() else DEFAULT_GAME)


def state_path(folder: pathlib.Path | None = None) -> pathlib.Path:
    """The state file of a game folder (default: the current one), after renaming the names of an earlier release."""
    folder = game_dir() if folder is None else folder
    if folder.is_dir():
        migrate.adopt(folder)
    return folder / STATE_FILE


def data_file(name: str) -> pathlib.Path:
    """A file in data/, or the same file under its name of an earlier release (rule texts built before)."""
    return migrate.path(DATA, name, migrate.DATA_FILES)


def check_new_game_folder(name: str, force: bool = False) -> pathlib.Path:
    """'new' must not overwrite a game silently. Raises a Violation if the folder ROOT/name already holds a
    game state and force is not set; returns the folder path. Call it before .current_game is switched."""
    folder = ROOT / name
    if migrate.path(folder, STATE_FILE).exists() and not force:
        raise rules.Violation(
            f"Game folder {name} already holds a game ({STATE_FILE}); choose another name or add --force to overwrite it"
        )
    return folder


# The state as last read from or written to disk: save_state diffs the markers against the old file without
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
        entries=len(s["protocol"]) if isinstance(s.get("protocol"), list) else None,
    )


def _disk_before_save(path: pathlib.Path) -> tuple[str, int, Callable[[], GameState]] | None:
    """(phase, protocol length, loader of the full old state) of the state file as it is on disk; None without a file.
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
        return c["phase"], c["entries"], lambda: migrate.state(json.loads(text))
    old = migrate.state(json.loads(path.read_text(encoding="utf-8")))
    return old["phase"], len(old["protocol"]), lambda: old


def load_state() -> GameState:
    p = state_path()
    if not p.exists():
        sys.exit("No game state. First: fof.py new <setup.json>")
    try:
        text = p.read_text(encoding="utf-8")
        s = migrate.state(json.loads(text))  # a game saved before is read with English keys and values
        _remember_disk(p, text, s)
        from . import vehicles

        vehicles.refresh_jeeps(s)  # derived value, recomputed from the passengers
        return s
    except ValueError as err:  # a damaged file names the latest snapshot instead of a traceback
        snaps = sorted(
            (int(f.stem) for f in (game_dir() / HISTORY_DIR).glob("*.json") if f.stem.isdigit()), reverse=True
        )
        hint = f" Latest snapshot: {HISTORY_DIR}/{snaps[0]}.json (copy it over {STATE_FILE})." if snaps else ""
        sys.exit(f"{STATE_FILE} is not valid JSON ({err}).{hint}")


HISTORY_KEEP = 40


def save_snapshot(num: int, text: str) -> None:
    """Keep the state after protocol entry num as history/<num>.json; prune snapshots older than HISTORY_KEEP entries."""
    d = game_dir() / HISTORY_DIR
    try:
        d.mkdir(exist_ok=True)
        target = d / f"{num}.json"
        oldest = d / f"{num - HISTORY_KEEP - 1}.json"
        if not target.exists() and oldest.exists():
            # reuse the snapshot that drops out of the window (rename + overwrite): the history stays at
            # HISTORY_KEEP files even where deleting is not allowed (sandboxed shell on a synced folder)
            oldest.rename(target)
        write_atomic(target, text)  # never a half-written snapshot
        for f in d.glob("*.json"):
            if f.stem.isdigit() and int(f.stem) < num - HISTORY_KEEP:
                try:
                    f.unlink()
                except OSError:
                    pass  # no-delete folder: the rename above keeps the count bounded
    except OSError as err:
        # history is a convenience; a read-only or no-delete folder must not block the game, but say so
        # also when the reused (renamed) old file still sits under the new number; cmd_undo checks
        # the protocol length of a snapshot before using it
        print(f"NOTE: snapshot {HISTORY_DIR}/{num}.json not written ({err}); undo to this entry is not possible")


def snapshot_text(s: GameState) -> str:
    """A snapshot is the state without its protocol (the largest part by far); only the entry count is kept."""
    body = {k: v for k, v in s.items() if k != "protocol"}
    return json.dumps({**body, "protocol_entries": len(s["protocol"])}, indent=1, ensure_ascii=False)


def load_snapshot(num: int, protocol: list[dict[str, Any]]) -> GameState | None:
    """The state after protocol entry num, None without a snapshot. The protocol is cut from the current one; a
    snapshot written with its own protocol (earlier releases) is read as it is. ValueError: damaged file."""
    snap = game_dir() / HISTORY_DIR / f"{num}.json"
    if not snap.exists():
        return None
    old = json.loads(snap.read_text(encoding="utf-8"))
    if "protocol_entries" in old:
        old["protocol"] = copy.deepcopy(protocol[: old.pop("protocol_entries")])
    return migrate.state(old)


def cmd_undo(s: GameState, args: list[str]) -> None:
    """Alias of history.cmd_undo (a CLI handler, not state access) for old callers."""
    from . import history

    return history.cmd_undo(s, args)


MARKER_NOTES: list[str] = []  # VOF/Crossfire marker changes of the last save, printed before the CHECKSTAMP


def marker_summary(s):
    """Per card the VOF markers on the board (6.2.1): the strongest VOF from outside or off-map at the top, the best friendly
    Point Blank VOF upper right and the best enemy Point Blank VOF lower left, each only if better than the top marker;
    plus whether a Crossfire marker lies there."""
    from . import fire

    with fire.cached(s):  # read-only loop: one fire map for all cards
        return _marker_summary(s, fire)


def _marker_summary(s, fire):
    out = {}
    for k in s["cards"]:
        entries = fire.vof_entries(s, k)
        whole = [x for x in entries if x[3] is None]
        top = min(whole, key=lambda x: x[1]) if whole else None
        top_v = top[1] if top else 99
        # entry x[3] is the side that is hit: a friendly (US) Point Blank VOF hits the enemy, and vice versa
        by_us = [x for x in entries if x[3] == "Enemy" and x[1] < top_v]
        by_enemy = [x for x in entries if x[3] == "US" and x[1] < top_v]
        us_b = min(by_us, key=lambda x: x[1]) if by_us else None
        en_b = min(by_enemy, key=lambda x: x[1]) if by_enemy else None
        cf = fire.crossfire(s, k, "Enemy") or fire.crossfire(s, k, "US")
        if top or us_b or en_b or cf:
            out[k] = (
                (top[0], top[1]) if top else None,
                cf,
                (us_b[0], us_b[1]) if us_b else None,  # upper right: friendly Point Blank
                (en_b[0], en_b[1]) if en_b else None,  # lower left: enemy Point Blank
            )
    return out


def underlying_vof(s: GameState) -> dict[str, dict[tuple[str, int], list[str]]]:
    """Per card the VOF from outside that lies beneath the top marker: {(type, value): [sources]}."""
    from . import fire

    out = {}
    with fire.cached(s):
        for k in s["cards"]:
            whole = [x for x in fire.vof_entries(s, k) if x[3] is None]
            if len(whole) < 2:
                continue
            top = min(whole, key=lambda x: x[1])[:2]
            below: dict[tuple[str, int], list[str]] = {}
            for x in whole:
                if x[:2] != top:
                    below.setdefault(x[:2], []).append(x[2])
            out[k] = below
    return out


def pdf_pairs(s: GameState) -> set[tuple[str, str]]:
    """(from card, to card) of every direct PDF on the board."""
    pdf = set()
    for e in s["units"].values():
        target_card = e.get("target")
        if target_card and target_card != e.get("card") and not e.get("indirect"):
            pdf.add((e["card"], target_card))
    return pdf


def mutual_pdfs(s):
    """Pairs of cards whose units fire at each other along a PDF (V16)."""
    pdf = pdf_pairs(s)
    return {tuple(sorted(p)) for p in pdf if (p[1], p[0]) in pdf}


def sniper_vof_cards(s):
    """[RULE 7.15 p.57]: cards that carry a Sniper VOF marker (-3): a firing S! unit that is not Pinned and not on
    its Fire Team side places it on its target card, next to the Small Arms VOF. {card: [snipers]}."""
    out = {}
    for n, e in s.get("units", {}).items():
        if e.get("vof_rating") != "S!" or not e.get("target") or pinned(e) or fire_team_side(e):
            continue
        out.setdefault(e["target"], []).append(n)
    return out


def marker_changes(old, new):
    """Board lines for every card whose VOF marker or Crossfire marker changed between two states."""

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
        else:  # nobody fires along this PDF any more
            lines.append(
                f"PDF between {x} and {y}: nobody fires along it any more, remove the PDF marker [6.1.2, 6.3.1]"
            )
    for x, y in sorted(pdf_pairs(old) - left):  # a one-way PDF disappeared
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
    ua_, ub_ = underlying_vof(old), underlying_vof(new)
    for k in sorted(set(ua_) | set(ub_)):
        # a weaker VOF beneath the marker comes or goes while the marker itself stays or changes
        before, after, tops = ua_.get(k, {}), ub_.get(k, {}), (a.get(k, (None,))[0], b.get(k, (None,))[0])
        for v in sorted(set(before) ^ set(after)):
            if v in tops or tops[1] is None:
                continue  # that change is the marker line above
            gone = v in before
            lines.append(
                f"{k}: beneath the {name(tops[1])} marker {name(v)} ({', '.join((before if gone else after)[v])}) "
                + ("no longer applies" if gone else "now applies as well")
                + " (no marker change) [6.2.2]"
            )
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
    """Write text to path via a temporary file and os.replace, so a crash mid-write keeps the old file intact."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def heat_check(s: GameState) -> None:
    """[Naktong M1 p.17 Heat Casualties]: friendly units newly marked Exposed while the event runs get a draw."""
    heat: dict[str, Any] = s.get("heat") or {}
    active = bool(heat) and s.get("turn", 0) <= heat["until_turn"] and (s.get("weather") or 0) < 2
    for n, e in s.get("units", {}).items():
        if e.pop("_new_exposed", None) and active:
            s.setdefault("heat_open", []).append(n)
            s.setdefault("_hints", []).append(
                f'Heat Casualties: {n} marked Exposed, draw a card, R#/4 = 1 (only 1) = one step Casualty: fof.py heat "{n}" <R#/4 value> [Naktong M1 p.17]'
            )
    if heat and s.get("turn", 0) > heat["until_turn"]:
        s.pop("heat")


def save_state(s: GameState, entry: str | None = None, rule: str | None = None) -> None:
    from . import keys

    from . import naming

    from . import fire

    # generic teams follow their counter type and card; Concentrated Fire markers follow 7.11.5
    from . import enemy

    # Lone Mortar Reaction first: the flip may open fire
    renamed = enemy.lone_mortar_reaction(s) + fire.reconcile_concentrated(s) + naming.relabel(s)
    if renamed:
        MARKER_NOTES.extend(renamed)
        entry = "; ".join(([entry] if entry else []) + renamed)
    errors = briefing.consistency_check(s) + keys.check_state(s)  # register check only with FOF_KEY_CHECK=1
    if errors:
        raise rules.Violation("Check prevents saving: " + "; ".join(errors))
    if entry:
        s["protocol"].append(
            {
                "number": len(s["protocol"]) + 1,
                "turn": s["turn"],
                "phase": s["phase"],
                "text": entry,
                "rule": rule,
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
        )
    heat_check(s)
    from . import vehicles

    vehicles.refresh_jeeps(s)
    h = s.pop("_hints", None)
    for k in ("_order_opts", "_phase_before"):
        s.pop(k, None)
    path = state_path()
    try:
        old = _disk_before_save(path)  # the file as loaded, without reading and parsing it a second time
        if old is not None:
            old_phase, old_entries, old_state = old
            if s["phase"] == "3.7.4":
                # [RULE 3.7.4] VOF, PDF and level stay frozen until 3.8: announce the changes only when leaving
                if old_phase != "3.7.4":
                    s["_ce_start"] = old_entries
            else:
                base = None
                if old_phase == "3.7.4" and s.get("_ce_start"):
                    base = load_snapshot(s["_ce_start"], s["protocol"])
                s.pop("_ce_start", None)
                MARKER_NOTES.extend(marker_changes(base if base is not None else old_state(), s))
    except (ValueError, KeyError):
        pass  # announcement only; never blocks saving
    text = json.dumps(s, indent=1, ensure_ascii=False)  # serialized once, after the bookkeeping above
    write_atomic(path, text)  # never leave a half-written state file behind
    _remember_disk(path, text, s)
    save_snapshot(len(s["protocol"]), snapshot_text(s))
    if h:
        s["_hints"] = h  # series rules: hints (e.g. radio path) are kept for output, not saved
    briefing.briefing(s, errors)  # the consistency check above is not run a second time


def clear_pc(c: Card, promote: bool = True) -> None:
    """the PC marker of card c is resolved or removed. promote=True: a second marker on the card
    (pc2, a face-down one waiting for 8.2.3) becomes the card's marker; promote=False removes both (fired over, COP,
    defensive clean up)."""
    c["pc"] = c.pop("pc2", None) if promote else None
    c.pop("pc2", None)


PENDING_LISTS = ("mine_checks", "rally_open", "heat_open", "capture_open")
PENDING_DICTS = ("mine_check_info", "sniper_open")


def forget_pending(s: GameState, name: str) -> None:
    """a counter that leaves the board owes no mine check, event Rally, heat check, capture or sniper
    result any more; otherwise its name blocks phase next for good (cmd_mine: 'Unit unknown')."""
    for k in PENDING_LISTS:
        if name in (s.get(k) or []):
            s[k].remove(name)
    for k in PENDING_DICTS:
        (s.get(k) or {}).pop(name, None)


def free_cover(s: GameState, card_id: str, side: str = "US", steps: int = 0) -> list[dict[str, Any]]:
    """Cover markers on card card_id not occupied by units of the opposing side of `side` (one helper for the six copies).
    For an enemy unit pass side="Enemy": markers with US units under them are taken. steps > 0: only markers with room for
    that many more steps (capacity, 5.3.2)."""
    other = opponent_of_side(side)
    out = []
    for c in card(s, card_id).get("cover", []):
        under = [s["units"][m] for m in units_on(s, card_id) if s["units"][m].get("area") == c["id"]]
        if any(x["side"] == other for x in under):
            continue
        if steps and c.get("capacity") and sum(_steps(x) for x in under) + steps > c["capacity"]:
            continue
        out.append(c)
    return out


def _steps(e: Unit) -> int:
    return e.get("steps", 1)


def sop(s: GameState) -> list[tuple[str, str]]:
    return rules.SOP_DEFENSIVE if s["type"] == "defensive" else rules.SOP_OFFENSIVE


def phase_name(s: GameState, row_id: str | None = None) -> str:
    return dict(sop(s)).get(row_id or s["phase"], "?")


def unit(s: GameState, name: str) -> Unit:
    if name not in s["units"]:
        raise rules.Violation(f"Unit '{name}' unknown. Known: {', '.join(s['units'])}")
    return s["units"][name]


def card(s: GameState, card_id: str) -> Card:
    if card_id not in s["cards"]:
        raise rules.Violation(f"Card '{card_id}' unknown. Known: {', '.join(s['cards'])}")
    return s["cards"][card_id]


def is_hq(e: Unit) -> bool:
    return e["type"] in ("HQ", "Staff")


def is_lat(e: Unit) -> bool:
    return e["type"] in ("Paralyzed Team", "Litter Team", "Fire Team", "Assault Team")


def pinned(e: Unit) -> bool:
    return rules.PINNED in e["status"]


def fire_team_side(e: Unit) -> bool:
    return rules.FIRE_TEAM_SIDE in e["status"]


def in_deep_bunker(e: Unit) -> bool:
    """Inside a Deep Bunker (either side): no VOF, no Spot, no pyrotechnics, no Grenade Attack [rules.DEEP_BUNKER_REF]."""
    return bool(e.get("deep_bunker")) and e.get("area") == e["deep_bunker"]


def good_order(e: Unit) -> bool:
    return not pinned(e) and not is_lat(e) and not fire_team_side(e)


def steps(e: Unit) -> int:
    return e.get("steps", 1)


def units_on(s: GameState, card_id: str | None, side: str | None = None) -> list[str]:
    return [n for n, e in s["units"].items() if e["card"] == card_id and (side is None or e["side"] == side)]


def opponent_of_side(side: str) -> str:
    return "Enemy" if side == "US" else "US"


def option(s: GameState, key: str) -> Any:
    """Value of an open rules question: setup 'options' before OPTIONEN_STANDARD."""
    return s.get("options", {}).get(key, rules.DEFAULT_OPTIONS[key][0])


def open_reading(s: GameState, key: str) -> str:
    """Tag '[open Ux]' for output, only if the mission tracks open questions (setup 'options')."""
    return f" [open {key.split('_')[0]}]" if "options" in s else ""


def company(s: GameState) -> bool:
    """CO HQ is a unit on the board (CAC, campaign; also after its loss); PAC: co_hq = 'off-map'."""
    return s.get("co_hq") not in (None, "off-map")


def radio_active(s: GameState) -> bool:
    return bool(s.get("radio_active"))


def is_mortar(e: Unit) -> bool:
    return bool(e.get("mortar"))


def range_limits(s: GameState, e: Unit) -> tuple[int, int]:
    """[RULE 1.2.6 p.7] Range P/C/L/V; 'C-L' (Mtr Sec) = minimum and maximum range [open U12]."""
    r = e.get("range", "V") or "V"
    if e.get("out_of_ammo"):
        return 0, 1  # [RULE 7.18.2 p.61] Out of Ammo: range Close
    if fire_team_side(e) and e.get("ft_range"):
        r = e["ft_range"]  # E10: Fire Team side with its own range (German LMG: A/C)
    if "-" in r:
        a, b = r.split("-", 1)
        return rules.RANGE_CARDS.get(a, 0), rules.RANGE_CARDS.get(b, 3)
    return (1 if e.get("min_range") == "C" else 0), rules.RANGE_CARDS.get(r, 3)


def is_visible(e: Unit) -> bool:
    """US units always count as Spotted (8.5); enemies only with the flag."""
    return True if e["side"] == "US" else bool(e.get("spotted"))


def valid_target(s: GameState, card_id: str, shooter_side: str) -> list[str]:
    """Visible unit of the opposing side on the card (6.1.1)."""
    return [n for n in units_on(s, card_id, opponent_of_side(shooter_side)) if is_visible(s["units"][n])]


def is_campaign(s: GameState) -> bool:
    return "campaign" in s


def in_setup(s: GameState) -> bool:
    """Before the first 'phase next' (turn 1, phase 3.1) or during Reattempt preparation (3.9)."""
    return (s["turn"] == 1 and s["phase"] == sop(s)[0][0] and not s.get("setup_done")) or bool(s.get("reattempt_setup"))


def countermix_count(s: GameState, name: str) -> int:
    """Countermix count; if missing (null in the setup data = UNVERIFIED), 1 is assumed and reported."""
    v = s.get("countermix", {}).get(name, 1)
    if v is None:
        s.setdefault("_hints", []).append(f"Countermix {name}: count not recorded (UNVERIFIED), 1 assumed")
        return 1
    return v


def card_id(r: int, c: int) -> str:
    """Card id of row r, column c: '23'; negative columns (map extension to the left) get an 'm': row 2, column -1 is
    '2m1'. Columns from 10 on are plain digits ('210')."""
    return f"{r}{c}" if c >= 0 else f"{r}m{abs(c)}"


def us_front(s: GameState) -> int:
    """Row of the foremost US unit (Staging = row 1)."""
    rs = [card(s, e["card"])["row"] for e in s["units"].values() if e["side"] == "US" and e.get("card") in s["cards"]]
    return max(rs) if rs else 1


def top_row(s: GameState) -> int:
    return max(c["row"] for c in s["cards"].values() if not c.get("outside"))
