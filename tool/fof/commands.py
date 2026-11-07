"""Friendly Command Phase: activation, impulses, orders of the action menu, late orders, corrections (4.x).

The order pipeline lives here (cmd_order: order_context, resolve_originator, check_recipient, check_repeat_and_budget,
apply_skill, pre_draw_checks, the handler from ORDER_HANDLERS, book_order) together with movement (check_move,
move_unit), cover markers and Concentrate Fire. Split off by topic in L556 (code review 07.11.2026 E4):
fire_support (Call for Fire, Indirect Lay), grenades (Grenade Attacks, Jam), pickup (Pick Up, jeep), pyro (pyrotechnics)."""

from __future__ import annotations

import dataclasses
from typing import Any

from . import (
    briefing,
    campaign,
    combat,
    comms,
    contact,
    enemy,
    events,
    fire,
    fire_support,
    geometry,
    grenades,
    messages,
    options,
    pickup,
    pyro,
    rules,
    state,
)


YES_WORDS = ("ja", "yes")
NO_WORDS = ("nein", "no")

# Working flags and every other state key: lifetime, meaning, who sets and clears them are listed in fof/keys.py (L530).


def spotted_enemies(s, kid):
    """Enemy units on card kid that are Spotted, in board order (review Struktur 9: one helper for the copies)."""
    return [m for m in state.units_on(s, kid, "Feind") if s["einheiten"][m].get("spotted")]


def unspotted_enemies(s, kid):
    """Enemy units on card kid that are Unspotted, in board order (review Struktur 9)."""
    return [m for m in state.units_on(s, kid, "Feind") if not s["einheiten"][m].get("spotted")]


def text_opt(o, key):
    """L232 (review H12): a value option as text; a bare --flag where a value is needed is a Violation, not a crash
    on True.split(). Missing: None."""
    v = o.get(key)
    if v is True:
        raise rules.Violation(f"Option {key} needs a value ({key}=..)")
    return v


def parse_per_unit(value):
    """L230 (review H8): per-unit results '1/1:yes,2/1:no' (also ja/nein, any case) -> {'1/1': 'ja', '2/1': 'nein'}.
    One parser for Platoon Move/Infiltrate, Platoon Fire and pyro signals; a bad result word is a Violation."""
    result = {}
    for item in (value if isinstance(value, str) else "").split(","):
        if ":" not in item:
            continue
        unit_, word = item.rsplit(":", 1)
        w = word.strip().lower()
        if w in YES_WORDS:
            result[unit_.strip()] = "ja"
        elif w in NO_WORDS:
            result[unit_.strip()] = "nein"
        else:
            raise rules.Violation(f"{unit_.strip()}: result must be yes or no, got '{word.strip()}'")
    return result


def team_option(o, default):
    """L240 (review M13): --team=fire|assault in any spelling -> 'Fire' / 'Assault'; anything else is a Violation."""
    v = o.get("--team")
    if v is None or v is True:
        return default
    t = str(v).strip().capitalize()
    if t not in ("Fire", "Assault"):
        raise rules.Violation(f"--team=fire|assault expected, got '{v}'")
    return t


def check_impulse_budget(s, hq_name, cost, rule, free=False):
    """L234 (review M7): the Commands and the per-impulse cap of pay_commands, checked before the draw prompt so the
    player does not draw cards for an order that cannot be paid [RULE 4.1.3 p.20]."""
    if free:
        return
    k = s["kommandos"][hq_name]
    gi = hq_name == "GI"
    total_ = k["verfuegbar"] + (0 if gi else k["gespart"])
    if total_ < cost:
        raise rules.Violation(f"{hq_name} has {total_} Commands, action costs {cost} [RULE {rule}]")
    spent = s.get("impuls_ausgegeben", {}).get(hq_name, 0)
    if not gi and spent + cost > rules.MAX_PER_IMPULSE[s["sicht"]]:
        raise rules.Violation(
            f"At most {rules.MAX_PER_IMPULSE[s['sicht']]} Commands per impulse ({spent} spent, action costs {cost}) [RULE 4.1.3 p.20]"
        )


def pay_commands(s, hq_name, cost, rule):
    k = s["kommandos"][hq_name]
    check_impulse_budget(s, hq_name, cost, rule)
    spent = s.setdefault("impuls_ausgegeben", {}).get(hq_name, 0)
    remainder = cost
    if k["verfuegbar"] >= remainder:
        k["verfuegbar"] -= remainder
    else:
        remainder -= k["verfuegbar"]
        k["verfuegbar"] = 0
        k["gespart"] -= remainder
    s["impuls_ausgegeben"][hq_name] = spent + cost


def cmd_activate(s, args):
    rules.need(args, 1, "activate <hq>")
    hq = args[0]
    e = state.unit(s, hq)
    if not state.is_hq(e):
        raise rules.Violation(f"{hq} is not an HQ/Staff [RULE 4.2.1a p.22]")
    if s["phase"] == "3.3.1a" and events.bn_leader(s):
        bn = s.get("aktiver_hq")
        if e.get("ebene") != "CO" or not bn:
            raise rules.Violation("In the BN HQ impulse the BN HQ only activates the CO HQ [RULE 4.2.1a p.22]")
        activation_allowed(s, hq, e)  # L236 (review M9): same duplicate and Fire Team side checks as the other paths
        comms.communication(s, bn, hq)
        pay_commands(s, bn, 1, "4.2.1a p.22")
        s["kommandos"][hq]["aktiviert"] = True
        state.save_state(s, f"{bn} (BN HQ on the board) activates {hq}", "4.1.1 p.18, 4.2.1a p.22")
        print(
            f"{messages.ALLOWED}: {bn} activates {hq} (1 Command, remaining {s['kommandos'][bn]['verfuegbar']}); Command marker on Commands Available [4.1.1 p.18]"
        )
        briefing.print_board([], s)
        return
    if s["phase"] == "3.3.1a":
        if e.get("ebene") != "CO":
            raise rules.Violation("In the BN HQ impulse the BN HQ only activates the CO HQ [RULE 4.2.1a p.22]")
        if state.company(s) and s.get("bn_nicht_verfuegbar") == s["zug"]:
            raise rules.Violation("Comm Trouble: BN HQ does not activate the CO HQ this turn [Normandy M1 p.18]")
        if state.company(s):
            ok, reason = comms.bn_link(s)
            if not ok:
                raise rules.Violation(
                    f"BN HQ off-map cannot activate {hq}: {reason}; continue with 3.3.2a CO HQ Initiative [RULE 4.1.1 p.18/19, 4.0 p.18 footnote]"
                )
    elif s["phase"] == "3.3.1b":
        if e.get("ebene") == "CO":
            raise rules.Violation("The CO HQ is only activated by the BN HQ (3.3.1a) [RULE 4.2.1a p.22]")
    elif s["phase"] == "3.3.2a" and state.company(s):
        if not state.option(s, "U6_aktivieren_im_initiative_impuls"):
            raise rules.Violation(
                "No PLT HQs are activated in the CO HQ Initiative Impulse; non-activated PLT HQs draw Initiative in 3.3.2b [RULE 3.3.1c p.16, 3.3.2b p.16]"
                + state.open_reading(s, "U6_aktivieren_im_initiative_impuls")
            )
        co = s["co_hq"]
        if s.get("aktiver_hq") != co:
            raise rules.Violation(f"First 'hq {co}' and card draw")
        comms.communication(s, co, hq)
        pay_commands(s, co, 1, "4.2.1a p.22")
        state.save_state(
            s,
            f"{co} activates {hq} in the Initiative Impulse (option U6 reading a): 1 Command, no effect, {hq} draws Initiative in 3.3.2b",
            "4.2.1a p.22",
        )
        print(
            f"{messages.ALLOWED} under option U6: 1 Command paid, no effect; {hq} draws Initiative in 3.3.2b"
            + state.open_reading(s, "U6_aktivieren_im_initiative_impuls")
        )
        briefing.print_board([], s)
        return
    else:
        raise rules.Violation(f"Activation only in 3.3.1a/b, currently {s['phase']} [RULE 3.3.1 p.15]")
    k = activation_allowed(s, hq, e)
    co = s.get("co_hq")
    if co and co != "off-map" and s["phase"] == "3.3.1b":
        if s.get("aktiver_hq") != co:
            raise rules.Violation(f"First 'hq {co}' and card draw, then activate")
        ce = state.unit(s, co)
        if state.fire_team_side(ce):
            raise rules.Violation(f"{co} on its Fire Team side cannot activate [RULE 4.2.1a p.22]")
        if not s.get("co_immer_in_kommunikation"):
            comms.communication(s, co, hq)
        pay_commands(s, co, 1, "4.2.1a p.22")
    k["aktiviert"] = True
    who = "BN HQ (off-map)" if s["phase"] == "3.3.1a" else (co or "CO HQ (off-map)")
    state.save_state(s, f"{who} activates {hq}; Command marker on Commands Available", "4.2.1a p.22")
    print(
        f"{messages.ALLOWED}: {hq} activated. Flip Command marker to Commands Available."
        + (
            f" Cost 1 Command {co}, remaining {s['kommandos'][co]['verfuegbar']}+{s['kommandos'][co]['gespart']}."
            if state.company(s) and s["phase"] == "3.3.1b"
            else ""
        )
    )
    briefing.print_board([], s)


def activation_allowed(s, hq, e):
    """[RULE 4.1.4 p.20] no activation on the Fire Team side; an HQ is activated once per turn. Returns the Command record."""
    if state.fire_team_side(e):
        raise rules.Violation(
            f"{hq} is on its Fire Team side, cannot be activated, must draw Initiative [RULE 4.1.4 p.20]"
        )
    k = command_record(s, hq)
    if k["aktiviert"]:
        raise rules.Violation(f"{hq} is already activated")
    return k


def command_record(s, hq):
    """L233 (review M14): the Command record of an HQ/Staff; a unit without one (not an HQ) is a Violation, not a KeyError."""
    k = s["kommandos"].get(hq)
    if k is None:
        raise rules.Violation(f"{hq} is not an HQ/Staff with a Command marker [RULE 4.1 p.18]")
    return k


def cmd_hq(s, args):
    rules.need(args, 1, "hq <hq>")
    hq = args[0]
    e = state.unit(s, hq)
    k = command_record(s, hq)
    ph = s["phase"]
    if ph not in rules.IMPULSES - {"3.3.1a", "3.3.2d"}:
        raise rules.Violation(f"No HQ impulse in phase {ph}")
    if ph in ("3.3.1b", "3.3.2a") and e.get("ebene") != "CO":
        raise rules.Violation(f"In {ph} only the CO HQ acts")
    if ph == "3.3.1b" and not k["aktiviert"]:
        raise rules.Violation("CO HQ not activated; impulse only in 3.3.2a [RULE 3.3.1b p.15]")
    if ph == "3.3.2a" and k["aktiviert"]:
        raise rules.Violation("CO HQ was activated and has already acted [RULE 3.3.2a p.16]")
    if ph == "3.3.1c" and not (e.get("ebene") == "PLT" or e["typ"] == "Staff"):
        raise rules.Violation("In 3.3.1c PLT HQs and CO Staff act")
    if ph == "3.3.1c" and not k["aktiviert"]:
        raise rules.Violation(f"{hq} was not activated; impulse only in 3.3.2b/c (Initiative) [RULE 3.3.1c p.15]")
    if ph == "3.3.2b" and (k["aktiviert"] or e.get("ebene") != "PLT"):
        raise rules.Violation(f"{hq}: PLT HQ Initiative only for non-activated PLT HQs [RULE 3.3.2b p.16]")
    if ph == "3.3.2c":
        if e["typ"] != "Staff" or k["aktiviert"]:
            raise rules.Violation(
                "3.3.2c: only non-activated CO Staff, exactly 1 Command without card draw [RULE 3.3.2c p.16]"
            )
        k["verfuegbar"] = 1
    if k["fertig"]:
        raise rules.Violation(f"{hq} has already ended its impulse this turn")
    s["aktiver_hq"] = hq
    s["impuls_aktionen"] = {}
    state.save_state(s, f"Impulse {hq} begins", None)
    if ph in ("3.3.2a", "3.3.2b"):
        print(
            f"Active HQ: {hq} (Initiative). Now draw an Action card: fof.py card <no> <small number in the star>; modifiers 4.1.2, minimum 0 [RULE {ph} p.16, 4.1.1 p.19]"
        )
    else:
        print(
            f"Active HQ: {hq}."
            + (
                " Now draw an Action card: fof.py card <no> <helmet number>"
                if ph != "3.3.2c"
                else " 1 Command (Staff Initiative)."
            )
        )


def cmd_card(s, args):
    hq = s.get("aktiver_hq")
    if not hq or hq == "GI":
        raise rules.Violation("No active HQ (first 'hq <name>')")
    if s["phase"] not in rules.IMPULSES - {"3.3.1a", "3.3.2c", "3.3.2d"}:
        raise rules.Violation(f"Card draw for Commands only in HQ impulses, currently {s['phase']}")
    k = s["kommandos"][hq]
    if k.get("gezogen") == [s["zug"], s["phase"]]:
        raise rules.Violation(f"{hq} has already drawn in this impulse [RULE 4.1 p.18]")
    rules.need(args, 2, "card <no|?> <helmet number> [--raw]")
    nr, raw = args[0], rules.int_value(args[1], "helmet number")
    o = options.parse_opts(args[2:])
    e = state.unit(s, hq)
    mods = []
    if not o.get("--roh"):
        ez = comms.experience(e)
        if ez == "Green":
            mods.append(("Green", -1))
        if ez == "Veteran":
            mods.append(("Veteran", +1))
        if state.pinned(e):
            mods.append(("Pinned", -1))
        if e.get("bereich", "offen") != "offen":
            mods.append(("under cover", +1))
        v = fire.vof_against(s, e["karte"], e["seite"], ignore_mines=True)
        vm = rules.CMD_VOF_MODIFIERS.get(v[0], -3) if v else 0
        vn = f"VOF {rules.VOF_NAME.get(v[0], v[0])}" if v else ""
        if e.get("mine_hit") and vm > -3:
            vm, vn = -3, "Mines!-VOF"
        if enemy.sniper_on_card(s, e["karte"]) and vm > -3:
            vm, vn = -3, "Sniper on the card (7.15)"  # [RULE 4.1.2B p.20, 7.15 p.57]
        if vm:
            mods.append((vn, vm))
        if s.get("aktivitaet") == "No Contact":
            mods.append(("No Contact", +1))
    total = max(1 if k["aktiviert"] else 0, raw + sum(m for _, m in mods))
    k["verfuegbar"] = total
    k["gezogen"] = [s["zug"], s["phase"]]
    txt = (
        f"{hq} draws Action card #{nr}: {raw}"
        + (" " + " ".join(f"{n} {m:+d}" for n, m in mods) if mods else "")
        + f" = {total} Commands (saved {k['gespart']})"
    )
    evp = []
    if state.is_v4(s):
        events.event_pay_commands(s, hq, evp)
    state.save_state(s, txt + ("; " + "; ".join(evp) if evp else ""), "4.1.2 p.20")
    print(txt)
    for x in evp:
        print(f"{messages.BOARD}: " + x)
    bez = f", after event payment {k['verfuegbar']} new" if k["verfuegbar"] != total else ""  # [Normandy M1 p.18] L53
    sum_ = k["verfuegbar"] + k["gespart"]
    track_box = f"box {sum_}" if sum_ <= 10 else f"box 10 and remember {sum_ - 10} more (track ends at 10, K27)"  # L98
    print(
        f"Command marker on {track_box} (drawn {total}{bez}, saved {k['gespart']}); spend at most {rules.MAX_PER_IMPULSE[s['sicht']]} in this impulse [4.1.3]."
    )
    print(briefing.check_stamp(s))


