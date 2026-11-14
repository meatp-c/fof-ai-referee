"""Friendly Command Phase: activation, impulses, orders of the action menu, late orders, corrections (4.x).

The order pipeline lives here (cmd_order: order_context, resolve_originator, check_recipient, check_repeat_and_budget,
apply_skill, pre_draw_checks, the handler from ORDER_HANDLERS, book_order) together with movement (check_move,
move_unit), cover markers and Concentrate Fire. Split off by topic:
fire_support (Call for Fire, Indirect Lay), grenades (Grenade Attacks, Jam), pickup (Pick Up, jeep), pyro (pyrotechnics)."""

from __future__ import annotations

import copy
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
    naming,
    messages,
    migrate,
    options,
    pickup,
    pyro,
    rules,
    state,
)


YES_WORDS = ("yes", *migrate.german("yes"))  # German words accepted as aliases
NO_WORDS = ("no", *migrate.german("no"))

# Working flags and every other state key: lifetime, meaning, who sets and clears them are listed in fof/keys.py.


def spotted_enemies(s, card_id):
    """Enemy units on card card_id that are Spotted, in board order (one helper for the copies)."""
    return [m for m in state.units_on(s, card_id, "Enemy") if s["units"][m].get("spotted")]


def named_target(s, target_card, given):
    """--unit of a Concentrate Fire or Grenade Attack: an enemy by name, a Cover marker id for the stack beneath it
    ('C1'), or nothing when one Spotted enemy is the only choice (E91)."""
    targets = spotted_enemies(s, target_card)
    if given and given not in s["units"]:
        return next((m for m in targets if s["units"][m].get("area") == given), given)
    return targets[0] if not given and len(targets) == 1 else given


def unspotted_enemies(s, card_id):
    """Enemy units on card card_id that are Unspotted, in board order."""
    return [m for m in state.units_on(s, card_id, "Enemy") if not s["units"][m].get("spotted")]


def text_opt(o, key):
    """a value option as text; a bare --flag where a value is needed is a Violation, not a crash
    on True.split(). Missing: None."""
    v = o.get(key)
    if v is True:
        raise rules.Violation(f"Option {key} needs a value ({key}=..)")
    return v


def parse_per_unit(value):
    """per-unit results '1/1:yes,2/1:no' (also yes/no, any case) -> {'1/1': 'yes', '2/1': 'no'}.
    One parser for Platoon Move/Infiltrate, Platoon Fire and pyro signals; a bad result word is a Violation."""
    result = {}
    for item in (value if isinstance(value, str) else "").split(","):
        if ":" not in item:
            continue
        unit_, word = item.rsplit(":", 1)
        w = word.strip().lower()
        if w in YES_WORDS:
            result[unit_.strip()] = "yes"
        elif w in NO_WORDS:
            result[unit_.strip()] = "no"
        else:
            raise rules.Violation(f"{unit_.strip()}: result must be yes or no, got '{word.strip()}'")
    return result


def team_option(o, default):
    """--team=fire|assault in any spelling -> 'Fire' / 'Assault'; anything else is a Violation."""
    v = o.get("--team")
    if v is None or v is True:
        return default
    t = str(v).strip().capitalize()
    if t not in ("Fire", "Assault"):
        raise rules.Violation(f"--team=fire|assault expected, got '{v}'")
    return t


def check_impulse_budget(s, hq_name, cost, rule, free=False):
    """the Commands and the per-impulse cap of pay_commands, checked before the draw prompt so the
    player does not draw cards for an order that cannot be paid [RULE 4.1.3 p.20]."""
    if free:
        return
    k = s["commands"][hq_name]
    gi = hq_name == "GI"
    total_ = k["available"] + (0 if gi else k["saved"])
    if total_ < cost:
        raise rules.Violation(f"{hq_name} has {total_} Commands, action costs {cost} [RULE {rule}]")
    spent = s.get("impulse_spent", {}).get(hq_name, 0)
    if not gi and spent + cost > rules.MAX_PER_IMPULSE[s["sight"]]:
        raise rules.Violation(
            f"At most {rules.MAX_PER_IMPULSE[s['sight']]} Commands per impulse ({spent} spent, action costs {cost}) [RULE 4.1.3 p.20]"
        )


def pay_commands(s, hq_name, cost, rule):
    k = s["commands"][hq_name]
    check_impulse_budget(s, hq_name, cost, rule)
    spent = s.setdefault("impulse_spent", {}).get(hq_name, 0)
    remainder = cost
    if k["available"] >= remainder:
        k["available"] -= remainder
    else:
        remainder -= k["available"]
        k["available"] = 0
        k["saved"] -= remainder
    s["impulse_spent"][hq_name] = spent + cost


