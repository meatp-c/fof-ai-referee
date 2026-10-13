"""Friendly Command Phase: activation, impulses, orders of the action menu, late orders, corrections (4.x)."""

import types

from . import briefing, campaign, combat, comms, contact, enemy, events, fire, geometry, messages, options, rules, state


def pay_commands(s, hq_name, cost, rule):
    k = s["kommandos"][hq_name]
    gi = hq_name == "GI"
    total_ = k["verfuegbar"] + (0 if gi else k["gespart"])
    if total_ < cost:
        raise rules.Violation(f"{hq_name} has {total_} Commands, action costs {cost} [RULE {rule}]")
    spent = s.setdefault("impuls_ausgegeben", {}).get(hq_name, 0)
    if not gi and spent + cost > rules.MAX_PER_IMPULSE[s["sicht"]]:
        raise rules.Violation(f"At most {rules.MAX_PER_IMPULSE[s['sicht']]} Commands per impulse [RULE 4.1.3 p.20]")
    remainder = cost
    if k["verfuegbar"] >= remainder:
        k["verfuegbar"] -= remainder
    else:
        remainder -= k["verfuegbar"]
        k["verfuegbar"] = 0
        k["gespart"] -= remainder
    s["impuls_ausgegeben"][hq_name] = spent + cost


def cmd_activate(s, args):
    hq = args[0]
    e = state.unit(s, hq)
    if not state.is_hq(e):
        raise rules.Violation(f"{hq} is not an HQ/Staff [RULE 4.2.1a p.22]")
    if s["phase"] == "3.3.1a" and events.bn_leader(s):
        bn = s.get("aktiver_hq")
        if e.get("ebene") != "CO" or not bn:
            raise rules.Violation("In the BN HQ impulse the BN HQ only activates the CO HQ [RULE 4.2.1a p.22]")
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
    if state.fire_team_side(e):
        raise rules.Violation(
            f"{hq} is on its Fire Team side, cannot be activated, must draw Initiative [RULE 4.1.4 p.20]"
        )
    k = s["kommandos"][hq]
    if k["aktiviert"]:
        raise rules.Violation(f"{hq} is already activated")
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


def cmd_hq(s, args):
    hq = args[0]
    e = state.unit(s, hq)
    k = s["kommandos"][hq]
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
    nr, raw = args[0], int(args[1])
    e = state.unit(s, hq)
    mods = []
    if "--roh" not in args:
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
    nr, small_number = args[0], int(args[1])
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


def new_cover_marker(s, kid, type_, value):
    c = state.card(s, kid)
    i = len(c.setdefault("cover", [])) + 1
    cid = f"C{i}"
    while any(x["id"] == cid for x in c["cover"]):
        i += 1
        cid = f"C{i}"
    c["cover"].append({"id": cid, "typ": type_, "wert": value, "feld": type_ != "Basic Cover"})
    return cid


def mark(e, m):
    if m not in e["status"]:
        e["status"].append(m)


def new_name(s, type_):
    i = 1
    while f"{type_} {i}" in s["einheiten"] or f"{type_} {i}" in s.get("removed_from_play", []):
        i += 1
    return f"{type_} {i}"


def set_area(s, z, name, b):
    if b == "offen":
        z["bereich"] = "offen"
        return
    if not [c for c in state.card(s, z["karte"]).get("cover", []) if c["id"] == b]:
        raise rules.Violation(f"Cover {b} does not exist on {z['karte']}")
    occupied = {
        s["einheiten"][m]["seite"] for m in state.units_on(s, z["karte"]) if s["einheiten"][m].get("bereich") == b
    }
    if occupied and occupied != {z["seite"]}:
        raise rules.Violation(f"Cover {b} is occupied by the opposing side [5.3]")
    cv = [c for c in state.card(s, z["karte"])["cover"] if c["id"] == b][0]
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
    if "Exposed" in e["status"]:
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
        events.event_move(s, e, target_card, [])
    if state.pinned(e) or e["typ"] in ("Fire Team", "Litter Team", "Paralyzed Team") or state.fire_team_side(e):
        friend = [m for m in state.units_on(s, target_card, e["seite"]) if m != n]
        ok = (zk.get("staging") and akt in ("4.2.2a", "4.2.2b")) or (
            friend and fire.vof_against(s, target_card, e["seite"]) is None
        )
        if not ok:
            raise rules.Violation(
                f"{n} (Pinned/LAT/Fire Team side) may only move to a Staging Area or to a card occupied by friendly units without VOF [RULE 4.2.5 p.26]"
            )
    if e["typ"] == "Paralyzed Team" and akt != "4.2.2a":
        raise rules.Violation("Paralyzed Team: only Move to an Adjacent Card [RULE 4.2.5 p.26]")
    if (state.pinned(e) or e["typ"] == "Paralyzed Team") and (comms.radios_of(e) or e.get("traegt_casualties")):
        raise rules.Violation(
            f"{n} is Pinned/Paralyzed and carries Assets or Casualties; drop them first (fof.py drop, no Command) [RULE 4.2.5 p.27, 5.1.6E p.33]"
        )
    if akt in ("4.2.2c", "4.2.2d"):
        if (
            fire.vof_against(s, e["karte"], e["seite"]) is None
            and fire.vof_against(s, target_card, e["seite"]) is None
            and not state.card(s, e["karte"]).get("grenade_miss")
            and not zk.get("grenade_miss")
        ):
            raise rules.Violation(
                "Infiltration only if the origin or destination card has a VOF marker [RULE 5.1.4 p.32]"
            )
        if e.get("tripod") or e.get("vof_rating") == "H" or state.is_mortar(e):
            raise rules.Violation(f"{n} (tripod/H VOF) may not infiltrate [RULE 4.2.2c p.23]")
    ka = state.card(s, e["karte"])
    if abs(ka["reihe"] - zk["reihe"]) == 1 and abs(ka["spalte"] - zk["spalte"]) == 1:  # 5.1.2 diagonal through PDF
        e1, e2 = geometry.card_at(s, ka["reihe"], zk["spalte"]), geometry.card_at(s, zk["reihe"], ka["spalte"])
        if e1 and e2:
            for m, f in s["einheiten"].items():
                if fire.is_firing(f) and f["ziel"] != f["karte"]:
                    path_cards = [f["karte"]] + (geometry.line_between(s, f["karte"], f["ziel"]) or []) + [f["ziel"]]
                    for i in range(len(path_cards) - 1):
                        if {path_cards[i], path_cards[i + 1]} == {e1, e2}:
                            raise rules.Violation(
                                f"Diagonal {e['karte']} to {target_card} crosses the PDF {path_cards[i]} to {path_cards[i + 1]} [RULE 5.1.2 p.32]"
                            )


def grenade_stack(s, name):
    """[RULE 7.10.1 p.54] Target of a Grenade Attack: one unit out of cover or the whole stack under its Cover marker."""
    f = state.unit(s, name)
    if f.get("bereich", "offen") == "offen":
        return [name]
    return [m for m in state.units_on(s, f["karte"], f["seite"]) if s["einheiten"][m].get("bereich") == f["bereich"]]


def grenade_back_note(s, thrower, target, success, name=None):
    """7.10.5 Free Grenade Attack Response. K31 (BGG Shonai_Dweller 3563964, 3517434, 3780916): only against a Point Blank
    attack from the same card; never from inside a Bunker/Pillbox, never while Pinned; a LAT only with a VOF and only after
    a successful attack; the attacker must be Spotted."""
    who = name or target.get("typname", "Target")
    if thrower["karte"] != target["karte"]:
        return f"{who}: no response throw, the attack did not come from the same card (Point Blank only) [7.10.5, K31]"
    if not (thrower["seite"] == "US" or thrower.get("spotted")):
        return f"{who}: no response throw, the attacker is Unspotted [7.10.5]"
    if state.pinned(target):
        return f"{who}: no response throw, Pinned [7.10.5, K31]"
    cv = geometry.cover_marker(s, target)
    if cv and (cv["typ"] in rules.STRUCTURES or "Bunker" in cv["typ"]):
        return f"{who}: no response throw from the {cv['typ']} (no Point Blank attack from inside) [5.3.2, 7.10.5, K31]"
    if target["typ"] not in ("Paralyzed Team", "Litter Team", "Fire Team", "Assault Team"):
        return f"{who}: free response throw at the attacker (Good Order, same card) [7.10.5]"
    if target.get("vof_rating") and success:
        return f"{who} (unpinned LAT with VOF): free response throw at the attacker [7.10.5]"
    return f"{who}: no response throw (a LAT only with a VOF and only after a successful attack) [7.10.5]"


def grenade_back_notes(s, thrower, names, success, prot):
    """7.10.5 for every unit of the attacked stack (rule note: every eligible unit of a stack responds); one line at range."""
    if names and s["einheiten"][names[0]]["karte"] != thrower["karte"]:
        prot.append("No response throw: the attack did not come from the same card (Point Blank only) [7.10.5, K31]")
        return
    for m in names:
        prot.append(grenade_back_note(s, thrower, s["einheiten"][m], success, m))


def grenade_expires(s, e, name, prot):
    """7.10.4: if the target of a successful Grenade Attack moves before 3.7.4 (card change or within the card), it becomes a Grenade Miss on the original card."""
    if e.get("grenade"):
        rest = [
            m
            for m in state.units_on(s, e["karte"], e["seite"])
            if m != name and s["einheiten"][m].get("grenade") and s["einheiten"][m].get("bereich") == e.get("bereich")
        ]
        e["grenade"] = []
        e.pop("grenade_critical", None)
        if rest:
            # K32 (Manuel): the target was the stack; while part of it stays, the Grenade marker stays with it, no Grenade Miss
            prot.append(
                f"{name} leaves the grenaded stack; the Grenade marker stays with {', '.join(rest)} [7.10.4, K32]"
            )
            return
        state.card(s, e["karte"])["grenade_miss"] = True
        prot.append(
            f"Grenade marker on {name} becomes Grenade Miss (-1) on {e['karte']}: target moved before 3.7.4 [7.10.4]"
        )