def cmd_gi(s, args):
    if s["phase"] != "3.3.2d":
        raise rules.Violation(f"General Initiative only in 3.3.2d, currently {s['phase']} [RULE 3.3.2d p.16]")
    if len(args) < 2 or not args[1].lstrip("-").isdigit():  # L212: usage instead of a traceback
        raise rules.Violation(
            "General Initiative: fof.py gi <card no|?> <small number in the star (not the helmet), unmodified> [RULE 3.3.2d p.16]"
        )
    nr, small_number = args[0], rules.int_value(args[1], "small number")
    total = small_number // 2 if s.get("einzelzug") else small_number
    o = options.parse_opts(args[2:])
    gi_skill = ""
    if o.get("--skill-von"):
        h = o["--skill-von"]
        e = state.unit(s, h)
        if "General Initiative" not in (e.get("skills") or []):
            raise rules.Violation(f"{h} does not hold the General Initiative skill [RULE 12.7 p.82]")
        e["skills"].remove("General Initiative")
        total += 1
        gi_skill = f"; General Initiative skill of {h}: +1 GI Command, return skill marker (12.7: PLT HQ skill for units of this platoon) [Player Aid 2]"
    s["kommandos"].setdefault("GI", {"verfuegbar": 0, "gespart": 0, "aktiviert": False, "fertig": False})
    s["kommandos"]["GI"]["verfuegbar"] = total
    s["aktiver_hq"] = "GI"
    s["impuls_aktionen"] = {}
    txt = (
        f"General Initiative: Action card #{nr}, small number {small_number}"
        + (f", halved (single-platoon mission) = {total}" if s.get("einzelzug") else f" = {total}")
        + " Commands, unmodified, cannot be saved"
        + gi_skill
    )
    state.save_state(s, txt, "3.3.2d p.16, 4.1.1 p.19")
    print(txt)
    print(
        "Orders: fof.py order GI <unit> <action> ... (without HQ and communication; mandatory HQ actions with --originator=<HQ>)."
    )
    print(briefing.check_stamp(s))


def cmd_done(s, args):
    hq = s.get("aktiver_hq")
    if not hq:
        raise rules.Violation("No active HQ")
    k = s["kommandos"][hq]
    if hq == "GI":
        remainder = k["verfuegbar"]
        k["verfuegbar"] = 0
        s["aktiver_hq"] = None
        s["impuls_aktionen"] = {}
        state.save_state(
            s, "General Initiative ended" + (f", {remainder} Commands lost" if remainder else ""), "3.3.2d p.16"
        )
        print("General Initiative ended" + (f", {remainder} Commands lost (cannot be saved)" if remainder else ""))
        print(briefing.check_stamp(s))
        return
    e = state.unit(s, hq)
    limit = 0 if e.get("ebene") == "BN" else rules.SAVE_LIMIT[comms.experience(e)][0 if s["sicht"] == "tag" else 1]
    new = k["gespart"] + k["verfuegbar"]
    lost = max(0, new - limit)
    new = min(new, limit)
    k["gespart"], k["verfuegbar"], k["fertig"] = new, 0, True
    s["aktiver_hq"] = None
    s["impuls_aktionen"] = {}
    txt = f"{hq} ends impulse; saved {new}" + (f", {lost} lost (limit {comms.experience(e)} {limit})" if lost else "")
    state.save_state(s, txt, "4.1.3 p.20")
    print(txt)
    print(
        f"Board: flip Command marker {hq} to Activation Completed, Saved Commands zone box {new}"
        + (" (Zero Commands Box)" if new == 0 else "")
    )
    print(briefing.check_stamp(s))


def add_cover_marker(s, kid, type_, value, field=None):
    """New Cover marker on card kid with the lowest free id; returns the marker dict (L254). field: whether the marker
    is printed on the card (does not count towards the Cover Potential); default: everything but Basic Cover."""
    c = state.card(s, kid)
    i = len(c.setdefault("cover", [])) + 1
    cid = f"C{i}"
    while any(x["id"] == cid for x in c["cover"]):
        i += 1
        cid = f"C{i}"
    marker = {"id": cid, "typ": type_, "wert": value, "feld": type_ != "Basic Cover" if field is None else field}
    c["cover"].append(marker)
    return marker


def new_cover_marker(s, kid, type_, value):
    """Id of a new Cover marker (callers in contact, enemy and setup use the id)."""
    return add_cover_marker(s, kid, type_, value)["id"]


def mark(e, m):
    if m not in e["status"]:
        e["status"].append(m)
        if m == rules.EXPOSED and e.get("seite") == "US":
            e["_neu_exposed"] = True  # L483: Heat Casualties (Naktong M1 p.17) are checked in state.save_state


def new_name(s, type_, reuse_removed=False):
    """Lowest free counter number. reuse_removed: enemy counters Removed from Play return to the counter mix and are
    reused (glossary 'Removed from Play', E88, L215); friendly ones stay blocked (only back via Reconstitution)."""
    i = 1
    while f"{type_} {i}" in s["einheiten"] or (not reuse_removed and f"{type_} {i}" in s.get("removed_from_play", [])):
        i += 1
    return f"{type_} {i}"


def set_area(s, z, b):
    """Put unit z under Cover marker b on its card ('offen' = out of cover) [5.3]. _name is unused; it stays in the
    signature until the caller in setup.py stops passing it (review LOW)."""
    if b == "offen":
        z["bereich"] = "offen"
        return
    if not any(c["id"] == b for c in state.card(s, z["karte"]).get("cover", [])):
        raise rules.Violation(f"Cover {b} does not exist on {z['karte']}")
    occupied = {
        s["einheiten"][m]["seite"] for m in state.units_on(s, z["karte"]) if s["einheiten"][m].get("bereich") == b
    }
    if occupied and occupied != {z["seite"]}:
        raise rules.Violation(f"Cover {b} is occupied by the opposing side [5.3]")
    cv = next(c for c in state.card(s, z["karte"])["cover"] if c["id"] == b)  # exists, checked above
    if cv.get("kapazitaet"):
        st = sum(
            state.steps(s["einheiten"][m])
            for m in state.units_on(s, z["karte"])
            if s["einheiten"][m].get("bereich") == b and s["einheiten"][m] is not z
        )
        if st + state.steps(z) > cv["kapazitaet"]:
            raise rules.Violation(
                f"{cv['typ']} {b} holds at most {cv['kapazitaet']} steps, occupied {st} [RULE 5.3.2 p.37]"
            )
    z["bereich"] = b


def check_move(s, e, n, target_card, akt):
    """Legality of one card move (read-only). The VOF on the destination is computed at most once (review Effizienz)."""
    memo = {}

    def vof_on(kid, side=None):
        side = side or e["seite"]
        if (kid, side) not in memo:
            memo[kid, side] = fire.vof_against(s, kid, side)
        return memo[kid, side]

    if e.get("an_bord"):
        raise rules.Violation(
            f'{n} is on board the {e["an_bord"]} and moves with it in phase 3.6; to leave it first: order <HQ> "{n}" 4.2.2h --what=jeep [10.8.1, Normandy CSR 1]'
        )
    if rules.EXPOSED in e["status"]:
        raise rules.Violation(f"{n} is Exposed and may no longer change cards [RULE 5.1.2 p.31]")
    if not geometry.adjacent(s, e["karte"], target_card):
        raise rules.Violation(f"{target_card} is not adjacent to {e['karte']} (diagonal counts too) [RULE 5.1.2 p.31]")
    zk = state.card(s, target_card)
    if zk.get("ausserhalb") and e["seite"] == "US":
        raise rules.Violation(
            f"{target_card} lies outside the mission boundaries (map extension); friendly units may not go there [RULE 2.4.1 p.10, 8.4.5 p.65]"
        )
    if e["seite"] == "US" and s.get("hold_up") == s["zug"] and not state.units_on(s, target_card):
        raise rules.Violation(
            f"Hold up!: no movement onto an unoccupied card this turn ({target_card}) [Normandy M3 p.26]"
        )
    if e.get("mine_hit"):
        raise rules.Violation(
            f"{n} is under the Mine marker and may not move to an adjacent card this turn [RULE 7.9.1 p.54]"
        )
    if state.is_v4(s):
        event_move_check(s, e, target_card)
    if state.pinned(e) or e["typ"] in ("Fire Team", "Litter Team", "Paralyzed Team") or state.fire_team_side(e):
        friend = [m for m in state.units_on(s, target_card, e["seite"]) if m != n]
        ok = (zk.get("staging") and akt in ("4.2.2a", "4.2.2b")) or (friend and vof_on(target_card) is None)
        if not ok:
            raise rules.Violation(
                f"{n} (Pinned/LAT/Fire Team side) may only move to a Staging Area or to a card occupied by friendly units without VOF [RULE 4.2.5 p.26]"
            )
    if e["typ"] == "Paralyzed Team" and akt != "4.2.2a":
        raise rules.Violation("Paralyzed Team: only Move to an Adjacent Card [RULE 4.2.5 p.26]")
    if (state.pinned(e) or e["typ"] == "Paralyzed Team") and (
        comms.radios_of(e) or e.get("traegt_casualties") or e.get("assets")
    ):  # L523: also the asset list (smoke, illumination, rifle grenades), 4.2.5 footnote 'must drop any assets'
        load = [g["typ"] for g in comms.radios_of(e)] + list(e.get("assets") or [])
        if e.get("traegt_casualties"):
            load.append(f"{e['traegt_casualties']} Casualty")
        raise rules.Violation(
            f"{n} is Pinned/Paralyzed and carries Assets or Casualties ({', '.join(load)}); drop them first "
            f"(fof.py drop, no Command) [RULE 4.2.5 p.27 'must drop any assets or casualties', 5.1.6E p.33]"
        )
    if akt in ("4.2.2c", "4.2.2d"):
        if not infiltration_marker(
            s, e["karte"], target_card, vof_on
        ):  # L535 (review C1): same test as infiltrate_possible
            raise rules.Violation(
                "Infiltration only if the origin or destination card has a VOF marker [RULE 5.1.4 p.32]"
            )
        if e.get("tripod") or e.get("vof_rating") == "H" or state.is_mortar(e):
            raise rules.Violation(f"{n} (tripod/H VOF) may not infiltrate [RULE 4.2.2c p.23]")
    diagonal_pdf_check(s, e, target_card)


def infiltrate_possible(s, e, target_card):
    """L509 [RULE 5.1.4 p.32]: a friendly Good Order unit or an Assault/Fire Team (4.2.5 LAT list), not Exposed, without
    tripod/H/mortar, with a VOF marker (or a Grenade Miss marker) on the origin or the destination card."""
    if e["seite"] != "US" or state.pinned(e) or state.fire_team_side(e) or rules.EXPOSED in e["status"]:
        return False
    if state.is_lat(e) and "4.2.2c" not in rules.LAT_ALLOWED.get(e["typ"], ()):
        return False  # 4.2.5: Assault and Fire Teams may infiltrate, Paralyzed and Litter Teams may not
    if e.get("tripod") or e.get("vof_rating") == "H" or state.is_mortar(e):
        return False
    return infiltration_marker(s, e["karte"], target_card)


def infiltration_marker(s, origin, target_card, vof=None):
    """[RULE 5.1.4 p.32] a VOF marker (any side: K34, also the own Point Blank VOF) or a Grenade Miss marker on the
    origin or the destination card. One test for check_move and infiltrate_possible (L535, review C1); vof(kid, side)
    may be a memoized lookup (check_move)."""
    vof = vof or (lambda kid, side: fire.vof_against(s, kid, side))
    return any(
        vof(k, "US") is not None or vof(k, "Feind") is not None or state.card(s, k).get("grenade_miss")
        for k in (origin, target_card)
    )


_UNSET = object()


def event_move_check(s, e, target_card):
    """L241 (review M15): events.event_move for its Violations only (Trouble on the Flank). It also books the 'Event
    fulfilled' flag; here that flag is restored, so the booking and its protocol line happen once, in move_unit."""
    ev = s.get("ereignis_flanke")
    before = ev.get("erfuellt", _UNSET) if ev else _UNSET
    try:
        events.event_move(s, e, target_card, [])
    finally:
        if ev:
            if before is _UNSET:
                ev.pop("erfuellt", None)
            else:
                ev["erfuellt"] = before


def diagonal_pdf_check(s, e, target_card):
    """[RULE 5.1.2 p.32] a diagonal move may not cross a PDF between the two orthogonal neighbours (both sides, L131)."""
    ka, zk = state.card(s, e["karte"]), state.card(s, target_card)
    if abs(ka["reihe"] - zk["reihe"]) == 1 and abs(ka["spalte"] - zk["spalte"]) == 1:
        e1, e2 = geometry.card_at(s, ka["reihe"], zk["spalte"]), geometry.card_at(s, zk["reihe"], ka["spalte"])
        if e1 and e2:
            for f in s["einheiten"].values():
                if fire.is_firing(f) and f["ziel"] != f["karte"]:
                    path_cards = [f["karte"]] + (geometry.line_between(s, f["karte"], f["ziel"]) or []) + [f["ziel"]]
                    for i in range(len(path_cards) - 1):
                        if {path_cards[i], path_cards[i + 1]} == {e1, e2}:
                            raise rules.Violation(
                                f"Diagonal {e['karte']} to {target_card} crosses the PDF {path_cards[i]} to {path_cards[i + 1]} [RULE 5.1.2 p.32]"
                            )