def cmd_activate(s, args):
    rules.need(args, 1, "activate <hq>")
    hq = args[0]
    e = state.unit(s, hq)
    if not state.is_hq(e):
        raise rules.Violation(f"{hq} is not an HQ/Staff [RULE 4.2.1a p.22]")
    if s["phase"] == "3.3.1a" and events.bn_leader(s):
        bn = s.get("active_hq")
        if e.get("level") != "CO" or not bn:
            raise rules.Violation("In the BN HQ impulse the BN HQ only activates the CO HQ [RULE 4.2.1a p.22]")
        activation_allowed(s, hq, e)  # same duplicate and Fire Team side checks as the other paths
        comms.communication(s, bn, hq)
        pay_commands(s, bn, 1, "4.2.1a p.22")
        s["commands"][hq]["activated"] = True
        state.save_state(s, f"{bn} (BN HQ on the board) activates {hq}", "4.1.1 p.18, 4.2.1a p.22")
        print(
            f"{messages.ALLOWED}: {bn} activates {hq} (1 Command, remaining {s['commands'][bn]['available']}); Command marker on Commands Available [4.1.1 p.18]"
        )
        briefing.print_board([], s)
        return
    if s["phase"] == "3.3.1a":
        if e.get("level") != "CO":
            raise rules.Violation("In the BN HQ impulse the BN HQ only activates the CO HQ [RULE 4.2.1a p.22]")
        if state.company(s) and s.get("bn_reconstituting") == s["turn"]:
            raise rules.Violation("The BN HQ is being reconstituted and gives no orders this turn [RULE 6.5.2 p.50]")
        if state.company(s) and s.get("bn_unavailable") == s["turn"]:
            raise rules.Violation("Comm Trouble: BN HQ does not activate the CO HQ this turn [Normandy M1 p.18]")
        if state.company(s):
            ok, reason = comms.bn_link(s)
            if not ok:
                raise rules.Violation(
                    f"BN HQ off-map cannot activate {hq}: {reason}; continue with 3.3.2a CO HQ Initiative [RULE 4.1.1 p.18/19, 4.0 p.18 footnote]"
                )
    elif s["phase"] == "3.3.1b":
        if e.get("level") == "CO":
            raise rules.Violation("The CO HQ is only activated by the BN HQ (3.3.1a) [RULE 4.2.1a p.22]")
    elif s["phase"] == "3.3.2a" and state.company(s):
        if not state.option(s, "U6_activate_in_initiative_impulse"):
            raise rules.Violation(
                "No PLT HQs are activated in the CO HQ Initiative Impulse; non-activated PLT HQs draw Initiative in 3.3.2b [RULE 3.3.1c p.16, 3.3.2b p.16]"
                + state.open_reading(s, "U6_activate_in_initiative_impulse")
            )
        co = s["co_hq"]
        if s.get("active_hq") != co:
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
            + state.open_reading(s, "U6_activate_in_initiative_impulse")
        )
        briefing.print_board([], s)
        return
    else:
        raise rules.Violation(f"Activation only in 3.3.1a/b, currently {s['phase']} [RULE 3.3.1 p.15]")
    k = activation_allowed(s, hq, e)
    co = s.get("co_hq")
    if co and co != "off-map" and s["phase"] == "3.3.1b":
        if s.get("active_hq") != co:
            raise rules.Violation(f"First 'hq {co}' and card draw, then activate")
        ce = state.unit(s, co)
        if state.fire_team_side(ce):
            raise rules.Violation(f"{co} on its Fire Team side cannot activate [RULE 4.2.1a p.22]")
        if not s.get("co_always_in_comm"):
            comms.communication(s, co, hq)
        pay_commands(s, co, 1, "4.2.1a p.22")
    k["activated"] = True
    who = "BN HQ (off-map)" if s["phase"] == "3.3.1a" else (co or "CO HQ (off-map)")
    state.save_state(s, f"{who} activates {hq}; Command marker on Commands Available", "4.2.1a p.22")
    print(
        f"{messages.ALLOWED}: {hq} activated. Flip Command marker to Commands Available."
        + (
            f" Cost 1 Command {co}, remaining {s['commands'][co]['available']}+{s['commands'][co]['saved']}."
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
    if k["activated"]:
        raise rules.Violation(f"{hq} is already activated")
    return k


def command_record(s, hq):
    """the Command record of an HQ/Staff; a unit without one (not an HQ) is a Violation, not a KeyError."""
    k = s["commands"].get(hq)
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
    if ph in ("3.3.1b", "3.3.2a") and e.get("level") != "CO":
        raise rules.Violation(f"In {ph} only the CO HQ acts")
    if ph == "3.3.1b" and not k["activated"]:
        raise rules.Violation("CO HQ not activated; impulse only in 3.3.2a [RULE 3.3.1b p.15]")
    if ph == "3.3.2a" and k["activated"]:
        raise rules.Violation("CO HQ was activated and has already acted [RULE 3.3.2a p.16]")
    if ph == "3.3.1c" and not (e.get("level") == "PLT" or e["type"] == "Staff"):
        raise rules.Violation("In 3.3.1c PLT HQs and CO Staff act")
    if ph == "3.3.1c" and not k["activated"]:
        raise rules.Violation(f"{hq} was not activated; impulse only in 3.3.2b/c (Initiative) [RULE 3.3.1c p.15]")
    if ph == "3.3.2b" and (k["activated"] or e.get("level") != "PLT"):
        raise rules.Violation(f"{hq}: PLT HQ Initiative only for non-activated PLT HQs [RULE 3.3.2b p.16]")
    if ph == "3.3.2c":
        if e["type"] != "Staff" or k["activated"]:
            raise rules.Violation(
                "3.3.2c: only non-activated CO Staff, exactly 1 Command without card draw [RULE 3.3.2c p.16]"
            )
        if k.get("drawn") != [s["turn"], ph]:  # once per turn, also when the impulse is entered again
            k["available"], k["drawn"] = 1, [s["turn"], ph]
    if k["done"]:
        raise rules.Violation(f"{hq} has already ended its impulse this turn")
    s["active_hq"] = hq
    s["impulse_actions"] = {}
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
    note = events.open_flank_note(s)
    if note:
        print(note)


def cmd_card(s, args):
    hq = s.get("active_hq")
    if not hq or hq == "GI":
        raise rules.Violation("No active HQ (first 'hq <name>')")
    if s["phase"] not in rules.IMPULSES - {"3.3.1a", "3.3.2c", "3.3.2d"}:
        raise rules.Violation(f"Card draw for Commands only in HQ impulses, currently {s['phase']}")
    k = s["commands"][hq]
    if k.get("drawn") == [s["turn"], s["phase"]]:
        raise rules.Violation(f"{hq} has already drawn in this impulse [RULE 4.1 p.18]")
    rules.need(args, 2, "card <no|?> <helmet number> [--raw]")
    num, raw = args[0], rules.int_value(args[1], "helmet number")
    o = options.parse_opts(args[2:])
    e = state.unit(s, hq)
    mods = []
    if not o.get("--raw"):
        level = comms.experience(e)
        if level == "Green":
            mods.append(("Green", -1))
        if level == "Veteran":
            mods.append(("Veteran", +1))
        if state.pinned(e):
            mods.append(("Pinned", -1))
        if e.get("area", "open") != "open":
            mods.append(("under cover", +1))
        v = fire.vof_against(s, e["card"], e["side"], ignore_mines=True)
        vm = rules.CMD_VOF_MODIFIERS.get(v[0], -3) if v else 0
        vof_name = f"VOF {rules.VOF_NAME.get(v[0], v[0])}" if v else ""
        if e.get("mine_hit") and vm > -3:
            vm, vof_name = -3, "Mines!-VOF"
        if enemy.sniper_on_card(s, e["card"]) and vm > -3:
            vm, vof_name = -3, "Sniper on the card (7.15)"  # [RULE 4.1.2B p.20, 7.15 p.57]
        if vm:
            mods.append((vof_name, vm))
        if s.get("activity") == "No Contact":
            mods.append(("No Contact", +1))
    total = max(1 if k["activated"] else 0, raw + sum(m for _, m in mods))
    k["available"] = total
    k["drawn"] = [s["turn"], s["phase"]]
    txt = (
        f"{hq} draws Action card #{num}: {raw}"
        + (" " + " ".join(f"{n} {m:+d}" for n, m in mods) if mods else "")
        + f" = {total} Commands (saved {k['saved']})"
    )
    evp = []
    if state.is_campaign(s):
        events.event_pay_commands(s, hq, evp)
    state.save_state(s, txt + ("; " + "; ".join(evp) if evp else ""), "4.1.2 p.20")
    print(txt)
    for x in evp:
        print(f"{messages.BOARD}: " + x)
    bez = f", after event payment {k['available']} new" if k["available"] != total else ""  # [Normandy M1 p.18]
    sum_ = k["available"] + k["saved"]
    spent = s.get("impulse_spent", {}).get(hq, 0)  # an event payment counts against the impulse limit (4.1.3)
    left = max(0, rules.MAX_PER_IMPULSE[s["sight"]] - spent)
    paid = f" ({spent} of {rules.MAX_PER_IMPULSE[s['sight']]} already spent)" if spent else ""
    track_box = f"box {sum_}" if sum_ <= 10 else f"box 10 and remember {sum_ - 10} more (track ends at 10, K27)"
    print(
        f"Command marker on {track_box} (drawn {total}{bez}, saved {k['saved']}); spend at most {left} in this impulse{paid},"
        f" save at most {save_limit(s, hq)} [4.1.3]."
    )
    print(briefing.check_stamp(s))


def save_limit(s, hq):
    """[RULE 4.1.3 p.20] Commands an HQ may save at the end of its impulse: by experience, day or limited
    visibility; the BN HQ and the General Initiative save nothing."""
    if hq in ("GI", "BN") or hq not in s["units"]:
        return 0
    e = s["units"][hq]
    return 0 if e.get("level") == "BN" else rules.SAVE_LIMIT[comms.experience(e)][0 if s["sight"] == "day" else 1]


def _use_gi_skill(s, h: str) -> str:
    """12.7 p.82: hand in the General Initiative skill marker of h for one extra General Initiative Command."""
    e = state.unit(s, h)
    if "General Initiative" not in (e.get("skills") or []):
        raise rules.Violation(f"{h} does not hold the General Initiative skill [RULE 12.7 p.82]")
    e["skills"].remove("General Initiative")
    s["commands"].setdefault("GI", {"available": 0, "saved": 0, "activated": False, "done": False})
    s["commands"]["GI"].setdefault("skill_for", []).append(h)
    scope = "units of its platoon" if e.get("level") == "PLT" else f"{h} itself"
    return f"General Initiative skill of {h}: +1 GI Command for {scope}, return skill marker [12.7 p.82, Player Aid 2]"


def gi_skill_scope(s, ctx):
    """[RULE 12.7 p.82] 'If a Skill is held by a PLT HQ, it can be used by any unit in that platoon. If a Skill is held
    by the CO HQ or a CO Staff unit, it can only be used by that unit': the extra GI Command of a skill is spent on
    such a unit only (K49: attachments yes, LATs no). A matching order uses the skill's Command first."""
    k = s["commands"]["GI"]
    holders = k.get("skill_for") or []
    r = ctx.recipient

    def serves(h):
        hq = s["units"].get(h) or {}
        if ctx.target_name == h:
            return True
        in_platoon = r.get("platoon") == hq.get("platoon") or h in r.get("attached_to", [])
        return hq.get("level") == "PLT" and in_platoon and not state.is_lat(r)

    match = next((h for h in holders if serves(h)), None)
    if match:
        holders.remove(match)
    elif holders and k["available"] - len(holders) < ctx.cost:
        raise rules.Violation(
            f"The remaining General Initiative Command comes from the skill of {', '.join(holders)}: only for "
            "that HQ's platoon (PLT HQ) or the holder itself (CO HQ, Staff) [RULE 12.7 p.82]"
        )


def cmd_gi(s, args):
    if s["phase"] != "3.3.2d":
        raise rules.Violation(f"General Initiative only in 3.3.2d, currently {s['phase']} [RULE 3.3.2d p.16]")
    if len(args) == 2 and args[0] == "skill":  # K49 (BGG 3597449): any time during the impulse, also after the draw
        if not s["commands"].get("GI", {}).get("activated"):
            raise rules.Violation("General Initiative skill after the draw: fof.py gi <card no|?> <small number> first")
        txt = _use_gi_skill(s, args[1])
        s["commands"]["GI"]["available"] += 1
        s["active_hq"] = "GI"
        state.save_state(s, txt, "12.7 p.82")
        print(f"{txt}; GI Commands now {s['commands']['GI']['available']}")
        print(briefing.check_stamp(s))
        return
    if len(args) < 2 or not args[1].lstrip("-").isdigit():  # usage instead of a traceback
        raise rules.Violation(
            "General Initiative: fof.py gi <card no|?> <small number in the star (not the helmet), unmodified> [RULE 3.3.2d p.16]"
        )
    num, small_number = args[0], rules.int_value(args[1], "small number")
    total = small_number // 2 if s.get("single_platoon") else small_number
    o = options.parse_opts(args[2:])
    gi_skill = ""
    if o.get("--skill-from"):
        gi_skill = "; " + _use_gi_skill(s, o["--skill-from"])
        total += 1
    s["commands"].setdefault("GI", {"available": 0, "saved": 0, "activated": False, "done": False})
    s["commands"]["GI"].update(available=total, activated=True)  # activated: drawn this turn
    s["active_hq"] = "GI"
    s["impulse_actions"] = {}
    txt = (
        f"General Initiative: Action card #{num}, small number {small_number}"
        + (f", halved (single-platoon mission) = {total}" if s.get("single_platoon") else f" = {total}")
        + " Commands, unmodified, cannot be saved"
        + gi_skill
    )
    state.save_state(s, txt, "3.3.2d p.16, 4.1.1 p.19")
    print(txt)
    print(
        "Orders: fof.py order GI <unit> <action> ... (without HQ and communication; mandatory HQ actions with --originator=<HQ>)."
    )
    note = events.open_flank_note(s)
    if note:
        print(note)
    print(briefing.check_stamp(s))


def cmd_done(s, args):
    hq = s.get("active_hq")
    if not hq:
        raise rules.Violation("No active HQ")
    k = s["commands"][hq]
    if hq == "GI":
        remainder = k["available"]
        k["available"] = 0
        k.pop("skill_for", None)
        s["active_hq"] = None
        s["impulse_actions"] = {}
        state.save_state(
            s, "General Initiative ended" + (f", {remainder} Commands lost" if remainder else ""), "3.3.2d p.16"
        )
        print("General Initiative ended" + (f", {remainder} Commands lost (cannot be saved)" if remainder else ""))
        print(briefing.check_stamp(s))
        return
    e = state.unit(s, hq)
    limit = 0 if e.get("level") == "BN" else rules.SAVE_LIMIT[comms.experience(e)][0 if s["sight"] == "day" else 1]
    new = k["saved"] + k["available"]
    lost = max(0, new - limit)
    new = min(new, limit)
    k["saved"], k["available"], k["done"] = new, 0, True
    s["active_hq"] = None
    s["impulse_actions"] = {}
    txt = f"{hq} ends impulse; saved {new}" + (f", {lost} lost (limit {comms.experience(e)} {limit})" if lost else "")
    state.save_state(s, txt, "4.1.3 p.20")
    print(txt)
    print(
        f"Board: flip Command marker {hq} to Activation Completed, Saved Commands zone box {new}"
        + (" (Zero Commands Box)" if new == 0 else "")
    )
    print(briefing.check_stamp(s))


def add_cover_marker(s, card_id, type_, value, field=None):
    """New Cover marker on card card_id with the lowest free id; returns the marker dict. field: whether the marker
    is printed on the card (does not count towards the Cover Potential); default: everything but Basic Cover."""
    c = state.card(s, card_id)
    i = len(c.setdefault("cover", [])) + 1
    cid = f"C{i}"
    while any(x["id"] == cid for x in c["cover"]):
        i += 1
        cid = f"C{i}"
    marker = {"id": cid, "type": type_, "value": value, "field": type_ != "Basic Cover" if field is None else field}
    if type_ == "Church Tower":
        marker["capacity"] = 1  # [RULE 5.3.3 p.38] Observation Post: 'only a single step may be in this cover'
    c["cover"].append(marker)
    return marker


def new_cover_marker(s, card_id, type_, value):
    """Id of a new Cover marker (callers in contact, enemy and setup use the id)."""
    return add_cover_marker(s, card_id, type_, value)["id"]


def mark(e, m):
    if m not in e["status"]:
        e["status"].append(m)
        if m == rules.EXPOSED and e.get("side") == "US":
            e["_new_exposed"] = True  # Heat Casualties (Naktong M1 p.17) are checked in state.save_state


def new_name(s, type_, reuse_removed=False, side=None, card=None):
    """Lowest free counter number. reuse_removed: enemy counters Removed from Play return to the counter mix and are
    reused (glossary 'Removed from Play', E88); friendly ones stay blocked (only back via Reconstitution).
    with counter_names in the setup the counter keeps the name printed on it, the first free one in the order of
    the player's counter tray (a counter that leaves the map frees its name for the next placement). An enemy unit
    (side 'Enemy', or reuse_removed) gets the setup's enemy_prefix in front ('NKPA 1/1 HMG', 'NKPA Sniper 1')."""
    used = set(s["units"]) | (set() if reuse_removed else set(s.get("removed_from_play", [])))
    if card and s.get("lat_names") == "card" and type_ in naming.ABBREVIATION:
        # generic team named by counter type and card from the start (no second 'is now called' line)
        base = naming.base_label(s, {"side": side or "US", "type": type_, "card": card})
        return next(base + x for x in naming.SUFFIXES if base + x not in s["units"])
    free = [n for n in s.get("counter_names", {}).get(type_, []) if n not in used]
    if free:
        return free[0]
    prefix = s.get("enemy_prefix") if (side == "Enemy" or (side is None and reuse_removed)) else None
    base = f"{prefix} {type_}" if prefix and not type_.startswith(prefix + " ") else type_
    i = 1
    while f"{base} {i}" in used:
        i += 1
    return f"{base} {i}"


def set_area(s, unit, b):
    """Put the unit under Cover marker b on its card ('open' = out of cover) [5.3]. _name is unused; it stays in the
    signature until the caller in setup.py stops passing it."""
    unit.pop("deep_bunker", None)
    if b == "open":
        unit["area"] = "open"
        return
    if not any(c["id"] == b for c in state.card(s, unit["card"]).get("cover", [])):
        raise rules.Violation(f"Cover {b} does not exist on {unit['card']}")
    occupied = {s["units"][m]["side"] for m in state.units_on(s, unit["card"]) if s["units"][m].get("area") == b}
    if occupied and occupied != {unit["side"]}:
        raise rules.Violation(f"Cover {b} is occupied by the opposing side [5.3]")
    cv = next(c for c in state.card(s, unit["card"])["cover"] if c["id"] == b)  # exists, checked above
    if cv.get("capacity"):
        st = sum(
            state.steps(s["units"][m])
            for m in state.units_on(s, unit["card"])
            if s["units"][m].get("area") == b and s["units"][m] is not unit
        )
        if st + state.steps(unit) > cv["capacity"]:
            raise rules.Violation(
                f"{cv['type']} {b} holds at most {cv['capacity']} steps, occupied {st} [RULE 5.3.2 p.37]"
            )
    unit["area"] = b
    if cv["type"] == "Deep Bunker":  # no VOF from inside, for either side
        unit["deep_bunker"] = b
        fire.cease_fire(unit)


def _weak_unit_move_check(s, e, n, target_card, action_id, vof_on):
    """[RULE 4.2.5 p.26] Pinned units, LATs and units on their Fire Team side: where they may move and what they
    must drop first."""
    destination = state.card(s, target_card)
    if state.pinned(e) or e["type"] in ("Fire Team", "Litter Team", "Paralyzed Team") or state.fire_team_side(e):
        friend = [m for m in state.units_on(s, target_card, e["side"]) if m != n]
        ok = (destination.get("staging") and action_id in ("4.2.2a", "4.2.2b")) or (
            friend and vof_on(target_card) is None
        )
        if not ok:
            raise rules.Violation(
                f"{n} (Pinned/LAT/Fire Team side) may only move to a Staging Area or to a card occupied by friendly units without VOF [RULE 4.2.5 p.26]"
            )
    if e["type"] == "Paralyzed Team" and action_id != "4.2.2a":
        raise rules.Violation("Paralyzed Team: only Move to an Adjacent Card [RULE 4.2.5 p.26]")
    if (state.pinned(e) or e["type"] == "Paralyzed Team") and (
        comms.radios_of(e) or e.get("carries_casualties") or e.get("assets")
    ):  # also the asset list (smoke, illumination, rifle grenades), 4.2.5 footnote 'must drop any assets'
        load = [g["type"] for g in comms.radios_of(e)] + list(e.get("assets") or [])
        if e.get("carries_casualties"):
            load.append(f"{e['carries_casualties']} Casualty")
        raise rules.Violation(
            f"{n} is Pinned/Paralyzed and carries Assets or Casualties ({', '.join(load)}); drop them first "
            f"(fof.py drop, no Command) [RULE 4.2.5 p.27 'must drop any assets or casualties', 5.1.6E p.33]"
        )


def check_move(s, e, n, target_card, action_id):
    """Legality of one card move (read-only). The VOF on the destination is computed at most once."""
    memo = {}

    def vof_on(card_id, side=None):
        side = side or e["side"]
        if (card_id, side) not in memo:
            memo[card_id, side] = fire.vof_against(s, card_id, side)
        return memo[card_id, side]

    if e.get("on_board"):
        raise rules.Violation(
            f'{n} is on board the {e["on_board"]} and moves with it in phase 3.6; to leave it first: order <HQ> "{n}" 4.2.2h --what=jeep [10.8.1, Normandy CSR 1]'
        )
    if rules.EXPOSED in e["status"]:
        raise rules.Violation(f"{n} is Exposed and may no longer change cards [RULE 5.1.2 p.31]")
    if not geometry.adjacent(s, e["card"], target_card):
        raise rules.Violation(f"{target_card} is not adjacent to {e['card']} (diagonal counts too) [RULE 5.1.2 p.31]")
    destination = state.card(s, target_card)
    if destination.get("outside") and e["side"] == "US":
        raise rules.Violation(
            f"{target_card} lies outside the mission boundaries (map extension); friendly units may not go there [RULE 2.4.1 p.10, 8.4.5 p.65]"
        )
    if e["side"] == "US" and s.get("hold_up") == s["turn"] and not state.units_on(s, target_card):
        raise rules.Violation(
            f"Hold up!: no movement onto an unoccupied card this turn ({target_card}) [Normandy M3 p.26]"
        )
    if e.get("mine_hit"):
        raise rules.Violation(
            f"{n} is under the Mine marker and may not move to an adjacent card this turn [RULE 7.9.1 p.54]"
        )
    if state.is_campaign(s):
        event_move_check(s, e, target_card)
    _weak_unit_move_check(s, e, n, target_card, action_id, vof_on)
    if action_id in ("4.2.2c", "4.2.2d"):
        if not infiltration_marker(s, e["card"], target_card, vof_on):  # same test as infiltrate_possible
            raise rules.Violation(
                "Infiltration only if the origin or destination card has a VOF marker [RULE 5.1.4 p.32]"
            )
        if e.get("tripod") or e.get("vof_rating") == "H" or state.is_mortar(e):
            raise rules.Violation(f"{n} (tripod/H VOF) may not infiltrate [RULE 4.2.2c p.23]")
    diagonal_pdf_check(s, e, target_card)


def infiltrate_possible(s, e, target_card):
    """[RULE 5.1.4 p.32]: a friendly Good Order unit or an Assault/Fire Team (4.2.5 LAT list), not Exposed, without
    tripod/H/mortar, with a VOF marker (or a Grenade Miss marker) on the origin or the destination card."""
    if e["side"] != "US" or state.pinned(e) or state.fire_team_side(e) or rules.EXPOSED in e["status"]:
        return False
    if state.is_lat(e) and "4.2.2c" not in rules.LAT_ALLOWED.get(e["type"], ()):
        return False  # 4.2.5: Assault and Fire Teams may infiltrate, Paralyzed and Litter Teams may not
    if e.get("tripod") or e.get("vof_rating") == "H" or state.is_mortar(e):
        return False
    return infiltration_marker(s, e["card"], target_card)


def infiltration_marker(s, origin, target_card, vof=None):
    """[RULE 5.1.4 p.32] a VOF marker (any side: K34, also the own Point Blank VOF) or a Grenade Miss marker on the
    origin or the destination card. One test for check_move and infiltrate_possible; vof(card_id, side)
    may be a memoized lookup (check_move)."""
    vof = vof or (lambda card_id, side: fire.vof_against(s, card_id, side))
    return any(
        vof(k, "US") is not None or vof(k, "Enemy") is not None or state.card(s, k).get("grenade_miss")
        for k in (origin, target_card)
    )


_UNSET = object()


def event_move_check(s, e, target_card):
    """events.event_move for its Violations only (Trouble on the Flank). It also books the 'Event
    fulfilled' flag; here that flag is restored, so the booking and its protocol line happen once, in move_unit."""
    ev = s.get("event_flank")
    before = ev.get("fulfilled", _UNSET) if ev else _UNSET
    try:
        events.event_move(s, e, target_card, [])
    finally:
        if ev:
            if before is _UNSET:
                ev.pop("fulfilled", None)
            else:
                ev["fulfilled"] = before


def diagonal_pdf_check(s, e, target_card):
    """[RULE 5.1.2 p.32] a diagonal move may not cross a PDF between the two orthogonal neighbours (both sides)."""
    origin, destination = state.card(s, e["card"]), state.card(s, target_card)
    if abs(origin["row"] - destination["row"]) == 1 and abs(origin["column"] - destination["column"]) == 1:
        e1, e2 = (
            geometry.card_at(s, origin["row"], destination["column"]),
            geometry.card_at(s, destination["row"], origin["column"]),
        )
        if e1 and e2:
            for f in s["units"].values():
                if fire.is_firing(f) and f["target"] != f["card"]:
                    path_cards = [f["card"]] + (geometry.line_between(s, f["card"], f["target"]) or []) + [f["target"]]
                    for i in range(len(path_cards) - 1):
                        if {path_cards[i], path_cards[i + 1]} == {e1, e2}:
                            raise rules.Violation(
                                f"Diagonal {e['card']} to {target_card} crosses the PDF {path_cards[i]} to {path_cards[i + 1]} [RULE 5.1.2 p.32]"
                            )


def move_unit(s, n, target_card, area, exposed, prot, open_all=True):
    e = s["units"][n]
    from_ = e["card"]
    grenades.grenade_expires(s, e, n, prot)
    if state.is_campaign(s):
        comms.lay_line(s, n, e, from_, prot, s.get("_order_opts"))
        combat.ammo_surplus(s, n, e, from_, prot)
        events.event_move(s, e, target_card, prot)
    old_cover = fire.cover_of(s, e)
    e["card"] = target_card
    e["area"] = "open"
    e.pop("deep_bunker", None)
    if area and area != "open":
        set_area(s, e, area)
    new_cover = fire.cover_of(s, e)
    destination = state.card(s, target_card)
    if state.card(s, from_).get("staging") and destination.get("staging"):
        exposed = False  # 5.1.3
    if (
        old_cover
        and new_cover
        and old_cover["type"] in ("Trench", "Bunker", "Pillbox")
        and new_cover["type"] in ("Trench", "Bunker", "Pillbox")
    ):
        exposed = False  # 5.1.2
    if exposed:
        mark(e, rules.EXPOSED)
    prot.append(
        f"{n} to {target_card}"
        + (f" under {area}" if area and area != "open" else "")
        + (", Exposed" if rules.EXPOSED in e["status"] else ", not Exposed")
    )
    if (
        not area and e["side"] == "US" and not e.get("vehicle")
    ):  # vehicles use no cover markers: no reminder when the player chose --area=open explicitly
        # [RULE 5.1.2 p.31] 'When entering another card that has an unoccupied or friendly-occupied Cover marker,
        # the moving unit may move directly under the Cover marker.'
        free = [cv["id"] for cv in state.free_cover(s, target_card, e["side"], steps=state.steps(e))]
        if free:
            prot.append(
                f"{n} arrives out of cover; free or friendly Cover marker on {target_card}: {', '.join(free)} - "
                "the unit may go directly under it when entering (repeat the order with --area=<id>) [5.1.2 p.31]"
            )
    campaign.patrol_move(s, n, from_, target_card, prot)
    fire.fire_after_move(s, n, prot, origin=from_, open_all=open_all)
    if state.units_on(s, target_card, state.opponent_of_side(e["side"])):
        prot.append(f"Point Blank on {target_card}: each side's VOF only hits the opposing side [6.2.1b]")
    own_fire = friendly_fire_on(s, n, target_card)
    if own_fire:
        prot.append(
            f"WATCH friendly fire: {n} on {target_card} is under the VOF of own units from other cards: "
            f"{', '.join(own_fire)} (Cease Fire/Shift Fire, 4.2.4k/l) [6.3.3, 6.1]"
        )
    if state.is_campaign(s):
        pc_ = s.pop("_engineer_check", None)
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


def hq_back(s, hq_name2, recipient, prot):
    """[RULE 6.5.2 p.49] reconstituted HQ on the card of the receiving unit, always Green."""
    old = s.get("rfp_data", {}).get(hq_name2, {})
    e = {
        "type": "HQ",
        "level": old.get("level", "PLT"),
        "platoon": old.get("platoon", recipient.get("platoon")),
        "side": "US",
        "experience": "Green",
        "card": recipient["card"],
        "area": recipient.get("area", "open"),
        "status": [],
        "steps": 1,
        "fire_team_side": True,
        "ft_vof": old.get("ft_vof", "S"),
        "vof_rating": None,
        "range": "L",
        "target": None,
        "radio": [],
    }
    s["removed_from_play"].remove(hq_name2)
    s["units"][hq_name2] = e
    s["commands"].setdefault(hq_name2, {"available": 0, "saved": 0, "activated": False, "done": False})
    s["commands"][hq_name2].update(saved=0, available=0)
    prot.append(
        f"{hq_name2} reconstituted on {recipient['card']}, Green (saves at most {rules.SAVE_LIMIT['Green'][0]}) [RULE 6.5.2 p.49]"
    )
    return e


def hand_over_step(s, n, prot, team):
    """Receiving unit loses a step; if only one step of the squad remains, it becomes a Fire/Assault Team [RULE 6.5.2 p.49]."""
    unit = s["units"][n]
    if state.steps(unit) > 1:
        unit["steps"] = state.steps(unit) - 1
        prot.append(f"{n} down to {unit['steps']} steps")
        if state.steps(unit) == 1 and unit.get("last_step"):
            lat = (team or "Fire") + " Team"
            new = new_name(s, lat, side=unit["side"], card=unit["card"])
            s["units"][new] = combat.new_lat(unit, lat, n)
            s["units"][new]["status"] = []
            combat.remove_from_play(s, n, prot, f"last step becomes {lat} ({new}) [6.5.2 p.49]", successor=new)
    else:
        combat.remove_from_play(s, n, prot, "used for the reconstitution [6.5.2 p.49]")


def co_hq_candidates(s):
    """[RULE 6.5.2 p.49] 'Reconstitute the CO HQ from its second-in-command (i.e. the XO in a US company). If the
    second-in-command has already been Removed From Play, reconstitute from one of the following, in this order: Any
    Platoon HQ, Arty FO, CO Staff (in descending order of rank)': the first tier that still has a unit in play. A
    unit of that tier on its Fire Team side 'cannot be skipped over unless Removed from Play'."""
    us = {n: e for n, e in s["units"].items() if e["side"] == "US"}
    staff = sorted((n for n, e in us.items() if e["type"] == "Staff"), key=lambda n: us[n].get("rank", 9))
    tiers = [
        [n for n in staff if "XO" in n],
        [n for n, e in us.items() if e["type"] == "HQ" and e.get("level") == "PLT"],
        [n for n, e in us.items() if e["type"] == "FO" and "Arty" in n],
        *[[n] for n in staff if "XO" not in n],
    ]
    return next((tier for tier in tiers if tier), [])


def reconstitute_co_hq(s, target_name, prot, by_bn=False):
    """4.2.1e: the unit becomes the CO HQ (Green), keeps its radios and leaves play [RULE 6.5.2 p.49/50]."""
    co = s.get("co_hq")
    if co in s["units"] or co not in s.get("removed_from_play", []):
        raise rules.Violation(f"{co} is not Removed from Play")
    recipient = state.unit(s, target_name)
    tier = co_hq_candidates(s)
    if target_name not in tier:
        raise rules.Violation(
            f"The CO HQ is reconstituted from {' or '.join(tier) or 'nobody (no eligible unit left)'} first (XO, then any "
            "PLT HQ, Arty FO, CO Staff by rank; a unit on its Fire Team side is rallied first, not skipped) [RULE 6.5.2 p.49]"
        )
    if state.fire_team_side(recipient) or not state.good_order(recipient):
        raise rules.Violation(f"{target_name} must be on its Good Order side (rally first) [RULE 6.5.2 p.50]")
    if by_bn and state.radio_active(s) and not comms.radios_of(recipient, "SCR300", "BN TAC"):
        raise rules.Violation(
            f"{target_name} carries no BN TAC device; first pick up an SCR300 BN TAC (4.2.2h) [RULE 6.5.2 p.50, FM1 p.38] [open U8]"
        )
    if by_bn and not state.radio_active(s):
        prot.append("Mission without radio: BN TAC connection assumed per mission [open U8]")
    radio = [dict(g) for g in comms.radios_of(recipient)]
    recipient["radio"] = []
    e = hq_back(s, co, recipient, prot)
    e["level"] = "CO"
    e["radio"] = radio
    combat.remove_from_play(s, target_name, prot, f"becomes {co} [6.5.2 p.49]")


def order_bn(s, target_name, action_id):
    """[RULE 6.5.2 p.50] 'While off-map, the BN HQ can order the Reconstitution of the CO HQ from an eligible unit with a BN TAC
    radio/phone during the BN HQ Impulse.' Order: Any Platoon HQ, Arty FO, CO Staff."""
    if action_id != "4.2.1e":
        raise rules.Violation("The BN HQ (off-map) only gives 'Reconstitute the CO HQ' (4.2.1e) here [RULE 6.5.2 p.50]")
    if s["phase"] != "3.3.1a" or s.get("bn_hq") != "off-map":
        raise rules.Violation(
            "BN HQ off-map: reconstitution of the CO HQ only in the BN HQ Impulse 3.3.1a [RULE 6.5.2 p.50]"
        )
    if s.get("bn_reconstituting") == s["turn"]:
        raise rules.Violation("The BN HQ is being reconstituted this turn and gives no orders [RULE 6.5.2 p.50]")
    prot = []
    reconstitute_co_hq(s, target_name, prot, by_bn=True)
    state.save_state(
        s, f"BN HQ orders Reconstitute the CO HQ: {target_name}; " + "; ".join(prot), "4.2.1e p.22, 6.5.2 p.50"
    )
    print(f"{messages.ALLOWED} {messages.rule('4.2.1e p.22, 6.5.2 p.50')}")
    briefing.print_board(prot, s)


# [RULE 12.7 p.82, Player Aid 2 Skills] Skills in use
SKILL_AUTO = {
    "Auto Spot": ("4.2.4a",),
    "Auto Cover": ("4.2.2e",),
    "Auto Concentrate": ("4.2.4b",),  # marker name as in rules.SKILL_MARKERS_NORMANDY and the setup data
    "Auto Infiltrate": ("4.2.2c", "4.2.2g"),
    "Auto Grenade": ("4.2.4d",),
}


def skill_holder(s, unit_name, skill):
    """12.7: PLT HQ skill for every unit of the platoon; CO HQ and Staff skill only for the unit itself."""
    unit = s["units"][unit_name]
    if skill in (unit.get("skills") or []) and (unit["type"] in ("HQ", "Staff")):
        return unit_name
    p = unit.get("platoon")
    if p:
        for n, e in s["units"].items():
            if (
                e.get("side") == "US"
                and e["type"] == "HQ"
                and e.get("level") == "PLT"
                and str(e.get("platoon")) == str(p)
                and skill in (e.get("skills") or [])
            ):
                return n
    raise rules.Violation(
        f"Skill {skill} is not available to {unit_name}: PLT HQ skills only for units of this platoon, CO HQ/Staff skills only for the unit itself [RULE 12.7 p.82]"
    )


def cmd_late_order(s, args):
    """(V22): forgotten order of an HQ/Staff whose impulse already ended this turn.
    Runs like 'order' (all checks except the repeat check of that impulse), cost from its saved Commands,
    the 6-per-impulse limit counts what the HQ already spent this turn (s['impulse_spent'], 4.1.3)."""
    if len(args) < 3:
        raise rules.Violation("lateorder <HQ> <unit> <action> [--target=..] [--area=..] ...")
    hq = args[0]
    if s["phase"] not in rules.IMPULSES:
        raise rules.Violation(
            f"Late order only in the Friendly Command Phase 3.3, currently {s['phase']} [RULE 3.3 p.15]"
        )
    k = s["commands"].get(hq)
    if hq == "GI" or not k or not k.get("done"):
        raise rules.Violation(f"Late order only for an HQ/Staff whose impulse ended this turn ({hq})")
    if hq == s.get("active_hq"):
        raise rules.Violation(f"{hq} is active: use the normal 'order'")
    spent = s.get("impulse_spent", {}).get(hq, 0)
    cmd_order(s, args, late_order=hq)
    print(
        f"Late order {hq}: {spent} already spent in that impulse; Commands now {s['commands'][hq]['saved']} (Saved Commands zone)"
    )


def cmd_correct(s, args):
    """(V22): the board is the master - fix a proven wrong booking instead of editing the JSON by hand.
    correct casualty <card> <+n|-n> [--side=Enemy|US] --reason=<text>"""
    usage = "correct casualty <card> <+n|-n> [--side=Enemy|US] --reason=.. | correct status <unit> <marker> remove|add --reason=.. | correct grenade <unit> expired <origin card> --reason=.. | correct ammo <unit> <+n|-n> --reason=.. | correct target <unit> <card> --reason=.. | correct number <card> <card number> --reason=.."
    positional = {
        "casualty": 3,
        "ammo": 3,
        "target": 3,
        "number": 3,
        "status": 4,
        "grenade": 4,
    }  # subwords: grenade, ammo, target
    if not args or args[0] not in positional:
        raise rules.Violation(usage)
    rules.need(args, positional[args[0]], usage)  # Violation instead of IndexError
    o = options.parse_opts(args[positional[args[0]] :])
    if not o.get("--reason"):
        raise rules.Violation("give --reason=<text> (source of the correction, e.g. counter photo, player decision)")
    if args[0] == "number":
        # the printed number of a terrain card, read wrongly when the card was entered
        c = state.card(s, args[1])
        txt = f"Correction {args[1]}: card number {c.get('card_number') or '-'} becomes {args[2]} ({o['--reason']})"
        c["card_number"] = args[2]
        state.save_state(s, txt, "2.2.1 p.9")
        briefing.print_board([txt], s)
        return
    if args[0] == "target":
        # restore a fire target afterwards (wrongly booked Cease Fire)
        n, card_id = args[1], args[2]
        e = state.unit(s, n)
        state.card(s, card_id)
        e["target"] = card_id
        txt = f"Correction {n}: fires on {card_id} again, PDF from {e['card']} to {card_id} ({o['--reason']})"
        state.save_state(s, txt, "6.1.2 p.44")
        print(f"Board: place PDF {n} from {e['card']} to {card_id}, VOF on {fire.effective_fire_target(s, n)}")
        print(briefing.check_stamp(s))
        return
    if args[0] == "ammo":
        # set an ammo marker afterwards (e.g. ammo spent on fire that did not happen because LOS was lost, 7.18.4)
        n = args[1]
        e = state.unit(s, n)
        m = e.get("ammo")
        if not m:
            raise rules.Violation(f"{n} carries no ammo")
        d = rules.int_value(args[2], "ammo correction")
        old = m["points"]
        m["points"] = max(0, min(m.get("start", old + d), old + d))
        txt = f"Correction {n}: {m.get('type', '')} ammo {old} to {m['points']} ({o['--reason']})"
        state.save_state(s, txt, "7.18.4 p.61")
        print(f"Board: turn ammo marker {n} from {old} to {m['points']}")
        print(briefing.check_stamp(s))
        return
    if args[0] == "grenade":
        # expire a Grenade marker afterwards as a Grenade Miss on the origin card (7.10.4)
        n, card_id = args[1], args[3]
        e = state.unit(s, n)
        if not e.get("grenade"):
            raise rules.Violation(f"{n} carries no Grenade marker")
        state.card(s, card_id)["grenade_miss"] = True
        e["grenade"] = []
        if (
            s["phase"] == "3.7.4"
            and n in s.get("combat_open", [])
            and fire.vof_against(s, e["card"], e["side"], ignore_mines=True) is None
            and not state.card(s, e["card"]).get("grenade_miss")
            and not e.get("mine_hit")
        ):
            s["combat_open"].remove(n)
            s.get("combat_ncm", {}).pop(n, None)  # frozen state without this unit (no VOF against it any more)
        txt = f"Correction {n}: Grenade marker expired, Grenade Miss (-1) on {card_id} ({o['--reason']})"
        state.save_state(s, txt, "7.10.4 p.55")
        print(f"Board: take the Grenade marker from {n}, Grenade Miss marker (-1) on {card_id}")
        print(briefing.check_stamp(s))
        return
    if args[0] == "status":
        # set/remove a unit's status marker afterwards (e.g. a move re-rated as a successful infiltration)
        n, marker, how = args[1], args[2], args[3]
        e = state.unit(s, n)
        if how == "remove":
            if marker not in e["status"]:
                raise rules.Violation(f"{n} has no {marker} marker")
            e["status"].remove(marker)
        elif how == "add":
            mark(e, marker)
        else:
            raise rules.Violation("remove | add")
        txt = f"Correction {n}: {marker} {'removed' if how == 'remove' else 'added'} ({o['--reason']})"
        state.save_state(s, txt, "AI_BRIEFING: the board is the master")
        print(f"Board: {marker} marker on {n}: " + ("remove" if how == "remove" else "place"))
        print(briefing.check_stamp(s))
        return
    card_id, n = args[1], rules.int_value(args[2], "casualty correction")
    c = state.card(s, card_id)
    key = "casualties_enemy" if o.get("--side", "Enemy") == "Enemy" else "casualties"
    old = c.get(key, 0)
    if old + n < 0:
        raise rules.Violation(f"Only {old} casualties ({key}) lie on {card_id}")
    c[key] = old + n
    txt = f"Correction {card_id}: {key} {old} to {c[key]} ({o['--reason']})"
    state.save_state(s, txt, "AI_BRIEFING: the board is the master")
    print(f"Board: casualty markers on {card_id}: {old} to {c[key]}")
    print(briefing.check_stamp(s))


def _order_move(s, ctx):
    """Order handler for: action_id in ('4.2.2a', '4.2.2c')"""
    target_card = ctx.o.get("--target")
    if not target_card:
        raise rules.Violation("--target=<card> missing")
    state.card(s, target_card)
    check_move(s, ctx.recipient, ctx.target_name, target_card, ctx.action_id)
    plain = ctx.o.get("--plain")  # --plain=no is not a yes; a bare --plain is
    if plain not in (None, True, *YES_WORDS, *NO_WORDS):
        raise rules.Violation("--plain=yes|no")
    if (
        ctx.action_id == "4.2.2a"
        and plain not in (True, *YES_WORDS)
        and infiltrate_possible(s, ctx.recipient, target_card)
    ):
        # a Move where an Infiltrate would be possible is never better (a failed attempt is the same Move)
        raise rules.Violation(
            f"{ctx.target_name} could infiltrate to {target_card} (VOF on the origin or destination card) [RULE 5.1.4 p.32]: "
            "order 4.2.2c with --success=yes|no (2 cards, Infiltrate icon), or --plain=yes for an intended Move; nothing booked"
        )
    engineer = (
        ctx.action_id == "4.2.2c"
        and contact.engineers_clear(s, ctx.recipient)
        and bool(contact.mines_on(s, target_card))
    )
    if engineer:
        s["_engineer_check"] = (ctx.target_name, target_card, 1 if ctx.success == "yes" else 3)
        exposed = False  # CSR 10: failed Engineer infiltration without Exposed, but 3 cards
    else:
        exposed = ctx.action_id == "4.2.2a" or ctx.success == "no"
    move_unit(s, ctx.target_name, target_card, ctx.o.get("--area"), exposed=exposed, prot=ctx.prot)
    ctx.moved = [ctx.target_name]


def platoon_move_members(s, orig_name, orig, action_id):
    """[RULE 4.2.2b/d p.23] the units a Platoon Move/Infiltrate takes along: Good Order, not Exposed, in the chain of
    command and in communication with the originator, on its card; no tripod/H units for an infiltration. one
    member set for the stacking pre-check and the handler."""
    candidate = []
    for n, e in s["units"].items():
        if e["side"] != "US" or e["card"] != orig["card"]:
            continue
        try:
            comms.chain_of_command(s, orig_name, n)
            comms.communication(s, orig_name, n)
        except rules.Violation:
            continue
        if not state.good_order(e) or rules.EXPOSED in e["status"]:
            continue
        if e.get("on_board") or e.get("vehicle"):
            continue  # vehicles and units on board move in phase 3.6, not with the platoon
        if action_id == "4.2.2d" and (e.get("tripod") or e.get("vof_rating") == "H"):
            continue
        single = "4.2.2a" if action_id == "4.2.2b" else "4.2.2c"
        if single in (s.get("impulse_actions") or {}).get(n, []):
            continue  # already moved/infiltrated in this impulse (4.2 p.21)
        candidate.append(n)
    return candidate


def _order_move_platoon(s, ctx):
    """Order handler for: action_id in ('4.2.2b', '4.2.2d')"""
    target_card = ctx.o.get("--target")
    if not target_card:
        raise rules.Violation("--target=<card> missing")
    state.card(s, target_card)
    # [RULE 4.2 p.21, 4.2.2b/d 'Have each unit in the platoon perform a Move/an Attempt to Infiltrate'] every member
    # has made the single action too and may not repeat it in this impulse
    ctx.also_book = "4.2.2a" if ctx.action_id == "4.2.2b" else "4.2.2c"
    result = parse_per_unit(ctx.success)  # yes/no and yes/no per unit
    candidate = (
        ctx.candidates
        if ctx.candidates is not None
        else platoon_move_members(s, ctx.orig_name, ctx.orig, ctx.action_id)
    )
    if not candidate:
        raise rules.Violation(
            "No Good Order unit of the platoon without Exposed in communication on the HQ's card [RULE 4.2.2b p.23]"
        )
    with fire.cached(s):  # read-only checks of the same move: one fire map for all members
        for n in candidate:
            # legality of every member before the draw prompt, as 4.2.2c does
            check_move(s, s["units"][n], n, target_card, ctx.action_id)
    if ctx.action_id == "4.2.2d" and any(n not in result for n in candidate):
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
            ctx.o.get("--area"),
            exposed=(ctx.action_id == "4.2.2b" or result.get(n) == "no"),
            prot=ctx.prot,
            open_all=False,
        )
    # the platoon moves together: the board-wide 6.1.1 check once after the last member, so members still on the
    # origin card no longer open fire there only to cease fire again when they move
    fire.open_fire(s, ctx.prot)
    ctx.moved = candidate


def _check_seek_cover(s, ctx):
    """State-only legality of Seek Cover, also before the draw."""
    if ctx.recipient.get("on_board"):
        raise rules.Violation(
            f"{ctx.target_name} is on board the {ctx.recipient['on_board']}: no cover marker [10.8.1]"
        )
    if ctx.recipient.get("area", "open") != "open":
        raise rules.Violation(f"{ctx.target_name} is already under cover [RULE 4.2.2e p.23]")
    present = len([c for c in ctx.recipient_card.get("cover", []) if not c.get("field")])
    if ctx.recipient_card.get("cover_max") is not None and present >= ctx.recipient_card["cover_max"]:
        raise rules.Violation(
            f"{ctx.recipient['card']} has reached its Cover Potential ({ctx.recipient_card['cover_max']}) [RULE 5.3 p.36]"
        )


def _order_seek_cover(s, ctx):
    """Order handler for: action_id == '4.2.2e'"""
    _check_seek_cover(s, ctx)
    if ctx.success == "yes":
        if ctx.recipient_card.get("building_table") and state.is_campaign(s):
            # [5.3.3 p.38, campaign building table] urban card: cover type by R#
            if not ctx.o.get("--building"):
                col, ref = contact.building_table_ref(s, ctx.recipient["card"])
                raise rules.Violation(
                    f"Seek Cover on Village/Farm/Cemetery/Church: R# column {col} on the building table, --building=<R#> [--building-value=<n>] [{ref}]"
                )
            building_type, building_value, upper_ = contact.building_cover(
                s, ctx.recipient["card"], ctx.o["--building"], ctx.o.get("--building-value")
            )
            cover = add_cover_marker(s, ctx.recipient["card"], building_type, building_value, field=False)
            us = upper_story_type(ctx.recipient_card)
            if building_type != "Basic Cover" and us:
                # [RULE 5.3.3 p.38, 5.2.2B p.36] Multi-Story/Church symbol on the card: add Upper Story or Church Tower,
                # same value, does not count towards the Cover Potential (the star of the CSR 8 table applies to snipers/spotters only)
                uid = add_cover_marker(s, ctx.recipient["card"], us, building_value, field=True)["id"]
                ctx.prot.append(
                    f"additionally {us} marker {uid} (+{building_value}) on {ctx.recipient['card']}; does not count towards the Cover Potential"
                    + (", 1 step only" if us == "Church Tower" else "")
                    + " [5.3.3 p.38, 5.2.2B p.36]"
                )
            elif upper_:
                ctx.prot.append(
                    "card without Multi-Story symbol: no Upper Story marker (star only for snipers/spotters) [CSR 8 p.15, 5.3.3 p.38]"
                )
        else:
            cover = add_cover_marker(
                s, ctx.recipient["card"], "Basic Cover", options.int_opt(ctx.o, "--value", "cover value", 1)
            )
        grenades.grenade_expires(s, ctx.recipient, ctx.target_name, ctx.prot)  # [RULE 7.10.4] moving within the card
        ctx.recipient["area"] = cover["id"]
        mark(ctx.recipient, rules.EXPOSED)
        ctx.prot.append(
            f"new cover marker {cover['id']} ({cover['type']}) on {ctx.recipient['card']}, {ctx.target_name} beneath it, Exposed"
        )
        if state.is_campaign(s) and state.option(s, "U20_mine_on_seek_cover"):
            contact.request_mine_check(
                s,
                [ctx.target_name],
                ctx.recipient["card"],
                ctx.prot,
                "movement under new cover" + state.open_reading(s, "U20_mine_on_seek_cover"),
            )
    else:
        ctx.prot.append(f"{ctx.target_name}: Seek Cover failed, nothing happens")
        s["last_attempt"] = [ctx.target_name, ctx.action_id, s["phase"]]


def _check_move_within_card(s, ctx):
    """State-only legality of Move/Infiltrate within a Card, also before the draw; returns the area."""
    if ctx.recipient.get("on_board"):  # as Seek Cover, no cover marker for a jeep passenger
        raise rules.Violation(
            f"{ctx.target_name} is on board the {ctx.recipient['on_board']}: no cover marker [10.8.1]"
        )
    b = options.text_opt(ctx.o, "--area", "--area=<cover-id|open>")
    if (
        not b
        and ctx.action_id == "4.2.2g"
        and contact.engineers_clear(s, ctx.recipient)
        and contact.mines_on(s, ctx.recipient["card"])
    ):
        b = ctx.recipient.get("area", "open")  # [Normandy CSR 10] engineers clearing mines need no destination
    if not b:
        raise rules.Violation("Specify --area=<cover-id|open>")
    if ctx.action_id == "4.2.2g" and fire.vof_against(s, ctx.recipient["card"], ctx.recipient["side"]) is None:
        raise rules.Violation("Infiltrate within a Card requires a VOF on the card [RULE 4.2.2g p.23]")
    if ctx.action_id == "4.2.2g" and (
        ctx.recipient.get("tripod") or ctx.recipient.get("vof_rating") == "H" or state.is_mortar(ctx.recipient)
    ):
        raise rules.Violation(
            f"{ctx.target_name} (tripod/H VOF) may not infiltrate, also not within the card [RULE 5.1.4 p.32]"
        )
    if ctx.action_id == "4.2.2g" and rules.EXPOSED in ctx.recipient["status"]:
        raise rules.Violation(f"{ctx.target_name} is Exposed and may not infiltrate [RULE 5.1.4 p.32]")
    if ctx.recipient.get("mine_hit"):
        raise rules.Violation(
            f"{ctx.target_name} is under the Mine marker and may not move this turn [RULE 7.9.1 p.54]"
        )
    if b != "open" and not any(c["id"] == b for c in ctx.recipient_card.get("cover", [])):
        raise rules.Violation(f"No cover marker {b} on {ctx.recipient['card']}")
    return b


def _offer_infiltrate_within(s, ctx, old_cv, b):
    """A Move within a Card where an Infiltrate within the Card is possible is never better (a failed attempt is the
    same Move): refuse and name 4.2.2g, as 4.2.2a does for 4.2.2c."""
    e = ctx.recipient
    new_type = next((c["type"] for c in ctx.recipient_card.get("cover", []) if c["id"] == b), None)
    if old_cv and old_cv["type"] in rules.FIXED_COVER and new_type in rules.FIXED_COVER:
        return  # no Exposed marker anyway [RULE 5.1.1 p.31]
    if (
        fire.vof_against(s, e["card"], e["side"]) is None
        or e.get("tripod")
        or e.get("vof_rating") == "H"
        or state.is_mortar(e)
        or e.get("vehicle")
    ):
        return
    try:
        comms.action_allowed(e, ctx.target_name, "4.2.2g")
    except rules.Violation:
        return
    raise rules.Violation(
        f"{ctx.target_name} could infiltrate within {e['card']} (VOF on the card) [RULE 4.2.2g p.23]: "
        "order 4.2.2g with --success=yes|no (2 cards, Infiltrate icon), or --plain=yes for an intended Move; nothing booked"
    )


def _order_move_within_card(s, ctx):
    """Order handler for: action_id in ('4.2.2f', '4.2.2g')"""
    b = _check_move_within_card(s, ctx)
    old_cv = fire.cover_of(s, ctx.recipient)
    if ctx.action_id == "4.2.2f" and ctx.o.get("--plain") not in (True, *YES_WORDS):
        _offer_infiltrate_within(s, ctx, old_cv, b)
    grenades.grenade_expires(s, ctx.recipient, ctx.target_name, ctx.prot)
    set_area(s, ctx.recipient, b)
    new_cv = fire.cover_of(s, ctx.recipient)
    fixed = bool(old_cv and new_cv and old_cv["type"] in rules.FIXED_COVER and new_cv["type"] in rules.FIXED_COVER)
    engineer = (
        ctx.action_id == "4.2.2g"
        and contact.engineers_clear(s, ctx.recipient)
        and bool(contact.mines_on(s, ctx.recipient["card"]))
    )
    if (ctx.action_id == "4.2.2f" or ctx.success == "no") and not fixed and not engineer:
        mark(ctx.recipient, rules.EXPOSED)
    if fixed:
        ctx.prot.append("between Trench/Bunker/Pillbox markers of the same card without Exposed [RULE 5.1.1 p.31]")
    ctx.prot.append(
        f"{ctx.target_name} to {'open' if b == 'open' else b} on {ctx.recipient['card']}"
        + (", Exposed" if rules.EXPOSED in ctx.recipient["status"] else ", not Exposed")
    )
    if state.is_mortar(ctx.recipient) and fire.is_firing(ctx.recipient) is False and ctx.recipient.get("target"):
        ctx.prot.append(
            f"{ctx.target_name} (mortar) is Exposed and does not fire, VOF is removed until Exposed is removed [RULE 7.3.1 p.53]"
        )
    if state.is_campaign(s):
        if engineer:
            contact.request_mine_check(
                s,
                [ctx.target_name],
                ctx.recipient["card"],
                ctx.prot,
                "Engineers clear a path"
                + (
                    " (infiltration succeeded)"
                    if ctx.success == "yes"
                    else " (infiltration failed: not Exposed, no path)"
                ),
                cards=1 if ctx.success == "yes" else 3,
                path_=ctx.success == "yes",
            )
        else:
            contact.request_mine_check(
                s, [ctx.target_name], ctx.recipient["card"], ctx.prot, "move within the mined card"
            )


def _check_rally(s, ctx):
    if not state.pinned(ctx.recipient):
        raise rules.Violation(f"{ctx.target_name} is not Pinned [RULE 4.2.3a p.24]")


def _order_rally(s, ctx):
    """Order handler for: action_id == '4.2.3a'"""
    _check_rally(s, ctx)
    if fire.vof_against(s, ctx.recipient["card"], ctx.recipient["side"]) is None or ctx.success == "yes":
        ctx.recipient["status"].remove(rules.PINNED)
        ctx.prot.append(
            f"{ctx.target_name}: remove Pinned marker"
            + ("" if ctx.success == "yes" else " (automatic, no VOF)")
            + (", VOF back to Basic" if fire.is_firing(ctx.recipient) else "")
            + " [6.5.1]"
        )
        s["last_attempt"] = None
    else:
        ctx.prot.append(f"{ctx.target_name}: Rally failed")
        s["last_attempt"] = [ctx.target_name, ctx.action_id, s["phase"]]


def _check_convert_team(s, ctx):
    from_ = {"4.2.3b": "Paralyzed Team", "4.2.3c": "Litter Team", "4.2.3d": "Fire Team"}[ctx.action_id]
    if ctx.recipient["type"] != from_ or state.pinned(ctx.recipient):
        raise rules.Violation(f"{ctx.target_name} must be an Unpinned {from_} [RULE {ctx.rule}]")


def _order_convert_team(s, ctx):
    """Order handler for: action_id in ('4.2.3b', '4.2.3c', '4.2.3d')"""
    to_ = {"4.2.3b": "Litter Team", "4.2.3c": "Fire Team", "4.2.3d": "Assault Team"}[ctx.action_id]
    _check_convert_team(s, ctx)
    if fire.vof_against(s, ctx.recipient["card"], ctx.recipient["side"]) is None or ctx.success == "yes":
        ctx.recipient["type"] = to_
        ctx.recipient["experience"] = rules.LAT_EXPERIENCE[to_]
        combat.set_lat_values(ctx.recipient, to_)
        ctx.prot.append(
            f"{ctx.target_name} becomes {to_} (swap counter)"
            + ("" if ctx.success == "yes" else ", automatic without VOF")
            + " [6.5.1]"
        )
    else:
        ctx.prot.append(f"{ctx.target_name}: conversion failed")
        s["last_attempt"] = [ctx.target_name, ctx.action_id, s["phase"]]


def _order_assault_to_fire_team(s, ctx):
    """Order handler for: action_id == '4.2.3e'"""
    if ctx.recipient["type"] != "Assault Team" or state.pinned(ctx.recipient):
        raise rules.Violation("Only an Unpinned Assault Team [RULE 4.2.3e p.24]")
    ctx.recipient["type"], ctx.recipient["experience"] = "Fire Team", "Green"
    combat.set_lat_values(ctx.recipient, "Fire Team")
    ctx.prot.append(f"{ctx.target_name} becomes Fire Team")


def _check_flip_to_front(s, ctx):
    if not state.fire_team_side(ctx.recipient) or state.pinned(ctx.recipient):
        raise rules.Violation(f"{ctx.target_name} must be Unpinned on its Fire Team side [RULE 4.2.3f p.24]")
    m = combat.ammo(ctx.recipient)
    if ctx.recipient.get("ooa_flip") and m and not m.get("points") and ctx.o.get("--ooa-flip") != "yes":
        # [open U45] on the Fire Team side only because Out of Ammo (7.18.2): the front side would have no ammo;
        # resupply (7.18.3) undoes the flip. Allowed only on purpose with --ooa-flip=yes.
        raise rules.Violation(
            f"{ctx.target_name} is on its Fire Team side only because it is Out of Ammo (7.18.2); resupply it (7.18.3) "
            f"instead, the front side would have 0 ammo. Deliberately anyway: --ooa-flip=yes [open U45]"
        )


def _order_flip_to_front(s, ctx):
    """Order handler for: action_id == '4.2.3f'"""
    _check_flip_to_front(s, ctx)
    if fire.vof_against(s, ctx.recipient["card"], ctx.recipient["side"]) is None or ctx.success == "yes":
        ctx.recipient["status"].remove(rules.FIRE_TEAM_SIDE)
        ctx.recipient.pop("ooa_flip", None)  # a later flip is HIT-caused; resupply must not undo it
        ctx.recipient.pop("ooa_fallback", None)
        ctx.prot.append(
            f"Flip {ctx.target_name} to its front side (experience back to {ctx.recipient.get('experience', 'Line')}) [6.5.1]"
        )
    else:
        ctx.prot.append(f"{ctx.target_name}: Flip failed")
        s["last_attempt"] = [ctx.target_name, ctx.action_id, s["phase"]]


def upper_story_type(card):
    """[RULE 5.2.2B p.36]: 'Church Tower' on a Church card (also 'Church on 1 Hill', OP icon), 'Upper Story' on a
    Multi-Story card, otherwise None."""
    base = (card.get("terrain") or "").split(" on ")[0]
    if base == "Church" or card.get("op"):
        return "Church Tower"
    if card.get("multistory"):
        return "Upper Story"
    return None


def _order_detach_team(s, ctx):
    """Order handler for: action_id == '4.2.3g'"""
    if not state.good_order(ctx.recipient) or not (
        (ctx.recipient["type"] == "Squad" and state.steps(ctx.recipient) >= 3)
        or (ctx.recipient["type"] == "Weapons Team" and state.steps(ctx.recipient) == 2)
    ):
        raise rules.Violation("Detach Team: Good Order squad with 3-4 steps or 2-step Weapons Team [RULE 4.2.3g p.24]")
    team = team_option(ctx.o, "Assault") + " Team"
    ctx.recipient["steps"] = state.steps(ctx.recipient) - 1
    new = new_name(s, team, side=ctx.recipient["side"], card=ctx.recipient["card"])
    s["units"][new] = combat.new_lat(ctx.recipient, team, ctx.target_name)
    # (replaces E103) [Stead BGG 3493975, 3727147, 2nd printing] the detached team is placed without an Exposed
    # marker; the squad stays Exposed
    s["units"][new]["status"] = []
    exposed = rules.EXPOSED in ctx.recipient["status"]
    ctx.prot.append(
        f"{ctx.target_name} down to {ctx.recipient['steps']} steps, place {new} on {ctx.recipient['card']}"
        + (" (not Exposed; the squad stays Exposed, Stead BGG 3727147)" if exposed else "")
    )


def _order_supplement_squad(s, ctx):
    """Order handler for: action_id == '4.2.3h'"""
    sq = ctx.o.get("--squad")
    if not sq:
        raise rules.Violation("Specify --squad=<squad with 2-3 steps>")
    q = state.unit(s, sq)
    if (
        ctx.recipient["type"] not in ("Fire Team", "Assault Team")
        or state.pinned(ctx.recipient)
        or q["type"] != "Squad"
        or not state.good_order(q)
        or not (2 <= state.steps(q) <= 3)
        or q["card"] != ctx.recipient["card"]
    ):
        raise rules.Violation(
            "Supplement: Unpinned Fire/Assault Team plus Good Order squad with 2-3 steps on the same card [RULE 4.2.3h p.24]"
        )
    q["steps"] = state.steps(q) + 1
    # the team leaves play through remove_from_play (radio to the squad, Casualties/Assets onto the card)
    combat.remove_from_play(s, ctx.target_name, ctx.prot, f"joins {sq} [4.2.3h p.24]", successor=sq)
    ctx.prot.append(f"{sq} up to {q['steps']} steps (check experience on the Multi-Step Chart)")


def _check_reconstitute_squad(s, ctx):
    """State-only legality of 4.2.3i, also before the draw; returns (teams, squad, experience)."""
    teams = [ctx.target_name] + options.list_option(ctx.o, "--with")  # a bare --with is a Violation
    if len(set(teams)) != len(teams):
        raise rules.Violation(
            f"A team is named twice ({', '.join(teams)}); --with lists the further teams [RULE 4.2.3i p.24]"
        )
    sq = options.text_opt(ctx.o, "--squad")
    if not sq or sq not in s.get("removed_from_play", []):
        raise rules.Violation(
            "Specify --squad=<Removed from Play squad> and --with=<further teams, comma-separated> [RULE 4.2.3i p.24]"
        )
    for t in teams:
        lat = state.unit(s, t)
        if (
            lat["type"] not in ("Fire Team", "Assault Team")
            or state.pinned(lat)
            or lat["card"] != ctx.recipient["card"]
        ):
            raise rules.Violation(f"{t}: only Unpinned Fire/Assault Teams on the same card [RULE 4.2.3i p.24]")
    most = min(4, s.get("setup_units", {}).get(sq, {}).get("steps", 4))
    if not 2 <= len(teams) <= most:
        raise rules.Violation(
            f"2 to {most} teams ({sq} has {most} steps: 'a previously removed squad with the same number of steps') [RULE 4.2.3i p.24, 6.5.2 p.49]"
        )
    if ctx.o.get("--experience"):
        level = rules.experience_value(ctx.o["--experience"], "--experience")
    else:  # [RULE 6.5.2 p.49] 'Line for Assault Teams, Green for all others' and table 12.6
        level = campaign.experience_from_steps([rules.LAT_EXPERIENCE[s["units"][t]["type"]] for t in teams]) or "Green"
    return teams, sq, level


def _order_reconstitute_squad(s, ctx):
    """Order handler for: action_id == '4.2.3i'"""
    teams, sq, level = _check_reconstitute_squad(s, ctx)
    if ctx.success == "yes":
        s["removed_from_play"].remove(sq)
        # the squad comes back as its own counter (VOF, range, platoon as set up): never more firepower than it
        # started with [RULE 6.5.2 p.49]; a game without the setup record falls back to a plain rifle squad
        orig = copy.deepcopy(s.get("setup_units", {}).get(sq)) or {
            "type": "Squad",
            "side": "US",
            "platoon": ctx.recipient.get("platoon"),
            "vof_rating": "S",
            "range": "L",
            "last_step": "Fire Team",
        }
        for k in ("assets", "radio", "ammo", "skills", "grenade", "concentrated"):
            orig.pop(k, None)  # what the squad carried is gone with it
        s["units"][sq] = {
            **orig,
            "experience": level,
            "card": ctx.recipient["card"],
            "area": ctx.recipient["area"],
            "status": [],
            "steps": len(teams),
            "target": None,
        }
        for t in teams:  # the teams leave play through remove_from_play, the squad is their successor
            combat.remove_from_play(s, t, ctx.prot, f"reconstituted into {sq} [4.2.3i p.24]", successor=sq)
        ctx.prot.append(
            f"{sq} back in play with {len(teams)} steps; experience per Multi-Step Unit Experience Chart from the teams (Assault Line, others Green), here {level} [6.5.2]"
        )
        fire.open_fire(s, ctx.prot, only=[sq])
    else:
        ctx.prot.append("Reconstitute failed")
        s["last_attempt"] = [ctx.target_name, ctx.action_id, s["phase"]]


def _order_4_2_3j(s, ctx):
    """Order handler for: action_id == '4.2.3j'"""
    if not ctx.recipient.get("fire_team_side") or state.fire_team_side(ctx.recipient):
        raise rules.Violation("Only units with a named Fire Team side [RULE 4.2.3j p.24]")
    mark(ctx.recipient, rules.FIRE_TEAM_SIDE)
    ctx.prot.append(f"Flip {ctx.target_name} to its Fire Team side")


def _order_spot(s, ctx):
    """Order handler for: action_id == '4.2.4a'"""
    target_k = ctx.o["--target"]
    if ctx.success == "yes":
        for m in state.units_on(s, target_k, "Enemy"):
            s["units"][m]["spotted"] = True
        ctx.prot.append(f"Enemies on {target_k} Spotted: remove Unspotted markers [8.5]")
        fire.open_fire(s, ctx.prot)
        s["last_attempt"] = None
    else:
        ctx.prot.append("Spotting failed")
        s["last_attempt"] = [ctx.target_name, ctx.action_id, s["phase"]]


def _order_concentrate_fire(s, ctx):
    """Order handler for: action_id == '4.2.4b'"""
    if not fire.is_firing(ctx.recipient):
        raise rules.Violation(f"{ctx.target_name} is not firing [RULE 4.2.4b p.25]")
    target_card = fire.effective_fire_target(s, ctx.target_name)
    if not spotted_enemies(s, target_card):
        raise rules.Violation(f"No Spotted enemy on {target_card} [RULE 4.2.4b p.25]")
    if ctx.o.get("--jam") == "yes" and grenades.jam_prone(ctx.recipient):
        grenades.jam(s, ctx.target_name, ctx.prot)
        ctx.success = "no"
    elif ctx.success == "yes":
        target_unit_name = named_target(s, target_card, ctx.o.get("--unit"))
        if not target_unit_name:
            raise rules.Violation(
                f"Specify --unit=<target enemy> (stack under a cover marker or random unit without cover on {target_card})"
            )
        cf_target_check(s, target_card, target_unit_name, ctx.recipient)  # [RULE 7.11.1 p.56], LOS to the unit
        cf_before = fire.cf_counts(s, target_card)
        for _m in enemy.cf_stack(s, target_unit_name):
            s["units"][_m]["cf"] = s["units"][_m].get("cf", 0) + 1
        ctx.prot.append(  # the text names the 1 ammo that is booked below
            f"Concentrated Fire marker on {target_unit_name} (stack: {', '.join(enemy.cf_stack(s, target_unit_name))}; -1 NCM, cumulative; 1 ammo with ammo tracking) [7.11]"
        )
        cf_critical(s, target_unit_name, ctx.o, ctx.prot)  # [RULE 7.11.4 p.56]
        fire.track_concentrated(s, ctx.recipient, cf_before)
        if combat.fire_ammo(ctx.recipient):  # no rockets for Concentrate Fire
            combat.ammo_use(
                s, ctx.target_name, ctx.recipient, 1, "successful Concentrate Fire", ctx.prot
            )  # [RULE 7.11.3 p.56]
    else:
        ctx.prot.append("Concentrate Fire failed")
        s["last_attempt"] = [ctx.target_name, ctx.action_id, s["phase"]]


def cf_critical(s, target_unit_name, o, prot):
    """[RULE 7.11.4 p.56] two or more Crosshairs: under cover the stack loses the cover benefit in the NCM (Critical Hit
    Concentrated Fire marker), out of cover a second Concentrated Fire marker."""
    if o.get("--critical") != "yes":
        return
    f = state.unit(s, target_unit_name)
    if f.get("area", "open") != "open":
        for m in enemy.cf_stack(s, target_unit_name):
            s["units"][m]["cf_critical"] = True
        prot.append(
            f"Critical Hit: place the Critical Hit Concentrated Fire marker on {target_unit_name} (stack {f['area']}): no cover benefit in Combat Effects [7.11.4 p.56]"
        )
    else:
        f["cf"] = f.get("cf", 0) + 1
        prot.append(f"Critical Hit: a second Concentrated Fire marker on {target_unit_name} (both count) [7.11.4 p.56]")


def target_unit_check(s, target_card, target_unit_name, what, rule, side="Enemy"):
    """the named target unit is an opposing, Spotted unit on the target card (Concentrate Fire and
    Grenade Attack alike). Returns the unit."""
    f = state.unit(s, target_unit_name)
    if f["side"] != side or f["card"] != target_card:
        raise rules.Violation(
            f"{target_unit_name} is not an opposing unit on the target card {target_card} [RULE {rule}]"
        )
    if not state.is_visible(f):
        raise rules.Violation(f"{target_unit_name} is Unspotted: {what} only on Spotted units [RULE {rule}]")
    return f


def cf_target_check(s, target_card, target_unit_name, firer=None, side="Enemy"):
    """[RULE 7.11.1 p.56] Concentrate Fire target: a stack of Spotted units under a Cover marker on the target card or
    a random Spotted unit out of cover (R# among the units out of cover). [RULE 5.2.2 p.35 Fig 3]: the firing unit
    needs LOS to that unit (Upper Story counts for the target), not only to the card."""
    f = target_unit_check(s, target_card, target_unit_name, "Concentrate Fire", "7.11.1 p.56", side)
    if firer is not None and firer["card"] != target_card:
        ok, why = geometry.los(
            s, firer["card"], target_card, ha=geometry.height_bonus(s, firer), hb=geometry.height_bonus(s, f)
        )
        if not ok:
            raise rules.Violation(
                f"No LOS to {target_unit_name} itself ({why}); only units in LOS can be targeted (e.g. in the Upper Story) [RULE 5.2.2 p.35 Fig 3]"
            )
    if f.get("area", "open") == "open":
        # the units of the targeted side (side="US" for an enemy Concentrate Fire)
        open_ = [
            m
            for m in state.units_on(s, target_card, side)
            if s["units"][m].get("area", "open") == "open" and state.is_visible(s["units"][m])
        ]
        if len(open_) > 1:
            s.setdefault("_hints", []).append(
                f"Concentrate Fire out of cover on {target_card}: random target among {', '.join(open_)} (R# column {len(open_)}); {target_unit_name} booked [7.11.1]"
            )


def _platoon_fire_candidates(s, ctx, single):
    """Unpinned units of the platoon on the HQ's card that can make the single action now: (names, skip notes)."""
    candidate, skipped = [], []
    for n, e in s["units"].items():
        if e["side"] != "US" or e["card"] != ctx.orig["card"] or state.pinned(e):
            continue
        if not ctx.late_order and single in s["impulse_actions"].get(n, []):
            skipped.append(f"{n}: already made its {rules.ACTIONS[single][0]} in this impulse [4.2 p.21]")
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
            target_card = fire.effective_fire_target(s, n)
            if not spotted_enemies(s, target_card):
                continue
        else:
            try:
                grenades.check_grenade(s, e, n, ctx.o)
            except rules.Violation as ex:
                skipped.append(f"{n}: {ex}")
                continue
        candidate.append(n)
    return candidate, skipped


def _platoon_fire_prompt(s, ctx, single, candidate, skipped):
    """The draw instruction of a Platoon Fire: cards per unit, success symbol, Jam and Critical Hit watches."""
    word = "Crosshairs" if single == "4.2.4b" else "Grenade symbol (2 or more: Critical Hit, --critical=<units>)"
    lines = []
    for n in candidate:
        n_cards, who, base = comms.card_count(s, single, ctx.orig, s["units"][n], 0, None)
        lines.append(
            f"{n} {n_cards} cards ({comms.experience(who)}{', tripod +1' if n_cards > base + {'Green': -1, 'Veteran': 1}.get(comms.experience(who), 0) else ''})"
        )
    ranged_any = single == "4.2.4d" and ctx.o.get("--target", ctx.orig["card"]) != ctx.orig["card"]
    # [RULE 7.12 p.56] only jam-prone units
    watches = [n for n in candidate if grenades.jam_prone(s["units"][n]) and (single == "4.2.4b" or ranged_any)]
    return rules.Violation(
        f"{rules.ACTIONS[ctx.action_id][0]}: each unit draws itself, success on {word}: "
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


def _order_platoon_fire(s, ctx):
    """Order handler for: action_id in ('4.2.4c', '4.2.4h') [RULE 4.2.4c/h p.25]: every eligible unit of the platoon on the HQ's
    card makes its own attempt (4.2.4b Concentrate Fire with S/A/A-S/H VOF on a card with Spotted enemies, or 4.2.4d
    Grenade Attack) on the chosen target; one draw per unit. --unit=<target> (all) or --unit=<attacker>:<target>,..
    (7.11.1 note: new random target per attempt out of cover); --success=<attacker>:yes|no,..; grenade: --critical=<attackers>,
    --jam=<attackers>, --target=<card> for G! units."""
    single = "4.2.4b" if ctx.action_id == "4.2.4c" else "4.2.4d"
    ctx.also_book = single  # every attacker is booked with the single action too
    result = parse_per_unit(ctx.success)
    targets, common = {}, None
    for t in (text_opt(ctx.o, "--unit") or "").split(","):
        if ":" in t:
            a, b = t.split(":", 1)
            targets[a.strip()] = b.strip()
        elif t.strip():
            common = t.strip()
    candidate, skipped = _platoon_fire_candidates(s, ctx, single)
    if not candidate:
        raise rules.Violation(
            f"No eligible unit of the platoon on {ctx.orig['card']} for {rules.ACTIONS[ctx.action_id][0]}"
            + ("; " + "; ".join(skipped) if skipped else "")
            + f" [RULE {ctx.rule}]"
        )
    if any(n not in result for n in candidate):
        raise _platoon_fire_prompt(s, ctx, single, candidate, skipped)
    crit = [x.strip() for x in (text_opt(ctx.o, "--critical") or "").split(",") if x.strip()]
    jammed = [x.strip() for x in (text_opt(ctx.o, "--jam") or "").split(",") if x.strip()]
    for n in candidate:
        e = s["units"][n]
        o2 = dict(ctx.o)
        o2.pop("--success", None)
        tgt = targets.get(n, common)
        if tgt:
            o2["--unit"] = tgt
        else:
            o2.pop("--unit", None)
        o2["--critical"] = "yes" if n in crit else "no"
        o2["--jam"] = "yes" if n in jammed else "no"
        # shallow copy: prot (and the other lists) stay shared with ctx, so the handler's lines land in this order
        ctx2 = dataclasses.replace(ctx, action_id=single, target_name=n, recipient=e, o=o2, success=result[n])
        ctx.prot.append(f"{n} ({'success' if ctx2.success == 'yes' else 'no success'}):")
        if single == "4.2.4b":
            _order_concentrate_fire(s, ctx2)
        else:
            grenades.order_grenade_attack(s, ctx2)
    for line in skipped:
        ctx.prot.append("skipped " + line)
    ctx.moved = candidate


def _order_4_2_1l(s, ctx):
    """Order handler for: action_id == '4.2.1l'"""
    old = s.get("ccp")
    s["ccp"] = ctx.recipient["card"]
    ctx.prot.append(
        f"Casualty Collection Point on {ctx.recipient['card']}"
        + (f" (previously {old}, only one CCP at a time)" if old and old != ctx.recipient["card"] else "")
        + "; Casualties lying there at the end of the turn are evacuated in Clean Up [RULE 5.1.7 p.33/34, FM1 p.42]"
    )


def _order_cease_fire(s, ctx):
    """Order handler for: action_id == '4.2.4k'"""
    card_id = ctx.recipient["card"]
    # [RULE 4.2.4k Action Menu: 'Remove the VOF/PDF generated by all occupants of the card ... passed on and carried
    # out by all units on the card whether they are in communication or not']: the Recipient itself need not be firing
    if not any(e["side"] == "US" and e["card"] == card_id and fire.is_firing(e) for e in s["units"].values()):
        raise rules.Violation(f"No friendly unit on {card_id} is firing [RULE 4.2.4k p.26]")
    # [RULE 4.3.1 p.27 note] "the order will be passed on to all occupants of a card (including Pinned units)" (K21)
    stopped = []
    for n, e in s["units"].items():
        if e["side"] == "US" and e["card"] == card_id and fire.is_firing(e):
            stopped.append(f"{n} (at {fire.effective_fire_target(s, n)})")
            fire.cease_fire(e)
    ctx.prot.append(
        f"Cease Fire: all firing units on {card_id} cease fire: {', '.join(stopped)}; they reopen fire immediately when a Spotted enemy is in LOS and range [4.3.1 p.27, 6.3.3]"
    )
    fire.open_fire(s, ctx.prot)


def _order_shift_fire(s, ctx):
    """Order handler for: action_id == '4.2.4l'"""
    target_card = ctx.o.get("--target")
    card_id = ctx.recipient["card"]
    # like Cease Fire the order is passed on to all occupants of the card; the Recipient itself need not fire
    if not target_card or not any(
        e["side"] == "US" and e["card"] == card_id and fire.is_firing(e) for e in s["units"].values()
    ):
        raise rules.Violation(
            f"Shift Fire: --target=<card in LOS>, a friendly unit on {card_id} must be firing [RULE 4.2.4l p.26]"
        )
    state.card(s, target_card)
    if unspotted_enemies(s, target_card) and not state.units_on(s, target_card, "US"):
        raise rules.Violation("Cards with Unspotted enemies may not be fired at [6.3.3]")
    ok, reason = geometry.los(
        s,
        ctx.orig["card"],
        target_card,
        ha=geometry.height_bonus(s, ctx.orig),
        hb=geometry.card_height_bonus(s, target_card, "Enemy"),
    )
    if not ok:
        raise rules.Violation(f"Originator has no LOS to {target_card}: {reason}")
    # the PDF situation before the shift, so the board instruction names the marker that turns
    firing_before = {
        n: e["target"]
        for n, e in s["units"].items()
        if e["side"] == "US" and e["card"] == card_id and fire.is_firing(e)
    }
    ceased = []
    for n, e in s["units"].items():
        if e["side"] == "US" and e["card"] == card_id and fire.is_firing(e):  # passed on to all occupants [4.3.1 p.27]
            los_ok, los_reason = geometry.los(
                s,
                card_id,
                target_card,
                ha=geometry.height_bonus(s, e),
                hb=geometry.card_height_bonus(s, target_card, "Enemy"),
            )
            if not geometry.in_range(s, e, target_card) or not los_ok:
                # [RULE 6.1.2 p.39] the firing unit itself needs LOS and range to the new card; otherwise it ceases fire
                fire.cease_fire(e)
                ceased.append(n)
                ctx.prot.append(
                    f"{n}: no {'range' if los_ok else 'LOS'} to {target_card} ({'out of range' if los_ok else los_reason}), ceases fire instead [6.1.2]"
                )
                continue
            e["target"] = target_card
            e.pop("concentrated", None)
    if ceased:
        # [RULE 6.1.1 p.39, 6.3.5 p.44] a unit that cannot fire along the new PDF opens fire at once on an enemy it
        # can target, which places a second PDF
        fire.open_fire(s, ctx.prot, only=ceased)
    already = sorted(n for n, fired_at in firing_before.items() if fired_at == target_card)
    if already:
        how = f"PDF marker {card_id} to {target_card} already lies there from {', '.join(already)}"
    else:  # the old marker is handled by the board summary (removed, or back to a single arrow if it was mutual)
        how = f"place a new PDF marker {card_id} to {target_card}"
    others = sorted(
        {
            x["target"]
            for x in s["units"].values()
            if x.get("card") == card_id
            and x.get("target")
            and x["target"] not in (card_id, target_card)
            and fire.is_firing(x)
        }
    )
    ctx.prot.append(
        f"Shift Fire: units on {card_id} now fire at {target_card}: {how}"
        + (f"; further PDF from {card_id}: to {', '.join(others)}" if others else f"; no other PDF from {card_id}")
        + " [6.3.3]"
    )


def _order_4_2_1b(s, ctx):
    """Order handler for: action_id == '4.2.1b'"""
    last = s.get("last_attempt")
    if not last or last[0] != ctx.target_name or last[2] != s["phase"]:
        raise rules.Violation("Exhort only for a unit that has just failed an attempt [RULE 4.2.1b p.22]")
    if ctx.success not in ("yes", "no"):
        raise rules.Violation("Exhort: draw one more Action card; --success=yes|no (symbol of the original attempt)")
    s["last_attempt"] = None
    if ctx.success == "yes":
        s["exhort_free"] = [ctx.target_name, last[1], s["phase"]]  # [RULE 4.2.1b p.22] 'Draw one more Action card'
    ctx.prot.append(
        f"Exhort for {ctx.target_name} ({last[1]}): "
        + (
            "attempt counts as successful; now enter the effect with the original order and --success=yes (costs no Command, add --free=yes)"
            if ctx.success == "yes"
            else "again no success"
        )
    )


def _order_4_2_1c(s, ctx):
    """Order handler for: action_id == '4.2.1c'"""
    if state.is_campaign(s):
        pyro.execute_pyro(s, ctx.recipient, ctx.target_name, ctx.o, ctx.prot)
    else:
        ctx.prot.append(f"{ctx.target_name} uses pyrotechnics (effect per Mission Log) [4.4]")


def _order_4_2_1d(s, ctx):
    """Order handler for: action_id == '4.2.1d'"""
    hq_n = ctx.o.get("--hq")
    if not hq_n or hq_n not in s.get("removed_from_play", []):
        raise rules.Violation("Specify --hq=<Removed from Play PLT HQ> [RULE 4.2.1d p.22]")
    if s.get("rfp_data", {}).get(hq_n, {}).get("level", "PLT") != "PLT":
        raise rules.Violation(
            f"{hq_n} is not a PLT HQ; the CO HQ is reconstituted by the BN HQ: fof.py order BN <unit> 4.2.1e [RULE 6.5.2 p.50]"
        )
    target_platoon = s.get("rfp_data", {}).get(hq_n, {}).get("platoon")
    if hq_n not in s.get("rfp_data", {}):
        target_platoon = ctx.recipient.get("platoon")
        ctx.prot.append(
            f"Platoon of {hq_n} not stored (game state before v3), check the platoon of {ctx.target_name} on the board"
        )
    if not state.good_order(ctx.recipient) or not (
        ctx.recipient["type"] == "Staff" or (target_platoon and ctx.recipient.get("platoon") == target_platoon)
    ):
        raise rules.Violation(f"Recipient: CO Staff or a Good Order step of platoon {target_platoon} [RULE 6.5.2 p.49]")
    hq_back(s, hq_n, ctx.recipient, ctx.prot)
    hand_over_step(s, ctx.target_name, ctx.prot, team_option(ctx.o, "Fire"))


def _order_4_2_1e(s, ctx):
    """Order handler for: action_id == '4.2.1e'"""
    # [Action Menu 4.2.1e] originator 'BN HQ or CO Staff'; the BN HQ off-map orders it with 'order BN <unit> 4.2.1e'
    reconstitute_co_hq(s, ctx.target_name, ctx.prot)


def _order_4_2_1i(s, ctx):
    """[RULE 4.2.1i p.22, 10.4 p.72] Activate for AT Combat & Vehicle Movement."""
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
    "4.2.1i": _order_4_2_1i,
    "4.2.4k": _order_cease_fire,
    "4.2.4l": _order_shift_fire,
    "4.2.1b": _order_4_2_1b,
    "4.2.1c": _order_4_2_1c,
    "4.2.1d": _order_4_2_1d,
    "4.2.1e": _order_4_2_1e,
}


ATTEMPT_WORD = {"yes": "successful", "no": "failed"}  # internal yes/no, English output
ORIGINATOR_WORD = {
    "PLT": "a PLT HQ",
    "CO_BN": "the CO HQ or BN HQ",
    "CO_ONLY": "the CO HQ",
    "BN_STAFF": "the BN HQ or a CO Staff",
}
ORIGINATOR_KINDS = tuple(ORIGINATOR_WORD)


def originator_eligible(orig, originator_kind):
    """[RULE 4.2 Action Menu] originator column: PLT (a PLT HQ), CO_BN (CO HQ or BN HQ), CO_ONLY (the CO HQ)."""
    if originator_kind == "PLT":
        return orig["type"] == "HQ" and orig.get("level") == "PLT"
    if originator_kind == "CO_BN":
        return orig.get("level") in ("CO", "BN")
    if originator_kind == "BN_STAFF":
        return orig.get("level") == "BN" or orig["type"] == "Staff"
    if originator_kind == "CO_ONLY":
        return orig.get("level") == "CO" and orig["type"] == "HQ"
    return True


def check_stacking(s, recipient, action_id, o, orig_name, orig):
    """[RULE 5.1.5 p.32]: 16 steps of infantry per card; vehicles count separately (at most 4), their crews are no
    steps here. Returns the members of a Platoon Move (None for other actions) so the handler uses the same set."""
    candidates = None
    if action_id in ("4.2.2b", "4.2.2d"):
        candidates = platoon_move_members(s, orig_name, orig, action_id)
    target = o.get("--target")
    if action_id not in ("4.2.2a", "4.2.2b", "4.2.2c", "4.2.2d") or not target or target not in s["cards"]:
        return candidates
    if s["cards"][target].get("staging"):
        return candidates
    members = [recipient] if candidates is None else [s["units"][n] for n in candidates]
    st = sum(
        state.steps(e)
        for e in s["units"].values()
        if e["side"] == "US" and e["card"] == target and e["type"] != "Casualty" and not e.get("vehicle")
    ) + sum(state.steps(e) for e in members if not e.get("vehicle"))
    if st > 16:
        raise rules.Violation(f"Stacking: {target} would have {st} US steps, at most 16 per card [RULE 5.1.5 p.32]")
    return candidates


def attempt_text(success):
    """English attempt text, also for per-unit lists 'A:yes,B:no' (Platoon Infiltrate)."""
    if ":" not in success:
        return ATTEMPT_WORD.get(success, success)
    return ", ".join(f"{a} {ATTEMPT_WORD[b]}" for a, b in parse_per_unit(success).items())  # also yes/no


def cmd_order(s, args, late_order=None):
    """4.2: one order. lateorder=<HQ>: late order for an HQ whose impulse already ended this turn.
    Contract: everything that can refuse the order runs before the draw prompt (resolve_originator,
    check_stacking, check_repeat_and_budget, apply_skill, pre_draw_checks); the prompt is the last Violation before
    the handler, so the player never draws cards for an order that is refused afterwards (M8)."""
    rules.need(args, 3, "order <hq|GI|BN> <unit> <action id> [--target=K] [--success=yes|no] ...")
    hq_name, target_name, action_id = args[0], args[1], args[2]
    o = options.parse_opts(args[3:])
    if hq_name == "BN":
        return order_bn(s, target_name, action_id)
    s["_order_opts"] = o
    if state.is_campaign(s):
        contact.mine_lock(s)
        if action_id in ("4.2.1g", "4.2.1h") and target_name in s.get("runner_box", []):
            return order_runner_box(s, hq_name, target_name, action_id, o)
    ctx = order_context(s, hq_name, target_name, action_id, o, late_order)
    resolve_originator(s, ctx)
    ctx.candidates = check_stacking(s, ctx.recipient, action_id, o, ctx.orig_name, ctx.orig)
    check_recipient(s, ctx)
    check_repeat_and_budget(s, ctx)
    apply_skill(s, ctx)
    pre_draw_checks(s, ctx)
    handler = ORDER_HANDLERS.get(action_id)
    if handler:
        handler(s, ctx)
    elif not order_comms_action(s, target_name, action_id, o, ctx.orig, ctx.prot):
        raise rules.order_not_implemented(action_id)
    book_order(s, ctx)


@dataclasses.dataclass
class OrderCtx:
    """The working record of one order (a dataclass instead of a SimpleNamespace). Built by
    order_context; resolve_originator, check_stacking, apply_skill, the handlers and book_order fill the rest.
    Platoon Fire copies it per firing unit with dataclasses.replace (shallow: prot, moved and mods stay shared)."""

    # the order as given
    action_id: str  # action id, e.g. "4.2.4b"
    hq_name: str  # active HQ, "GI" or "BN"
    target_name: str  # recipient
    recipient: dict  # recipient unit
    recipient_card: dict  # recipient's card
    o: dict  # parsed options
    # the action's row of rules.ACTIONS
    name: str
    cost: int
    draw_kind: str  # e.g. "auto"
    originator_kind: str  # e.g. "HQ", "CO_BN"
    rule: str
    late_order: str | None = None  # the HQ of a late order (cmd_late_order), else None
    gi: bool = False  # under General Initiative
    success: str | None = None  # --success: "yes"/"no" or per unit "1/1:yes,.."
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
    draw_note: str | None = None  # the draw of a booked attempt (cards, base, experience, success symbol)
    moved: list = dataclasses.field(default_factory=list)  # units moved by the order
    prot: list = dataclasses.field(default_factory=list)  # protocol lines


def order_context(s, hq_name, target_name, action_id, o, late_order):
    """The working record of one order (ctx): the action's table row, the recipient and the fields the handlers fill."""
    if s["phase"] not in rules.IMPULSES:
        raise rules.Violation(f"Orders only in the Friendly Command Phase 3.3, currently {s['phase']} [RULE 3.3 p.15]")
    if s.get("active_hq") != hq_name and not late_order:
        raise rules.Violation(f"Active HQ is {s.get('active_hq')}, not {hq_name}")
    if action_id not in rules.ACTIONS:
        raise rules.Violation(f"Action {action_id} not in the table. Known: {', '.join(rules.ACTIONS)}")
    name, cost, draw_kind, originator_kind, rule = rules.ACTIONS[action_id]
    recipient = state.unit(s, target_name)
    if recipient["side"] != "US":
        raise rules.Violation("Orders only to friendly units")
    return OrderCtx(
        action_id=action_id,
        hq_name=hq_name,
        target_name=target_name,
        recipient=recipient,
        recipient_card=state.card(s, recipient["card"]),
        o=o,
        name=name,
        cost=cost,
        draw_kind=draw_kind,
        originator_kind=originator_kind,
        rule=rule,
        late_order=late_order,
        gi=hq_name == "GI",
        success=options.text_opt(o, "--success", "--success=yes|no"),  # bare --success is a Violation
        skill=o.get("--skill"),
    )


def resolve_originator(s, ctx):
    """Originator of the order: the active HQ, or under General Initiative the recipient itself or --originator
    [RULE 4.1.1 p.19, 4.2 Action Menu originator column, 4.1.4 p.20]."""
    kind, name, rule, recipient = ctx.originator_kind, ctx.name, ctx.rule, ctx.recipient
    if ctx.gi:
        ctx.orig_name = ctx.o.get("--originator", ctx.target_name)
        if (
            ctx.action_id in rules.HQ_REQUIRED_UNDER_GI
            and ctx.orig_name == ctx.target_name
            and not state.is_hq(recipient)
        ):
            raise rules.Violation(
                f"{name} needs an HQ/Staff even under General Initiative: --originator=<HQ> [RULE 4.1.1 p.19, Clarification 3]"
            )
        ctx.orig = state.unit(s, ctx.orig_name)
        if kind in ORIGINATOR_KINDS and not originator_eligible(ctx.orig, kind):
            # a PLT HQ may name itself as originator of its own platoon action under GI
            raise rules.Violation(
                f"{name} needs the responsible HQ as originator (--originator=<{ORIGINATOR_WORD[kind]}>) [RULE {rule}]"
            )
    else:
        ctx.orig_name, ctx.orig = ctx.hq_name, state.unit(s, ctx.hq_name)
        if kind in ORIGINATOR_KINDS and not originator_eligible(ctx.orig, kind):
            raise rules.Violation(f"{name} may only be ordered by {ORIGINATOR_WORD[kind]} [RULE {rule}]")
        if state.fire_team_side(ctx.orig) and ctx.target_name != ctx.hq_name:
            raise rules.Violation(f"{ctx.hq_name} on its Fire Team side may only order itself [RULE 4.1.4 p.20]")


def check_recipient(s, ctx):
    """Recipient of a CO-level action is the HQ itself; otherwise chain of command and communication [RULE 4.0, 4.3]."""
    orig, orig_name, target_name, action_id = ctx.orig, ctx.orig_name, ctx.target_name, ctx.action_id
    if ctx.originator_kind == "CO":
        # [RULE 4.2.1l p.22] Originator 'CO HQ or CO Staff (or PLT HQ in a single-platoon mission)', Recipient 'The HQ itself'
        if not (
            orig.get("level") == "CO"
            or orig["type"] == "Staff"
            or (s.get("single_platoon") and orig.get("level") == "PLT")
        ):
            raise rules.Violation(
                f"{ctx.name}: only CO HQ or CO Staff (PLT HQ only in single-platoon missions) [RULE {ctx.rule}]"
            )
        if target_name != orig_name:
            raise rules.Violation(f"{ctx.name}: recipient is the HQ itself [RULE {ctx.rule}]")
    if orig_name != target_name:
        if action_id not in ("4.2.4k", "4.2.4l", "4.2.4j"):
            comms.chain_of_command(s, orig_name, target_name)
        if action_id != "4.2.4j":
            comms.communication(s, orig_name, target_name, action_id)


def check_repeat_and_budget(s, ctx):
    """Exhort follow-up (--free), one action per unit and impulse [RULE 4.2 p.21], 4.2.5 restrictions, Commands and
    the per-impulse cap [RULE 4.1.3 p.20]."""
    o, action_id, target_name = ctx.o, ctx.action_id, ctx.target_name
    ex = s.get("exhort_free")
    ctx.after_exhort = bool(
        ex and ex[0] == target_name and ex[1] == action_id and ex[2] == s["phase"] and o.get("--free") == "yes"
    )
    if o.get("--free") == "yes" and not ctx.after_exhort:
        raise rules.Violation(
            "--free=yes only for the effect of a successful Exhort (4.2.1b) with the same unit and action [RULE 4.2.1b p.22]"
        )
    already = [] if ctx.late_order else s["impulse_actions"].setdefault(target_name, [])
    if action_id in already and action_id != "4.2.2f" and not ctx.after_exhort:
        raise rules.Violation(
            f"{target_name} has already carried out '{ctx.name}' in this impulse; only Move within a Card may be repeated [RULE 4.2 p.21]"
        )
    comms.action_allowed(ctx.recipient, target_name, action_id)
    ctx.k = command_record(s, ctx.hq_name)
    check_impulse_budget(s, ctx.hq_name, ctx.cost, ctx.rule, free=ctx.after_exhort or o.get("--free") == "yes")
    if ctx.gi and ctx.cost and not ctx.after_exhort:
        gi_skill_scope(s, ctx)


def apply_skill(s, ctx):
    """[RULE 12.7 p.82, Player Aid 2] --skill=<Auto ...|Extra Draw>: the holder hands in the marker; Auto skills make
    the attempt succeed (cards still drawn for Critical Hit/Jam); --short only for a Call for Fire."""
    skill, action_id, o, recipient = ctx.skill, ctx.action_id, ctx.o, ctx.recipient
    if skill == "Auto Concentrate Fire":  # long name on the counter mix list (E67) = the marker 'Auto Concentrate'
        skill = ctx.skill = "Auto Concentrate"
    if skill:
        if skill not in SKILL_AUTO and skill != "Extra Draw":
            raise rules.Violation(f"Skill in an order: {', '.join(list(SKILL_AUTO) + ['Extra Draw'])} [RULE 12.7 p.82]")
        if skill in SKILL_AUTO and action_id not in SKILL_AUTO[skill]:
            raise rules.Violation(f"{skill} only applies to {', '.join(SKILL_AUTO[skill])} [Player Aid 2, Skills]")
        holder = skill_holder(s, ctx.target_name, skill)
        if skill in SKILL_AUTO and action_id in ("4.2.4b", "4.2.4d") and "--critical" not in o:
            # [RULE 12.7 p.82] 'the cards still need to be drawn to determine if a critical hit or jam takes place'
            n_cards, _who, _base = comms.card_count(
                s, action_id, ctx.orig if action_id.startswith("4.2.3") else recipient, recipient
            )
            ranged = action_id == "4.2.4d" and o.get("--target", recipient["card"]) != recipient["card"]
            raise rules.Violation(
                f"Skill {skill}: success is certain, but draw {n_cards} Action cards for Critical Hit/Jam; then repeat with --critical=yes|no"
                + (" --jam=yes|no" if grenades.jam_prone(recipient) and (action_id == "4.2.4b" or ranged) else "")
                + " "
                + grenades.draw_watch(s, "cf" if action_id == "4.2.4b" else "grenade", recipient, ranged)
            )
        if skill in SKILL_AUTO:
            ctx.success = "yes"
            ctx.skill_text = (
                f"Skill {skill} of {holder}: attempt automatically successful; Commands are spent anyway"
                + (
                    ", draw cards only for Critical Hit/Jam"
                    if action_id in ("4.2.4b", "4.2.4d")
                    else ", no cards needed"
                )
                + " [RULE 12.7 p.82]"
            )
        s["units"][holder]["skills"].remove(skill)
        ctx.skill_text = (
            ctx.skill_text or f"Skill Extra Draw from {holder}: one more card [Player Aid 2]"
        ) + "; hand in the Skill marker"
    if ctx.after_exhort and ctx.success != "yes":
        raise rules.Violation("After a successful Exhort enter the effect with --success=yes --free=yes")
    if o.get("--short") == "yes" and action_id == "4.2.4i":  # only a Call for Fire knows 'Short'
        ctx.success = "yes"  # [RULE 7.16.4 p.59] 'Short' takes precedence; the Pending marker is placed anyway
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
    action_id, o, recipient, success = ctx.action_id, ctx.o, ctx.recipient, ctx.success
    extra_cff = 0
    if action_id == "4.2.4i":
        ctx.base_cff, extra_cff, ctx.agency = fire_support.cff_precheck(s, recipient, ctx.target_name, o)
    if not (
        ctx.draw_kind in ("attempt", "cover", "cff")
        or (ctx.draw_kind == "attempt_vof" and fire.vof_against(s, recipient["card"], recipient["side"]) is not None)
    ):
        return
    if action_id == "4.2.4i":
        ctx.extra = extra_cff
        if extra_cff:
            ctx.mods = [(f"Target marker {ctx.agency} on {o['--target']}", extra_cff)]
    if action_id == "4.2.4a":
        target_k = o.get("--target")
        if not target_k:
            raise rules.Violation("Spot: specify --target=<card with Unspotted enemies> [4.2.4a]")
        state.card(s, target_k)
        if not unspotted_enemies(s, target_k):
            raise rules.Violation(f"There is no Unspotted enemy on {target_k} [8.5]")
        if ctx.recipient_card.get("staging"):
            raise rules.Violation("No spotting from the Staging Area [8.5 Note]")
        ok, reason = geometry.los(
            s,
            recipient["card"],
            target_k,
            ha=geometry.height_bonus(s, recipient),
            hb=geometry.card_height_bonus(s, target_k, "Enemy"),
        )
        if not ok:
            raise rules.Violation(f"No LOS from {recipient['card']} to {target_k}: {reason}")
        ctx.mods = comms.spot_modifiers(s, recipient, target_k)
        ctx.extra = sum(m for _, m in ctx.mods)
    if action_id == "4.2.4d":
        grenades.check_grenade(s, recipient, ctx.target_name, o)
    if action_id == "4.2.4b" and combat.cf_ammo_short(recipient):
        raise rules.Violation(
            f"{ctx.target_name} has {combat.ammo(recipient)['points']} ammo: not enough for a Concentrate Fire this turn "
            "(one for the attempt and one in the Combat Effects Segment) [RULE 7.18.4 p.61]"
        )
    if action_id == "4.2.4b" and success not in ("yes", "no"):  # legality before the draw
        if not fire.is_firing(recipient):
            raise rules.Violation(f"{ctx.target_name} is not firing (no target, no VOF) [RULE 4.2.4b p.25]")
        zt_ = fire.effective_fire_target(s, ctx.target_name)
        if not spotted_enemies(s, zt_):
            raise rules.Violation(f"No Spotted enemy on {zt_} [RULE 4.2.4b p.25]")
    if action_id in ("4.2.4c", "4.2.4h") and success and ":" not in success:
        raise rules.Violation(f"{ctx.name}: --success=<unit>:yes|no,.. per unit [RULE {ctx.rule}]")
    if ctx.skill == "Extra Draw":
        ctx.extra += 1
        ctx.mods = list(ctx.mods) + [("Skill Extra Draw", 1)]
    if action_id == "4.2.2c" and o.get("--target") and success not in ("yes", "no"):
        # legality (5.1.4 VOF on origin or destination) before the draw
        check_move(s, recipient, ctx.target_name, o["--target"], action_id)
    if action_id in PRE_DRAW_CHECKS and success not in ("yes", "no"):
        PRE_DRAW_CHECKS[action_id](s, ctx)  # every refusal that needs no card comes before the draw
    if action_id not in ("4.2.2d", "4.2.4c", "4.2.4h") and success not in ("yes", "no"):
        raise rules.Violation(draw_prompt(s, ctx))
    if action_id not in ("4.2.2d", "4.2.4c", "4.2.4h"):
        # the booked line names the draw too, so the player can check the number of cards he drew
        core, word = draw_core(s, ctx)
        ctx.draw_note = f"{core}, success on {word}"


def draw_core(s, ctx):
    """'N Action cards (base b, experience X of the recipient, modifiers)' and the success symbol."""
    action_id, recipient = ctx.action_id, ctx.recipient
    n_cards, who, base = comms.card_count(s, action_id, ctx.orig, recipient, ctx.extra, ctx.base_cff)
    word = {
        "4.2.2c": "Infiltrate symbol",
        "4.2.2g": "Infiltrate symbol",
        "4.2.2e": "word Cover",
        "4.2.4a": "Crosshairs",
        "4.2.4b": "Crosshairs",
        "4.2.4d": "Grenade symbol (2 or more: Critical Hit, --critical=yes)",
        "4.2.4i": "Burst symbol (also 3 Bursts; 'Short!' takes precedence)",
    }.get(action_id, "word Rally")
    core = f"{n_cards} Action cards (base {base}" + (
        ""
        if action_id == "4.2.4a"
        else f", experience {comms.experience(who)} of the {'originator' if action_id.startswith('4.2.3') else 'recipient'}"
    )
    if action_id in ("4.2.4b", "4.2.4c") and recipient.get("tripod") and not state.fire_team_side(recipient):
        core += ", tripod MG +1"  # the extra card comms.card_count adds (7.11.2), named in the breakdown too
    if ctx.mods:
        core += ", " + ", ".join(f"{t} {m:+d}" for t, m in ctx.mods) + (", minimum 1" if action_id == "4.2.4a" else "")
    return core + ")", word


def draw_prompt(s, ctx):
    """Text only: how many Action cards to draw for the attempt, which symbol counts, and what to watch for."""
    action_id, o, recipient = ctx.action_id, ctx.o, ctx.recipient
    core, word = draw_core(s, ctx)
    agency = ctx.agency
    msg = f"{ctx.name}: draw {core}" + (
        f"; success on {word}. Then --success=yes|no"
        + (" (on 'Short' --short=yes)" if action_id == "4.2.4i" and s.get("fm_values") else "")
        + (
            " WATCH: 3 Bursts icon = Battalion Fire Mission possible: --battalion=K1,K2 (two cards adjacent to the target) [RULE 7.16.2B p.58]"
            if action_id == "4.2.4i"
            and agency
            and (s.get("fm_group") or {}).get(agency, agency) in (s.get("battalion_fm") or [])
            else ""
        )
        + f" [RULE 4.2 p.21, {ctx.rule}]"
    )
    kind = {"4.2.4b": "cf", "4.2.4d": "grenade", "4.2.4i": "cff", "4.2.4a": "spot"}.get(action_id, "other")
    ranged = action_id == "4.2.4d" and o.get("--target", recipient["card"]) != recipient["card"]
    watch = grenades.draw_watch(s, kind, recipient, ranged, skill=bool(ctx.skill_text))
    if kind == "cff" and o.get("--target") in s["cards"] and "Illum" not in (agency or ""):
        watch = "; ".join(x for x in (watch, fire_support.cff_friendly_fire(s, recipient, o["--target"])) if x)
    return msg + (" " + watch if watch else "")


def book_order(s, ctx):
    """After the handler: pay the Commands, note the action per unit for the repeat check, activity level, save, print."""
    o, k, cost, moved, success = ctx.o, ctx.k, ctx.cost, ctx.moved, ctx.success
    last = s.get("last_attempt")
    if success == "yes" and last and last[0] == ctx.target_name:
        s["last_attempt"] = None  # Exhort is for the last attempt, which has now succeeded
    if ctx.after_exhort:
        s["exhort_free"] = None
    elif o.get("--free") != "yes":
        pay_commands(s, ctx.hq_name, cost, ctx.rule)
    if ctx.hq_name != "GI" and ctx.hq_name not in s["units"] and s.get("active_hq") == ctx.hq_name:
        # the ordering HQ left play with this order (e.g. a Staff hands over its step in 4.2.1d):
        # its impulse ends here, its remaining and saved Commands are lost; otherwise 'done' and 'phase next' dead-end
        k["available"], k["saved"], k["done"] = 0, 0, True
        s["active_hq"] = None
        s["impulse_actions"] = {}
        ctx.prot.append(f"{ctx.hq_name} has left play: its impulse ends, remaining Commands are lost [4.1.3]")
        moved = []  # nothing to note for the repeat check: the impulse is over
    elif not moved:
        moved = [ctx.target_name]
    for n in moved:
        if not ctx.after_exhort and not ctx.late_order:
            s["impulse_actions"].setdefault(n, []).append(ctx.action_id)
            if ctx.also_book:  # Platoon Fire also counts as the single action of every attacker
                s["impulse_actions"][n].append(ctx.also_book)
    activity_note = fire.update_activity(s)
    if activity_note:
        ctx.prot.append(activity_note)
    s.pop("_order_opts", None)
    txt = ("Late order for the impulse of " + ctx.late_order + ": " if ctx.late_order else "") + (
        f"{ctx.hq_name} orders {ctx.target_name}: {ctx.name}"
        + (f" to {o['--target']}" if o.get("--target") else "")
        + (f", attempt {attempt_text(success)}" if success else "")  # English output
        + (f" ({ctx.draw_note})" if success and ctx.draw_note else "")
        + (f" (with {', '.join(moved)})" if len(moved) > 1 else "")
        + f"; cost {0 if o.get('--free') == 'yes' else cost}, remaining {k['available']}+{k['saved']}"
        + (f" (save limit {save_limit(s, ctx.hq_name)})" if ctx.hq_name not in ("GI",) else " (cannot be saved)")
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
    if target == "off":
        fire.cease_fire(e)
        prot.append(f"{n} no longer fires (correction)")
    else:
        state.card(s, target)
        if e.get("target_open") and target not in e["target_open"]:
            raise rules.Violation(f"{target} not among the candidates {', '.join(e['target_open'])}")
        if e.get("target_open"):
            # [RULE 6.3.5 p.43 'Units will never place an extra PDF if they are able to fire along the card's
            # current PDF', 6.1.1]: a second pending unit on the card joins a PDF chosen meanwhile
            joined = sorted(
                {
                    x["target"]
                    for m, x in s["units"].items()
                    if m != n
                    and x["side"] == e["side"]
                    and x.get("card") == e["card"]
                    and fire.is_firing(x)
                    and x["target"] in e["target_open"]
                }
            )
            if joined and target not in joined:
                raise rules.Violation(
                    f"{n} can fire along the existing PDF from {e['card']} to {', '.join(joined)}: no extra PDF [RULE 6.3.5 p.43]"
                )
        e["target"] = target
        e.pop("target_open", None)
        prot.append(
            f"{n} fires at {target}"
            + (
                ""
                if target == e["card"]
                else f", PDF from {e['card']} to {target}" + fire.pdf_note(s, e["card"], target, n)
            )
            + fire.grazing_note(s, n)
        )
        if target != e["card"]:
            # [RULE 6.3.5 p.43]: other pending units of this card that can fire along the new PDF join it
            for m, x in s["units"].items():
                if (
                    m != n
                    and x["side"] == e["side"]
                    and x.get("card") == e["card"]
                    and target in (x.get("target_open") or [])
                ):
                    x["target"] = target
                    x.pop("target_open", None)
                    prot.append(
                        f"{m} joins the fire along the PDF from {e['card']} to {target} (no extra PDF) [6.3.5 p.43]"
                    )
    activity_note = fire.update_activity(s)
    if activity_note:
        prot.append(activity_note)
    state.save_state(s, "; ".join(prot), "6.1.1 p.39")
    briefing.print_board(prot, s)


def friendly_fire_on(s, n, card_id):
    """[RULE 6.1, 6.3.3 p.43]: own-side units on other cards whose VOF lies on card_id (friendly fire on the mover)."""
    side = s["units"][n]["side"]
    return [
        m
        for m, x in s["units"].items()
        if m != n
        and x["side"] == side
        and x["card"] != card_id
        and fire.is_firing(x)
        and fire.effective_fire_target(s, m) == card_id
    ]


def hq_rank(e):
    return {"BN": 0, "CO": 1}.get(e.get("level"), e.get("rank", 9) if e["type"] == "Staff" else 5)


def order_comms_action(s, target_name, action_id, o, orig, prot):
    """Runner, net change, phone line repair. Returns True if the action was handled here."""
    if action_id == "4.2.1f":
        recipient = state.unit(s, target_name)
        if comms.runner_count(s) >= 2:
            raise rules.Violation("At most two Runners in play [4.3.2 p.27, 4.2.1f p.22]")
        if not (
            state.good_order(recipient)
            or (recipient["type"] in ("Assault Team", "Fire Team") and not state.pinned(recipient))
        ) or state.is_hq(recipient):
            raise rules.Violation("Recipient: Good Order unit or unpinned Assault/Fire Team [4.2.1f p.22]")
        rn = new_name(s, "Runner")
        while rn in comms.runner_box(s):
            rn = rn[:-1] + str(int(rn[-1]) + 1)
        hand_over_step(s, target_name, prot, "Fire")
        comms.runner_box(s).append(rn)
        prot.append(f"{rn} (Line) into the CO HQ Assets Box; moves with the CO HQ [4.2.1f p.22, 4.3.2 p.27]")
        return True
    if action_id in ("4.2.1g", "4.2.1h"):
        raise rules.Violation(
            f"{target_name} is not in the CO HQ Assets Box (en route or not a Runner); Runner orders only to Runners in the box [4.3.2 p.27]"
        )
    if action_id == "4.2.1k":
        recipient = state.unit(s, target_name)
        c = state.card(s, recipient["card"])
        if orig["card"] != recipient["card"]:
            raise rules.Violation("Originator must be on the same card as the cut phone line [4.2.1k p.22]")
        cut = [l for l in c.get("lines", []) if l.get("cut")]
        if not cut or not state.good_order(recipient):
            raise rules.Violation(
                f"No cut phone line on {recipient['card']} or {target_name} not in Good Order [4.2.1k p.22]"
            )
        for l in cut:
            l["cut"] = False
        prot.append(f"Phone Line on {recipient['card']} repaired (flip the marker back) [4.2.1k p.22]")
        return True
    if action_id == "4.2.1j":
        recipient = state.unit(s, target_name)
        from_, to_ = o.get("--source"), o.get("--to")
        g = [x for x in comms.radios_of(recipient) if x["net"] == from_]
        if not g:
            raise rules.Violation(
                f"{target_name} has no device in net {from_}; --source=<net> --to=<net> [4.2.1j p.22]"
            )
        gone = f"{g[0]['type']} {to_}"
        if gone not in s.get("radio_destroyed", []):
            raise rules.Violation(
                f"No {g[0]['type']} of net {to_} is Removed from Play; only the same device type can replace it [4.2.1j p.22, BGG D2]"
            )
        s["radio_destroyed"].remove(gone)
        s["radio_destroyed"].append(f"{g[0]['type']} {from_}")
        g[0]["net"] = to_
        prot.append(f"{target_name}: {g[0]['type']} now in net {to_} (net {from_} drops out instead) [4.2.1j p.22]")
        return True
    return False


def order_runner_box(s, hq_name, target_name, action_id, o):
    """4.2.1g/h to a Runner in the CO HQ Assets Box (not a unit on the board)."""
    co = s.get("co_hq")
    if hq_name != co and not (hq_name == "GI" and o.get("--originator") == co):
        raise rules.Violation("Only the CO HQ gives Runner orders [4.2.1g/h p.22]")
    if s["phase"] not in rules.IMPULSES or s.get("active_hq") != hq_name:
        raise rules.Violation(f"Active HQ is {s.get('active_hq')}, not {hq_name}")
    name, cost, _, _, rule = rules.ACTIONS[action_id]
    k = command_record(s, hq_name)
    check_impulse_budget(s, hq_name, cost, rule)  # Commands and per-impulse cap before anything else
    ce = state.unit(s, co)
    prot = []
    if action_id == "4.2.1g":
        hq = o.get("--target")
        h = s["units"].get(hq)
        if not h or not (h.get("level") == "PLT" or h["type"] == "Staff"):
            raise rules.Violation("--target=<PLT HQ or CO Staff on the board> to be activated next turn [4.2.1g p.22]")
        comms.runner_box(s).remove(target_name)
        s["units"][target_name] = {
            "type": "Runner",
            "side": "US",
            "experience": "Line",
            "card": h["card"],
            "area": h.get("area", "open"),
            "status": [rules.EXPOSED],
            "steps": 1,
            "vof_rating": None,
            "range": "C",
            "target": None,
            "runner_target": hq,
            "en_route_since": s["turn"],
            "fire_team_side": False,
            "note": "Runner, Line (4.2.1f); counter VOF UNVERIFIED",
        }
        prot.append(
            f"{target_name} to {hq} on {h['card']}, Exposed; activates {hq} in the CO HQ Impulse of the next turn unless hit/pinned [4.2.1g p.22, 4.3.2 p.27]"
        )
    else:
        e = o.get("--unit")
        x = s["units"].get(e)
        if (
            not x
            or x["card"] != ce["card"]
            or x.get("area", "open") != ce.get("area", "open")
            or not state.good_order(x)
        ):
            raise rules.Violation(
                "--unit=<Good Order unit in the same card area as the CO HQ that can absorb a step> [4.2.1h p.22]"
            )
        maxst = s.get("setup_units", {}).get(e, {}).get("steps", state.steps(x))
        if state.steps(x) >= maxst:
            raise rules.Violation(f"{e} cannot absorb a step (has {state.steps(x)} of {maxst})")
        comms.runner_box(s).remove(target_name)
        x["steps"] = state.steps(x) + 1
        prot.append(f"{target_name} released, {e} at {x['steps']} steps [4.2.1h p.22]")
    pay_commands(s, hq_name, cost, rule)
    txt = f"{hq_name} orders {target_name}: {name}; remaining {k['available']}+{k['saved']}"
    state.save_state(s, txt + "; " + "; ".join(prot), rule)
    print(f"{messages.ALLOWED} {messages.rule(rule)}")
    print(txt)
    briefing.print_board(prot, s)