def move_unit(s, n, target_card, area, exposed, prot):
    e = s["einheiten"][n]
    from_ = e["karte"]
    grenade_expires(s, e, n, prot)
    if state.is_v4(s):
        comms.lay_line(s, n, e, from_, prot, s.get("_befehl_opts"))
        combat.ammo_surplus(s, n, e, from_, prot)
        events.event_move(s, e, target_card, prot)
    old_cover = fire.cover_of(s, e)
    e["karte"] = target_card
    e["bereich"] = "offen"
    if area and area != "offen":
        set_area(s, e, n, area)
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
        mark(e, "Exposed")
    prot.append(
        f"{n} to {target_card}"
        + (f" under {area}" if area and area != "offen" else "")
        + (", Exposed" if "Exposed" in e["status"] else ", not Exposed")
    )
    campaign.patrol_move(s, n, from_, target_card, prot)
    fire.fire_after_move(s, n, prot)
    if state.units_on(s, target_card, state.opponent_of_side(e["seite"])):
        prot.append(f"Point Blank on {target_card}: each side's VOF only hits the opposing side [6.2.1b]")
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


def cff_precheck(s, z, name, orig_name, o):
    """7.16.1 p.58: valid target (Spotted), eligible observer with LOS, connection to the firing unit; number of cards per observer."""
    fm = s.get("feuermissionen", 0)
    if not isinstance(fm, dict) and fm != "unbegrenzt" and (fm or 0) <= 0:
        raise rules.Violation("No Fire Mission available any more [7.16.1]")
    observer = s.get("cff_beobachter", {})
    if z["typ"] != "FO" and not z.get("beobachter") and name not in observer:
        raise rules.Violation(
            f"{name} is not an observer according to the mission [7.16.1]"
            + (f"; eligible: {', '.join(observer)}" if observer else "")
        )
    if state.fire_team_side(z):
        raise rules.Violation("Observer on its Fire Team side cannot call for fire [7.16.1]")
    zt = o.get("--ziel")
    if not zt:
        raise rules.Violation("Specify --target=<card with Spotted enemy> [7.16.1]")
    state.card(s, zt)
    wp = "WP" in (o.get("--agentur") or "")
    illum = "Illum" in (o.get("--agentur") or "")
    if illum:
        if state.card(s, zt).get("staging"):
            raise rules.Violation("Illumination only on terrain cards [7.16.2E]")
    elif not wp and not [m for m in state.units_on(s, zt, "Feind") if s["einheiten"][m].get("spotted")]:
        raise rules.Violation(
            f"No Spotted enemy on {zt} [7.16.1]"
            + (" (WP missions may hit empty/Unspotted cards, 7.16.2C)" if isinstance(fm, dict) else "")
        )
    if not illum:
        ok, reason = geometry.los(
            s, z["karte"], zt, ha=geometry.height_bonus(s, z), hb=geometry.card_height_bonus(s, zt, "Feind")
        )
        if not ok:
            raise rules.Violation(f"Observer needs LOS to the target: {reason} [7.16.1]")
    agency = None
    if s.get("fm_werte"):
        fw = s["fm_werte"]
        agency = o.get("--agentur") or (list(fw)[0] if len(fw) == 1 else None)
        if agency not in fw:
            raise rules.Violation(
                f"Specify --agency={'|'.join(fw)} ({', '.join(f'{a} {w:+d}' for a, w in fw.items())}) [FM1 p.36, 7.16.1 p.58]"
            )
        if isinstance(fm, dict) and fm.get(agency, 0) <= 0:
            raise rules.Violation(f"No {agency} Fire Mission left ({fm}) [7.16.1, Normandy M1 p.17]")
        sp = s.get("fm_gesperrt") or {}
        if sp.get("zug") == s["zug"] and s.get("fm_gruppe", {}).get(agency, agency) == sp.get("gruppe"):
            raise rules.Violation(f"Artillery Displacing: {sp['gruppe']} not available this turn [Normandy M1 p.18]")
        # Connection to the firing unit [RULE 7.16.1 p.58]
        if z["typ"] == "FO":
            fd = [g for g in comms.radios_of(z) if "FD" in g.get("netz", "")]
            if not fd and state.radio_active(s) and not state.option(s, "U2_fo_fd_funk"):
                raise rules.Violation(
                    f"{name} has no FD radio, no connection to the firing unit [RULE 7.16.1 p.58]"
                    + state.open_reading(s, "U2_fo_fd_funk")
                )
            if not fd and state.radio_active(s):
                s.setdefault("_hinweise", []).append(
                    f"{name} calls over its FD net (device implicit under option U2){state.open_reading(s, 'U2_fo_fd_funk')}"
                )
        elif z.get("ebene") == "CO" and state.radio_active(s) and not s.get("co_immer_in_kommunikation"):
            if not comms.radios_of(z, "SCR300", "BN TAC"):
                raise rules.Violation(f"{name} calls over the BN TAC Net and needs its SCR300 [RULE 7.16.1 p.58]")
    tab = s.get("cff_tabelle") or {}
    if agency in tab:
        if name not in tab[agency]:
            raise rules.Violation(
                f"{name} may not call {agency}; eligible: {', '.join(tab[agency])} [Normandy M2 p.22]"
            )
        base = tab[agency][name]  # [Normandy M2 p.22] number of cards per firing unit and observer
    else:
        base = observer.get(name, s.get("cff_karten", 2))
    extra = (
        1 if agency and s.get("target_marker", {}).get(target_marker_key(s, agency)) == zt else 0
    )  # [RULE 7.16.5 p.59]
    return base, extra, agency


def target_marker_key(s, agency):
    """Target marker per firing unit; HE and WP of the same battery share it [open U29]."""
    if s.get("fm_gruppe") and state.option(s, "U29_ein_target_marker_he_wp"):
        return s["fm_gruppe"].get(agency, agency)
    return agency


def jam_prone(e):
    """[RULE 7.12 p.56] A, G! and H weapons teams, AT guns, A squads with ammo tracking."""
    r = e.get("vof_rating")
    if e["typ"] in ("Weapons Team", "AT Gun") and r in ("A", "G", "H"):
        return True
    return e["typ"] == "Squad" and r == "A" and bool(e.get("munition"))


def jam(s, n, prot):
    """[RULE 7.12 p.56] Jam: unit immediately out of play, its steps become generic Fire Teams; success of the attempt is lost."""
    e = s["einheiten"][n]
    new_units = []
    for _ in range(state.steps(e)):
        nn = new_name(s, "Fire Team")
        s["einheiten"][nn] = combat.new_lat(e, "Fire Team", n)
        s["einheiten"][nn]["status"] = []
        new_units.append(nn)
    combat.remove_from_play(
        s,
        n,
        prot,
        f"JAM: weapon out of action, steps become {', '.join(new_units)}",
        successor=new_units[0] if new_units else None,
    )
    prot.append("Jam cancels any success of this attempt [7.12 p.56]")


def short_place(s, z, zt, o):
    """[RULE 7.16.4 p.59] Short: one card closer to the observer along the LOS; observer on the target card: random adjacent card."""
    if z["karte"] == zt:
        pl = o.get("--platz")
        if not pl or not geometry.adjacent(s, zt, pl):
            nb = [k for k in s["karten"] if geometry.adjacent(s, zt, k)]
            raise rules.Violation(
                f"Short, observer is on the target card: draw a random adjacent card (R#/{len(nb)} from {', '.join(nb)}) and --place=<card> [RULE 7.16.4 p.59]"
            )
        return pl
    between = geometry.line_between(s, z["karte"], zt) or []
    return between[-1] if between else z["karte"]