def move_unit(s, n, target_card, area, exposed, prot, open_all=True):
    e = s["einheiten"][n]
    from_ = e["karte"]
    grenades.grenade_expires(s, e, n, prot)
    if state.is_v4(s):
        comms.lay_line(s, n, e, from_, prot, s.get("_befehl_opts"))
        combat.ammo_surplus(s, n, e, from_, prot)
        events.event_move(s, e, target_card, prot)
    old_cover = fire.cover_of(s, e)
    e["karte"] = target_card
    e["bereich"] = "offen"
    if area and area != "offen":
        set_area(s, e, area)
    new_cover = fire.cover_of(s, e)
    zk = state.card(s, target_card)
    if state.card(s, from_).get("staging") and zk.get("staging"):
        exposed = False  # 5.1.3
    if (
        old_cover
        and new_cover
        and old_cover["typ"] in ("Trench", "Bunker", "Pillbox")
        and new_cover["typ"] in ("Trench", "Bunker", "Pillbox")
    ):
        exposed = False  # 5.1.2
    if exposed:
        mark(e, rules.EXPOSED)
    prot.append(
        f"{n} to {target_card}"
        + (f" under {area}" if area and area != "offen" else "")
        + (", Exposed" if rules.EXPOSED in e["status"] else ", not Exposed")
    )
    if (
        not area and e["seite"] == "US" and not e.get("fahrzeug")
    ):  # L180; L187 vehicles use no cover markers: no reminder when the player chose --area=open explicitly
        # L161 [RULE 5.1.2 p.31] 'When entering another card that has an unoccupied or friendly-occupied Cover marker,
        # the moving unit may move directly under the Cover marker.'
        free = [cv["id"] for cv in state.free_cover(s, target_card, e["seite"], steps=state.steps(e))]  # L534
        if free:
            prot.append(
                f"{n} arrives out of cover; free or friendly Cover marker on {target_card}: {', '.join(free)} - "
                "the unit may go directly under it when entering (repeat the order with --area=<id>) [5.1.2 p.31]"
            )
    campaign.patrol_move(s, n, from_, target_card, prot)
    fire.fire_after_move(s, n, prot, origin=from_, open_all=open_all)
    if state.units_on(s, target_card, state.opponent_of_side(e["seite"])):
        prot.append(f"Point Blank on {target_card}: each side's VOF only hits the opposing side [6.2.1b]")
    own_fire = friendly_fire_on(s, n, target_card)
    if own_fire:
        prot.append(
            f"WATCH friendly fire: {n} on {target_card} is under the VOF of own units from other cards: "
            f"{', '.join(own_fire)} (Cease Fire/Shift Fire, 4.2.4k/l) [6.3.3, 6.1]"
        )
    if state.is_v4(s):
        pc_ = s.pop("_pionier_check", None)
        if pc_ and pc_[0] == n and pc_[1] == target_card:
            contact.request_mine_check(
                s,
                [n],
                target_card,
                prot,
                "Engineers clear a path"
                + (" (infiltration succeeded)" if pc_[2] == 1 else " (infiltration failed: not Exposed, no path)"),
                cards=pc_[2],
                path_=pc_[2] == 1,
            )
        else:
            contact.request_mine_check(s, [n], target_card, prot, "unit enters a mined card")


def hq_back(s, hq_name2, z, prot):
    """[RULE 6.5.2 p.49] reconstituted HQ on the card of the receiving unit, always Green."""
    old = s.get("rfp_daten", {}).get(hq_name2, {})
    e = {
        "typ": "HQ",
        "ebene": old.get("ebene", "PLT"),
        "platoon": old.get("platoon", z.get("platoon")),
        "seite": "US",
        "erfahrung": "Green",
        "karte": z["karte"],
        "bereich": z.get("bereich", "offen"),
        "status": [],
        "steps": 1,
        "fire_team_seite": True,
        "ft_vof": old.get("ft_vof", "S"),
        "vof_rating": None,
        "reichweite": "L",
        "ziel": None,
        "funk": [],
    }
    s["removed_from_play"].remove(hq_name2)
    s["einheiten"][hq_name2] = e
    s["kommandos"].setdefault(hq_name2, {"verfuegbar": 0, "gespart": 0, "aktiviert": False, "fertig": False})
    s["kommandos"][hq_name2].update(gespart=0, verfuegbar=0)
    prot.append(
        f"{hq_name2} reconstituted on {z['karte']}, Green (saves at most {rules.SAVE_LIMIT['Green'][0]}) [RULE 6.5.2 p.49]"
    )
    return e


def hand_over_step(s, n, prot, team):
    """Receiving unit loses a step; if only one step of the squad remains, it becomes a Fire/Assault Team [RULE 6.5.2 p.49]."""
    z = s["einheiten"][n]
    if state.steps(z) > 1:
        z["steps"] = state.steps(z) - 1
        prot.append(f"{n} down to {z['steps']} steps")
        if state.steps(z) == 1 and z.get("letzter_step"):
            lat = (team or "Fire") + " Team"
            new = new_name(s, lat)
            s["einheiten"][new] = combat.new_lat(z, lat, n)
            s["einheiten"][new]["status"] = []
            combat.remove_from_play(s, n, prot, f"last step becomes {lat} ({new}) [6.5.2 p.49]", successor=new)
    else:
        combat.remove_from_play(s, n, prot, "used for the reconstitution [6.5.2 p.49]")


def order_bn(s, target_name, akt):
    """[RULE 6.5.2 p.50] 'While off-map, the BN HQ can order the Reconstitution of the CO HQ from an eligible unit with a BN TAC
    radio/phone during the BN HQ Impulse.' Order: Any Platoon HQ, Arty FO, CO Staff."""
    if akt != "4.2.1e":
        raise rules.Violation("The BN HQ (off-map) only gives 'Reconstitute the CO HQ' (4.2.1e) here [RULE 6.5.2 p.50]")
    if s["phase"] != "3.3.1a" or s.get("bn_hq") != "off-map":
        raise rules.Violation(
            "BN HQ off-map: reconstitution of the CO HQ only in the BN HQ Impulse 3.3.1a [RULE 6.5.2 p.50]"
        )
    co = s.get("co_hq")
    if co in s["einheiten"] or co not in s.get("removed_from_play", []):
        raise rules.Violation(f"{co} is not Removed from Play")
    z = state.unit(s, target_name)
    plt = [n for n, e in s["einheiten"].items() if e.get("ebene") == "PLT" and e["typ"] == "HQ"]
    if z.get("ebene") != "PLT" and plt:
        raise rules.Violation(
            f"A PLT HQ first ({', '.join(plt)}); on the Fire Team side rally first [RULE 6.5.2 p.49/50]"
        )
    if z.get("ebene") != "PLT" and not (z["typ"] == "FO" and "Arty" in target_name) and z["typ"] != "Staff":
        raise rules.Violation(f"{target_name} is not eligible (Any Platoon HQ, Arty FO, CO Staff) [RULE 6.5.2 p.49]")
    if state.fire_team_side(z) or not state.good_order(z):
        raise rules.Violation(f"{target_name} must be on its Good Order side (rally first) [RULE 6.5.2 p.50]")
    if state.radio_active(s) and not comms.radios_of(z, "SCR300", "BN TAC"):
        raise rules.Violation(
            f"{target_name} carries no BN TAC device; first pick up an SCR300 BN TAC (4.2.2h) [RULE 6.5.2 p.50, FM1 p.38] [open U8]"
        )
    prot = []
    if not state.radio_active(s):
        prot.append("Mission without radio: BN TAC connection assumed per mission [open U8]")
    radio = [dict(g) for g in comms.radios_of(z)]
    z["funk"] = []
    e = hq_back(s, co, z, prot)
    e["ebene"] = "CO"
    e["funk"] = radio
    combat.remove_from_play(s, target_name, prot, f"becomes {co} [6.5.2 p.49]")
    state.save_state(
        s, f"BN HQ orders Reconstitute the CO HQ: {target_name}; " + "; ".join(prot), "4.2.1e p.22, 6.5.2 p.50"
    )
    print(f"{messages.ALLOWED} {messages.rule('4.2.1e p.22, 6.5.2 p.50')}")
    briefing.print_board(prot, s)


# [RULE 12.7 p.82, Player Aid 2 Skills] Skills in use
SKILL_AUTO = {
    "Auto Spot": ("4.2.4a",),
    "Auto Cover": ("4.2.2e",),
    "Auto Concentrate": ("4.2.4b",),  # L476: marker name as in rules.SKILL_MARKERS_NORMANDY and the setup data
    "Auto Infiltrate": ("4.2.2c", "4.2.2g"),
    "Auto Grenade": ("4.2.4d",),
}


def skill_holder(s, z_name, skill):
    """12.7: PLT HQ skill for every unit of the platoon; CO HQ and Staff skill only for the unit itself."""
    z = s["einheiten"][z_name]
    if skill in (z.get("skills") or []) and (z["typ"] in ("HQ", "Staff")):
        return z_name
    p = z.get("platoon")
    if p:
        for n, e in s["einheiten"].items():
            if (
                e.get("seite") == "US"
                and e["typ"] == "HQ"
                and e.get("ebene") == "PLT"
                and str(e.get("platoon")) == str(p)
                and skill in (e.get("skills") or [])
            ):
                return n
    raise rules.Violation(
        f"Skill {skill} is not available to {z_name}: PLT HQ skills only for units of this platoon, CO HQ/Staff skills only for the unit itself [RULE 12.7 p.82]"
    )


def cmd_late_order(s, args):
    """L78 (V22): forgotten order of an HQ/Staff whose impulse already ended this turn.
    Runs like 'order' (all checks except the repeat check of that impulse), cost from its saved Commands,
    the 6-per-impulse limit counts what the HQ already spent this turn (s['impuls_ausgegeben'], 4.1.3)."""
    if len(args) < 3:
        raise rules.Violation("lateorder <HQ> <unit> <action> [--target=..] [--area=..] ...")
    hq = args[0]
    if s["phase"] not in rules.IMPULSES:
        raise rules.Violation(
            f"Late order only in the Friendly Command Phase 3.3, currently {s['phase']} [RULE 3.3 p.15]"
        )
    k = s["kommandos"].get(hq)
    if hq == "GI" or not k or not k.get("fertig"):
        raise rules.Violation(f"Late order only for an HQ/Staff whose impulse ended this turn ({hq})")
    if hq == s.get("aktiver_hq"):
        raise rules.Violation(f"{hq} is active: use the normal 'order'")
    spent = s.get("impuls_ausgegeben", {}).get(hq, 0)
    cmd_order(s, args, late_order=hq)
    print(
        f"Late order {hq}: {spent} already spent in that impulse; Commands now {s['kommandos'][hq]['gespart']} (Saved Commands zone)"
    )


def cmd_correct(s, args):
    """L80 (V22): the board is the master - fix a proven wrong booking instead of editing the JSON by hand.
    correct casualty <card> <+n|-n> [--side=Feind|US] --reason=<text>"""
    usage = "correct casualty <card> <+n|-n> [--side=Feind|US] --reason=.. | correct status <unit> <marker> remove|add --reason=.. | correct grenade <unit> expired <origin card> --reason=.. | correct ammo <unit> <+n|-n> --reason=.. | correct target <unit> <card> --reason=.."
    positional = {"casualty": 3, "munition": 3, "ziel": 3, "status": 4, "granate": 4}  # subwords: grenade, ammo, target
    if not args or args[0] not in positional:
        raise rules.Violation(usage)
    rules.need(args, positional[args[0]], usage)  # L232 (review H12): Violation instead of IndexError
    o = options.parse_opts(args[positional[args[0]] :])
    if not o.get("--grund"):
        raise rules.Violation("give --reason=<text> (source of the correction, e.g. counter photo, player decision)")
    if args[0] == "ziel":
        # L96: restore a fire target afterwards (wrongly booked Cease Fire)
        n, kid = args[1], args[2]
        e = state.unit(s, n)
        state.card(s, kid)
        e["ziel"] = kid
        txt = f"Correction {n}: fires on {kid} again, PDF from {e['karte']} to {kid} ({o['--grund']})"
        state.save_state(s, txt, "6.1.2 p.44")
        print(f"Board: place PDF {n} from {e['karte']} to {kid}, VOF on {fire.effective_fire_target(s, n)}")
        print(briefing.check_stamp(s))
        return
    if args[0] == "munition":
        # L95: set an ammo marker afterwards (e.g. ammo spent on fire that did not happen because LOS was lost, 7.18.4)
        n = args[1]
        e = state.unit(s, n)
        m = e.get("munition")
        if not m:
            raise rules.Violation(f"{n} carries no ammo")
        d = rules.int_value(args[2], "ammo correction")
        old = m["punkte"]
        m["punkte"] = max(0, min(m.get("start", old + d), old + d))
        txt = f"Correction {n}: {m.get('typ', '')} ammo {old} to {m['punkte']} ({o['--grund']})"
        state.save_state(s, txt, "7.18.4 p.61")
        print(f"Board: turn ammo marker {n} from {old} to {m['punkte']}")
        print(briefing.check_stamp(s))
        return
    if args[0] == "granate":
        # L92: expire a Grenade marker afterwards as a Grenade Miss on the origin card (7.10.4)
        n, kid = args[1], args[3]
        e = state.unit(s, n)
        if not e.get("grenade"):
            raise rules.Violation(f"{n} carries no Grenade marker")
        state.card(s, kid)["grenade_miss"] = True
        e["grenade"] = []
        if (
            s["phase"] == "3.7.4"
            and n in s.get("kampf_offen", [])
            and fire.vof_against(s, e["karte"], e["seite"], ignore_mines=True) is None
            and not state.card(s, e["karte"]).get("grenade_miss")
            and not e.get("mine_hit")
        ):
            s["kampf_offen"].remove(n)
            s.get("kampf_ncm", {}).pop(n, None)  # frozen state without this unit (no VOF against it any more)
        txt = f"Correction {n}: Grenade marker expired, Grenade Miss (-1) on {kid} ({o['--grund']})"
        state.save_state(s, txt, "7.10.4 p.55")
        print(f"Board: take the Grenade marker from {n}, Grenade Miss marker (-1) on {kid}")
        print(briefing.check_stamp(s))
        return
    if args[0] == "status":
        # L83: set/remove a unit's status marker afterwards (e.g. a move re-rated as a successful infiltration)
        n, marker, how = args[1], args[2], args[3]
        e = state.unit(s, n)
        if how == "weg":
            if marker not in e["status"]:
                raise rules.Violation(f"{n} has no {marker} marker")
            e["status"].remove(marker)
        elif how == "dazu":
            mark(e, marker)
        else:
            raise rules.Violation("remove | add")
        txt = f"Correction {n}: {marker} {'removed' if how == 'weg' else 'added'} ({o['--grund']})"
        state.save_state(s, txt, "AI_BRIEFING: the board is the master")
        print(f"Board: {marker} marker on {n}: " + ("remove" if how == "weg" else "place"))
        print(briefing.check_stamp(s))
        return
    kid, n = args[1], rules.int_value(args[2], "casualty correction")
    c = state.card(s, kid)
    key = "casualties_feind" if o.get("--seite", "Feind") == "Feind" else "casualties"
    old = c.get(key, 0)
    if old + n < 0:
        raise rules.Violation(f"Only {old} casualties ({key}) lie on {kid}")
    c[key] = old + n
    txt = f"Correction {kid}: {key} {old} to {c[key]} ({o['--grund']})"
    state.save_state(s, txt, "AI_BRIEFING: the board is the master")
    print(f"Board: casualty markers on {kid}: {old} to {c[key]}")
    print(briefing.check_stamp(s))