def indirect_lay(s, hq_name, orig_name, orig, mortar_name, m, o, prot, gi):
    """4.2.4j p.25, 7.3.2 p.53: HQ with LOS calls Indirect Lay of the multi-step mortar unit; VOF H without PDF, terrain like Incoming."""
    if not state.is_mortar(m):
        raise rules.Violation(f"{mortar_name} is not an on-map mortar unit [RULE 4.2.4j p.25]")
    if gi and orig_name == mortar_name:
        raise rules.Violation(
            "Indirect Lay needs an HQ eligible to give orders as observer: --originator=<HQ> [RULE 7.3.2 p.53]"
            + state.open_reading(s, "U12_indirekt_unter_gi")
        )
    if gi and not state.option(s, "U12_indirekt_unter_gi"):
        raise rules.Violation(
            "Indirect Lay under General Initiative not allowed under option U12 (reading a); order it in the impulse of an eligible HQ [RULE 7.3.2 p.53]"
            + state.open_reading(s, "U12_indirekt_unter_gi")
        )
    if not state.is_hq(orig):
        raise rules.Violation("Originator must be an HQ or Staff [RULE 4.2.4j p.25]")
    comms.chain_of_command(
        s, orig_name, mortar_name
    )  # [RULE 7.3.2 p.53] 'someone who is eligible to issue orders to the mortar'
    if state.steps(m) < 2:
        raise rules.Violation(
            f"{mortar_name} has {state.steps(m)} step; Indirect Lay only with at least two steps [RULE 4.2.4j p.25, 7.3.2 p.53]"
        )
    if not state.good_order(m) or "Exposed" in m["status"]:
        raise rules.Violation(f"{mortar_name} must be Good Order and not Exposed [RULE 4.2.4j p.25, 7.3.1 p.53]")
    if state.card(s, m["karte"]).get("staging"):
        raise rules.Violation("No firing from the Staging Area [RULE 2.5 p.12]")
    vb = fire.fire_position_forbidden(s, m)
    if vb:
        raise rules.Violation(vb)
    # Connection: visual-verbal/radio or mortar in the same card area as an HQ with radio/phone (relay) [RULE 7.3.2 p.53]
    try:
        comms.communication(s, orig_name, mortar_name, "4.2.4j")
    except rules.Violation as v:
        relay = [
            n
            for n, e in s["einheiten"].items()
            if state.is_hq(e)
            and e["karte"] == m["karte"]
            and e.get("bereich", "offen") == m.get("bereich", "offen")
            and comms.radios_of(e)
        ]
        if not relay:
            raise rules.Violation(
                f"No connection {orig_name} with {mortar_name}: {v}; also no HQ with radio in the same card area as relay [RULE 7.3.2 p.53]"
            ) from None
        prot.append(f"Order via relay {relay[0]} (HQ with radio in the same area) [7.3.2 p.53]")
    zt = o.get("--ziel")
    if not zt:
        raise rules.Violation("Specify --target=<card with Spotted enemy> [RULE 4.2.4j p.25]")
    state.card(s, zt)
    if not [x for x in state.units_on(s, zt, "Feind") if s["einheiten"][x].get("spotted")]:
        raise rules.Violation(f"No Spotted enemy on {zt} [RULE 4.2.4j p.25]")
    ok, reason = geometry.los(
        s, orig["karte"], zt, ha=geometry.height_bonus(s, orig), hb=geometry.card_height_bonus(s, zt, "Feind")
    )
    if not ok:
        raise rules.Violation(f"Observer {orig_name} has no LOS to {zt}: {reason} [RULE 7.3.2 p.53]")
    lo, hi = state.range_limits(s, m)
    d = geometry.distance(s, m["karte"], zt)
    if not (max(1, lo) <= d <= hi):
        raise rules.Violation(
            f"{zt} is {d} cards away from {mortar_name}; range in cards (diagonals counted, own card excluded) {max(1, lo)} to {hi} [RULE 7.3.2 p.53]"
            + state.open_reading(s, "U12_moerser_reichweite")
        )
    if m.get("ziel"):
        prot.append(
            f"{mortar_name}: remove Direct Lay PDF and VOF to {m['ziel']}, Indirect Lay takes precedence [RULE 7.3.2 p.53]"
        )
        m["ziel"] = None
    m["indirekt"] = True
    state.card(s, zt).setdefault("extern", []).append(
        {"typ": "Indirect", "wert": rules.VOF_VALUE["H"], "quelle": mortar_name, "seite": "US"}
    )
    prot.append(
        f"Heavy Weapons VOF (-3, Indirect Lay) on {zt}, no PDF, no Crossfire; hits all units on the card; lower C&C value and Burst apply; remove in Clean Up"
        + state.open_reading(s, "U12_moerser_reichweite")
        + " [RULE 7.3.2 p.53, 5.2.3 p.36]"
    )


def pick_up(s, z, name, what, prot):
    """4.2.2h p.23 Pick up: pick up a Casualty or radio from the card (5.1.6B)."""
    c = state.card(s, z["karte"])
    if what.lower() == "casualty":
        if not c.get("casualties"):
            raise rules.Violation(f"There is no friendly Casualty on {z['karte']} [RULE 5.1.6 p.33]")
        c["casualties"] -= 1
        z["traegt_casualties"] = z.get("traegt_casualties", 0) + 1
        prot.append(
            f"{name} picks up a Casualty (marker under the counter or in the Assets box) [5.1.6B p.33, FM1 p.43]"
        )
        return
    ground = c.get("assets_boden", [])
    if what in ground:  # [RULE 5.1.6B p.33] pick up a dropped Asset (e.g. Rifle Grenade, smoke)
        ground.remove(what)
        z.setdefault("assets", []).append(what)
        prot.append(f"{name} picks up Asset {what} from the card [5.1.6B p.33]")
        return
    lies = [g for g in c.get("assets", []) if g["typ"] == what or f"{g['typ']} {g['netz']}" == what]
    if not lies:
        raise rules.Violation(
            f"On {z['karte']} there is no device '{what}'" + (f"; on the ground: {', '.join(ground)}" if ground else "")
        )
    if lies[0].get("schaden_offen"):
        raise rules.Violation(
            f"First draw R# 1/2 for {lies[0]['typ']}: fof.py radio damage {z['karte']} {lies[0]['typ']} intact|destroyed [RULE 4.3.5 p.30]"
        )
    c["assets"].remove(lies[0])
    z.setdefault("funk", []).append({"typ": lies[0]["typ"], "netz": lies[0]["netz"]})
    prot.append(f"{name} picks up {lies[0]['typ']} {lies[0]['netz']} [4.3.5 p.30, 5.1.6B p.33]")


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


def order_bn(s, target_name, akt, o):
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


def check_grenade(s, z, target_name, o):
    """7.10.1: legality of a Grenade Attack (before the card draw and when booking). v4: Rifle Grenade (7.6), Mortar Team (7.3), ammo."""
    zt = o.get("--ziel", z["karte"])
    state.card(s, zt)
    rg = (
        state.is_v4(s)
        and "Rifle Grenade" in z.get("assets", [])
        and z.get("vof_rating") != "G"
        and not z.get("grenade_ranged")
    )
    if zt != z["karte"] and z.get("vof_rating") != "G" and not z.get("grenade_ranged") and not rg:
        raise rules.Violation("Grenade Attack without G! rating only Point Blank (own card) [RULE 7.10.1 p.54]")
    if zt != z["karte"]:
        if rg:
            hi = rules.RANGE_CARDS.get(s.get("rifle_grenade_reichweite", "C"), 1)
            cv = geometry.cover_marker(s, z)
            if cv and cv["typ"] in rules.STRUCTURES + (
                "Building",
                "Strong Building",
                "Light Building",
                "Cave",
                "Upper Story",
                "Church Tower",
            ):
                raise rules.Violation(
                    "Rifle Grenades cannot be fired from Building/Bunker/Cave/Pillbox cover, nor from Upper Story/Church Tower (E55) [RULE 7.6 p.54, 5.2.2B p.36]"
                )
            if (
                geometry.distance(s, z["karte"], zt) > hi
                or not geometry.los(
                    s, z["karte"], zt, ha=geometry.height_bonus(s, z), hb=geometry.card_height_bonus(s, zt, "Feind")
                )[0]
            ):
                raise rules.Violation(
                    f"Rifle Grenade: target in LOS up to {s.get('rifle_grenade_reichweite', 'C')} (range per Asset counter UNVERIFIED) [RULE 7.10.1 p.55]"
                )
        elif (
            not geometry.in_range(s, z, zt)
            or not geometry.los(
                s, z["karte"], zt, ha=geometry.height_bonus(s, z), hb=geometry.card_height_bonus(s, zt, "Feind")
            )[0]
        ):
            raise rules.Violation("Ranged Grenade Attack: target must be in LOS and range [RULE 7.10.1 p.55]")
        if not rg and combat.ammo(z) and combat.ammo(z)["typ"] == "RKT":
            cv = geometry.cover_marker(s, z)  # L97 [RULE 7.4 p.54]
            if cv and cv["typ"] in rules.STRUCTURES + (
                "Building",
                "Strong Building",
                "Light Building",
                "Cave",
                "Upper Story",
                "Church Tower",
            ):
                raise rules.Violation(
                    "Rocket launchers (Bazooka/Panzerschreck/RCL) cannot fire from Building/Bunker/Cave/Pillbox cover, nor from Upper Story/Church Tower (E55); Point Blank with hand grenades stays allowed [RULE 7.4 p.54, 7.10.1 p.54]"
                )
        if combat.ammo(z) and combat.ammo(z)["punkte"] <= 0 and not rg:
            raise rules.Violation(f"{target_name} has no ammo left for ranged Grenade Attacks [RULE 7.18.2 p.61]")
        if state.is_mortar(z):
            vb = fire.fire_position_forbidden(s, z)
            if vb or "Exposed" in z["status"]:
                raise rules.Violation(vb or "Mortar with Exposed marker does not fire [RULE 7.3.1 p.53]")
        pdf_targets = {
            fire.effective_fire_target(s, m)
            for m in state.units_on(s, z["karte"], z["seite"])
            if fire.is_firing(s["einheiten"][m])
        }
        pdf_targets.discard(z["karte"])
        if pdf_targets and zt not in pdf_targets:
            raise rules.Violation(
                f"Ranged Grenade Attack must follow the card's PDF (PDF from {z['karte']} to {', '.join(sorted(pdf_targets))}); Shift Fire first [RULE 7.10.1 p.55]"
            )
        if state.units_on(s, z["karte"], "Feind"):
            raise rules.Violation("No Ranged Grenade Attack out of Point Blank combat [RULE 7.10.1 p.55]")
        if any(
            state.units_on(s, between, None if not state.is_mortar(z) else state.opponent_of_side(z["seite"]))
            for between in (geometry.line_between(s, z["karte"], zt) or [])
        ):
            raise rules.Violation(
                "Ranged Grenade Attack not through other units (mortar: over friendly units, 7.3.1) [RULE 7.10.1 p.55]"
            )
    if not [m for m in state.units_on(s, zt, "Feind") if s["einheiten"][m].get("spotted")]:
        raise rules.Violation(f"No Spotted enemy on {zt} [7.10]")
    return zt