def _order_move(s, ctx):
    """Order handler for: akt in ('4.2.2a', '4.2.2c')"""
    target_card = ctx.o.get("--ziel")
    if not target_card:
        raise rules.Violation("--target=<card> missing")
    state.card(s, target_card)
    check_move(s, ctx.z, ctx.target_name, target_card, ctx.akt)
    plain = ctx.o.get("--normal")  # L547 (review K6): --plain=no is not a yes; a bare --plain is
    if plain not in (None, True, *YES_WORDS, *NO_WORDS):
        raise rules.Violation("--plain=yes|no")
    if ctx.akt == "4.2.2a" and plain not in (True, *YES_WORDS) and infiltrate_possible(s, ctx.z, target_card):
        # L509: a Move where an Infiltrate would be possible is never better (a failed attempt is the same Move)
        raise rules.Violation(
            f"{ctx.target_name} could infiltrate to {target_card} (VOF on the origin or destination card) [RULE 5.1.4 p.32]: "
            "order 4.2.2c with --success=yes|no (2 cards, Infiltrate icon), or --plain=yes for an intended Move; nothing booked"
        )
    engineer = ctx.akt == "4.2.2c" and contact.engineers_clear(s, ctx.z) and bool(contact.mines_on(s, target_card))
    if engineer:
        s["_pionier_check"] = (ctx.target_name, target_card, 1 if ctx.success == "ja" else 3)
        exposed = False  # CSR 10: failed Engineer infiltration without Exposed, but 3 cards
    else:
        exposed = ctx.akt == "4.2.2a" or ctx.success == "nein"
    move_unit(s, ctx.target_name, target_card, ctx.o.get("--bereich"), exposed=exposed, prot=ctx.prot)
    ctx.moved = [ctx.target_name]


def platoon_move_members(s, orig_name, orig, akt):
    """[RULE 4.2.2b/d p.23] the units a Platoon Move/Infiltrate takes along: Good Order, not Exposed, in the chain of
    command and in communication with the originator, on its card; no tripod/H units for an infiltration. L249: one
    member set for the stacking pre-check and the handler."""
    candidate = []
    for n, e in s["einheiten"].items():
        if e["seite"] != "US" or e["karte"] != orig["karte"]:
            continue
        try:
            comms.chain_of_command(s, orig_name, n)
            comms.communication(s, orig_name, n)
        except rules.Violation:
            continue
        if not state.good_order(e) or rules.EXPOSED in e["status"]:
            continue
        if e.get("an_bord") or e.get("fahrzeug"):
            continue  # L454: vehicles and units on board move in phase 3.6, not with the platoon
        if akt == "4.2.2d" and (e.get("tripod") or e.get("vof_rating") == "H"):
            continue
        single = "4.2.2a" if akt == "4.2.2b" else "4.2.2c"
        if single in (s.get("impuls_aktionen") or {}).get(n, []):
            continue  # L511: already moved/infiltrated in this impulse (4.2 p.21)
        candidate.append(n)
    return candidate


def _order_move_platoon(s, ctx):
    """Order handler for: akt in ('4.2.2b', '4.2.2d')"""
    target_card = ctx.o.get("--ziel")
    if not target_card:
        raise rules.Violation("--target=<card> missing")
    state.card(s, target_card)
    # L511 [RULE 4.2 p.21, 4.2.2b/d 'Have each unit in the platoon perform a Move/an Attempt to Infiltrate'] every member
    # has made the single action too and may not repeat it in this impulse
    ctx.also_book = "4.2.2a" if ctx.akt == "4.2.2b" else "4.2.2c"
    result = parse_per_unit(ctx.success)  # L230 (review H8): yes/no and ja/nein per unit
    candidate = (
        ctx.candidates if ctx.candidates is not None else platoon_move_members(s, ctx.orig_name, ctx.orig, ctx.akt)
    )
    if not candidate:
        raise rules.Violation(
            "No Good Order unit of the platoon without Exposed in communication on the HQ's card [RULE 4.2.2b p.23]"
        )
    with fire.cached(s):  # read-only checks of the same move: one fire map for all members (L450)
        for n in candidate:
            # L235 (review M8): legality of every member before the draw prompt, as 4.2.2c does (L120)
            check_move(s, s["einheiten"][n], n, target_card, ctx.akt)
    if ctx.akt == "4.2.2d" and any(n not in result for n in candidate):
        raise rules.Violation(
            "Platoon Infiltrate: each unit draws itself (2 cards, own experience, Infiltrate symbol): --success="
            + ",".join(f"{n}:yes|no" for n in candidate)
            + " [RULE 4.2 Notes p.21]"
        )
    for n in candidate:
        move_unit(
            s,
            n,
            target_card,
            ctx.o.get("--bereich"),
            exposed=(ctx.akt == "4.2.2b" or result.get(n) == "nein"),
            prot=ctx.prot,
            open_all=False,
        )
    # the platoon moves together: the board-wide 6.1.1 check once after the last member (L450), so members still on the
    # origin card no longer open fire there only to cease fire again when they move
    fire.open_fire(s, ctx.prot)
    ctx.moved = candidate


def _check_seek_cover(s, ctx):
    """State-only legality of Seek Cover, also before the draw (L545, review C5)."""
    if ctx.z.get("an_bord"):
        raise rules.Violation(f"{ctx.target_name} is on board the {ctx.z['an_bord']}: no cover marker [10.8.1]")
    if ctx.z.get("bereich", "offen") != "offen":
        raise rules.Violation(f"{ctx.target_name} is already under cover [RULE 4.2.2e p.23]")
    present = len([c for c in ctx.zk.get("cover", []) if not c.get("feld")])
    if ctx.zk.get("cover_max") is not None and present >= ctx.zk["cover_max"]:
        raise rules.Violation(
            f"{ctx.z['karte']} has reached its Cover Potential ({ctx.zk['cover_max']}) [RULE 5.3 p.36]"
        )


def _order_seek_cover(s, ctx):
    """Order handler for: akt == '4.2.2e'"""
    _check_seek_cover(s, ctx)
    if ctx.success == "ja":
        if ctx.zk.get("gebaeude_tabelle") and state.is_v4(s):
            # [CSR 8 p.15, 5.3.3 p.38] urban card: cover type by R# column 8
            if not ctx.o.get("--gebaeude"):
                raise rules.Violation(
                    "Seek Cover on Village/Farm/Cemetery/Church: R# column 8 on the building table, --building=<R#> [--building-value=<n>] [CSR 8 p.15]"
                )
            gt, gw, upper_ = contact.building_cover(
                s, ctx.z["karte"], ctx.z, ctx.o["--gebaeude"], ctx.o.get("--gebaeude_wert")
            )
            cover = add_cover_marker(s, ctx.z["karte"], gt, gw, field=False)
            us = upper_story_type(ctx.zk)
            if gt != "Basic Cover" and us:
                # L73 [RULE 5.3.3 p.38, 5.2.2B p.36] Multi-Story/Church symbol on the card: add Upper Story or Church Tower,
                # same value, does not count towards the Cover Potential (the star of the CSR 8 table applies to snipers/spotters only)
                uid = add_cover_marker(s, ctx.z["karte"], us, gw, field=True)["id"]
                ctx.prot.append(
                    f"additionally {us} marker {uid} (+{gw}) on {ctx.z['karte']}; does not count towards the Cover Potential"
                    + (", 1 step only" if us == "Church Tower" else "")
                    + " [5.3.3 p.38, 5.2.2B p.36]"
                )
            elif upper_:
                ctx.prot.append(
                    "card without Multi-Story symbol: no Upper Story marker (star only for snipers/spotters) [CSR 8 p.15, 5.3.3 p.38]"
                )
        else:
            cover = add_cover_marker(
                s, ctx.z["karte"], "Basic Cover", options.int_opt(ctx.o, "--wert", "cover value", 1)
            )
        grenades.grenade_expires(s, ctx.z, ctx.target_name, ctx.prot)  # L171 [RULE 7.10.4] moving within the card
        ctx.z["bereich"] = cover["id"]
        mark(ctx.z, rules.EXPOSED)
        ctx.prot.append(
            f"new cover marker {cover['id']} ({cover['typ']}) on {ctx.z['karte']}, {ctx.target_name} beneath it, Exposed"
        )
        if state.is_v4(s) and state.option(s, "U20_mine_bei_seek_cover"):
            contact.request_mine_check(
                s,
                [ctx.target_name],
                ctx.z["karte"],
                ctx.prot,
                "movement under new cover" + state.open_reading(s, "U20_mine_bei_seek_cover"),
            )
    else:
        ctx.prot.append(f"{ctx.target_name}: Seek Cover failed, nothing happens")
        s["letzter_versuch"] = [ctx.target_name, ctx.akt, s["phase"]]


def _check_move_within_card(s, ctx):
    """State-only legality of Move/Infiltrate within a Card, also before the draw (L545, review C5); returns the area."""
    if ctx.z.get("an_bord"):  # L545 (review C6): as Seek Cover, no cover marker for a jeep passenger
        raise rules.Violation(f"{ctx.target_name} is on board the {ctx.z['an_bord']}: no cover marker [10.8.1]")
    b = options.text_opt(ctx.o, "--bereich", "--area=<cover-id|open>")
    if not b and ctx.akt == "4.2.2g" and contact.engineers_clear(s, ctx.z) and contact.mines_on(s, ctx.z["karte"]):
        b = ctx.z.get("bereich", "offen")  # [Normandy CSR 10] engineers clearing mines need no destination (L107)
    if not b:
        raise rules.Violation("Specify --area=<cover-id|open>")
    if ctx.akt == "4.2.2g" and fire.vof_against(s, ctx.z["karte"], ctx.z["seite"]) is None:
        raise rules.Violation("Infiltrate within a Card requires a VOF on the card [RULE 4.2.2g p.23]")
    if ctx.akt == "4.2.2g" and (ctx.z.get("tripod") or ctx.z.get("vof_rating") == "H" or state.is_mortar(ctx.z)):
        raise rules.Violation(
            f"{ctx.target_name} (tripod/H VOF) may not infiltrate, also not within the card [RULE 5.1.4 p.32]"
        )  # L139
    if ctx.akt == "4.2.2g" and rules.EXPOSED in ctx.z["status"]:
        raise rules.Violation(f"{ctx.target_name} is Exposed and may not infiltrate [RULE 5.1.4 p.32]")  # L139
    if ctx.z.get("mine_hit"):
        raise rules.Violation(
            f"{ctx.target_name} is under the Mine marker and may not move this turn [RULE 7.9.1 p.54]"
        )
    if b != "offen" and not any(c["id"] == b for c in ctx.zk.get("cover", [])):
        raise rules.Violation(f"No cover marker {b} on {ctx.z['karte']}")
    return b


def _order_move_within_card(s, ctx):
    """Order handler for: akt in ('4.2.2f', '4.2.2g')"""
    b = _check_move_within_card(s, ctx)
    old_cv = fire.cover_of(s, ctx.z)
    grenades.grenade_expires(s, ctx.z, ctx.target_name, ctx.prot)
    set_area(s, ctx.z, b)
    new_cv = fire.cover_of(s, ctx.z)
    fixed = bool(old_cv and new_cv and old_cv["typ"] in rules.FIXED_COVER and new_cv["typ"] in rules.FIXED_COVER)
    engineer = ctx.akt == "4.2.2g" and contact.engineers_clear(s, ctx.z) and bool(contact.mines_on(s, ctx.z["karte"]))
    if (ctx.akt == "4.2.2f" or ctx.success == "nein") and not fixed and not engineer:
        mark(ctx.z, rules.EXPOSED)
    if fixed:
        ctx.prot.append("between Trench/Bunker/Pillbox markers of the same card without Exposed [RULE 5.1.1 p.31]")
    ctx.prot.append(
        f"{ctx.target_name} to {'open' if b == 'offen' else b} on {ctx.z['karte']}"
        + (", Exposed" if rules.EXPOSED in ctx.z["status"] else ", not Exposed")
    )
    if state.is_mortar(ctx.z) and fire.is_firing(ctx.z) is False and ctx.z.get("ziel"):
        ctx.prot.append(
            f"{ctx.target_name} (mortar) is Exposed and does not fire, VOF is removed until Exposed is removed [RULE 7.3.1 p.53]"
        )
    if state.is_v4(s):
        if engineer:
            contact.request_mine_check(
                s,
                [ctx.target_name],
                ctx.z["karte"],
                ctx.prot,
                "Engineers clear a path"
                + (
                    " (infiltration succeeded)"
                    if ctx.success == "ja"
                    else " (infiltration failed: not Exposed, no path)"
                ),
                cards=1 if ctx.success == "ja" else 3,
                path_=ctx.success == "ja",
            )
        else:
            contact.request_mine_check(s, [ctx.target_name], ctx.z["karte"], ctx.prot, "move within the mined card")


def _check_rally(s, ctx):
    if not state.pinned(ctx.z):
        raise rules.Violation(f"{ctx.target_name} is not Pinned [RULE 4.2.3a p.24]")


def _order_rally(s, ctx):
    """Order handler for: akt == '4.2.3a'"""
    _check_rally(s, ctx)
    if fire.vof_against(s, ctx.z["karte"], ctx.z["seite"]) is None or ctx.success == "ja":
        ctx.z["status"].remove(rules.PINNED)
        ctx.prot.append(
            f"{ctx.target_name}: remove Pinned marker"
            + ("" if ctx.success == "ja" else " (automatic, no VOF)")
            + (", VOF back to Basic" if fire.is_firing(ctx.z) else "")
            + " [6.5.1]"
        )
        s["letzter_versuch"] = None
    else:
        ctx.prot.append(f"{ctx.target_name}: Rally failed")
        s["letzter_versuch"] = [ctx.target_name, ctx.akt, s["phase"]]


def _check_convert_team(s, ctx):
    from_ = {"4.2.3b": "Paralyzed Team", "4.2.3c": "Litter Team", "4.2.3d": "Fire Team"}[ctx.akt]
    if ctx.z["typ"] != from_ or state.pinned(ctx.z):
        raise rules.Violation(f"{ctx.target_name} must be an Unpinned {from_} [RULE {ctx.rule}]")


def _order_convert_team(s, ctx):
    """Order handler for: akt in ('4.2.3b', '4.2.3c', '4.2.3d')"""
    to_ = {"4.2.3b": "Litter Team", "4.2.3c": "Fire Team", "4.2.3d": "Assault Team"}[ctx.akt]
    _check_convert_team(s, ctx)
    if fire.vof_against(s, ctx.z["karte"], ctx.z["seite"]) is None or ctx.success == "ja":
        ctx.z["typ"] = to_
        ctx.z["erfahrung"] = rules.LAT_EXPERIENCE[to_]
        combat.set_lat_values(ctx.z, to_)
        ctx.prot.append(
            f"{ctx.target_name} becomes {to_} (swap counter)"
            + ("" if ctx.success == "ja" else ", automatic without VOF")
            + " [6.5.1]"
        )
    else:
        ctx.prot.append(f"{ctx.target_name}: conversion failed")
        s["letzter_versuch"] = [ctx.target_name, ctx.akt, s["phase"]]


def _order_assault_to_fire_team(s, ctx):
    """Order handler for: akt == '4.2.3e'"""
    if ctx.z["typ"] != "Assault Team" or state.pinned(ctx.z):
        raise rules.Violation("Only an Unpinned Assault Team [RULE 4.2.3e p.24]")
    ctx.z["typ"], ctx.z["erfahrung"] = "Fire Team", "Green"
    combat.set_lat_values(ctx.z, "Fire Team")
    ctx.prot.append(f"{ctx.target_name} becomes Fire Team")


def _check_flip_to_front(s, ctx):
    if not state.fire_team_side(ctx.z) or state.pinned(ctx.z):
        raise rules.Violation(f"{ctx.target_name} must be Unpinned on its Fire Team side [RULE 4.2.3f p.24]")
    m = combat.ammo(ctx.z)
    if ctx.z.get("ooa_flip") and m and not m.get("punkte") and ctx.o.get("--ooa-flip") != "ja":
        # L524 [open U45] on the Fire Team side only because Out of Ammo (7.18.2): the front side would have no ammo;
        # resupply (7.18.3) undoes the flip. Allowed only on purpose with --ooa-flip=yes.
        raise rules.Violation(
            f"{ctx.target_name} is on its Fire Team side only because it is Out of Ammo (7.18.2); resupply it (7.18.3) "
            f"instead, the front side would have 0 ammo. Deliberately anyway: --ooa-flip=yes [open U45]"
        )


def _order_flip_to_front(s, ctx):
    """Order handler for: akt == '4.2.3f'"""
    _check_flip_to_front(s, ctx)
    if fire.vof_against(s, ctx.z["karte"], ctx.z["seite"]) is None or ctx.success == "ja":
        ctx.z["status"].remove(rules.FIRE_TEAM_SIDE)
        ctx.z.pop("ooa_flip", None)  # L539 (review C3): a later flip is HIT-caused; resupply must not undo it
        ctx.z.pop("ooa_fallback", None)
        ctx.prot.append(
            f"Flip {ctx.target_name} to its front side (experience back to {ctx.z.get('erfahrung', 'Line')}) [6.5.1]"
        )
    else:
        ctx.prot.append(f"{ctx.target_name}: Flip failed")
        s["letzter_versuch"] = [ctx.target_name, ctx.akt, s["phase"]]


def upper_story_type(zk):
    """L195 [RULE 5.2.2B p.36]: 'Church Tower' on a Church card (also 'Church on 1 Hill', OP icon), 'Upper Story' on a
    Multi-Story card, otherwise None."""
    base = (zk.get("terrain") or "").split(" on ")[0].split(" auf ")[0]
    if base == "Church" or zk.get("op"):
        return "Church Tower"
    if zk.get("mehrstoeckig"):
        return "Upper Story"
    return None


def _order_detach_team(s, ctx):
    """Order handler for: akt == '4.2.3g'"""
    if not state.good_order(ctx.z) or not (
        (ctx.z["typ"] == "Squad" and state.steps(ctx.z) >= 3)
        or (ctx.z["typ"] == "Weapons Team" and state.steps(ctx.z) == 2)
    ):
        raise rules.Violation("Detach Team: Good Order squad with 3-4 steps or 2-step Weapons Team [RULE 4.2.3g p.24]")
    team = team_option(ctx.o, "Assault") + " Team"  # L240 (review M13)
    ctx.z["steps"] = state.steps(ctx.z) - 1
    new = new_name(s, team)
    s["einheiten"][new] = combat.new_lat(ctx.z, team, ctx.target_name)
    # L514 (replaces L496/E103) [Stead BGG 3493975, 3727147, 2nd printing] the detached team is placed without an Exposed
    # marker; the squad stays Exposed
    s["einheiten"][new]["status"] = []
    exposed = rules.EXPOSED in ctx.z["status"]
    ctx.prot.append(
        f"{ctx.target_name} down to {ctx.z['steps']} steps, place {new} on {ctx.z['karte']}"
        + (" (not Exposed; the squad stays Exposed, Stead BGG 3727147)" if exposed else "")
    )


def _order_supplement_squad(s, ctx):
    """Order handler for: akt == '4.2.3h'"""
    sq = ctx.o.get("--squad")
    if not sq:
        raise rules.Violation("Specify --squad=<squad with 2-3 steps>")
    q = state.unit(s, sq)
    if (
        ctx.z["typ"] not in ("Fire Team", "Assault Team")
        or state.pinned(ctx.z)
        or q["typ"] != "Squad"
        or not state.good_order(q)
        or not (2 <= state.steps(q) <= 3)
        or q["karte"] != ctx.z["karte"]
    ):
        raise rules.Violation(
            "Supplement: Unpinned Fire/Assault Team plus Good Order squad with 2-3 steps on the same card [RULE 4.2.3h p.24]"
        )
    q["steps"] = state.steps(q) + 1
    # L237 (review M10): the team leaves play through remove_from_play (radio to the squad, Casualties/Assets onto the card)
    combat.remove_from_play(s, ctx.target_name, ctx.prot, f"joins {sq} [4.2.3h p.24]", successor=sq)
    ctx.prot.append(f"{sq} up to {q['steps']} steps (check experience on the Multi-Step Chart)")


def _check_reconstitute_squad(s, ctx):
    """State-only legality of 4.2.3i, also before the draw (L545); returns (teams, squad, experience)."""
    teams = [ctx.target_name] + options.list_option(ctx.o, "--mit")  # L529 (review C7): a bare --with is a Violation
    if len(set(teams)) != len(teams):
        raise rules.Violation(
            f"A team is named twice ({', '.join(teams)}); --with lists the further teams [RULE 4.2.3i p.24]"
        )
    level = rules.experience_value(ctx.o["--erfahrung"], "--experience") if ctx.o.get("--erfahrung") else "Green"
    sq = options.text_opt(ctx.o, "--squad")
    if not sq or sq not in s.get("removed_from_play", []):
        raise rules.Violation(
            "Specify --squad=<Removed from Play squad> and --with=<further teams, comma-separated> [RULE 4.2.3i p.24]"
        )
    for t in teams:
        te = state.unit(s, t)
        if te["typ"] not in ("Fire Team", "Assault Team") or state.pinned(te) or te["karte"] != ctx.z["karte"]:
            raise rules.Violation(f"{t}: only Unpinned Fire/Assault Teams on the same card [RULE 4.2.3i p.24]")
    if not 2 <= len(teams) <= 4:
        raise rules.Violation("2 to 4 teams [RULE 4.2.3i p.24]")
    return teams, sq, level


def _order_reconstitute_squad(s, ctx):
    """Order handler for: akt == '4.2.3i'"""
    teams, sq, level = _check_reconstitute_squad(s, ctx)
    if ctx.success == "ja":
        s["removed_from_play"].remove(sq)
        s["einheiten"][sq] = {
            "typ": "Squad",
            "seite": "US",
            "platoon": ctx.z.get("platoon"),
            "erfahrung": level,
            "karte": ctx.z["karte"],
            "bereich": ctx.z["bereich"],
            "status": [],
            "steps": len(teams),
            "ziel": None,
            "vof_rating": "S",
            "reichweite": "L",
            "letzter_step": "Fire Team",
        }
        for (
            t
        ) in teams:  # L237 (review M10): the teams leave play through remove_from_play, the squad is their successor
            combat.remove_from_play(s, t, ctx.prot, f"reconstituted into {sq} [4.2.3i p.24]", successor=sq)
        ctx.prot.append(
            f"{sq} back in play with {len(teams)} steps; experience per Multi-Step Unit Experience Chart from the teams (Assault Line, others Green), here {level} [6.5.2]"
        )
        fire.open_fire(s, ctx.prot, only=[sq])
    else:
        ctx.prot.append("Reconstitute failed")
        s["letzter_versuch"] = [ctx.target_name, ctx.akt, s["phase"]]


def _order_4_2_3j(s, ctx):
    """Order handler for: akt == '4.2.3j'"""
    if not ctx.z.get("fire_team_seite") or state.fire_team_side(ctx.z):
        raise rules.Violation("Only units with a named Fire Team side [RULE 4.2.3j p.24]")
    mark(ctx.z, rules.FIRE_TEAM_SIDE)
    ctx.prot.append(f"Flip {ctx.target_name} to its Fire Team side")


def _order_spot(s, ctx):
    """Order handler for: akt == '4.2.4a'"""
    target_k = ctx.o["--ziel"]
    if ctx.success == "ja":
        for m in state.units_on(s, target_k, "Feind"):
            s["einheiten"][m]["spotted"] = True
        ctx.prot.append(f"Enemies on {target_k} Spotted: remove Unspotted markers [8.5]")
        fire.open_fire(s, ctx.prot)
        s["letzter_versuch"] = None
    else:
        ctx.prot.append("Spotting failed")
        s["letzter_versuch"] = [ctx.target_name, ctx.akt, s["phase"]]


def _order_concentrate_fire(s, ctx):
    """Order handler for: akt == '4.2.4b'"""
    if not fire.is_firing(ctx.z):
        raise rules.Violation(f"{ctx.target_name} is not firing [RULE 4.2.4b p.25]")
    zt = fire.effective_fire_target(s, ctx.target_name)
    if not spotted_enemies(s, zt):
        raise rules.Violation(f"No Spotted enemy on {zt} [RULE 4.2.4b p.25]")
    if ctx.o.get("--jam") == "ja" and grenades.jam_prone(ctx.z):
        grenades.jam(s, ctx.target_name, ctx.prot)
        ctx.success = "nein"
    elif ctx.success == "ja":
        ze = ctx.o.get("--einheit")
        targets = spotted_enemies(s, zt)
        if not ze and len(targets) == 1:
            ze = targets[0]  # L457 (E91): the only spotted enemy on the card is the target, no --unit needed
        if not ze:
            raise rules.Violation(
                f"Specify --unit=<target enemy> (stack under a cover marker or random unit without cover on {zt})"
            )
        cf_target_check(s, zt, ze, ctx.z)  # L140 [RULE 7.11.1 p.56], L150 LOS to the unit
        for _m in enemy.cf_stack(s, ze):
            s["einheiten"][_m]["cf"] = s["einheiten"][_m].get("cf", 0) + 1
        ctx.prot.append(  # L245: the text names the 1 ammo that is booked below
            f"Concentrated Fire marker on {ze} (stack: {', '.join(enemy.cf_stack(s, ze))}; -1 NCM, cumulative; 1 ammo with ammo tracking) [7.11]"
        )
        cf_critical(s, ze, ctx.o, ctx.prot)  # L154 [RULE 7.11.4 p.56]
        if combat.fire_ammo(ctx.z):  # L173: no rockets for Concentrate Fire
            combat.ammo_use(s, ctx.target_name, ctx.z, 1, "successful Concentrate Fire", ctx.prot)  # [RULE 7.11.3 p.56]
    else:
        ctx.prot.append("Concentrate Fire failed")
        s["letzter_versuch"] = [ctx.target_name, ctx.akt, s["phase"]]


def cf_critical(s, ze, o, prot):
    """L154 [RULE 7.11.4 p.56] two or more Crosshairs: under cover the stack loses the cover benefit in the NCM (Critical Hit
    Concentrated Fire marker), out of cover a second Concentrated Fire marker."""
    if o.get("--kritisch") != "ja":
        return
    f = state.unit(s, ze)
    if f.get("bereich", "offen") != "offen":
        for m in enemy.cf_stack(s, ze):
            s["einheiten"][m]["cf_critical"] = True
        prot.append(
            f"Critical Hit: place the Critical Hit Concentrated Fire marker on {ze} (stack {f['bereich']}): no cover benefit in Combat Effects [7.11.4 p.56]"
        )
    else:
        f["cf"] = f.get("cf", 0) + 1
        prot.append(f"Critical Hit: a second Concentrated Fire marker on {ze} (both count) [7.11.4 p.56]")


def target_unit_check(s, zt, ze, what, rule, side="Feind"):
    """L238 (review M11): the named target unit is an opposing, Spotted unit on the target card (Concentrate Fire and
    Grenade Attack alike). Returns the unit."""
    f = state.unit(s, ze)
    if f["seite"] != side or f["karte"] != zt:
        raise rules.Violation(f"{ze} is not an opposing unit on the target card {zt} [RULE {rule}]")
    if not state.is_visible(f):
        raise rules.Violation(f"{ze} is Unspotted: {what} only on Spotted units [RULE {rule}]")
    return f


def cf_target_check(s, zt, ze, firer=None, side="Feind"):
    """L140 [RULE 7.11.1 p.56] Concentrate Fire target: a stack of Spotted units under a Cover marker on the target card or
    a random Spotted unit out of cover (R# among the units out of cover). L150 [RULE 5.2.2 p.35 Fig 3]: the firing unit
    needs LOS to that unit (Upper Story counts for the target), not only to the card."""
    f = target_unit_check(s, zt, ze, "Concentrate Fire", "7.11.1 p.56", side)
    if firer is not None and firer["karte"] != zt:
        ok, why = geometry.los(
            s, firer["karte"], zt, ha=geometry.height_bonus(s, firer), hb=geometry.height_bonus(s, f)
        )
        if not ok:
            raise rules.Violation(
                f"No LOS to {ze} itself ({why}); only units in LOS can be targeted (e.g. in the Upper Story) [RULE 5.2.2 p.35 Fig 3]"
            )
    if f.get("bereich", "offen") == "offen":
        # L551 (review E11): the units of the targeted side (side="US" for an enemy Concentrate Fire)
        open_ = [
            m
            for m in state.units_on(s, zt, side)
            if s["einheiten"][m].get("bereich", "offen") == "offen" and state.is_visible(s["einheiten"][m])
        ]
        if len(open_) > 1:
            s.setdefault("_hinweise", []).append(
                f"Concentrate Fire out of cover on {zt}: random target among {', '.join(open_)} (R# column {len(open_)}); {ze} booked [7.11.1]"
            )