# [RULE 12.7 p.82, Player Aid 2 Skills] Skills in use
SKILL_AUTO = {
    "Auto Spot": ("4.2.4a",),
    "Auto Cover": ("4.2.2e",),
    "Auto Concentrate Fire": ("4.2.4b",),
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
    if len(args) < 3 or args[0] not in (
        "casualty",
        "status",
        "granate",
        "munition",
        "ziel",
    ):  # subwords: grenade, ammo, target
        raise rules.Violation(
            "correct casualty <card> <+n|-n> [--side=Feind|US] --reason=.. | correct status <unit> <marker> remove|add --reason=.. | correct grenade <unit> expired <origin card> --reason=.. | correct ammo <unit> <+n|-n> --reason=.. | correct target <unit> <card> --reason=.."
        )
    o = options.parse_opts(args[3:] if args[0] in ("casualty", "munition", "ziel") else args[4:])
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
        d = int(args[2])
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
    kid, n = args[1], int(args[2])
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
    engineer = ctx.akt == "4.2.2c" and contact.engineers_clear(s, ctx.z) and bool(contact.mines_on(s, target_card))
    if engineer:
        s["_pionier_check"] = (ctx.target_name, target_card, 1 if ctx.success == "ja" else 3)
        exposed = False  # CSR 10: failed Engineer infiltration without Exposed, but 3 cards
    else:
        exposed = ctx.akt == "4.2.2a" or ctx.success == "nein"
    move_unit(s, ctx.target_name, target_card, ctx.o.get("--bereich"), exposed=exposed, prot=ctx.prot)
    ctx.moved = [ctx.target_name]


def _order_move_platoon(s, ctx):
    """Order handler for: akt in ('4.2.2b', '4.2.2d')"""
    target_card = ctx.o.get("--ziel")
    if not target_card:
        raise rules.Violation("--target=<card> missing")
    state.card(s, target_card)
    result = {}
    for t in (ctx.success or "").split(","):
        if ":" in t:
            a, b = t.split(":")
            result[a] = b
    candidate = []
    for n, e in s["einheiten"].items():
        if e["seite"] != "US" or e["karte"] != ctx.orig["karte"]:
            continue
        try:
            comms.chain_of_command(s, ctx.orig_name, n)
            comms.communication(s, ctx.orig_name, n)
        except rules.Violation:
            continue
        if not state.good_order(e) or "Exposed" in e["status"]:
            continue
        if ctx.akt == "4.2.2d" and (e.get("tripod") or e.get("vof_rating") == "H"):
            continue
        candidate.append(n)
    if not candidate:
        raise rules.Violation(
            "No Good Order unit of the platoon without Exposed in communication on the HQ's card [RULE 4.2.2b p.23]"
        )
    if ctx.akt == "4.2.2d" and any(n not in result for n in candidate):
        raise rules.Violation(
            "Platoon Infiltrate: each unit draws itself (2 cards, own experience, Infiltrate symbol): --success="
            + ",".join(f"{n}:yes|no" for n in candidate)
            + " [RULE 4.2 Notes p.21]"
        )
    for n in candidate:
        check_move(s, s["einheiten"][n], n, target_card, ctx.akt)
    for n in candidate:
        move_unit(
            s,
            n,
            target_card,
            ctx.o.get("--bereich"),
            exposed=(ctx.akt == "4.2.2b" or result.get(n) == "nein"),
            prot=ctx.prot,
        )
    ctx.moved = candidate


def _order_seek_cover(s, ctx):
    """Order handler for: akt == '4.2.2e'"""
    if ctx.z.get("bereich", "offen") != "offen":
        raise rules.Violation(f"{ctx.target_name} is already under cover [RULE 4.2.2e p.23]")
    present = len([c for c in ctx.zk.get("cover", []) if not c.get("feld")])
    if ctx.zk.get("cover_max") is not None and present >= ctx.zk["cover_max"]:
        raise rules.Violation(
            f"{ctx.z['karte']} has reached its Cover Potential ({ctx.zk['cover_max']}) [RULE 5.3 p.36]"
        )
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
            cid = new_cover_marker(s, ctx.z["karte"], gt, gw)
            if gt != "Basic Cover":
                [c_ for c_ in ctx.zk["cover"] if c_["id"] == cid][0]["feld"] = False
            if gt != "Basic Cover" and (ctx.zk.get("mehrstoeckig") or ctx.zk.get("terrain") == "Church"):
                # L73 [RULE 5.3.3 p.38, 5.2.2B p.36] Multi-Story/Church symbol on the card: add Upper Story or Church Tower,
                # same value, does not count towards the Cover Potential (the star of the CSR 8 table applies to snipers/spotters only)
                us = "Church Tower" if ctx.zk.get("terrain") == "Church" else "Upper Story"
                uid = new_cover_marker(s, ctx.z["karte"], us, gw)
                [c_ for c_ in ctx.zk["cover"] if c_["id"] == uid][0]["feld"] = True
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
            cid = new_cover_marker(s, ctx.z["karte"], "Basic Cover", int(ctx.o.get("--wert", 1)))
        ctx.z["bereich"] = cid
        mark(ctx.z, "Exposed")
        ctx.prot.append(
            f"new cover marker {cid} ({[c_ for c_ in ctx.zk['cover'] if c_['id'] == cid][0]['typ']}) on {ctx.z['karte']}, {ctx.target_name} beneath it, Exposed"
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


def _order_move_within_card(s, ctx):
    """Order handler for: akt in ('4.2.2f', '4.2.2g')"""
    b = ctx.o.get("--bereich")
    if not b and ctx.akt == "4.2.2g" and contact.engineers_clear(s, ctx.z) and contact.mines_on(s, ctx.z["karte"]):
        b = ctx.z.get("bereich", "offen")  # [Normandy CSR 10] engineers clearing mines need no destination (L107)
    if not b:
        raise rules.Violation("Specify --area=<cover-id|open>")
    if ctx.akt == "4.2.2g" and fire.vof_against(s, ctx.z["karte"], ctx.z["seite"]) is None:
        raise rules.Violation("Infiltrate within a Card requires a VOF on the card [RULE 4.2.2g p.23]")
    if ctx.z.get("mine_hit"):
        raise rules.Violation(
            f"{ctx.target_name} is under the Mine marker and may not move this turn [RULE 7.9.1 p.54]"
        )
    old_cv = fire.cover_of(s, ctx.z)
    grenade_expires(s, ctx.z, ctx.target_name, ctx.prot)
    set_area(s, ctx.z, ctx.target_name, b)
    new_cv = fire.cover_of(s, ctx.z)
    fixed = bool(old_cv and new_cv and old_cv["typ"] in rules.FIXED_COVER and new_cv["typ"] in rules.FIXED_COVER)
    engineer = ctx.akt == "4.2.2g" and contact.engineers_clear(s, ctx.z) and bool(contact.mines_on(s, ctx.z["karte"]))
    if (ctx.akt == "4.2.2f" or ctx.success == "nein") and not fixed and not engineer:
        mark(ctx.z, "Exposed")
    if fixed:
        ctx.prot.append("between Trench/Bunker/Pillbox markers of the same card without Exposed [RULE 5.1.1 p.31]")
    ctx.prot.append(
        f"{ctx.target_name} to {'open' if b == 'offen' else b} on {ctx.z['karte']}"
        + (", Exposed" if "Exposed" in ctx.z["status"] else ", not Exposed")
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


def _order_pick_up(s, ctx):
    """Order handler for: akt == '4.2.2h'"""
    what = ctx.o.get("--was")
    if what and ":" in what and what.split(":")[0] in rules.AMMO_CAPACITY:
        combat.ammo_pick_up(s, ctx.z, ctx.target_name, what, ctx.prot)
    elif what and what.startswith("Leitung"):
        nz = int(what.split(":")[1]) if ":" in what else 1
        if ctx.zk.get("leitung_assets", 0) < nz:
            raise rules.Violation(f"On {ctx.z['karte']} there are not {nz} Phone Line(s)")
        ctx.zk["leitung_assets"] -= nz
        ctx.z["leitungen"] = ctx.z.get("leitungen", 0) + nz
        ctx.prot.append(f"{ctx.target_name} picks up {nz} Phone Line(s) [4.3.4, 5.1.6]")
    elif what:
        # L71 [RULE 5.1.6 p.32] 'One Command to have a unit pick up any ammo, assets and casualties in their card area':
        # several items in one order, comma separated; 'Casualty:<n>' for several casualties
        for part in [x.strip() for x in what.split(",") if x.strip()]:
            if part.lower().startswith("casualty:"):
                for _ in range(int(part.split(":")[1])):
                    pick_up(s, ctx.z, ctx.target_name, "Casualty", ctx.prot)
            else:
                pick_up(s, ctx.z, ctx.target_name, part, ctx.prot)
        if ctx.z.get("traegt_casualties", 0) > state.steps(ctx.z):
            raise rules.Violation(
                f"{ctx.target_name} can carry at most {state.steps(ctx.z)} casualties (1 per step) [RULE 5.1.6A p.32]"
            )
    mark(ctx.z, "Exposed")
    ctx.prot.append(f"{ctx.target_name}: pick up/load, Exposed [5.1.6]")


def _order_rally(s, ctx):
    """Order handler for: akt == '4.2.3a'"""
    if not state.pinned(ctx.z):
        raise rules.Violation(f"{ctx.target_name} is not Pinned [RULE 4.2.3a p.24]")
    if fire.vof_against(s, ctx.z["karte"], ctx.z["seite"]) is None or ctx.success == "ja":
        ctx.z["status"].remove("Pinned")
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


def _order_convert_team(s, ctx):
    """Order handler for: akt in ('4.2.3b', '4.2.3c', '4.2.3d')"""
    from_ = {"4.2.3b": "Paralyzed Team", "4.2.3c": "Litter Team", "4.2.3d": "Fire Team"}[ctx.akt]
    to_ = {"4.2.3b": "Litter Team", "4.2.3c": "Fire Team", "4.2.3d": "Assault Team"}[ctx.akt]
    if ctx.z["typ"] != from_ or state.pinned(ctx.z):
        raise rules.Violation(f"{ctx.target_name} must be an Unpinned {from_} [RULE {ctx.rule}]")
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


def _order_flip_to_front(s, ctx):
    """Order handler for: akt == '4.2.3f'"""
    if not state.fire_team_side(ctx.z) or state.pinned(ctx.z):
        raise rules.Violation(f"{ctx.target_name} must be Unpinned on its Fire Team side [RULE 4.2.3f p.24]")
    if fire.vof_against(s, ctx.z["karte"], ctx.z["seite"]) is None or ctx.success == "ja":
        ctx.z["status"].remove("Fire Team side")
        ctx.prot.append(
            f"Flip {ctx.target_name} to its front side (experience back to {ctx.z.get('erfahrung', 'Line')}) [6.5.1]"
        )
    else:
        ctx.prot.append(f"{ctx.target_name}: Flip failed")
        s["letzter_versuch"] = [ctx.target_name, ctx.akt, s["phase"]]


def _order_detach_team(s, ctx):
    """Order handler for: akt == '4.2.3g'"""
    if not state.good_order(ctx.z) or not (
        (ctx.z["typ"] == "Squad" and state.steps(ctx.z) >= 3)
        or (ctx.z["typ"] == "Weapons Team" and state.steps(ctx.z) == 2)
    ):
        raise rules.Violation("Detach Team: Good Order squad with 3-4 steps or 2-step Weapons Team [RULE 4.2.3g p.24]")
    team = ctx.o.get("--team", "Assault") + " Team"
    ctx.z["steps"] = state.steps(ctx.z) - 1
    new = new_name(s, team)
    s["einheiten"][new] = combat.new_lat(ctx.z, team, ctx.target_name)
    s["einheiten"][new]["status"] = []
    ctx.prot.append(f"{ctx.target_name} down to {ctx.z['steps']} steps, place {new} on {ctx.z['karte']}")


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
    del s["einheiten"][ctx.target_name]
    ctx.prot.append(
        f"{ctx.target_name} out of play, {sq} up to {q['steps']} steps (check experience on the Multi-Step Chart)"
    )


def _order_reconstitute_squad(s, ctx):
    """Order handler for: akt == '4.2.3i'"""
    teams = [ctx.target_name] + [t for t in ctx.o.get("--mit", "").split(",") if t]
    sq = ctx.o.get("--squad")
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
    if ctx.success == "ja":
        for t in teams:
            del s["einheiten"][t]
        s["removed_from_play"].remove(sq)
        s["einheiten"][sq] = {
            "typ": "Squad",
            "seite": "US",
            "platoon": ctx.z.get("platoon"),
            "erfahrung": ctx.o.get("--erfahrung", "Green"),
            "karte": ctx.z["karte"],
            "bereich": ctx.z["bereich"],
            "status": [],
            "steps": len(teams),
            "ziel": None,
            "vof_rating": "S",
            "reichweite": "L",
            "letzter_step": "Fire Team",
        }
        ctx.prot.append(
            f"{sq} back in play with {len(teams)} steps; experience per Multi-Step Unit Experience Chart from the teams (Assault Line, others Green), here {ctx.o.get('--erfahrung', 'Green')} [6.5.2]"
        )
        fire.open_fire(s, ctx.prot, only=[sq])
    else:
        ctx.prot.append("Reconstitute failed")
        s["letzter_versuch"] = [ctx.target_name, ctx.akt, s["phase"]]


def _order_4_2_3j(s, ctx):
    """Order handler for: akt == '4.2.3j'"""
    if not ctx.z.get("fire_team_seite") or state.fire_team_side(ctx.z):
        raise rules.Violation("Only units with a named Fire Team side [RULE 4.2.3j p.24]")
    mark(ctx.z, "Fire Team side")
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
    if not [m for m in state.units_on(s, zt, "Feind") if s["einheiten"][m].get("spotted")]:
        raise rules.Violation(f"No Spotted enemy on {zt} [RULE 4.2.4b p.25]")
    if ctx.o.get("--jam") == "ja" and jam_prone(ctx.z):
        jam(s, ctx.target_name, ctx.prot)
        ctx.success = "nein"
    elif ctx.success == "ja":
        ze = ctx.o.get("--einheit")
        if not ze:
            raise rules.Violation(
                f"Specify --unit=<target enemy> (stack under a cover marker or random unit without cover on {zt})"
            )
        state.unit(s, ze)  # validates the name
        for _m in enemy.cf_stack(s, ze):
            s["einheiten"][_m]["cf"] = s["einheiten"][_m].get("cf", 0) + 1
        ctx.prot.append(
            f"Concentrated Fire marker on {ze} (stack: {', '.join(enemy.cf_stack(s, ze))}; -1 NCM, cumulative; 2 ammo with ammo tracking) [7.11]"
        )
        if combat.ammo(ctx.z):
            combat.ammo_use(s, ctx.target_name, ctx.z, 1, "successful Concentrate Fire", ctx.prot)  # [RULE 7.11.3 p.56]
    else:
        ctx.prot.append("Concentrate Fire failed")
        s["letzter_versuch"] = [ctx.target_name, ctx.akt, s["phase"]]


def _order_grenade_attack(s, ctx):
    """Order handler for: akt == '4.2.4d'"""
    zt = check_grenade(s, ctx.z, ctx.target_name, ctx.o)
    if zt != ctx.z["karte"] and state.is_v4(s):
        if (
            "Rifle Grenade" in ctx.z.get("assets", [])
            and ctx.z.get("vof_rating") != "G"
            and not ctx.z.get("grenade_ranged")
        ):
            ctx.z["assets"].remove("Rifle Grenade")
            ctx.prot.append(f"{ctx.target_name}: Rifle Grenade used up (1 shot, hit or not) [7.6 p.54]")
        elif combat.ammo(ctx.z):
            combat.ammo_use(s, ctx.target_name, ctx.z, 1, "ranged Grenade Attack", ctx.prot)  # [RULE 8.1 p.61 box]
        if state.is_mortar(ctx.z) and not fire.is_firing(ctx.z):
            ctx.z["ziel"], ctx.z["nur_pdf"] = zt, True
            ctx.prot.append(
                f"{ctx.target_name} (Mortar Team) lays its own PDF to {zt} (counts for Crossfire, removed in Clean Up) [7.3.2 p.53]"
            )
        if ctx.o.get("--jam") == "ja" and jam_prone(ctx.z):
            jam(s, ctx.target_name, ctx.prot)
            ctx.success = "nein"
    if ctx.success == "ja" and zt == ctx.z["karte"] and state.is_v4(s):
        campaign.book_xp(
            s,
            campaign.xp_table(s, "pb_granate") or 1,
            f"successful Point Blank Grenade Attack ({ctx.target_name})",
            ctx.prot,
        )
    if ctx.success == "ja":
        ze = ctx.o.get("--einheit")
        if not ze:
            raise rules.Violation("--unit=<target enemy or cover stack>")
        f = state.unit(s, ze)
        value = int(ctx.o.get("--wert", -4))
        under = f.get("bereich", "offen") != "offen"
        # [RULE 7.10.1 p.54] "Direct a Grenade Attack at one specific unit out of cover or a stack of units under a Cover marker" (L112)
        stack = grenade_stack(s, ze)
        critical = ctx.o.get("--kritisch") == "ja"
        for m in stack:
            g = s["einheiten"][m]
            g.setdefault("grenade", []).append(value)
            if critical and under:
                g["grenade_critical"] = True
            elif critical:
                g["grenade"].append(value)
        where = f" (stack under {f['bereich']})" if under else ""
        ctx.prot.append(f"Grenade VOF {value} on {', '.join(stack)}{where} (cumulative) [7.10.1, 7.10.6]")
        if critical:
            ctx.prot.append(
                f"Critical Hit: use the combined Grenade/Critical Hit marker instead of the plain Grenade VOF marker (E61); the stack loses the benefit of cover {f['bereich']} in Combat Effects [7.10.3 p.55]"
                if under
                else f"Critical Hit: a second Grenade VOF marker on {ze} (both count) [7.10.3 p.55]"
            )
        grenade_back_notes(s, ctx.z, stack, True, ctx.prot)
    else:
        state.card(s, zt)["grenade_miss"] = True
        ctx.prot.append(f"Grenade Miss Modifier (-1) on {zt} [7.10.4]")
        ze = ctx.o.get("--einheit")
        grenade_back_notes(s, ctx.z, grenade_stack(s, ze) if ze else state.units_on(s, zt, "Feind"), False, ctx.prot)
        s["letzter_versuch"] = [ctx.target_name, ctx.akt, s["phase"]]


def _order_call_for_fire(s, ctx):
    """Order handler for: akt == '4.2.4i'"""
    zt = ctx.o["--ziel"]
    if ctx.success == "ja":
        place = ctx.o.get("--platz", zt)
        if ctx.o.get("--short") == "ja":
            place = short_place(s, ctx.z, zt, ctx.o)
        if s.get("fm_werte") and "Illum" in ctx.agency:
            # [RULE 7.16.2E p.58, 9.2 p.70] Illumination: on any terrain card, without LOS, immediately, no Pending
            iv = (s.get("illum_werte") or {}).get(ctx.agency)
            if ctx.o.get("--illum"):
                top_value, _, un = ctx.o["--illum"].partition("/")
                iv = {"oben": int(top_value), "unten": int(un) if un else None}
            if not iv:
                raise rules.Violation(
                    f"Illumination values for {ctx.agency} not recorded: read them off the marker, --illum=<top>/<bottom> [9.2]"
                )
            state.card(s, place).setdefault("illum", []).append(
                {"oben": iv["oben"], "unten": iv.get("unten"), "quelle": ctx.agency}
            )
            if isinstance(s.get("feuermissionen"), dict):
                s["feuermissionen"][ctx.agency] -= 1
            ctx.prot.append(
                f"Illumination marker {iv['oben']:+d}"
                + (f"/{iv['unten']:+d}" if iv.get("unten") is not None else "")
                + f" ({ctx.agency}) immediately on {place}"
                + (f" (Short instead of {zt})" if place != zt else "")
                + f"; Fire Missions: {s['feuermissionen']}; removed in Clean Up [RULE 7.16.2E p.58, 9.2 p.70]"
            )
            if place == zt and ctx.o.get("--target") != "nein":
                # [RULE 7.16.5 p.59 "after a successful Fire Mission"; BGG Shonai_Dweller 3520262: Illumination also moves the Target marker]
                old = s.setdefault("target_marker", {}).get(target_marker_key(s, ctx.agency))
                s["target_marker"][target_marker_key(s, ctx.agency)] = place
                ctx.prot.append(
                    f"Target marker ({ctx.agency} Concentration) on {place}"
                    + (f", moved from {old}" if old and old != place else "")
                    + " [RULE 7.16.5 p.59, BGG 3520262]"
                )
            fire.open_fire(s, ctx.prot)
        elif s.get("fm_werte"):
            value = int(ctx.o.get("--wert", s["fm_werte"][ctx.agency]))
            state.card(s, place).setdefault("extern", []).append(
                {"typ": "Pending", "wert": value, "quelle": ctx.target_name, "agentur": ctx.agency, "seite": "US"}
            )
            if isinstance(s.get("feuermissionen"), dict):
                s["feuermissionen"][ctx.agency] -= 1
            elif s.get("feuermissionen") != "unbegrenzt":
                s["feuermissionen"] -= 1
            bat = options.list_option(ctx.o, "--bataillon")
            if bat:
                gr = s.get("fm_gruppe", {}).get(ctx.agency, ctx.agency)
                if gr not in s.get("bataillon_fm", []):
                    raise rules.Violation(
                        f"Battalion Fire Mission for {gr} not available per mission [RULE 7.16.2B p.58]"
                    )
                if ctx.o.get("--short") == "ja" or len(bat) != 2 or len(set(bat)) != 2:
                    raise rules.Violation(
                        "Battalion Fire Mission: 3 Bursts symbol, two different cards adjacent to the target card: --battalion=K1,K2 [RULE 7.16.2B p.58]"
                    )
                for bk in bat:
                    if geometry.distance(s, zt, bk) != 1 or state.card(s, bk).get("staging"):
                        raise rules.Violation(
                            f"{bk} is not adjacent to {zt} (terrain card required) [RULE 7.16.2B p.58]"
                        )
                    state.card(s, bk).setdefault("extern", []).append(
                        {
                            "typ": "Pending",
                            "wert": value,
                            "quelle": ctx.target_name,
                            "agentur": ctx.agency,
                            "seite": "US",
                        }
                    )
                ctx.prot.append(
                    f"Battalion Fire Mission: additional Pending markers {ctx.agency} ({value:+d}) on {', '.join(bat)}, without observer LOS [RULE 7.16.2B p.58]"
                )
            ctx.prot.append(
                f"Pending Fire Mission Marker {ctx.agency} (value {value:+d}) on {place}"
                + (f" (Short, one card closer to the observer instead of {zt})" if place != zt else "")
                + f"; Fire Missions: {s['feuermissionen']}; becomes active in 3.7.1 (Incoming!), takes effect in 3.7.4, is removed in 3.7.1 of the following turn [RULE 7.16.3 p.59, 3.7.1 p.17]"
            )
            if place == zt or state.option(s, "U13_target_marker_bei_short"):
                if ctx.o.get("--target") != "nein":
                    old = s.setdefault("target_marker", {}).get(target_marker_key(s, ctx.agency))
                    s["target_marker"][target_marker_key(s, ctx.agency)] = place
                    ctx.prot.append(
                        f"Target marker ({ctx.agency} Concentration) on {place}"
                        + (f", moved from {old}" if old and old != place else "")
                        + "; later calls of this firing unit on this card +1 card [RULE 7.16.5 p.59, FM1 p.42]"
                    )
            else:
                ctx.prot.append(
                    "Short: Target marker not moved automatically (7.16.5 does not cover this case)"
                    + state.open_reading(s, "U13_target_marker_bei_short")
                )
        else:
            state.card(s, place).setdefault("extern", []).append(
                {"typ": "Pending", "wert": int(ctx.o.get("--wert", s.get("fm_wert", -3))), "quelle": ctx.target_name}
            )
            s["feuermissionen"] -= 1
            ctx.prot.append(
                f"Pending Fire Mission Marker on {place} (value {ctx.o.get('--wert', s.get('fm_wert', -3))}), Fire Mission crossed off ({s['feuermissionen']} left); active from 3.7.1 of this turn [RULE 3.7.1 p.17, FM1 p.44]. On 'Short!': one card closer to the observer (--place) [7.16.3, 7.16.4]"
            )
    else:
        ctx.prot.append("Call for Fire failed, no Fire Mission used")
        s["letzter_versuch"] = [ctx.target_name, ctx.akt, s["phase"]]


def _order_indirect_lay(s, ctx):
    """Order handler for: akt == '4.2.4j'"""
    indirect_lay(s, ctx.hq_name, ctx.orig_name, ctx.orig, ctx.target_name, ctx.z, ctx.o, ctx.prot, ctx.gi)


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
    if not fire.is_firing(ctx.z):
        raise rules.Violation(f"{ctx.target_name} is not firing [RULE 4.2.4k p.26]")
    kk = ctx.z["karte"]
    # [RULE 4.3.1 p.27 note] "the order will be passed on to all occupants of a card (including Pinned units)" (L114, K21)
    stopped = []
    for n, e in s["einheiten"].items():
        if e["seite"] == "US" and e["karte"] == kk and fire.is_firing(e):
            stopped.append(f"{n} (at {fire.effective_fire_target(s, n)})")
            e["ziel"] = None
            e.pop("konzentriert", None)
    ctx.prot.append(
        f"Cease Fire: all firing units on {kk} cease fire: {', '.join(stopped)}; they reopen fire immediately when a Spotted enemy is in LOS and range [4.3.1 p.27, 6.3.3]"
    )
    fire.open_fire(s, ctx.prot)


def _order_shift_fire(s, ctx):
    """Order handler for: akt == '4.2.4l'"""
    zt = ctx.o.get("--ziel")
    if not zt or not fire.is_firing(ctx.z):
        raise rules.Violation("Shift Fire: --target=<card in LOS>, unit must be firing [RULE 4.2.4l p.26]")
    state.card(s, zt)
    if [m for m in state.units_on(s, zt, "Feind") if not s["einheiten"][m].get("spotted")] and not state.units_on(
        s, zt, "US"
    ):
        raise rules.Violation("Cards with Unspotted enemies may not be fired at [6.3.3]")
    ok, reason = geometry.los(
        s, ctx.orig["karte"], zt, ha=geometry.height_bonus(s, ctx.orig), hb=geometry.card_height_bonus(s, zt, "Feind")
    )
    if not ok:
        raise rules.Violation(f"Originator has no LOS to {zt}: {reason}")
    kk = ctx.z["karte"]
    for n, e in s["einheiten"].items():
        if (
            e["seite"] == "US"
            and e["karte"] == kk
            and fire.is_firing(e)
            and geometry.in_range(s, e, zt)  # L114: passed on to all occupants of the card [4.3.1 p.27]
        ):
            e["ziel"] = zt
            e.pop("konzentriert", None)
    ctx.prot.append(
        f"Shift Fire: units on {kk} now fire at {zt} (move PDF)" + fire.pdf_note(s, kk, zt, None) + " [6.3.3]"
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
        execute_pyro(s, ctx.z, ctx.target_name, ctx.o, ctx.prot)
    else:
        ctx.prot.append(f"{ctx.target_name} uses pyrotechnics (effect per Mission Log) [4.4]")


def _order_4_2_1d(s, ctx):
    """Order handler for: akt == '4.2.1d'"""
    hq_n = ctx.o.get("--hq")
    if not hq_n or hq_n not in s.get("removed_from_play", []):
        raise rules.Violation("Specify --hq=<Removed from Play PLT HQ> [RULE 4.2.1d p.22]")
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
    hand_over_step(s, ctx.target_name, ctx.prot, (ctx.o.get("--team") or "Fire").capitalize())


def _order_4_2_1e(s, ctx):
    """Order handler for: akt == '4.2.1e'"""
    raise rules.Violation(
        "Reconstitute the CO HQ is given by the BN HQ in the BN HQ Impulse: fof.py order BN <unit> 4.2.1e [RULE 6.5.2 p.50]"
    )


ORDER_HANDLERS = {
    "4.2.2a": _order_move,
    "4.2.2c": _order_move,
    "4.2.2b": _order_move_platoon,
    "4.2.2d": _order_move_platoon,
    "4.2.2e": _order_seek_cover,
    "4.2.2f": _order_move_within_card,
    "4.2.2g": _order_move_within_card,
    "4.2.2h": _order_pick_up,
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
    "4.2.4d": _order_grenade_attack,
    "4.2.4i": _order_call_for_fire,
    "4.2.4j": _order_indirect_lay,
    "4.2.1l": _order_4_2_1l,
    "4.2.4k": _order_cease_fire,
    "4.2.4l": _order_shift_fire,
    "4.2.1b": _order_4_2_1b,
    "4.2.1c": _order_4_2_1c,
    "4.2.1d": _order_4_2_1d,
    "4.2.1e": _order_4_2_1e,
}


def cmd_order(s, args, late_order=None):
    """4.2: one order. nachtrag=<HQ>: late order for an HQ whose impulse already ended this turn (L78)."""
    hq_name, target_name, akt = args[0], args[1], args[2]
    o = options.parse_opts(args[3:])
    agency = None
    if hq_name == "BN":
        return order_bn(s, target_name, akt, o)
    s["_befehl_opts"] = o
    if state.is_v4(s):
        contact.mine_lock(s)
        if akt in ("4.2.1g", "4.2.1h") and target_name in s.get("runner_box", []):
            return order_runner_box(s, hq_name, target_name, akt, o)
    if s["phase"] not in rules.IMPULSES:
        raise rules.Violation(f"Orders only in the Friendly Command Phase 3.3, currently {s['phase']} [RULE 3.3 p.15]")
    if s.get("aktiver_hq") != hq_name and not late_order:
        raise rules.Violation(f"Active HQ is {s.get('aktiver_hq')}, not {hq_name}")
    if akt not in rules.ACTIONS:
        raise rules.Violation(f"Action {akt} not in the table. Known: {', '.join(rules.ACTIONS)}")
    if (
        akt in ("4.2.2a", "4.2.2b", "4.2.2c", "4.2.2d")
        and o.get("--ziel")
        and o["--ziel"] in s["karten"]
        and not s["karten"][o["--ziel"]].get("staging")
    ):
        _z = state.unit(s, target_name)
        _mit = (
            [_z]
            if akt in ("4.2.2a", "4.2.2c")
            else [
                e
                for e in s["einheiten"].values()
                if e["seite"] == "US"
                and e["karte"] == _z["karte"]
                and e.get("platoon") == _z.get("platoon")
                and "Exposed" not in e["status"]
                and e["typ"] not in ("Litter Team", "Paralyzed Team")
            ]
        )
        _st = sum(
            e["steps"]
            for e in s["einheiten"].values()
            if e["seite"] == "US" and e["karte"] == o["--ziel"] and e["typ"] != "Casualty"
        ) + sum(e["steps"] for e in _mit)
        if _st > 16:
            raise rules.Violation(
                f"Stacking: {o['--ziel']} would have {_st} US steps, at most 16 per card [RULE 5.1.5 p.32]"
            )
    name, cost, draw_kind, originator_kind, rule = rules.ACTIONS[akt]
    gi = hq_name == "GI"
    z = state.unit(s, target_name)
    if z["seite"] != "US":
        raise rules.Violation("Orders only to friendly units")
    if gi:
        orig_name = o.get("--originator", target_name)
        if akt in rules.HQ_REQUIRED_UNDER_GI and orig_name == target_name and not state.is_hq(z):
            raise rules.Violation(
                f"{name} needs an HQ/Staff even under General Initiative: --originator=<HQ> [RULE 4.1.1 p.19, Clarification 3]"
            )
        if originator_kind in ("PLT", "CO_BN", "CO_ONLY") and orig_name == target_name:
            raise rules.Violation(f"{name} needs the responsible HQ as originator (--originator=<HQ>) [RULE {rule}]")
        orig = state.unit(s, orig_name)
        if originator_kind == "CO_ONLY" and not (orig.get("ebene") == "CO" and orig["typ"] == "HQ"):
            raise rules.Violation(f"{name}: originator only the CO HQ [RULE {rule}]")
    else:
        orig_name, orig = hq_name, state.unit(s, hq_name)
        if originator_kind == "PLT" and not (orig["typ"] == "HQ" and orig.get("ebene") == "PLT"):
            raise rules.Violation(f"{name} may only be ordered by a PLT HQ [RULE {rule}]")
        if originator_kind == "CO_BN" and orig.get("ebene") not in ("CO", "BN"):
            raise rules.Violation(f"{name} may only be ordered by the CO HQ or BN HQ [RULE {rule}]")
        if originator_kind == "CO_ONLY" and not (orig.get("ebene") == "CO" and orig["typ"] == "HQ"):
            raise rules.Violation(f"{name}: originator only the CO HQ [RULE {rule}]")
        if state.fire_team_side(orig) and target_name != hq_name:
            raise rules.Violation(f"{hq_name} on its Fire Team side may only order itself [RULE 4.1.4 p.20]")
    if originator_kind == "CO":
        # [RULE 4.2.1l p.22] Originator 'CO HQ or CO Staff (or PLT HQ in a single-platoon mission)', Recipient 'The HQ itself'
        if not (
            orig.get("ebene") == "CO" or orig["typ"] == "Staff" or (s.get("einzelzug") and orig.get("ebene") == "PLT")
        ):
            raise rules.Violation(
                f"{name}: only CO HQ or CO Staff (PLT HQ only in single-platoon missions) [RULE {rule}]"
            )
        if target_name != orig_name:
            raise rules.Violation(f"{name}: recipient is the HQ itself [RULE {rule}]")
    if orig_name != target_name:
        if akt not in ("4.2.4k", "4.2.4l", "4.2.4j"):
            comms.chain_of_command(s, orig_name, target_name)
        if akt != "4.2.4j":
            comms.communication(s, orig_name, target_name, akt)
    ex = s.get("exhort_frei")
    after_exhort = bool(
        ex and ex[0] == target_name and ex[1] == akt and ex[2] == s["phase"] and o.get("--gratis") == "ja"
    )
    if o.get("--gratis") == "ja" and not after_exhort:
        raise rules.Violation(
            "--free=yes only for the effect of a successful Exhort (4.2.1b) with the same unit and action [RULE 4.2.1b p.22]"
        )
    already = [] if late_order else s["impuls_aktionen"].setdefault(target_name, [])
    if akt in already and akt != "4.2.2f" and not after_exhort:
        raise rules.Violation(
            f"{target_name} has already carried out '{name}' in this impulse; only Move within a Card may be repeated [RULE 4.2 p.21]"
        )
    comms.action_allowed(z, target_name, akt)
    k = s["kommandos"][hq_name]
    if k["verfuegbar"] + (0 if gi else k["gespart"]) < cost and not after_exhort:
        raise rules.Violation(
            f"{hq_name} has {k['verfuegbar'] + (0 if gi else k['gespart'])} Commands, action costs {cost} [RULE {rule}]"
        )
    success = o.get("--erfolg")
    skill = o.get("--skill")
    skill_text = None
    if skill:
        if skill not in SKILL_AUTO and skill != "Extra Draw":
            raise rules.Violation(f"Skill in an order: {', '.join(list(SKILL_AUTO) + ['Extra Draw'])} [RULE 12.7 p.82]")
        if skill in SKILL_AUTO and akt not in SKILL_AUTO[skill]:
            raise rules.Violation(f"{skill} only applies to {', '.join(SKILL_AUTO[skill])} [Player Aid 2, Skills]")
        holder = skill_holder(s, target_name, skill)
        if skill in SKILL_AUTO:
            success = "ja"
            skill_text = (
                f"Skill {skill} of {holder}: attempt automatically successful; Commands are spent anyway"
                + (", draw cards only for Critical Hit/Jam" if akt in ("4.2.4b", "4.2.4d") else ", no cards needed")
                + " [RULE 12.7 p.82]"
            )
        s["einheiten"][holder]["skills"].remove(skill)
        skill_text = (
            skill_text or f"Skill Extra Draw from {holder}: one more card [Player Aid 2]"
        ) + "; hand in the Skill marker"
    if after_exhort and success != "ja":
        raise rules.Violation("After a successful Exhort enter the effect with --success=yes --free=yes")
    if o.get("--short") == "ja":
        success = "ja"  # [RULE 7.16.4 p.59] 'Short' takes precedence; the Pending marker is placed anyway
    prot, moved = [], []
    if skill_text:
        prot.append(skill_text)
    zk = state.card(s, z["karte"])
    mods = []
    base_cff = None
    if akt == "4.2.4i":
        base_cff, extra_cff, agency = cff_precheck(s, z, target_name, orig_name, o)
    if draw_kind in ("attempt", "cover", "cff") or (
        draw_kind == "attempt_vof" and fire.vof_against(s, z["karte"], z["seite"]) is not None
    ):
        extra = 0
        if akt == "4.2.4i":
            extra = extra_cff
            if extra:
                mods = [(f"Target marker {agency} on {o['--ziel']}", extra)]
        if akt == "4.2.4a":
            target_k = o.get("--ziel")
            if not target_k:
                raise rules.Violation("Spot: specify --target=<card with Unspotted enemies> [4.2.4a]")
            state.card(s, target_k)
            if not [m for m in state.units_on(s, target_k, "Feind") if not s["einheiten"][m].get("spotted")]:
                raise rules.Violation(f"There is no Unspotted enemy on {target_k} [8.5]")
            if zk.get("staging"):
                raise rules.Violation("No spotting from the Staging Area [8.5 Note]")
            ok, reason = geometry.los(
                s,
                z["karte"],
                target_k,
                ha=geometry.height_bonus(s, z),
                hb=geometry.card_height_bonus(s, target_k, "Feind"),
            )
            if not ok:
                raise rules.Violation(f"No LOS from {z['karte']} to {target_k}: {reason}")
            mods = comms.spot_modifiers(s, z, target_k)
            extra = sum(m for _, m in mods)
        if akt == "4.2.4d":
            check_grenade(s, z, target_name, o)
        if skill == "Extra Draw":
            extra += 1
            mods = list(mods) + [("Skill Extra Draw", 1)]
        if akt == "4.2.2c" and o.get("--ziel") and success not in ("ja", "nein"):
            check_move(
                s, z, target_name, o["--ziel"], akt
            )  # L120: legality (5.1.4 VOF on origin or destination) before the draw
        if akt not in ("4.2.2d",) and success not in ("ja", "nein"):
            n_cards, who, base = comms.card_count(s, akt, orig, z, extra, base_cff)
            word = {
                "4.2.2c": "Infiltrate symbol",
                "4.2.2g": "Infiltrate symbol",
                "4.2.2e": "word Cover",
                "4.2.4a": "Crosshairs",
                "4.2.4b": "Crosshairs",
                "4.2.4d": "Grenade symbol (2 or more: Critical Hit, --critical=yes)",
                "4.2.4i": "Burst symbol (also 3 Bursts; 'Short!' takes precedence)",
            }.get(akt, "word Rally")
            msg = f"{name}: draw {n_cards} Action cards (base {base}" + (
                ""
                if akt == "4.2.4a"
                else f", experience {comms.experience(who)} of the {'originator' if akt.startswith('4.2.3') else 'recipient'}"
            )
            if mods:
                msg += ", " + ", ".join(f"{t} {m:+d}" for t, m in mods) + (", minimum 1" if akt == "4.2.4a" else "")
            msg += (
                f"); success on {word}. Then --success=yes|no"
                + (" (on 'Short' --short=yes)" if akt == "4.2.4i" and s.get("fm_werte") else "")
                + f" [RULE 4.2 p.21, {rule}]"
            )
            raise rules.Violation(msg)
    # ---------------- Movement
    ctx = types.SimpleNamespace(
        agency=agency,
        akt=akt,
        moved=moved,
        success=success,
        after_exhort=after_exhort,
        gi=gi,
        hq_name=hq_name,
        k=k,
        cost=cost,
        late_order=late_order,
        name=name,
        o=o,
        orig=orig,
        orig_name=orig_name,
        prot=prot,
        rule=rule,
        z=z,
        target_name=target_name,
        zk=zk,
    )
    handler = ORDER_HANDLERS.get(akt)
    if handler:
        handler(s, ctx)
    elif order_v4(s, hq_name, target_name, akt, o, orig, prot):
        pass
    else:
        raise rules.Violation(f"Action {akt} not implemented yet")
    moved, success = ctx.moved, ctx.success
    if after_exhort:
        s["exhort_frei"] = None
    elif o.get("--gratis") != "ja":
        pay_commands(s, hq_name, cost, rule)
    for n in moved or [target_name]:
        if not after_exhort and not late_order:
            s["impuls_aktionen"].setdefault(n, []).append(akt)
    ak = fire.update_activity(s)
    if ak:
        prot.append(ak)
    s.pop("_befehl_opts", None)
    txt = ("Late order for the impulse of " + late_order + ": " if late_order else "") + (
        f"{hq_name} orders {target_name}: {name}"
        + (f" to {o['--ziel']}" if o.get("--ziel") else "")
        + (f", attempt {success}" if success else "")
        + (f" (with {', '.join(moved)})" if len(moved) > 1 else "")
        + f"; cost {0 if o.get('--gratis') == 'ja' else cost}, remaining {k['verfuegbar']}+{k['gespart']}"
    )
    state.save_state(s, txt + "; " + "; ".join(prot), rule)
    print(f"{messages.ALLOWED} {messages.rule(rule)}")
    print(txt)
    briefing.print_board(prot, s)


def cmd_fire(s, args):
    n, target = args[0], args[1]
    e = state.unit(s, n)
    prot = []
    if target == "aus":
        e["ziel"] = None
        e.pop("ziel_offen", None)
        e.pop("konzentriert", None)
        prot.append(f"{n} no longer fires (correction)")
    else:
        state.card(s, target)
        if e.get("ziel_offen") and target not in e["ziel_offen"]:
            raise rules.Violation(f"{target} not among the candidates {', '.join(e['ziel_offen'])}")
        e["ziel"] = target
        e.pop("ziel_offen", None)
        prot.append(
            f"{n} fires at {target}"
            + (
                ""
                if target == e["karte"]
                else f", PDF from {e['karte']} to {target}" + fire.pdf_note(s, e["karte"], target, n)
            )
        )
    ak = fire.update_activity(s)
    if ak:
        prot.append(ak)
    state.save_state(s, "; ".join(prot), "6.1.1 p.39")
    briefing.print_board(prot, s)


def execute_pyro(s, z, name, o, prot):
    type_ = o.get("--asset")
    if not type_ or type_ not in z.get("assets", []):
        raise rules.Violation(
            f"{name}: specify --asset=<type>; carries {', '.join(z.get('assets', [])) or 'no pyro asset'} [4.2.1c p.22]"
        )
    if not (state.good_order(z) or (z["typ"] in ("Assault Team", "Fire Team") and not state.pinned(z))):
        raise rules.Violation("Recipient: Good Order unit or unpinned Assault/Fire Team [4.2.1c p.22]")
    zk = o.get("--ziel", z["karte"])
    state.card(s, zk)
    if type_ in rules.PYRO_AERIAL:
        if zk != z["karte"] and not geometry.adjacent(s, z["karte"], zk):
            raise rules.Violation("Aerial pyrotechnics on the own card or an adjacent card [4.4 p.30]")
    elif zk != z["karte"]:
        raise rules.Violation("Non-aerial (smoke) only on the own card [4.4 p.30]")
    z["assets"].remove(type_)
    if type_ == "Handheld Illumination":
        iv = (s.get("illum_werte") or {}).get(type_) or {"oben": -1, "unten": None}
        state.card(s, zk).setdefault("illum", []).append(
            {"oben": iv["oben"], "unten": iv.get("unten"), "quelle": type_}
        )
        prot.append(
            f"Hand Held Illumination {iv['oben']:+d} on {zk} (this card only), immediately; removed in Clean Up [4.4, 9.2 p.70, Marker E34]"
        )
        fire.open_fire(s, prot)
        return
    if type_ in ("HC Smoke", "WP Smoke"):
        w = o.get("--wert")
        if w is None:
            raise rules.Violation(
                f"{type_}: read the cover value from the marker (UNVERIFIED) and specify --value=<n> [4.4.3 p.31]"
            )
        state.card(s, zk).setdefault("extern", []).append(
            {"typ": "Smoke", "wert": int(w), "quelle": type_, "seite": "US"}
        )
        prot.append(
            f"{type_} on {zk} (cover +{w} against everything except Incoming/Air Strike/Mines/Grenade; blocks LOS out of and through {zk}; removed in Clean Up) [4.4.3 p.31, 5.4 p.38]"
        )
        for n, e in s["einheiten"].items():
            if e["karte"] == zk and fire.is_firing(e) and e["ziel"] != zk:
                e["ziel"] = None
                prot.append(f"{n} loses LOS out of the card, remove PDF [5.4]")
        return
    code = s.get("pyro_belegung", {}).get(type_)
    prot.append(
        f"{type_} on {zk} fired"
        + (f", Mission Log: {code}" if code else ", no assignment (no effect)")
        + " [4.4.1 p.30]"
    )
    if not code:
        return
    state.card(s, zk).setdefault("pyro", []).append(type_)  # display only; removed in Clean Up (3.8), no VOF
    # [RULE 4.4.1 p.30] Colored flares visible everywhere; colored smoke only with normal LOS to the card
    consequences = []
    for n, e in s["einheiten"].items():
        if e["seite"] != "US":
            continue
        if type_ in rules.PYRO_COLOR and not (e["karte"] == zk or geometry.los(s, e["karte"], zk)[0]):
            continue
        if (
            not state.option(s, "U21_pyro_alle_einheiten")
            and state.is_hq(e)
            and n != name
            and hq_rank(e) < hq_rank(state.unit(s, name))
        ):
            continue
        consequences.append(n)
    zi = s.get("ziele", {})
    if code == "CF":
        for n in consequences:
            e = s["einheiten"][n]
            if fire.is_firing(e):
                e["ziel"] = None
                e.pop("konzentriert", None)
                prot.append(f"{n} ceases fire [4.2.4k]")
        fire.open_fire(s, prot)
        prot.append(
            "Cease Fire by signal: units with a Spotted enemy in LOS open fire again immediately per 6.1.1 [4.4.1 footnote]"
        )
        return
    targets_of = {}
    for n in consequences:
        e = s["einheiten"][n]
        if code == "M2S" and geometry.adjacent(s, e["karte"], zk):
            targets_of[n] = zk
        elif code in ("M2PO", "M2SO"):
            obj = zi.get("primaer" if code == "M2PO" else "sekundaer")
            if obj and geometry.adjacent(s, e["karte"], obj):
                targets_of[n] = obj
        elif code.startswith("M2RP"):
            rp = zi.get("route", {}).get(code[4:])
            if rp and geometry.adjacent(s, e["karte"], rp):
                targets_of[n] = rp
        elif code.startswith("XPL"):
            r = zi.get("phaselines", {}).get(code[3:])
            if r is not None and state.card(s, e["karte"])["reihe"] == r:
                k2 = geometry.card_at(s, r + 1, state.card(s, e["karte"])["spalte"])
                if k2:
                    targets_of[n] = k2
        elif code in ("InfAP2PO", "InfAP2SO"):
            obj = zi.get("primaer" if code == "InfAP2PO" else "sekundaer")
            if obj and e["karte"] == zi.get("ap"):
                targets_of[n] = obj
    result = {}
    for t in (o.get("--erfolg") or "").split(","):
        if ":" in t:
            a, b = t.split(":")
            result[a] = b
    for n, zk2 in targets_of.items():
        e = s["einheiten"][n]
        akt = "4.2.2c" if code.startswith("Inf") else "4.2.2a"
        try:
            check_move(s, e, n, zk2, akt)
        except rules.Violation as v:
            prot.append(f"{n} cannot follow the signal: {v}")
            continue
        if akt == "4.2.2c" and result.get(n) not in ("ja", "nein"):
            raise rules.Violation(
                "infiltration by signal: every unit draws 2 cards (own experience): --success="
                + ",".join(f"{m}:yes|no" for m in targets_of)
                + " [4.4.1 p.30]"
            )
        move_unit(s, n, zk2, None, exposed=(akt == "4.2.2a" or result.get(n) == "nein"), prot=prot)
    if not targets_of:
        prot.append("no unit meets the requirement of the signal")


def hq_rank(e):
    return {"BN": 0, "CO": 1}.get(e.get("ebene"), e.get("rang", 9) if e["typ"] == "Staff" else 5)


def order_v4(s, hq_name, target_name, akt, o, orig, prot):
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
    k = s["kommandos"][hq_name]
    if k["verfuegbar"] + (0 if hq_name == "GI" else k["gespart"]) < cost:
        raise rules.Violation(f"{hq_name} has too few Commands [RULE {rule}]")
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
            "status": ["Exposed"],
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