def _order_platoon_fire(s, ctx):
    """Order handler for: akt in ('4.2.4c', '4.2.4h') [RULE 4.2.4c/h p.25]: every eligible unit of the platoon on the HQ's
    card makes its own attempt (4.2.4b Concentrate Fire with S/A/A-S/H VOF on a card with Spotted enemies, or 4.2.4d
    Grenade Attack) on the chosen target; one draw per unit. --unit=<target> (all) or --unit=<attacker>:<target>,..
    (7.11.1 note: new random target per attempt out of cover); --success=<attacker>:yes|no,..; grenade: --critical=<attackers>,
    --jam=<attackers>, --target=<card> for G! units. L136"""
    single = "4.2.4b" if ctx.akt == "4.2.4c" else "4.2.4d"
    ctx.also_book = single  # L244 (review M18): every attacker is booked with the single action too
    result = parse_per_unit(ctx.success)  # L230 (review H8)
    targets, common = {}, None
    for t in (text_opt(ctx.o, "--einheit") or "").split(","):
        if ":" in t:
            a, b = t.split(":", 1)
            targets[a.strip()] = b.strip()
        elif t.strip():
            common = t.strip()
    candidate, skipped = [], []
    for n, e in s["einheiten"].items():
        if e["seite"] != "US" or e["karte"] != ctx.orig["karte"] or state.pinned(e):
            continue
        if not ctx.late_order and single in s["impuls_aktionen"].get(n, []):
            skipped.append(f"{n}: already made its {rules.ACTIONS[single][0]} in this impulse [4.2 p.21]")  # L244
            continue
        if n != ctx.orig_name:
            try:
                comms.chain_of_command(s, ctx.orig_name, n)
                comms.communication(s, ctx.orig_name, n, single)
            except rules.Violation:
                continue
        try:
            comms.action_allowed(e, n, single)
        except rules.Violation:
            continue
        if single == "4.2.4b":
            if not fire.is_firing(e) or fire.current_vof_rating(e, False) not in ("S", "A", "A/S", "H"):
                continue
            zt = fire.effective_fire_target(s, n)
            if not spotted_enemies(s, zt):
                continue
        else:
            try:
                grenades.check_grenade(s, e, n, ctx.o)
            except rules.Violation as ex:
                skipped.append(f"{n}: {ex}")
                continue
        candidate.append(n)
    if not candidate:
        raise rules.Violation(
            f"No eligible unit of the platoon on {ctx.orig['karte']} for {rules.ACTIONS[ctx.akt][0]}"
            + ("; " + "; ".join(skipped) if skipped else "")
            + f" [RULE {ctx.rule}]"
        )
    missing = [n for n in candidate if n not in result]
    if missing:
        word = "Crosshairs" if single == "4.2.4b" else "Grenade symbol (2 or more: Critical Hit, --critical=<units>)"
        lines = []
        for n in candidate:
            n_cards, who, base = comms.card_count(s, single, ctx.orig, s["einheiten"][n], 0, None)
            lines.append(
                f"{n} {n_cards} cards ({comms.experience(who)}{', tripod +1' if n_cards > base + {'Green': -1, 'Veteran': 1}.get(comms.experience(who), 0) else ''})"
            )
        ranged_any = single == "4.2.4d" and ctx.o.get("--ziel", ctx.orig["karte"]) != ctx.orig["karte"]
        watches = []
        for n in candidate:
            # L172 [RULE 7.12 p.56]: only jam-prone units (the old text check also matched "no malfunction")
            if grenades.jam_prone(s["einheiten"][n]) and (single == "4.2.4b" or ranged_any):
                watches.append(n)
        raise rules.Violation(
            f"{rules.ACTIONS[ctx.akt][0]}: each unit draws itself, success on {word}: "
            + "; ".join(lines)
            + (
                f". WATCH: Jam icon for {', '.join(watches)} = weapon malfunction, cancels its success, unit leaves play (--jam=<units>) [7.12]"
                if watches
                else ""
            )
            + ". WATCH: 2 or more success icons for one unit = Critical Hit (--critical=<units>) [7.10.3, 7.11.4]"
            + "; then --success="
            + ",".join(f"{n}:yes|no" for n in candidate)
            + " --unit=<target>"
            + ("; skipped: " + "; ".join(skipped) if skipped else "")
            + f" [RULE 4.2 p.21, {ctx.rule}]"
        )
    crit = [x.strip() for x in (text_opt(ctx.o, "--kritisch") or "").split(",") if x.strip()]
    jammed = [x.strip() for x in (text_opt(ctx.o, "--jam") or "").split(",") if x.strip()]
    for n in candidate:
        e = s["einheiten"][n]
        o2 = dict(ctx.o)
        o2.pop("--erfolg", None)
        tgt = targets.get(n, common)
        if tgt:
            o2["--einheit"] = tgt
        else:
            o2.pop("--einheit", None)
        o2["--kritisch"] = "ja" if n in crit else "nein"
        o2["--jam"] = "ja" if n in jammed else "nein"
        # shallow copy: prot (and the other lists) stay shared with ctx, so the handler's lines land in this order
        ctx2 = dataclasses.replace(ctx, akt=single, target_name=n, z=e, o=o2, success=result[n])
        ctx.prot.append(f"{n} ({'success' if ctx2.success == 'ja' else 'no success'}):")
        if single == "4.2.4b":
            _order_concentrate_fire(s, ctx2)
        else:
            grenades.order_grenade_attack(s, ctx2)
    for line in skipped:
        ctx.prot.append("skipped " + line)
    ctx.moved = candidate


def _order_4_2_1l(s, ctx):
    """Order handler for: akt == '4.2.1l'"""
    old = s.get("ccp")
    s["ccp"] = ctx.z["karte"]
    ctx.prot.append(
        f"Casualty Collection Point on {ctx.z['karte']}"
        + (f" (previously {old}, only one CCP at a time)" if old and old != ctx.z["karte"] else "")
        + "; Casualties lying there at the end of the turn are evacuated in Clean Up [RULE 5.1.7 p.33/34, FM1 p.42]"
    )


def _order_cease_fire(s, ctx):
    """Order handler for: akt == '4.2.4k'"""
    kk = ctx.z["karte"]
    # L217 [RULE 4.2.4k Action Menu: 'Remove the VOF/PDF generated by all occupants of the card ... passed on and carried
    # out by all units on the card whether they are in communication or not']: the Recipient itself need not be firing
    if not any(e["seite"] == "US" and e["karte"] == kk and fire.is_firing(e) for e in s["einheiten"].values()):
        raise rules.Violation(f"No friendly unit on {kk} is firing [RULE 4.2.4k p.26]")
    # [RULE 4.3.1 p.27 note] "the order will be passed on to all occupants of a card (including Pinned units)" (L114, K21)
    stopped = []
    for n, e in s["einheiten"].items():
        if e["seite"] == "US" and e["karte"] == kk and fire.is_firing(e):
            stopped.append(f"{n} (at {fire.effective_fire_target(s, n)})")
            fire.cease_fire(e)
    ctx.prot.append(
        f"Cease Fire: all firing units on {kk} cease fire: {', '.join(stopped)}; they reopen fire immediately when a Spotted enemy is in LOS and range [4.3.1 p.27, 6.3.3]"
    )
    fire.open_fire(s, ctx.prot)


def _order_shift_fire(s, ctx):
    """Order handler for: akt == '4.2.4l'"""
    zt = ctx.o.get("--ziel")
    kk = ctx.z["karte"]
    # L248: like Cease Fire (L217) the order is passed on to all occupants of the card; the Recipient itself need not fire
    if not zt or not any(
        e["seite"] == "US" and e["karte"] == kk and fire.is_firing(e) for e in s["einheiten"].values()
    ):
        raise rules.Violation(
            f"Shift Fire: --target=<card in LOS>, a friendly unit on {kk} must be firing [RULE 4.2.4l p.26]"
        )
    state.card(s, zt)
    if unspotted_enemies(s, zt) and not state.units_on(s, zt, "US"):
        raise rules.Violation("Cards with Unspotted enemies may not be fired at [6.3.3]")
    ok, reason = geometry.los(
        s, ctx.orig["karte"], zt, ha=geometry.height_bonus(s, ctx.orig), hb=geometry.card_height_bonus(s, zt, "Feind")
    )
    if not ok:
        raise rules.Violation(f"Originator has no LOS to {zt}: {reason}")
    # L458: the PDF situation before the shift, so the board instruction names the marker that turns
    firing_before = {
        n: e["ziel"] for n, e in s["einheiten"].items() if e["seite"] == "US" and e["karte"] == kk and fire.is_firing(e)
    }
    for n, e in s["einheiten"].items():
        if (
            e["seite"] == "US" and e["karte"] == kk and fire.is_firing(e)
        ):  # L114: passed on to all occupants [4.3.1 p.27]
            los_ok, los_reason = geometry.los(
                s, kk, zt, ha=geometry.height_bonus(s, e), hb=geometry.card_height_bonus(s, zt, "Feind")
            )
            if not geometry.in_range(s, e, zt) or not los_ok:
                # L132 [RULE 6.1.2 p.39] the firing unit itself needs LOS and range to the new card; otherwise it ceases fire
                fire.cease_fire(e)
                ctx.prot.append(
                    f"{n}: no {'range' if los_ok else 'LOS'} to {zt} ({'out of range' if los_ok else los_reason}), ceases fire instead [6.1.2]"
                )
                continue
            e["ziel"] = zt
            e.pop("konzentriert", None)
    already = sorted(n for n, z in firing_before.items() if z == zt)
    if already:
        how = f"PDF marker {kk} to {zt} already lies there from {', '.join(already)}"
    else:  # the old marker is handled by the board summary (removed, or back to a single arrow if it was mutual)
        how = f"place a new PDF marker {kk} to {zt}"
    others = sorted(
        {
            x["ziel"]
            for x in s["einheiten"].values()
            if x.get("karte") == kk and x.get("ziel") and x["ziel"] not in (kk, zt) and fire.is_firing(x)
        }
    )
    ctx.prot.append(
        f"Shift Fire: units on {kk} now fire at {zt}: {how}"
        + (f"; further PDF from {kk}: to {', '.join(others)}" if others else f"; no other PDF from {kk}")
        + " [6.3.3]"
    )


def _order_4_2_1b(s, ctx):
    """Order handler for: akt == '4.2.1b'"""
    lv = s.get("letzter_versuch")
    if not lv or lv[0] != ctx.target_name or lv[2] != s["phase"]:
        raise rules.Violation("Exhort only for a unit that has just failed an attempt [RULE 4.2.1b p.22]")
    if ctx.success not in ("ja", "nein"):
        raise rules.Violation("Exhort: draw one more Action card; --success=yes|no (symbol of the original attempt)")
    s["letzter_versuch"] = None
    if ctx.success == "ja":
        s["exhort_frei"] = [ctx.target_name, lv[1], s["phase"]]  # [RULE 4.2.1b p.22] 'Draw one more Action card'
    ctx.prot.append(
        f"Exhort for {ctx.target_name} ({lv[1]}): "
        + (
            "attempt counts as successful; now enter the effect with the original order and --success=yes (costs no Command, add --free=yes)"
            if ctx.success == "ja"
            else "again no success"
        )
    )


def _order_4_2_1c(s, ctx):
    """Order handler for: akt == '4.2.1c'"""
    if state.is_v4(s):
        pyro.execute_pyro(s, ctx.z, ctx.target_name, ctx.o, ctx.prot)
    else:
        ctx.prot.append(f"{ctx.target_name} uses pyrotechnics (effect per Mission Log) [4.4]")


def _order_4_2_1d(s, ctx):
    """Order handler for: akt == '4.2.1d'"""
    hq_n = ctx.o.get("--hq")
    if not hq_n or hq_n not in s.get("removed_from_play", []):
        raise rules.Violation("Specify --hq=<Removed from Play PLT HQ> [RULE 4.2.1d p.22]")
    if s.get("rfp_daten", {}).get(hq_n, {}).get("ebene", "PLT") != "PLT":  # L537 (review C9)
        raise rules.Violation(
            f"{hq_n} is not a PLT HQ; the CO HQ is reconstituted by the BN HQ: fof.py order BN <unit> 4.2.1e [RULE 6.5.2 p.50]"
        )
    target_platoon = s.get("rfp_daten", {}).get(hq_n, {}).get("platoon")
    if hq_n not in s.get("rfp_daten", {}):
        target_platoon = ctx.z.get("platoon")
        ctx.prot.append(
            f"Platoon of {hq_n} not stored (game state before v3), check the platoon of {ctx.target_name} on the board"
        )
    if not state.good_order(ctx.z) or not (
        ctx.z["typ"] == "Staff" or (target_platoon and ctx.z.get("platoon") == target_platoon)
    ):
        raise rules.Violation(f"Recipient: CO Staff or a Good Order step of platoon {target_platoon} [RULE 6.5.2 p.49]")
    hq_back(s, hq_n, ctx.z, ctx.prot)
    hand_over_step(s, ctx.target_name, ctx.prot, team_option(ctx.o, "Fire"))  # L240 (review M13)


def _order_4_2_1e(s, ctx):
    """Order handler for: akt == '4.2.1e'"""
    raise rules.Violation(
        "Reconstitute the CO HQ is given by the BN HQ in the BN HQ Impulse: fof.py order BN <unit> 4.2.1e [RULE 6.5.2 p.50]"
    )


def _order_4_2_1i(s, ctx):
    """L187 [RULE 4.2.1i p.22, 10.4 p.72] Activate for AT Combat & Vehicle Movement."""
    from . import vehicles

    vehicles.order_4_2_1i(s, ctx)


ORDER_HANDLERS = {
    "4.2.2a": _order_move,
    "4.2.2c": _order_move,
    "4.2.2b": _order_move_platoon,
    "4.2.2d": _order_move_platoon,
    "4.2.2e": _order_seek_cover,
    "4.2.2f": _order_move_within_card,
    "4.2.2g": _order_move_within_card,
    "4.2.2h": lambda s, ctx: pickup.order_pick_up(s, ctx),
    "4.2.3a": _order_rally,
    "4.2.3b": _order_convert_team,
    "4.2.3c": _order_convert_team,
    "4.2.3d": _order_convert_team,
    "4.2.3e": _order_assault_to_fire_team,
    "4.2.3f": _order_flip_to_front,
    "4.2.3g": _order_detach_team,
    "4.2.3h": _order_supplement_squad,
    "4.2.3i": _order_reconstitute_squad,
    "4.2.3j": _order_4_2_3j,
    "4.2.4a": _order_spot,
    "4.2.4b": _order_concentrate_fire,
    "4.2.4c": _order_platoon_fire,
    "4.2.4d": lambda s, ctx: grenades.order_grenade_attack(s, ctx),
    "4.2.4h": _order_platoon_fire,
    "4.2.4i": lambda s, ctx: fire_support.order_call_for_fire(s, ctx),
    "4.2.4j": lambda s, ctx: fire_support.order_indirect_lay(s, ctx),
    "4.2.1l": _order_4_2_1l,
    "4.2.1i": _order_4_2_1i,  # L187
    "4.2.4k": _order_cease_fire,
    "4.2.4l": _order_shift_fire,
    "4.2.1b": _order_4_2_1b,
    "4.2.1c": _order_4_2_1c,
    "4.2.1d": _order_4_2_1d,
    "4.2.1e": _order_4_2_1e,
}


ATTEMPT_WORD = {"ja": "successful", "nein": "failed"}  # L182: internal ja/nein, English output
ORIGINATOR_WORD = {"PLT": "a PLT HQ", "CO_BN": "the CO HQ or BN HQ", "CO_ONLY": "the CO HQ"}


def originator_eligible(orig, originator_kind):
    """[RULE 4.2 Action Menu] originator column: PLT (a PLT HQ), CO_BN (CO HQ or BN HQ), CO_ONLY (the CO HQ)."""
    if originator_kind == "PLT":
        return orig["typ"] == "HQ" and orig.get("ebene") == "PLT"
    if originator_kind == "CO_BN":
        return orig.get("ebene") in ("CO", "BN")
    if originator_kind == "CO_ONLY":
        return orig.get("ebene") == "CO" and orig["typ"] == "HQ"
    return True


def check_stacking(s, z, akt, o, orig_name, orig):
    """L193 [RULE 5.1.5 p.32]: 16 steps of infantry per card; vehicles count separately (at most 4), their crews are no
    steps here. Returns the members of a Platoon Move (None for other actions) so the handler uses the same set (L249)."""
    candidates = None
    if akt in ("4.2.2b", "4.2.2d"):
        candidates = platoon_move_members(s, orig_name, orig, akt)
    target = o.get("--ziel")
    if akt not in ("4.2.2a", "4.2.2b", "4.2.2c", "4.2.2d") or not target or target not in s["karten"]:
        return candidates
    if s["karten"][target].get("staging"):
        return candidates
    members = [z] if candidates is None else [s["einheiten"][n] for n in candidates]
    st = sum(
        state.steps(e)
        for e in s["einheiten"].values()
        if e["seite"] == "US" and e["karte"] == target and e["typ"] != "Casualty" and not e.get("fahrzeug")
    ) + sum(state.steps(e) for e in members if not e.get("fahrzeug"))
    if st > 16:
        raise rules.Violation(f"Stacking: {target} would have {st} US steps, at most 16 per card [RULE 5.1.5 p.32]")
    return candidates


def attempt_text(success):
    """L197: English attempt text, also for per-unit lists 'A:ja,B:nein' (Platoon Infiltrate)."""
    if ":" not in success:
        return ATTEMPT_WORD.get(success, success)
    return ", ".join(f"{a} {ATTEMPT_WORD[b]}" for a, b in parse_per_unit(success).items())  # L230: also yes/no


def cmd_order(s, args, late_order=None):
    """4.2: one order. nachtrag=<HQ>: late order for an HQ whose impulse already ended this turn (L78).
    Contract (L255): everything that can refuse the order runs before the draw prompt (resolve_originator,
    check_stacking, check_repeat_and_budget, apply_skill, pre_draw_checks); the prompt is the last Violation before
    the handler, so the player never draws cards for an order that is refused afterwards (review M7, M8)."""
    rules.need(args, 3, "order <hq|GI|BN> <unit> <action id> [--target=K] [--success=yes|no] ...")
    hq_name, target_name, akt = args[0], args[1], args[2]
    o = options.parse_opts(args[3:])
    if hq_name == "BN":
        return order_bn(s, target_name, akt)
    s["_befehl_opts"] = o
    if state.is_v4(s):
        contact.mine_lock(s)
        if akt in ("4.2.1g", "4.2.1h") and target_name in s.get("runner_box", []):
            return order_runner_box(s, hq_name, target_name, akt, o)
    ctx = order_context(s, hq_name, target_name, akt, o, late_order)
    resolve_originator(s, ctx)
    ctx.candidates = check_stacking(s, ctx.z, akt, o, ctx.orig_name, ctx.orig)
    check_recipient(s, ctx)
    check_repeat_and_budget(s, ctx)
    apply_skill(s, ctx)
    pre_draw_checks(s, ctx)
    handler = ORDER_HANDLERS.get(akt)
    if handler:
        handler(s, ctx)
    elif not order_v4(s, target_name, akt, o, ctx.orig, ctx.prot):
        raise rules.order_not_implemented(akt)  # L449
    book_order(s, ctx)


@dataclasses.dataclass
class OrderCtx:
    """The working record of one order (review Struktur 10: a dataclass instead of a SimpleNamespace). Built by
    order_context; resolve_originator, check_stacking, apply_skill, the handlers and book_order fill the rest.
    Platoon Fire copies it per firing unit with dataclasses.replace (shallow: prot, moved and mods stay shared)."""

    # the order as given
    akt: str  # action id, e.g. "4.2.4b"
    hq_name: str  # active HQ, "GI" or "BN"
    target_name: str  # recipient
    z: dict  # recipient unit
    zk: dict  # recipient's card
    o: dict  # parsed options
    # the action's row of rules.ACTIONS
    name: str
    cost: int
    draw_kind: str  # e.g. "auto"
    originator_kind: str  # e.g. "HQ", "CO_BN"
    rule: str
    late_order: str | None = None  # the HQ of a late order (cmd_late_order), else None
    gi: bool = False  # under General Initiative
    success: str | None = None  # --success: "ja"/"nein" or per unit "1/1:ja,.."
    skill: str | None = None  # --skill
    # filled during the order
    orig_name: str | None = None  # originator (resolve_originator)
    orig: dict | None = None
    candidates: list | None = None  # stacking candidates (check_stacking)
    skill_text: str | None = None  # apply_skill
    k: dict | None = None  # Command record of the ordering HQ (command_record)
    mods: list = dataclasses.field(default_factory=list)  # draw modifiers
    extra: int = 0
    base_cff: Any = None
    agency: str | None = None  # fire-support agency of Call for Fire
    also_book: str | None = None  # second action booked with this one
    after_exhort: bool = False
    moved: list = dataclasses.field(default_factory=list)  # units moved by the order
    prot: list = dataclasses.field(default_factory=list)  # protocol lines


def order_context(s, hq_name, target_name, akt, o, late_order):
    """The working record of one order (ctx): the action's table row, the recipient and the fields the handlers fill."""
    if s["phase"] not in rules.IMPULSES:
        raise rules.Violation(f"Orders only in the Friendly Command Phase 3.3, currently {s['phase']} [RULE 3.3 p.15]")
    if s.get("aktiver_hq") != hq_name and not late_order:
        raise rules.Violation(f"Active HQ is {s.get('aktiver_hq')}, not {hq_name}")
    if akt not in rules.ACTIONS:
        raise rules.Violation(f"Action {akt} not in the table. Known: {', '.join(rules.ACTIONS)}")
    name, cost, draw_kind, originator_kind, rule = rules.ACTIONS[akt]
    z = state.unit(s, target_name)
    if z["seite"] != "US":
        raise rules.Violation("Orders only to friendly units")
    return OrderCtx(
        akt=akt,
        hq_name=hq_name,
        target_name=target_name,
        z=z,
        zk=state.card(s, z["karte"]),
        o=o,
        name=name,
        cost=cost,
        draw_kind=draw_kind,
        originator_kind=originator_kind,
        rule=rule,
        late_order=late_order,
        gi=hq_name == "GI",
        success=options.text_opt(o, "--erfolg", "--success=yes|no"),  # L529 (review C8): bare --success is a Violation
        skill=o.get("--skill"),
    )


def resolve_originator(s, ctx):
    """Originator of the order: the active HQ, or under General Initiative the recipient itself or --originator
    [RULE 4.1.1 p.19, 4.2 Action Menu originator column, 4.1.4 p.20]."""
    kind, name, rule, z = ctx.originator_kind, ctx.name, ctx.rule, ctx.z
    if ctx.gi:
        ctx.orig_name = ctx.o.get("--originator", ctx.target_name)
        if ctx.akt in rules.HQ_REQUIRED_UNDER_GI and ctx.orig_name == ctx.target_name and not state.is_hq(z):
            raise rules.Violation(
                f"{name} needs an HQ/Staff even under General Initiative: --originator=<HQ> [RULE 4.1.1 p.19, Clarification 3]"
            )
        ctx.orig = state.unit(s, ctx.orig_name)
        if kind in ("PLT", "CO_BN", "CO_ONLY") and not originator_eligible(ctx.orig, kind):
            # L242 (review M16): a PLT HQ may name itself as originator of its own platoon action under GI
            raise rules.Violation(
                f"{name} needs the responsible HQ as originator (--originator=<{ORIGINATOR_WORD[kind]}>) [RULE {rule}]"
            )
    else:
        ctx.orig_name, ctx.orig = ctx.hq_name, state.unit(s, ctx.hq_name)
        if kind in ("PLT", "CO_BN", "CO_ONLY") and not originator_eligible(ctx.orig, kind):
            raise rules.Violation(f"{name} may only be ordered by {ORIGINATOR_WORD[kind]} [RULE {rule}]")
        if state.fire_team_side(ctx.orig) and ctx.target_name != ctx.hq_name:
            raise rules.Violation(f"{ctx.hq_name} on its Fire Team side may only order itself [RULE 4.1.4 p.20]")


def check_recipient(s, ctx):
    """Recipient of a CO-level action is the HQ itself; otherwise chain of command and communication [RULE 4.0, 4.3]."""
    orig, orig_name, target_name, akt = ctx.orig, ctx.orig_name, ctx.target_name, ctx.akt
    if ctx.originator_kind == "CO":
        # [RULE 4.2.1l p.22] Originator 'CO HQ or CO Staff (or PLT HQ in a single-platoon mission)', Recipient 'The HQ itself'
        if not (
            orig.get("ebene") == "CO" or orig["typ"] == "Staff" or (s.get("einzelzug") and orig.get("ebene") == "PLT")
        ):
            raise rules.Violation(
                f"{ctx.name}: only CO HQ or CO Staff (PLT HQ only in single-platoon missions) [RULE {ctx.rule}]"
            )
        if target_name != orig_name:
            raise rules.Violation(f"{ctx.name}: recipient is the HQ itself [RULE {ctx.rule}]")
    if orig_name != target_name:
        if akt not in ("4.2.4k", "4.2.4l", "4.2.4j"):
            comms.chain_of_command(s, orig_name, target_name)
        if akt != "4.2.4j":
            comms.communication(s, orig_name, target_name, akt)


def check_repeat_and_budget(s, ctx):
    """Exhort follow-up (--free), one action per unit and impulse [RULE 4.2 p.21], 4.2.5 restrictions, Commands and
    the per-impulse cap [RULE 4.1.3 p.20]."""
    o, akt, target_name = ctx.o, ctx.akt, ctx.target_name
    ex = s.get("exhort_frei")
    ctx.after_exhort = bool(
        ex and ex[0] == target_name and ex[1] == akt and ex[2] == s["phase"] and o.get("--gratis") == "ja"
    )
    if o.get("--gratis") == "ja" and not ctx.after_exhort:
        raise rules.Violation(
            "--free=yes only for the effect of a successful Exhort (4.2.1b) with the same unit and action [RULE 4.2.1b p.22]"
        )
    already = [] if ctx.late_order else s["impuls_aktionen"].setdefault(target_name, [])
    if akt in already and akt != "4.2.2f" and not ctx.after_exhort:
        raise rules.Violation(
            f"{target_name} has already carried out '{ctx.name}' in this impulse; only Move within a Card may be repeated [RULE 4.2 p.21]"
        )
    comms.action_allowed(ctx.z, target_name, akt)
    ctx.k = command_record(s, ctx.hq_name)
    check_impulse_budget(
        s, ctx.hq_name, ctx.cost, ctx.rule, free=ctx.after_exhort or o.get("--gratis") == "ja"
    )  # L234 (review M7)


def apply_skill(s, ctx):
    """[RULE 12.7 p.82, Player Aid 2] --skill=<Auto ...|Extra Draw>: the holder hands in the marker; Auto skills make
    the attempt succeed (cards still drawn for Critical Hit/Jam, L153); --short only for a Call for Fire (L250)."""
    skill, akt, o, z = ctx.skill, ctx.akt, ctx.o, ctx.z
    if (
        skill == "Auto Concentrate Fire"
    ):  # L476: long name on the counter mix list (E67) = the marker 'Auto Concentrate'
        skill = ctx.skill = "Auto Concentrate"
    if skill:
        if skill not in SKILL_AUTO and skill != "Extra Draw":
            raise rules.Violation(f"Skill in an order: {', '.join(list(SKILL_AUTO) + ['Extra Draw'])} [RULE 12.7 p.82]")
        if skill in SKILL_AUTO and akt not in SKILL_AUTO[skill]:
            raise rules.Violation(f"{skill} only applies to {', '.join(SKILL_AUTO[skill])} [Player Aid 2, Skills]")
        holder = skill_holder(s, ctx.target_name, skill)
        if skill in SKILL_AUTO and akt in ("4.2.4b", "4.2.4d") and "--kritisch" not in o:
            # L153 [RULE 12.7 p.82] 'the cards still need to be drawn to determine if a critical hit or jam takes place'
            n_cards, _who, _base = comms.card_count(s, akt, ctx.orig if akt.startswith("4.2.3") else z, z)
            ranged = akt == "4.2.4d" and o.get("--ziel", z["karte"]) != z["karte"]
            raise rules.Violation(
                f"Skill {skill}: success is certain, but draw {n_cards} Action cards for Critical Hit/Jam; then repeat with --critical=yes|no"
                + (" --jam=yes|no" if grenades.jam_prone(z) and (akt == "4.2.4b" or ranged) else "")
                + " "
                + grenades.draw_watch(s, "cf" if akt == "4.2.4b" else "grenade", z, ranged)
            )
        if skill in SKILL_AUTO:
            ctx.success = "ja"
            ctx.skill_text = (
                f"Skill {skill} of {holder}: attempt automatically successful; Commands are spent anyway"
                + (", draw cards only for Critical Hit/Jam" if akt in ("4.2.4b", "4.2.4d") else ", no cards needed")
                + " [RULE 12.7 p.82]"
            )
        s["einheiten"][holder]["skills"].remove(skill)
        ctx.skill_text = (
            ctx.skill_text or f"Skill Extra Draw from {holder}: one more card [Player Aid 2]"
        ) + "; hand in the Skill marker"
    if ctx.after_exhort and ctx.success != "ja":
        raise rules.Violation("After a successful Exhort enter the effect with --success=yes --free=yes")
    if o.get("--short") == "ja" and akt == "4.2.4i":  # L250: only a Call for Fire knows 'Short'
        ctx.success = "ja"  # [RULE 7.16.4 p.59] 'Short' takes precedence; the Pending marker is placed anyway
    if ctx.skill_text:
        ctx.prot.append(ctx.skill_text)


PRE_DRAW_CHECKS = {
    "4.2.2e": _check_seek_cover,
    "4.2.2g": _check_move_within_card,
    "4.2.3a": _check_rally,
    "4.2.3b": _check_convert_team,
    "4.2.3c": _check_convert_team,
    "4.2.3d": _check_convert_team,
    "4.2.3f": _check_flip_to_front,
    "4.2.3i": _check_reconstitute_squad,
}


def pre_draw_checks(s, ctx):
    """Legality of an attempt before the card draw (Spot LOS, Grenade Attack, Concentrate Fire target, Infiltrate 5.1.4)
    and the draw modifiers; without --success the draw prompt is raised (draw_prompt)."""
    akt, o, z, success = ctx.akt, ctx.o, ctx.z, ctx.success
    extra_cff = 0
    if akt == "4.2.4i":
        ctx.base_cff, extra_cff, ctx.agency = fire_support.cff_precheck(s, z, ctx.target_name, o)
    if not (
        ctx.draw_kind in ("attempt", "cover", "cff")
        or (ctx.draw_kind == "attempt_vof" and fire.vof_against(s, z["karte"], z["seite"]) is not None)
    ):
        return
    if akt == "4.2.4i":
        ctx.extra = extra_cff
        if extra_cff:
            ctx.mods = [(f"Target marker {ctx.agency} on {o['--ziel']}", extra_cff)]
    if akt == "4.2.4a":
        target_k = o.get("--ziel")
        if not target_k:
            raise rules.Violation("Spot: specify --target=<card with Unspotted enemies> [4.2.4a]")
        state.card(s, target_k)
        if not unspotted_enemies(s, target_k):
            raise rules.Violation(f"There is no Unspotted enemy on {target_k} [8.5]")
        if ctx.zk.get("staging"):
            raise rules.Violation("No spotting from the Staging Area [8.5 Note]")
        ok, reason = geometry.los(
            s, z["karte"], target_k, ha=geometry.height_bonus(s, z), hb=geometry.card_height_bonus(s, target_k, "Feind")
        )
        if not ok:
            raise rules.Violation(f"No LOS from {z['karte']} to {target_k}: {reason}")
        ctx.mods = comms.spot_modifiers(s, z, target_k)
        ctx.extra = sum(m for _, m in ctx.mods)
    if akt == "4.2.4d":
        grenades.check_grenade(s, z, ctx.target_name, o)
    if akt == "4.2.4b" and success not in ("ja", "nein"):  # L184: legality before the draw
        if not fire.is_firing(z):
            raise rules.Violation(f"{ctx.target_name} is not firing (no target, no VOF) [RULE 4.2.4b p.25]")
        zt_ = fire.effective_fire_target(s, ctx.target_name)
        if not spotted_enemies(s, zt_):
            raise rules.Violation(f"No Spotted enemy on {zt_} [RULE 4.2.4b p.25]")
    if akt in ("4.2.4c", "4.2.4h") and success and ":" not in success:
        raise rules.Violation(f"{ctx.name}: --success=<unit>:yes|no,.. per unit [RULE {ctx.rule}]")
    if ctx.skill == "Extra Draw":
        ctx.extra += 1
        ctx.mods = list(ctx.mods) + [("Skill Extra Draw", 1)]
    if akt == "4.2.2c" and o.get("--ziel") and success not in ("ja", "nein"):
        # L120: legality (5.1.4 VOF on origin or destination) before the draw
        check_move(s, z, ctx.target_name, o["--ziel"], akt)
    if akt in PRE_DRAW_CHECKS and success not in ("ja", "nein"):
        PRE_DRAW_CHECKS[akt](s, ctx)  # L545 (review C5): every refusal that needs no card comes before the draw
    if akt not in ("4.2.2d", "4.2.4c", "4.2.4h") and success not in ("ja", "nein"):
        raise rules.Violation(draw_prompt(s, ctx))


def draw_prompt(s, ctx):
    """Text only: how many Action cards to draw for the attempt, which symbol counts, and what to watch for (L153)."""
    akt, o, z = ctx.akt, ctx.o, ctx.z
    n_cards, who, base = comms.card_count(s, akt, ctx.orig, z, ctx.extra, ctx.base_cff)
    word = {
        "4.2.2c": "Infiltrate symbol",
        "4.2.2g": "Infiltrate symbol",
        "4.2.2e": "word Cover",
        "4.2.4a": "Crosshairs",
        "4.2.4b": "Crosshairs",
        "4.2.4d": "Grenade symbol (2 or more: Critical Hit, --critical=yes)",
        "4.2.4i": "Burst symbol (also 3 Bursts; 'Short!' takes precedence)",
    }.get(akt, "word Rally")
    msg = f"{ctx.name}: draw {n_cards} Action cards (base {base}" + (
        ""
        if akt == "4.2.4a"
        else f", experience {comms.experience(who)} of the {'originator' if akt.startswith('4.2.3') else 'recipient'}"
    )
    if ctx.mods:
        msg += ", " + ", ".join(f"{t} {m:+d}" for t, m in ctx.mods) + (", minimum 1" if akt == "4.2.4a" else "")
    agency = ctx.agency
    msg += (
        f"); success on {word}. Then --success=yes|no"
        + (" (on 'Short' --short=yes)" if akt == "4.2.4i" and s.get("fm_werte") else "")
        + (
            " WATCH: 3 Bursts icon = Battalion Fire Mission possible: --battalion=K1,K2 (two cards adjacent to the target) [RULE 7.16.2B p.58]"
            if akt == "4.2.4i"
            and agency
            and (s.get("fm_gruppe") or {}).get(agency, agency) in (s.get("bataillon_fm") or [])
            else ""
        )  # L207
        + f" [RULE 4.2 p.21, {ctx.rule}]"
    )
    kind = {"4.2.4b": "cf", "4.2.4d": "grenade", "4.2.4i": "cff", "4.2.4a": "spot"}.get(akt, "other")
    ranged = akt == "4.2.4d" and o.get("--ziel", z["karte"]) != z["karte"]
    watch = grenades.draw_watch(s, kind, z, ranged, skill=bool(ctx.skill_text))
    return msg + (" " + watch if watch else "")


def book_order(s, ctx):
    """After the handler: pay the Commands, note the action per unit for the repeat check, activity level, save, print."""
    o, k, cost, moved, success = ctx.o, ctx.k, ctx.cost, ctx.moved, ctx.success
    lv = s.get("letzter_versuch")
    if success == "ja" and lv and lv[0] == ctx.target_name:
        s["letzter_versuch"] = None  # L549 (review C13): Exhort is for the last attempt, which has now succeeded
    if ctx.after_exhort:
        s["exhort_frei"] = None
    elif o.get("--gratis") != "ja":
        pay_commands(s, ctx.hq_name, cost, ctx.rule)
    if ctx.hq_name != "GI" and ctx.hq_name not in s["einheiten"] and s.get("aktiver_hq") == ctx.hq_name:
        # L537 (review C2): the ordering HQ left play with this order (e.g. a Staff hands over its step in 4.2.1d):
        # its impulse ends here, its remaining and saved Commands are lost; otherwise 'done' and 'phase next' dead-end
        k["verfuegbar"], k["gespart"], k["fertig"] = 0, 0, True
        s["aktiver_hq"] = None
        s["impuls_aktionen"] = {}
        ctx.prot.append(f"{ctx.hq_name} has left play: its impulse ends, remaining Commands are lost [4.1.3]")
        moved = []  # nothing to note for the repeat check: the impulse is over
    elif not moved:
        moved = [ctx.target_name]
    for n in moved:
        if not ctx.after_exhort and not ctx.late_order:
            s["impuls_aktionen"].setdefault(n, []).append(ctx.akt)
            if ctx.also_book:  # L244 (review M18): Platoon Fire also counts as the single action of every attacker
                s["impuls_aktionen"][n].append(ctx.also_book)
    ak = fire.update_activity(s)
    if ak:
        ctx.prot.append(ak)
    s.pop("_befehl_opts", None)
    txt = ("Late order for the impulse of " + ctx.late_order + ": " if ctx.late_order else "") + (
        f"{ctx.hq_name} orders {ctx.target_name}: {ctx.name}"
        + (f" to {o['--ziel']}" if o.get("--ziel") else "")
        + (f", attempt {attempt_text(success)}" if success else "")  # L182/L197 English output
        + (f" (with {', '.join(moved)})" if len(moved) > 1 else "")
        + f"; cost {0 if o.get('--gratis') == 'ja' else cost}, remaining {k['verfuegbar']}+{k['gespart']}"
    )
    state.save_state(s, txt + "; " + "; ".join(ctx.prot), ctx.rule)
    print(f"{messages.ALLOWED} {messages.rule(ctx.rule)}")
    print(txt)
    briefing.print_board(ctx.prot, s)


def cmd_fire(s, args):
    rules.need(args, 2, "fire <unit> <card|off>")
    n, target = args[0], args[1]
    e = state.unit(s, n)
    prot = []
    if target == "aus":
        fire.cease_fire(e)
        prot.append(f"{n} no longer fires (correction)")
    else:
        state.card(s, target)
        if e.get("ziel_offen") and target not in e["ziel_offen"]:
            raise rules.Violation(f"{target} not among the candidates {', '.join(e['ziel_offen'])}")
        if e.get("ziel_offen"):
            # L218 [RULE 6.3.5 p.43 'Units will never place an extra PDF if they are able to fire along the card's
            # current PDF', 6.1.1 L122]: a second pending unit on the card joins a PDF chosen meanwhile
            joined = sorted(
                {
                    x["ziel"]
                    for m, x in s["einheiten"].items()
                    if m != n
                    and x["seite"] == e["seite"]
                    and x.get("karte") == e["karte"]
                    and fire.is_firing(x)
                    and x["ziel"] in e["ziel_offen"]
                }
            )
            if joined and target not in joined:
                raise rules.Violation(
                    f"{n} can fire along the existing PDF from {e['karte']} to {', '.join(joined)}: no extra PDF [RULE 6.3.5 p.43]"
                )
        e["ziel"] = target
        e.pop("ziel_offen", None)
        prot.append(
            f"{n} fires at {target}"
            + (
                ""
                if target == e["karte"]
                else f", PDF from {e['karte']} to {target}" + fire.pdf_note(s, e["karte"], target, n)
            )
            + fire.grazing_note(s, n)
        )
        if target != e["karte"]:
            # L218 [RULE 6.3.5 p.43]: other pending units of this card that can fire along the new PDF join it
            for m, x in s["einheiten"].items():
                if (
                    m != n
                    and x["seite"] == e["seite"]
                    and x.get("karte") == e["karte"]
                    and target in (x.get("ziel_offen") or [])
                ):
                    x["ziel"] = target
                    x.pop("ziel_offen", None)
                    prot.append(
                        f"{m} joins the fire along the PDF from {e['karte']} to {target} (no extra PDF) [6.3.5 p.43]"
                    )
    ak = fire.update_activity(s)
    if ak:
        prot.append(ak)
    state.save_state(s, "; ".join(prot), "6.1.1 p.39")
    briefing.print_board(prot, s)


def friendly_fire_on(s, n, kid):
    """L466 [RULE 6.1, 6.3.3 p.43]: own-side units on other cards whose VOF lies on kid (friendly fire on the mover)."""
    side = s["einheiten"][n]["seite"]
    return [
        m
        for m, x in s["einheiten"].items()
        if m != n
        and x["seite"] == side
        and x["karte"] != kid
        and fire.is_firing(x)
        and fire.effective_fire_target(s, m) == kid
    ]


def hq_rank(e):
    return {"BN": 0, "CO": 1}.get(e.get("ebene"), e.get("rang", 9) if e["typ"] == "Staff" else 5)


def order_v4(s, target_name, akt, o, orig, prot):
    """Runner, net change, phone line repair. Returns True if the action was handled here."""
    if akt == "4.2.1f":
        z = state.unit(s, target_name)
        if comms.runner_count(s) >= 2:
            raise rules.Violation("At most two Runners in play [4.3.2 p.27, 4.2.1f p.22]")
        if not (
            state.good_order(z) or (z["typ"] in ("Assault Team", "Fire Team") and not state.pinned(z))
        ) or state.is_hq(z):
            raise rules.Violation("Recipient: Good Order unit or unpinned Assault/Fire Team [4.2.1f p.22]")
        rn = new_name(s, "Runner")
        while rn in comms.runner_box(s):
            rn = rn[:-1] + str(int(rn[-1]) + 1)
        hand_over_step(s, target_name, prot, "Fire")
        comms.runner_box(s).append(rn)
        prot.append(f"{rn} (Line) into the CO HQ Assets Box; moves with the CO HQ [4.2.1f p.22, 4.3.2 p.27]")
        return True
    if akt in ("4.2.1g", "4.2.1h"):
        raise rules.Violation(
            f"{target_name} is not in the CO HQ Assets Box (en route or not a Runner); Runner orders only to Runners in the box [4.3.2 p.27]"
        )
    if akt == "4.2.1k":
        z = state.unit(s, target_name)
        c = state.card(s, z["karte"])
        if orig["karte"] != z["karte"]:
            raise rules.Violation("Originator must be on the same card as the cut phone line [4.2.1k p.22]")
        cut = [l for l in c.get("leitungen", []) if l.get("cut")]
        if not cut or not state.good_order(z):
            raise rules.Violation(f"No cut phone line on {z['karte']} or {target_name} not in Good Order [4.2.1k p.22]")
        for l in cut:
            l["cut"] = False
        prot.append(f"Phone Line on {z['karte']} repaired (flip the marker back) [4.2.1k p.22]")
        return True
    if akt == "4.2.1j":
        z = state.unit(s, target_name)
        from_, to_ = o.get("--von"), o.get("--nach")
        g = [x for x in comms.radios_of(z) if x["netz"] == from_]
        if not g:
            raise rules.Violation(
                f"{target_name} has no device in net {from_}; --source=<net> --to=<net> [4.2.1j p.22]"
            )
        gone = f"{g[0]['typ']} {to_}"
        if gone not in s.get("funk_zerstoert", []):
            raise rules.Violation(
                f"No {g[0]['typ']} of net {to_} is Removed from Play; only the same device type can replace it [4.2.1j p.22, BGG D2]"
            )
        s["funk_zerstoert"].remove(gone)
        s["funk_zerstoert"].append(f"{g[0]['typ']} {from_}")
        g[0]["netz"] = to_
        prot.append(f"{target_name}: {g[0]['typ']} now in net {to_} (net {from_} drops out instead) [4.2.1j p.22]")
        return True
    return False


def order_runner_box(s, hq_name, target_name, akt, o):
    """4.2.1g/h to a Runner in the CO HQ Assets Box (not a unit on the board)."""
    co = s.get("co_hq")
    if hq_name != co and not (hq_name == "GI" and o.get("--originator") == co):
        raise rules.Violation("Only the CO HQ gives Runner orders [4.2.1g/h p.22]")
    if s["phase"] not in rules.IMPULSES or s.get("aktiver_hq") != hq_name:
        raise rules.Violation(f"Active HQ is {s.get('aktiver_hq')}, not {hq_name}")
    name, cost, _, _, rule = rules.ACTIONS[akt]
    k = command_record(s, hq_name)
    check_impulse_budget(s, hq_name, cost, rule)  # L234 (review M7): Commands and per-impulse cap before anything else
    ce = state.unit(s, co)
    prot = []
    if akt == "4.2.1g":
        hq = o.get("--ziel")
        h = s["einheiten"].get(hq)
        if not h or not (h.get("ebene") == "PLT" or h["typ"] == "Staff"):
            raise rules.Violation("--target=<PLT HQ or CO Staff on the board> to be activated next turn [4.2.1g p.22]")
        comms.runner_box(s).remove(target_name)
        s["einheiten"][target_name] = {
            "typ": "Runner",
            "seite": "US",
            "erfahrung": "Line",
            "karte": h["karte"],
            "bereich": h.get("bereich", "offen"),
            "status": [rules.EXPOSED],
            "steps": 1,
            "vof_rating": None,
            "reichweite": "C",
            "ziel": None,
            "runner_ziel": hq,
            "unterwegs_seit": s["zug"],
            "fire_team_seite": False,
            "hinweis": "Runner, Line (4.2.1f); counter VOF UNVERIFIED",
        }
        prot.append(
            f"{target_name} to {hq} on {h['karte']}, Exposed; activates {hq} in the CO HQ Impulse of the next turn unless hit/pinned [4.2.1g p.22, 4.3.2 p.27]"
        )
    else:
        e = o.get("--einheit")
        x = s["einheiten"].get(e)
        if (
            not x
            or x["karte"] != ce["karte"]
            or x.get("bereich", "offen") != ce.get("bereich", "offen")
            or not state.good_order(x)
        ):
            raise rules.Violation(
                "--unit=<Good Order unit in the same card area as the CO HQ that can absorb a step> [4.2.1h p.22]"
            )
        maxst = s.get("aufbau_einheiten", {}).get(e, {}).get("steps", state.steps(x))
        if state.steps(x) >= maxst:
            raise rules.Violation(f"{e} cannot absorb a step (has {state.steps(x)} of {maxst})")
        comms.runner_box(s).remove(target_name)
        x["steps"] = state.steps(x) + 1
        prot.append(f"{target_name} released, {e} at {x['steps']} steps [4.2.1h p.22]")
    pay_commands(s, hq_name, cost, rule)
    txt = f"{hq_name} orders {target_name}: {name}; remaining {k['verfuegbar']}+{k['gespart']}"
    state.save_state(s, txt + "; " + "; ".join(prot), rule)
    print(f"{messages.ALLOWED} {messages.rule(rule)}")
    print(txt)
    briefing.print_board(prot, s)
