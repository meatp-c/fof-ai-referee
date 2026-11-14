"""Potential contact, enemy packages and placement, external VOF markers, mines (8.1 to 8.4, 8.7)."""

import copy
import types

from . import briefing, combat, commands, enemy, events, fire, geometry, grenades, migrate, options, rules, state


def package_units(pk):
    """Units of a package: list 'units' (series rules, e.g. package 7 'Squad in Trench + LMG in Bunker') or flat package (basic game)."""
    if pk.get("units"):
        return pk["units"]
    if pk.get("unit") or pk.get("unit_choice"):
        return [pk]
    return []


def in_play_count(s, type_name):
    return sum(1 for e in s["units"].values() if e["side"] == "Enemy" and e.get("type_name") == type_name)


def cover_count(s, type_):
    return sum(1 for c in s["cards"].values() for cv in c.get("cover", []) if cv["type"] == type_)


def type_free(s, u, needed=None):
    """Free counter types for a package unit; 'unit_choice' = choose the type at random [FM1 p.48], type in use: take another [RULE 8.3 p.62]."""
    cm, needed = s.get("countermix", {}), needed or {}
    names = u.get("unit_choice") or [u["unit"]]
    return [
        n for n in names if in_play_count(s, n) + needed.get(n, 0) < (cm.get(n, 1) if cm.get(n, 1) is not None else 1)
    ]


def package_available(s, p, choice=None):
    """[RULE 8.3 p.62/63, FM1 p.48 'Respect the counter mix'] all counters and markers of the package must be free.
    Marker packages without a unit (Incoming) are occupied as long as their marker is on the board ('in_play')."""
    pk = s["packages"][p]
    if pk.get("choice"):
        return any(
            all(type_free(s, u) for u in opt_) for opt_ in pk["choice"].values()
        )  # campaign: package with a choice (Normandy package 5)
    units = [u for u in package_units(pk) if not u.get("optional_r") and not u.get("only_if_available")]
    if not units and "place_vof" in pk:
        return True
    if not units:
        return not pk.get("in_play")
    cm = s.get("countermix", {})
    needed, cover_needed = {}, {}
    for u in units:
        free = type_free(s, u, needed)
        if choice and u.get("unit_choice"):
            free = [x for x in free if x == choice]
        if not free:
            return False
        needed[free[0]] = needed.get(free[0], 0) + 1
        if u.get("cover"):
            cover_needed[u["cover"]] = cover_needed.get(u["cover"], 0) + 1
    return all(
        cover_count(s, t) + n <= cm[t] for t, n in cover_needed.items() if cm.get(t) is not None
    )  # limit only cover types counted in the counter mix (Basic Cover unlimited); null = not recorded


def enemy_pdf_or_vof(s, k):
    """[RULE 8.4.3 p.63] 'cannot place a package on a card which is along the PDF of another enemy unit or if it has an enemy VOF marker'."""
    for n, e in s["units"].items():
        if e["side"] == "Enemy" and fire.is_firing(e) and e["target"] != e["card"]:
            if k in (geometry.line_between(s, e["card"], e["target"]) or []) + [e["target"]]:
                return f"along the PDF of {n}"
    for x in state.card(s, k).get("external", []):
        if x.get("side") == "Enemy" or any(pk.get("name") == x.get("source") for pk in s.get("packages", {}).values()):
            return "enemy VOF marker"
    return None


def valid_places(s, pk, card_id):
    out = []
    units = package_units(pk) or [pk]
    without_pb = all(u.get("cover") in rules.STRUCTURES for u in units)
    hi = min(rules.RANGE_CARDS.get((u.get("range") or "L").split("-")[-1], 2) for u in units)
    series = enemy.series_rules(s)  # one predicate for the series-rules placement restrictions
    for k, c in s["cards"].items():
        if pk.get("row") and c["row"] != pk["row"]:
            continue
        if c.get("staging") or state.units_on(s, k, "Enemy"):
            continue
        if state.units_on(s, k, "US") and k != card_id and not (series and without_pb):
            continue  # [RULE 8.4.3 p.63] '(unless Point Blank fire is not possible for the units in the package)'
        if series and without_pb and k == card_id:
            continue  # a bunker cannot fire Point Blank, but must be able to open fire on the trigger card
        if k != card_id:
            if (
                geometry.distance(s, k, card_id) > hi
                or not geometry.los(s, k, card_id, hb=geometry.card_height_bonus(s, card_id, "US"))[0]
            ):
                continue
            if any(state.units_on(s, between, "US") for between in (geometry.line_between(s, k, card_id) or [])):
                continue
        if series and enemy_pdf_or_vof(s, k):
            continue
        out.append(k)
    return out


def cmd_pc(s, args):
    """pc | pc <card> | pc reveal|set <card> <letter> | pc clear <card> | pc contact <card> <package> [..] (8.2-8.4).
    a switch over the sub-commands; each one is its own function."""
    if args and args[0] in ("reveal", "set") and cmd_pc_campaign(s, args):
        return None
    if not args:
        return pc_overview(s)
    if args[0] not in ("contact", "clear"):
        return pc_draw_info(s, args[0])
    if args[0] == "clear":
        return pc_clear(s, args)
    return pc_contact(s, args)


def pc_overview(s):
    """pc: the PC markers on cards with friendly units, by letter."""
    open_ = sorted(
        (k for k, c in s["cards"].items() if c.get("pc") and state.units_on(s, k, "US")),
        key=lambda k: (str(s["cards"][k]["pc"]), k),
    )  # by PC letter like the 3.7.2 list
    print(
        "PC markers with friendly units: "
        + (", ".join(f"{k} (PC {s['cards'][k]['pc']})" for k in open_) if open_ else "none")
    )


def pc_draw_info(s, card_id):
    """pc <card>: legality of resolving the PC marker and the draw instructions [8.2.4, 8.3]."""
    c = state.card(s, card_id)
    if not c.get("pc"):
        raise rules.Violation(f"{card_id} has no PC marker")
    if not state.units_on(s, card_id, "US"):
        raise rules.Violation(
            f"{card_id}: a PC marker is only resolved with a friendly unit on the card [RULE 8.2.4 p.62]"
        )
    if s["phase"] != "3.7.2":
        print(f"Note: PC resolution belongs in 3.7.2, currently {s['phase']}")
    # E39 (the player 07.10.2026): reveal ?-markers only on cards with friendly units (8.2.4; developer AAR BGG 2585005)
    if "?" in (c.get("pc"), c.get("pc2")) or any(
        "?" in (cc.get("pc"), cc.get("pc2")) for other_id, cc in s["cards"].items() if state.units_on(s, other_id, "US")
    ):
        raise rules.Violation(
            "First reveal the PC markers showing '?' on cards with friendly units: fof.py pc reveal <card> <A|B|C> [RULE 8.2.4 p.62, E39]"
        )
    higher = [k for k, cc in s["cards"].items() if cc.get("pc") and state.units_on(s, k, "US") and cc["pc"] < c["pc"]]
    if higher:
        raise rules.Violation(f"First resolve the higher letters: {', '.join(higher)} [RULE 8.2.4 p.62]")
    n = rules.PC_DRAWS[c["pc"]][s["activity"] or "No Contact"]
    print(
        f"PC {c['pc']} on {card_id} at {s['activity']}: "
        + (
            "Auto, contact without a draw"
            if n == 0
            else f"draw {n} Action cards (all), contact if one shows 'Contact' at the top"
        )
        + " [8.2.4, Charts 1]"
    )
    tab = s.get("package_table", {}).get("PC " + c["pc"], {})
    if (
        s.get("counterattack")
        and c["pc"] == "A"
        and s.get("package_table_counterattack")
        and state.option(s, "U28_counterattack_all_pc_a")
    ):
        tab = s["package_table_counterattack"]["PC A"]
        print(
            "Counter-attack active: PC A uses the Counter-Attack list"
            + state.open_reading(s, "U28_counterattack_all_pc_a")
            + " [Normandy M1 MSR 1 p.19]"
        )
    print(
        "On contact: draw an Action card, column PC "
        + c["pc"]
        + ": "
        + "; ".join(
            f"R# {v} = package {p} ({s['packages'][p]['name']}, {'free' if package_available(s, p) else 'IN USE'})"
            for p, v in tab.items()
            if p in s["packages"]
        )
    )
    if state.is_campaign(s):
        rt = s.get("direction_table", {})
        print(
            f"Package that cannot be placed: draw again (8.3 p.63, Normandy p.19; E6); if none can be placed, no contact. Direction per unit on the friendly card: R# column {rt.get('column', 8)}: "
            + ", ".join(f"{b} {v}" for b, v in rt.items() if b != "column")
            + " [8.4.2 p.63]. Then fof.py pc contact <card> <package> --direction=.. (the tool names any further inputs)"
        )
    elif state.company(s):
        print(
            "Occupied package drawn: ignore the draw and choose from the placeable packages (E6, FM1 p.48); if none can be placed, no contact. Squad type (A or A/S) at random [FM1 p.48]."
        )
    else:
        print(
            "Occupied package drawn: ignore the draw and draw again until an available package comes up (8.3); FM1 p.26 instead allows choosing from the available ones; if none can be placed, no contact."
        )


def pc_clear(s, args):
    """pc clear <card>: no contact, the PC marker is removed [8.2.4]."""
    rules.need(args, 2, "pc clear <card>")  # usage names the English word the CLI knows
    card_id = args[1]
    c = state.card(s, card_id)
    if not c.get("pc"):
        raise rules.Violation(f"{card_id} has no PC marker")
    old = c["pc"]
    state.clear_pc(c)
    state.save_state(s, f"PC {old} on {card_id}: no contact, PC marker removed", "8.2.4 p.62")
    print(f"No contact on {card_id}. Remove the PC marker [8.2.4].")
    print(briefing.check_stamp(s))


def pc_contact(s, args):
    """pc contact <card> <package> [--place=..] [--direction=..]: place the package (campaign: pc_contact_campaign) [8.3, 8.4]."""
    rules.need(args, 3, "pc contact <card> <package> [--place=..] [--direction=..]")
    card_id, package = args[1], args[2]
    o = options.parse_opts(args[3:])
    c = state.card(s, card_id)
    if not c.get("pc"):
        raise rules.Violation(f"{card_id} has no PC marker")
    pk = s.get("packages", {}).get(package)
    if not pk:
        raise rules.Violation(f"Package {package} unknown")
    if not state.units_on(s, card_id, "US"):
        raise rules.Violation(
            f"{card_id}: a PC marker is only resolved with a friendly unit on the card [RULE 8.2.4 p.62, 3.7.2 p.17]"
        )
    if "place_vof" in pk:
        if c.get("pc") == "?":
            raise rules.Violation("Reveal the PC marker first: fof.py pc reveal <card> <A|B|C>")
        return pc_contact_campaign(s, card_id, package, pk, o)
    if not package_available(s, package):
        raise rules.Violation(f"Package {package} not available (counter mix); ignore the draw [8.3 p.63, FM1 p.26]")
    prot = []
    pc_old = c["pc"]
    units = package_units(pk)
    if units:
        place = o.get("--place", card_id if pk["place"].startswith("trigger") else None)
        valid = valid_places(s, pk, card_id)
        if not place:
            raise rules.Violation(
                f"Package {package} ('{pk['place']}'): valid cards {', '.join(valid) if valid else 'NONE (redraw the package; if none can be placed, remove the PC marker without contact)'}; draw a random card, column {len(valid)}, and --place=<card> [8.4.3]"
            )
        state.card(s, place)
        if place not in valid:
            raise rules.Violation(
                f"{place} is not a valid place (row, LOS, range, enemies, friendly units in between, enemy PDF/VOF). Valid: {', '.join(valid) or 'none'} [8.4.3 p.63]"
            )
        types_ = series_counter_types(s, units, o, prot)  # split for readability
        new_units = [
            place_series_unit(s, u, type_name, place, card_id, package, pk, pc_old, prot)
            for u, type_name in zip(units, types_)
        ]
        contact_tail(s, new_units, prot, pdf_needs_vof=False)
    else:
        c.setdefault("external", []).append(
            {"type": "Incoming", "value": pk.get("value", -3), "source": pk["name"], "side": "Enemy"}
        )
        prot.append(
            f"{pk['name']}: Incoming marker (VOF {pk.get('value', -3)}) active on {card_id}, takes effect in this Combat Effects Segment; blocks LOS out of {card_id} [8.10, 5.4]"
        )
        fire.cease_fire_on_los_loss(s, prot)  # also fire THROUGH the card (5.4)
    pk["in_play"] = True
    state.clear_pc(c)  # a second marker on the card stays
    prot.append(f"Remove PC marker from {card_id} [8.2.4]")
    activity_note = fire.update_activity(s)
    if activity_note:
        prot.append(activity_note)
    state.save_state(
        s, f"Contact on {card_id}: package {package} {pk['name']}; " + "; ".join(prot), "8.3 p.62, 8.4.3 p.63"
    )
    print("CONTACT [RULE 8.3 p.62, 8.4.3 p.63]")
    briefing.print_board(prot, s)


def series_counter_types(s, units, o, prot):
    """series rules packages: the counter type of each unit (a free one; several free: random by --type, FM1 p.48)."""
    needed, types_ = {}, []
    for u in units:
        free = type_free(s, u, needed)
        if u.get("unit_choice") and len(free) > 1:
            w = o.get("--type")
            if w not in free:
                raise rules.Violation(
                    f"Choose the squad type at random (R#/{len(free)}): {', '.join(free)}; then --type=<counter name> [FM1 p.48]"
                )
            prot.append(f"Squad type at random: {w} [FM1 p.48]")
            free = [w]
        elif u.get("unit_choice") and len(free) == 1 and len(u["unit_choice"]) > 1:
            prot.append(f"Squad type: only {free[0]} is free, this one is taken [RULE 8.3 p.62]")
        needed[free[0]] = needed.get(free[0], 0) + 1
        types_.append(free[0])
    return types_


def place_series_unit(s, u, type_name, place, card_id, package, pk, pc_old, prot):
    """series rules packages: one enemy unit on its card, with cover marker and fire at the trigger card [8.3, 8.4.3]."""
    values_ = dict(u)
    values_.update(u.get("variants", {}).get(type_name, {}))
    fname = commands.new_name(s, type_name, reuse_removed=True)
    cid = None
    if values_.get("cover"):
        cid = commands.new_cover_marker(s, place, values_["cover"], values_.get("cover_value", 1))
        cv = next(x for x in state.card(s, place)["cover"] if x["id"] == cid)
        if values_.get("cover_capacity"):
            cv["capacity"] = values_["cover_capacity"]
        if values_["cover"] in rules.STRUCTURES and place != card_id:
            cv["direction"] = list(geometry.direction(s, place, card_id))
        prot.append(f"{values_['cover']} marker {cid} (+{values_.get('cover_value', 1)}) on {place}")
    e = {
        "type": values_.get("type", "Weapons Team"),
        "type_name": type_name,
        "side": "Enemy",
        "experience": values_.get("experience", "Line"),
        "card": place,
        "area": cid or "open",
        "status": [],
        "steps": values_.get("steps", 1),
        "vof_rating": values_["vof_rating"],
        "range": values_.get("range", "L"),
        "spotted": bool(pk.get("spotted", values_.get("spotted"))),
        "package": package,
        "pc_origin": pc_old,
        "fire_team_side": values_.get("fire_team_side", values_.get("steps", 1) == 1),
        "ft_vof": values_.get("ft_vof", "S"),
        "last_step": values_.get("last_step"),
        "target": None,
        "no_point_blank": values_.get("cover") in rules.STRUCTURES,
    }
    if values_.get("breakdown_note"):
        e["breakdown_note"] = values_["breakdown_note"]
    s["units"][fname] = e
    if values_.get("cover") in rules.STRUCTURES:
        e["bunker_direction"] = card_id
        prot.append(
            f"Point the bunker arrow at {card_id}; fires only in this direction, never Point Blank; redraw Shift Fire results [5.3.2]"
        )
    prot.append(
        f"Enemy {fname} ({type_name}, VOF {values_['vof_rating']}, {values_.get('steps', 1)} steps) on {place}"
        + (f" under {cid}" if cid else " without cover")
        + (", Spotted" if e["spotted"] else ", place an Unspotted marker")
    )
    e["target"] = card_id
    prot.append(
        f"{fname} opens fire on {card_id}"
        + ("" if place == card_id else f", PDF from {place} to {card_id}" + fire.pdf_note(s, place, card_id, fname))
        + " [8.4.3]"
    )
    return fname


def contact_tail(s, new_units, prot, pdf_needs_vof=True):
    """After the units of a package are placed:
    PC markers their PDFs fire over are removed [RULE 8.4.4], friendly units on a placement card with a Spotted enemy shift
    to Point Blank [RULE 6.1.2] and return fire opens [RULE 6.1.1]; Unspotted enemies draw no fire [RULE 8.5].
    pdf_needs_vof=False keeps the series rules reading: every placed PDF counts, also one without a VOF (G! unit, Deep Bunker)."""
    for fname in new_units:
        e = s["units"][fname]
        has_pdf = fire.is_firing(e) if pdf_needs_vof else e.get("target") is not None
        if has_pdf and e["target"] != e["card"]:
            for between in geometry.line_between(s, e["card"], e["target"]) or []:
                cb = state.card(s, between)
                if cb.get("pc") and cb.get("elevation", 1) == state.card(s, e["card"]).get("elevation", 1):
                    state.clear_pc(cb, promote=False)
                    prot.append(f"PC marker on {between} removed (fired over) [8.4.4]")
    for fname in new_units:
        e = s["units"][fname]
        if not e["spotted"]:
            continue
        for m, f in s["units"].items():
            if (
                f["side"] == "US"
                and f["card"] == e["card"]
                and fire.is_firing(f)
                and f["target"] != e["card"]
                and not geometry.no_point_blank(s, f)
            ):
                # the old PDF ceases (the campaign copy kept the Concentrated Fire flag and the other
                # fire fields of the old target), then the unit fires Point Blank
                fire.cease_fire(f)
                f["target"] = e["card"]
                prot.append(f"{m} shifts fire to its own card (Point Blank), the old PDF lapses [6.1.2]")
    if any(s["units"][f]["spotted"] for f in new_units):
        fire.open_fire(s, prot)
    elif new_units:
        prot.append("Enemy Unspotted: no return fire, spot it first [8.5, 6.1.1]")


def cmd_external(s, args):
    rules.need(
        args, 2, "external <card> <Incoming|Mines|AirStrike|Smoke|Pending> <value> [<source>] | external <card> remove"
    )
    card_id = args[0]
    c = state.card(s, card_id)
    prot = []
    if args[1] in ("remove", "away"):  # the words the usage and the CLI name
        c["external"] = []
        prot.append(f"external VOF on {card_id} removed")
    else:
        rules.need(args, 3, "external <card> <type> <value> [<source>]")
        type_, value = args[1], rules.int_value(args[2], "VOF value")
        if type_ not in ("Incoming", "Mines", "AirStrike", "Smoke", "Pending"):
            raise rules.Violation("Type: Incoming | Mines | AirStrike | Smoke | Pending")
        c.setdefault("external", []).append(
            {"type": type_, "value": value, "source": args[3] if len(args) > 3 else type_}
        )
        prot.append(f"{type_} {value} on {card_id}")
        if type_ in ("Incoming", "AirStrike", "Smoke"):
            fire.cease_fire_on_los_loss(s, prot)  # also fire THROUGH the card (5.4)
    activity_note = fire.update_activity(s)
    if activity_note:
        prot.append(activity_note)
    state.save_state(s, "; ".join(prot), "5.4 p.38")
    briefing.print_board(prot, s)


def cmd_enemy(s, args):
    rules.need(args, 1, "enemy <unit> spotted|unspotted|pinned|unpinned|remove|card=<card>|cover=<id>|steps=<n>")
    name = args[0]
    f = state.unit(s, name)
    if f["side"] != "Enemy":
        raise rules.Violation(f"{name} is not an enemy unit")
    prot = []
    for a in args[1:]:
        a = (
            "remove"
            if a in ("remove", "away", *migrate.german("remove"))
            else ("card=" + a.partition("=")[2] if a.partition("=")[0] in migrate.german("card") else a)
        )
        if a == "spotted":
            for m in state.units_on(s, f["card"], "Enemy"):
                s["units"][m]["spotted"] = True
            prot.append(f"Enemies on {f['card']} Spotted (per card) [8.5]")
            fire.open_fire(s, prot)
        elif a == "unspotted":
            if f.get("type_name") != "Sniper" and not f.get("out_of_ammo"):
                prot.append("WARNING: only snipers and Out-of-Ammo Fire Teams become Unspotted again [8.8, 8.11.1]")
            for m in state.units_on(s, f["card"], "Enemy"):
                s["units"][m]["spotted"] = False
            prot.append(f"Enemies on {f['card']} Unspotted")
        elif a == "pinned":
            commands.mark(f, rules.PINNED)
            prot.append(f"{name} Pinned (its VOF becomes 'All Pinned' +2)")
        elif a == "unpinned":
            f["status"] = [x for x in f["status"] if x != rules.PINNED]
            prot.append(f"{name} Pinned removed")
        elif a == "remove":
            enemy.remove_enemy(s, name, prot, reason="correction/removal")
            break
        elif a.startswith("card="):
            state.card(s, a[5:])
            # the one enemy move path (ammo surplus, Deep Bunker left, fire after move, mine check); the
            # correction command leaves the unit in the open, cover= sets the marker explicitly
            enemy.move_enemy(s, name, a[5:], prot, cover=False)
        elif a.startswith("cover="):
            grenades.grenade_expires(s, f, name, prot)
            commands.set_area(s, f, a[6:])
            prot.append(f"{name} under {a[6:]}")
        elif a.startswith("steps="):
            f["steps"] = rules.int_value(a[6:], "steps")
            prot.append(f"{name} {f['steps']} steps")
        else:
            raise rules.Violation(f"Unknown entry {a}")
    activity_note = fire.update_activity(s)
    if activity_note:
        prot.append(activity_note)
    state.save_state(s, "; ".join(prot), None)
    briefing.print_board(prot, s)


def mines_on(s, card_id):
    return [x for x in state.card(s, card_id).get("external", []) if x["type"] == "Mines"]


def engineers_clear(s, e):
    """[Normandy CSR 10 p.16]: Good Order Engineers with 2 or 3 steps clear paths (1 card after a successful infiltration)."""
    return bool(e.get("engineer")) and state.good_order(e) and state.steps(e) >= 2


def request_mine_check(s, names, card_id, prot, reason, cards=3, path_=False):
    if not mines_on(s, card_id):
        return
    names = [n for n in names if n in s["units"] and s["units"][n]["type"] not in ("Casualty",)]
    if not names:
        return
    s.setdefault("mine_checks", [])
    info = s.setdefault("mine_check_info", {})
    for n in names:
        if n not in s["mine_checks"]:
            s["mine_checks"].append(n)
        info[n] = {"cards": cards, "path": path_}
    if path_:
        prot.append(
            f"mine check on {card_id} ({reason}) for {', '.join(names)}: {cards} action card(s), hit on a Burst icon; without a hit the path is marked and the Mines marker comes off; then fof.py mine <unit> yes|no [CSR 10 p.16, 7.9.1 p.54]"
        )
    else:
        prot.append(
            f"mine check on {card_id} ({reason}) for {', '.join(names)}: {cards} action card(s) per unit, hit on a Burst icon (also multi-burst and Short); then fof.py mine <unit> yes|no [7.9.1 p.54]"
        )


def cmd_mine(s, args):
    rules.need(args, 2, "mine <unit> yes|no")
    n, result = args[0], args[1]
    if n not in s.get("mine_checks", []):
        raise rules.Violation(f"No mine check pending for {n}")
    e = state.unit(s, n)
    s["mine_checks"].remove(n)
    info = s.get("mine_check_info", {}).pop(n, {})
    prot = []
    if result == "yes":
        e["mine_hit"] = True
        for x in mines_on(s, e["card"]):
            x["active"] = True
        prot.append(
            f"{n} hit by a mine: flip the Mines marker to its explosion side, {n} under it; Mines! VOF -4 in 3.7.4; may not move within the card or to an adjacent card this turn [7.9.1 p.54]"
            + ("; path marking failed, the mines stay [CSR 10 p.16]" if info.get("path") else "")
        )
    elif result == "no":
        if info.get("path"):
            k = state.card(s, e["card"])
            k["external"] = [x for x in k.get("external", []) if x["type"] != "Mines"]
            prot.append(f"{n}: no mine hit, path marked: remove the Mines marker from {e['card']} [CSR 10 p.16]")
        else:
            prot.append(f"{n}: no mine hit")
    else:
        raise rules.Violation("yes | no")
    if s["phase"] == "3.6" and s.get("at36"):
        from . import vehicles  # the vehicle action continues after the mine check

        vehicles.resume(s, prot)  # purge, advance and name the next step
    activity_note = fire.update_activity(s)
    if activity_note:
        prot.append(activity_note)
    state.save_state(s, "; ".join(prot), "7.9.1 p.54")
    briefing.print_board(prot, s)


def mine_lock(s):
    reveal_lock(s)
    if s.get("heat_open"):
        raise rules.Violation(
            "First the Heat Casualties draws: "
            + ", ".join(s["heat_open"])
            + " (fof.py heat <unit> <R#/4 value>, only 1 is a loss) [Naktong M1 p.17]"
        )
    if s.get("mine_checks"):
        raise rules.Violation(
            "First resolve the pending mine checks: "
            + ", ".join(s["mine_checks"])
            + " (fof.py mine <unit> yes|no) [7.9.1 p.54, 8.7.1 p.67]"
        )


def reveal_lock(s):
    """[RULE 5.2 p.34]: the next step waits until the face-down cards in LOS are flipped (terrain entered)."""
    open_ = geometry.reveal_candidates(s)
    if open_:
        dep = geometry.reveal_dependencies(s, open_)
        now = sorted(k for k in open_ if k not in dep) or sorted(open_)
        raise rules.Violation(
            "First reveal the face-down cards in LOS: "
            + ", ".join(now)
            + (f" (then check again: {', '.join(sorted(dep))})" if dep and now != sorted(open_) else "")
            + " (fof.py terrain <card> <type>) [RULE 5.2 p.34, 5.2.2 p.35]"
        )


def cmd_pc_campaign(s, args):
    if args[0] == "reveal":
        rules.need(args, 3, "pc reveal <card> <A|B|C>")
        card_id, b = args[1], args[2]
        c = state.card(s, card_id)
        if b not in ("A", "B", "C"):
            raise rules.Violation("Letter A|B|C")
        prot = []
        if c.get("pc") == "?":
            c["pc"] = b
        elif c.get("pc2") == "?":
            c["pc2"] = b
        else:
            raise rules.Violation(f"{card_id} has no face-down PC marker")
        prot.append(f"PC marker on {card_id} revealed: {b}")
        if c.get("pc2") and c["pc"] != "?" and c["pc2"] != "?":
            high, deep = min(c["pc"], c["pc2"]), max(c["pc"], c["pc2"])
            c["pc"] = high
            c.pop("pc2")
            prot.append(f"two PC markers on {card_id}: the lower one ({deep}) is removed, {high} stays [8.2.3 p.62]")
        state.save_state(s, "; ".join(prot), "8.2.3 p.62")
        briefing.print_board(prot, s)
        return True
    if args[0] == "set":
        rules.need(args, 3, "pc set <card> <A|B|C|?>")
        card_id, b = args[1], args[2]
        c = state.card(s, card_id)
        if b not in ("A", "B", "C", "?"):
            raise rules.Violation("A|B|C|?")
        prot = [f"PC marker {b} on {card_id} (correction/event)"]
        if c.get("pc") and c["pc"] != "?" and b != "?":
            # two face-up markers on one card at once: 8.2.3 applies now, the lower one goes
            high, deep = min(c["pc"], b), max(c["pc"], b)
            c["pc"] = high
            prot.append(f"two PC markers on {card_id}: the lower one ({deep}) is removed, {high} stays [8.2.3 p.62]")
        elif c.get("pc"):
            c["pc2"] = b
        else:
            c["pc"] = b
        state.save_state(s, "; ".join(prot), "8.2.3 p.62")
        briefing.print_board(prot, s)
        return True
    return False


DIRECTION = {"Front": (1, 0), "Left Front": (1, -1), "Right Front": (1, 1), "Left": (1, -1), "Right": (1, 1)}


def check_placement(s, u, k, card_id, pk):
    """Placement restrictions 8.4.3 for a package unit on card k (trigger card_id)."""
    if state.units_on(s, k, "Enemy") and not u.get("_same_card_ok"):
        return f"{k}: enemies already there (8.4.3 'Other Enemy Units')"
    without_pb = (u.get("cover") in rules.STRUCTURES) or state.is_mortar(u)
    no_pdf = u.get("place") == "max_los" or not pk.get("place_vof", True) or not u.get("vof_rating")
    if k != card_id and state.units_on(s, k, "US") and not without_pb and not no_pdf:
        return (
            f"{k}: friendly units there (8.4.3)"  # only units that place a PDF (8.4.3 example 2: Spotter with US units)
        )
    if k != card_id and not no_pdf and not state.is_mortar(u):
        between = geometry.line_between(s, k, card_id) or []
        overhead = (u.get("vof_rating") == "H" or u.get("tripod")) and all(
            fire.overhead_possible(s, k, b, card_id) for b in between if state.units_on(s, b)
        )
        grazing = u.get("tripod") and all(
            state.card(s, b).get("elevation", 1) == state.card(s, k).get("elevation", 1) for b in between + [card_id]
        )
        if any(state.units_on(s, b, "US") for b in between) and not (overhead or grazing):
            return f"{k}: friendly units between {k} and {card_id} (8.4.3, no Grazing/Overhead Fire)"
        if any(state.units_on(s, b, "Enemy") for b in between) and not overhead:
            return f"{k}: own enemy units between {k} and {card_id} (8.4.3 example 1: only with Overhead Fire)"
    if enemy_pdf_or_vof(s, k):
        return f"{k}: {enemy_pdf_or_vof(s, k)} (8.4.3)"
    return None


def range_of(u):
    if u.get("place") == "max_los":
        return 3  # [RULE 8.4.3 p.63] Spotter/Patrol: Max LOS up to Very Long
    r = u.get("range") or "V"
    return rules.RANGE_CARDS.get(r.split("-")[-1], 3)


def building_table_ref(s, place):
    """R# column and source of the campaign's building table (Normandy CSR 8 p.15 column 8, Naktong CSR 6 p.14
    column 5), taken from the table itself instead of a fixed Normandy text."""
    tab = s.get("building_table", {}).get(state.card(s, place).get("building_table"), {})
    col = max((int(str(b).split("-")[-1]) for b in tab if str(b).split("-")[-1].isdigit()), default=8)
    ref = (s.get("building_table", {}).get("_source") or "CSR 8 S.15").split(",")[0].replace(" S.", " p.")
    return col, ref


def building_cover(s, place, r8, value_opt):
    """[CSR 8 p.15 Normandy, CSR 6 p.14 Naktong] Package in cover on Village/Farm/Cemetery/Church: R# on the building table; if the
    building value is equal to or better than the package cover, the unit goes inside; a worse result stays behind as a marker (BGG E21)."""
    tab = s.get("building_table", {}).get(state.card(s, place).get("building_table"), {})
    col, ref = building_table_ref(s, place)
    r8 = rules.int_value(r8, f"--building (R# column {col})")
    type_ = next((t for b, t in tab.items() if events.r_matches(b, r8)), None)
    if type_ is None:
        raise rules.Violation(f"R# {r8} not in the building table (column {col}) [{ref}]")
    upper_ = type_.endswith("*")
    type_ = type_.rstrip("*")
    w = s.get("cover_values", {}).get(type_)
    if w is None:
        if value_opt is None:
            raise rules.Violation(
                f"{type_}: cover value not recorded (UNVERIFIED); read it from the marker and give --building-value=<n> [{ref}]"
            )
        w = rules.int_value(value_opt, "--building-value")
    return type_, w, upper_


MORTAR_NO_FIRE_COVER = ("Light Building", "Strong Building", "Building", "Upper Story", "Church Tower")  # 7.3.1


def _building_table_cover(s, u, place, pk, o, building_list, cover_type, cover_value, prot):
    """Package in cover on a card with a building table: the building replaces the package cover if it is at least
    as good and the unit can fire from it; otherwise its marker stays on the card [CSR 8 p.15]. Returns the cover."""
    t = u["type_name"]
    if not building_list:
        col, ref = building_table_ref(s, place)
        raise rules.Violation(
            f"{t} in cover on {state.card(s, place)['terrain']}: R# column {col} on the building table, --building=<R#>[,..] [{ref}]"
        )
    building_type, building_value, upper_ = building_cover(s, place, building_list.pop(0), o.get("--building-value"))
    no_fire = u.get("mortar") and pk.get("place_vof", True) and building_type in MORTAR_NO_FIRE_COVER
    if building_value >= cover_value and no_fire:
        # E87/ [8.4.3 p.63, 7.3.1 p.52, BGG 3782765]: the package must be able to Open Fire on the trigger;
        # a mortar may not fire from building cover, so it keeps the cover of the package list
        prot.append(
            f"Building table gives {building_type} (+{building_value}), but a mortar may not fire from it (7.3.1): stays in {u['cover']} (8.4.3, E87)"
        )
        gid = commands.new_cover_marker(s, place, building_type, building_value)
        prot.append(f"{building_type} marker {gid} (+{building_value}) stays empty on {place} [CSR 8 p.15]")
    elif building_value >= cover_value:
        cover_type, cover_value = building_type, building_value
        prot.append(
            f"Building cover {building_type} (+{building_value}) instead of {u['cover']} [CSR 8 p.15]"
            + (
                " (Upper Story/Church Tower for Sniper/Spotter)"
                if upper_ and u["type"] in ("Sniper", "Spotter")
                else ""
            )
        )
    else:
        gid = commands.new_cover_marker(s, place, building_type, building_value)
        prot.append(
            f"Building {building_type} (+{building_value}) worse than {u['cover']}: marker {gid} stays on {place} (BGG E21)"
        )
    return cover_type, cover_value


def package_cover(s, u, idx, place, card_id, pk, o, building_list, cid_before, prot):
    """Cover marker of one package unit: with the previous/random squad, the package cover (building table, an existing
    free marker of the same kind), or none [8.4.3, CSR 8, E58]."""
    t = u["type_name"]
    cid = None
    if u["place"] == "with_previous" and cid_before.get(idx - 1) and not u.get("own_cover"):
        cid = cid_before[idx - 1]
    elif u["place"] == "with_random" and cid_before.get(u.get("_ref")) and not u.get("own_cover"):
        cid = cid_before[u["_ref"]]
    elif u.get("cover") and not u.get("no_cover") and not u.get("infiltration"):
        cover_type = u["cover"]
        cover_value = u.get("cover_value")
        if cover_value is None:  # take the value from the setup table instead of a silent +1 (audit C3)
            cover_value = s.get("cover_values", {}).get(cover_type)
        if cover_value is None:
            raise rules.Violation(
                f"Package unit {u.get('unit') or u.get('unit_choice')}: no value for cover marker {cover_type} (cover_value in the package or cover_values table)"
            )
        if state.card(s, place).get("building_table") and cover_type not in rules.STRUCTURES:
            cover_type, cover_value = _building_table_cover(
                s, u, place, pk, o, building_list, cover_type, cover_value, prot
            )
        # (E58): the same building/cover marker already lies free on the card: move in instead of a duplicate marker (5.3.3 Cover Potential)
        free = [
            x
            for x in state.free_cover(s, place, side="Enemy")
            if x["type"] == cover_type and x["value"] == cover_value and cover_type not in rules.STRUCTURES
        ]
        if free:
            cid = free[0]["id"]
            prot.append(
                f"{t} into the existing {cover_type} {cid} (+{cover_value}) on {place} (no second marker) [E58]"
            )
        else:
            cid = commands.new_cover_marker(s, place, cover_type, cover_value)
        cv = next(x for x in state.card(s, place)["cover"] if x["id"] == cid)
        if u.get("cover_capacity"):
            cv["capacity"] = u["cover_capacity"]
        if cover_type in rules.STRUCTURES and place != card_id:
            cv["direction"] = list(geometry.direction(s, place, card_id))
        if not free:
            prot.append(f"{cover_type} marker {cid} (+{cover_value}) on {place}")
    return cid


def package_unit(s, u, c, place, card_id, package, pk, cid, var, o, prot):
    """The unit record of one package unit: values of the package, attempt experience and ammo, spotter, infiltration
    attempt, Exposed [8.3, 8.4.3]."""
    t = u["type_name"]
    spotted = bool(u.get("spotted", pk.get("spotted")))
    e = {
        "type": u.get("type", "Weapons Team"),
        "type_name": t,
        "side": "Enemy",
        # the attempt plan may set the enemy experience (Naktong M1 p.15: Veteran, Veteran, Line, Green)
        "experience": s.get("enemy_experience_attempt") or u.get("experience", "Line"),
        "card": place,
        "area": cid or "open",
        "status": [],
        "steps": u.get("steps", 1),
        "vof_rating": u.get("vof_rating"),
        "range": u.get("range") or "L",
        "spotted": spotted,
        "package": package,
        "pc_origin": c.get("pc"),
        "fire_team_side": u.get("fire_team_side", u.get("steps", 1) == 1),
        "ft_vof": u.get("ft_vof") or "S",
        "last_step": u.get("last_step"),
        "target": None,
        "no_point_blank": u.get("cover") in rules.STRUCTURES,
    }
    if pk.get("human_wave"):
        e["human_wave"] = True  # [RULE 8.14 p.68]
    for f in (
        "ammo",
        "last_step_values",
        "ft_range",
        "mortar",
        "grenade_ranged",
        "tripod",
        "leader",
        "immobile",
        "breakdown_note",
        "spotter",
        "fj_breakdown",
        "breakdown",
        "rifle_grenades",
        "at_weapon",  # AT weapon (Vehicle and AT Weapons Chart) and Panzerfaust shots (Normandy M6 p.40)
        "panzerfaust",
        "vehicle",  # enemy tank (Naktong M1 package 10)
        "ambush",
    ):
        if u.get(f) is not None:
            e[f] = copy.deepcopy(u[f])
    from . import campaign  # local: campaign imports setup, which needs contact at import time

    _pm = (s.get("package_ammo") or {}).get(campaign.package_ammo_key(e))
    if _pm is not None and e.get("ammo"):  # package ammo per attempt (Naktong M1 p.18)
        e["ammo"]["points"] = e["ammo"]["start"] = _pm
    if e.get("spotter") or u.get("type") == "Spotter":
        e["spotter"] = True
        e["missions"] = (var or {}).get("missions", 2) - 1  # [BGG E19] the automatic first mission counts
        e["card_sequence"] = (var or {}).get("card_sequence", 3)
        e["fm_value"] = (var or {}).get("value", -3)
        s.setdefault("enemy_target", {})[t] = card_id
        # [RULE 8.10 p.68 'and Target marker if applicable as per 7.16.5']: announce the marker on the board too
        prot.append(f"Place the enemy Target marker ({t}) on {card_id} [8.10 p.68, 7.16.5]")
    if u.get("infiltration"):
        # base 2 cards adjusted for Experience (4.2: Veteran +1, Green -1); source per campaign
        # (Normandy CSR 6 p.14, Naktong CSR 3 p.13: 'drawing two cards (adjusted for Experience)')
        ref = pk.get("infiltration_rule") or "CSR 6 p.14"
        n_inf = 2 + {"Green": -1, "Veteran": 1}.get(e.get("experience"), 0)
        if o.get("--success") not in ("yes", "no"):
            raise rules.Violation(
                f"Infiltrate Attempt of the package: {n_inf} Action cards (2, experience {e['experience']}), success on the "
                f"Infiltrate symbol; --success=yes|no [{ref}, 4.2 p.21]"
            )
        if o["--success"] == "yes":
            free = state.free_cover(s, place, side="Enemy", steps=state.steps(e))
            if free:
                e["area"] = max(free, key=lambda x: x["value"])["id"]
            prot.append(
                "Infiltrate Attempt successful: not Exposed"
                + (f", under {e['area']}" if e["area"] != "open" else ", no free cover marker on the card")
                + f" [{ref}]"
            )
        else:
            commands.mark(e, rules.EXPOSED)
            prot.append(f"Infiltrate Attempt failed: without cover and Exposed [{ref}]")
    if u.get("exposed"):
        commands.mark(e, rules.EXPOSED)
        prot.append(f"{t}: Exposed, without cover [Normandy M3 p.27 'Squad marked Exposed out of cover']")
    return e


def package_structure(s, e, fname, cid, place, card_id, prot):
    """Deep Bunker (no VOF until it leaves) and Bunker/Pillbox fire arc of a placed unit [5.3.2]."""
    if cid and next(x for x in state.card(s, place)["cover"] if x["id"] == cid)["type"] == "Deep Bunker":
        e["deep_bunker"] = cid
        prot.append(
            f"{fname} in Deep Bunker {cid}: no VOF, no spotting, no Pyro, no grenades; leaves it on Fall Back or Grenade Attack in 3.4.2 (then --area=open) [{rules.DEEP_BUNKER_REF}]"
        )
    if cid and next(x for x in state.card(s, place)["cover"] if x["id"] == cid)["type"] in rules.STRUCTURES:
        e["bunker_direction"] = card_id
        prot.append(
            f"Arrow toward {card_id}; fires only in this direction, never Point Blank; redraw Shift results [5.3.2]"
        )


def package_open_fire(s, e, fname, place, card_id, pk, o, c, trigger, prot):
    """Place PDF/VOF of a placed unit [8.3, 8.4.3]: Place VOF No, Deep Bunker, forbidden position, the G! opening Grenade
    Attack, or fire at the trigger card. False if the weapon jammed (the unit left play)."""
    # Place PDF/VOF
    if not pk.get("place_vof", True):
        e["no_fire_until_clean_up"] = True
        prot.append(f"{fname}: Place PDF/VOF No, opens fire only in Clean Up [8.3 p.63]")
    elif e.get("deep_bunker"):  # no VOF and no target until it leaves the Deep Bunker
        prot.append(
            f"{fname} does not open fire from the Deep Bunker; it opens fire when it leaves [{rules.DEEP_BUNKER_REF}]"
        )
    elif fire.fire_position_forbidden(s, e):  # e.g. mortar placed in building cover (7.3.1)
        prot.append(f"{fname} does not open fire: {fire.fire_position_forbidden(s, e)}")
    elif e.get("vof_rating") == "G":
        g = o.get("--grenade")
        if g not in ("yes", "no"):
            n_cards = max(1, 2 + {"Green": -1, "Veteran": 1}.get(e.get("experience"), 0))  # 4.2 base 2 +/- experience
            raise rules.Violation(
                f"{fname} (G!) opens with a Grenade Attack on {card_id}: draw {n_cards} cards (base 2, experience {e.get('experience')}), Grenade symbol (watch for Jam); --grenade=yes|no [--unit=<target>] [--critical=yes] [--jam=yes] [8.4.3 p.63, 7.3.2]"
            )
        e["target"], e["pdf_only"] = card_id, True
        combat.ammo_use(s, fname, e, 1, "Grenade Attack at range", prot)
        if o.get("--jam") == "yes" and grenades.jam_prone(e):  # Jam as in the Activity Check path
            grenades.jam(s, fname, prot)
            return False  # jammed: the weapon is out of play, its steps became Fire Teams
        if g == "yes":
            target_unit_name = o.get("--unit") or (trigger[0] if len(trigger) == 1 else None)
            if not target_unit_name:
                raise rules.Violation(
                    "--unit=<target of the Grenade Attack> (stack under cover or random unit without cover)"
                )
            target_unit = enemy.grenade_target_check(s, card_id, target_unit_name, e)
            prot.append(f"{fname}: PDF to {card_id} [7.3.2 p.53]")
            # the whole stack under the cover marker, Critical Hit and 7.10.5 notes, as enemyaction
            enemy._apply_grenade_hit(
                s, types.SimpleNamespace(o=o, n=fname, e=e, prot=prot), target_unit_name, target_unit
            )
        else:
            c["grenade_miss"] = True
            prot.append(f"{fname}: PDF to {card_id}, Grenade Miss (-1) on {card_id} [7.10.4]")
    elif e.get("vof_rating"):
        e["target"] = card_id
        prot.append(
            f"{fname} opens fire on {card_id}"
            + ("" if place == card_id else f", PDF from {place} to {card_id}" + fire.pdf_note(s, place, card_id, fname))
            + (" (Small Arms on the card, Sniper VOF -3 on one target in 3.7.4)" if enemy.is_sniper(e) else "")
            + " [8.4.3]"
        )
    return True


def contact_place_units(s, c, units, card_id, o, package, pk, places, prot, trigger, var):
    """Part of pc_contact_campaign (extracted)."""
    new_units, cid_before = [], {}
    building_list = options.list_option(o, "--building")
    for idx, (u, place) in enumerate(zip(units, places)):
        t = u["type_name"]
        cid = package_cover(s, u, idx, place, card_id, pk, o, building_list, cid_before, prot)
        cid_before[idx] = cid
        e = package_unit(s, u, c, place, card_id, package, pk, cid, var, o, prot)
        fname = commands.new_name(s, t, reuse_removed=True)
        s["units"][fname] = e
        package_structure(s, e, fname, cid, place, card_id, prot)
        prot.append(
            f"Enemy {fname} ({t}, VOF {e['vof_rating']}, {e['steps']} step(s)"
            + (f", {e['ammo']['points']} {e['ammo']['type']}" if e.get("ammo") else "")
            + f") on {place}"
            + (f" under {e['area']}" if e["area"] != "open" else " without cover")
            + (", Spotted" if e["spotted"] else ", place Unspotted marker")
        )
        if package_open_fire(s, e, fname, place, card_id, pk, o, c, trigger, prot):
            new_units.append(fname)
    return new_units


def contact_place_markers(s, c, card_id, o, pk, prot, var):
    """Part of pc_contact_campaign (extracted)."""
    for mk in pk.get("marker", []):
        if mk["type"] == "Illum":
            # [Normandy M3 p.27, 9.2 p.70] Mortar Illumination on the trigger card
            iv = (s.get("illum_values") or {}).get(mk.get("source", "Mortar Illum"))
            if o.get("--illum"):
                top_value, _, un = o["--illum"].partition("/")
                iv = {
                    "top": rules.int_value(top_value, "--illum top value"),
                    "bottom": rules.int_value(un, "--illum bottom value") if un else None,
                }
            if not iv:
                raise rules.Violation(
                    "Read the illumination values (Mortar Illumination) from the marker: --illum=<top>/<bottom> [9.2]"
                )
            c.setdefault("illum", []).append(
                {"top": iv["top"], "bottom": iv.get("bottom"), "source": f"Enemy {mk.get('source', 'Mortar Illum')}"}
            )
            prot.append(
                f"Illumination marker {iv['top']:+d}"
                + (f"/{iv['bottom']:+d}" if iv.get("bottom") is not None else "")
                + f" on {card_id} (enemy, Mortar Illumination) [9.2]"
            )
            continue
        value = mk["value"] if mk["value"] is not None else (var or {}).get("value", -3)
        c.setdefault("external", []).append(
            {"type": mk["type"], "value": value, "source": pk["name"], "side": "Enemy", "active": mk["type"] != "Mines"}
        )
        if mk["type"] == "Mines":
            prot.append(
                f"Mines! marker (Draw 3 side, VOF {value}) on {card_id}; every unit on {card_id} checks immediately [8.7.1 p.67]"
            )
        else:
            prot.append(
                f"Incoming! marker (active, VOF {value}) on {card_id}; first fire mission automatic, blocks LOS out of {card_id} [8.10 p.68, 5.4]"
            )
            fire.cease_fire_on_los_loss(s, prot)  # also fire THROUGH the card (5.4)


def _is_spotter(u):
    return bool(u.get("spotter") or u.get("type") == "Spotter")


def _joined_place(units, idx, u, card_id, places, o):
    """Place of a unit that needs no direction: on the trigger card or with another unit of the package; else None."""
    m = u["place"]
    if m in ("pb", "trigger"):
        return card_id
    if m == "with_random":
        # [Naktong S.18 'place Leader with one random squad'] the Leader joins a squad drawn by R#
        squads = [i for i in range(idx) if units[i].get("type") == "Squad"]
        if not squads:
            raise rules.Violation(f"{u.get('unit')}: no squad in the package to join")
        pick = o.get("--leader-squad")
        if len(squads) == 1:
            u["_ref"] = squads[0]
        elif pick and pick.isdigit() and 1 <= int(pick) <= len(squads):
            u["_ref"] = squads[int(pick) - 1]
        else:
            raise rules.Violation(
                f"{u.get('unit')} joins a random squad: draw R# column {len(squads)} "
                f"(1-{len(squads)} = squad in the order of --direction); --leader-squad=<n>"
            )
        return places[u["_ref"]]
    if m == "with_squad":
        if o.get("--at") not in ("1", "2"):
            raise rules.Violation("HMG in bunker on the card of a squad: --at=1|2 (random) [Normandy M1 p.19]")
        return places[int(o["--at"]) - 1]
    if m == "with_previous":
        return places[idx - 1]
    return None


def _given_place(s, u, k, card_id, dir_name, hi):
    """Check a card named with --place. Returns True for a Point Blank placement on the trigger card [8.4.3 p.64]."""
    m = u["place"]
    state.card(s, k)
    if k == card_id and m != "close":
        # Point Blank placement on the trigger card if no card in the direction is valid
        if _is_spotter(u) or u.get("cover") in rules.STRUCTURES or state.is_mortar(u):
            raise rules.Violation(
                f"{u['unit']}: Point Blank placement on {card_id} not possible (spotter/structure/mortar) [8.4.3]"
            )
        return True
    if (
        geometry.direction(s, card_id, k) != DIRECTION[dir_name]
        or geometry.distance(s, card_id, k) > hi
        or (m == "close" and geometry.distance(s, card_id, k) != 1)
        or not geometry.los(s, k, card_id, hb=geometry.card_height_bonus(s, card_id, "US"))[0]
    ):
        raise rules.Violation(f"{k} is not in direction {dir_name} within LOS/range of {card_id} [8.4.2/8.4.3 p.63]")
    return False


def _place_in_direction(s, u, card_id, dir_name, hi, pk):
    """The farthest valid card in the direction (Close Range: the adjacent one) [8.4.2, 8.4.3]; a missing card that
    could have LOS asks for a map extension [8.4.5]."""
    m = u["place"]
    candidates, missing = [], None
    dr, dc = DIRECTION[dir_name]
    trigger_card = state.card(s, card_id)
    us_height = geometry.card_height_bonus(s, card_id, "US")
    los_ok, last = True, card_id  # LOS still open up to the last existing card?
    for d in [1] if m == "close" else range(1, hi + 1):
        place_id = geometry.card_at(s, trigger_card["row"] + dr * d, trigger_card["column"] + dc * d)
        if place_id is None:
            # extension only if a new card there could have LOS: chain so far in LOS and
            # (reading a: always, Hill possible) or (reading b: the last card lets LOS pass through it) [8.4.5, U19]
            if los_ok and (
                d == 1
                or state.option(s, "U19_extend_to_range")
                or geometry.see_through(state.card(s, last), (-dr, -dc), (dr, dc)) is not False
            ):
                missing = (trigger_card["row"] + dr * d, trigger_card["column"] + dc * d)
            break
        last = place_id
        los_ok = geometry.los(s, place_id, card_id, hb=us_height)[0]
        if not los_ok and not pk.get("place_vof", True) and not _is_spotter(u):
            # [RULE 8.4.3 p.63 'Max LOS for these units refers to the LOS of the triggering unit', 5.4]
            # a package without PDF counts the trigger's view INTO the card (Incoming/Smoke only block the view out)
            los_ok = geometry.los(s, card_id, place_id, ha=us_height)[0]
        if not los_ok and d > 1:
            break
        if los_ok and not check_placement(s, u, place_id, card_id, pk) and not state.card(s, place_id).get("staging"):
            candidates.append(place_id)
    if missing and (m == "close" or not candidates or state.option(s, "U19_extend_to_range")):
        raise rules.Violation(
            f"Direction {dir_name}: card row {missing[0]} column {missing[1]} missing; draw a terrain card and fof.py extend {missing[0]} {missing[1]} <type>, then repeat the contact"
            + ("" if m == "close" else state.open_reading(s, "U19_extend_to_range"))
            + " [8.4.5 p.65]"
        )
    if not candidates:
        raise rules.Violation(
            f"Direction {dir_name}: no valid card (LOS/range/8.4.3); redraw the direction, if none is possible, redraw the package [8.4.3 p.64]"
        )
    return candidates[-1]


PLACE_WORD = {"close": "Close Range", "max": "Max LOS/Range"}


def contact_choose_places(s, own, units, card_id, o, pk, places, place_list, prot, direction_list, rt):
    """The card of every unit of the package, in order: joined units first, then by direction (--direction, --place)."""
    for idx, u in enumerate(units):
        joined = _joined_place(units, idx, u, card_id, places, o)
        if joined is not None:
            places.append(joined)
            continue
        j = next(i for i, x in enumerate(own) if x is u)  # by identity, two equal units differ
        if j >= len(direction_list):
            raise rules.Violation(
                f"Direction per unit on its own card by R# column {rt.get('column', 8)} ({', '.join(f'{b} {v}' for b, v in rt.items() if b != 'column')}): --direction=Front|Left|Right[,..] [8.4.2 p.63]"
            )
        dir_name = direction_list[j]
        if dir_name not in DIRECTION:
            raise rules.Violation("Direction Front | Left | Right")
        hi = 3 if _is_spotter(u) else range_of(u)
        if place_list and j < len(place_list):
            k = place_list[j]
            if _given_place(s, u, k, card_id, dir_name, hi):
                places.append(k)
                continue
        else:
            k = _place_in_direction(s, u, card_id, dir_name, hi, pk)
        reason = check_placement(s, u, k, card_id, pk) if k not in places else None
        if reason:
            raise rules.Violation(reason + "; redraw the direction or the package [8.4.3 p.64]")
        places.append(k)
        prot.append(
            f"{u['type_name']}: direction {dir_name}, {PLACE_WORD.get(u['place'], 'Max LOS')} = card {k} [8.4.1-8.4.3 p.63]"
        )


def _package_extra(package, pk, units, o, prot):
    """The optional extra of a package (a unit or a marker on an R# band): --extra=yes|no. Returns (units, pk)."""
    opt_units = [u for u in units if u.get("optional_r")]
    opt_markers = [mk for mk in pk.get("marker", []) if mk.get("optional_r")]  # e.g. Sniper 'On R#1/3 also place Mines'
    if opt_units or opt_markers:
        extra_choice = o.get("--extra")
        extra = opt_units[0]["unit"] if opt_units else opt_markers[0]["type"]
        band = (opt_units or opt_markers)[0]["optional_r"]
        if extra_choice not in ("yes", "no"):
            raise rules.Violation(
                f"Package {package}: extra {extra} on R# {band} (random number column {band.rsplit('/', 1)[-1] if '/' in band else 2}, BGG B4): --extra=yes|no"
            )
        if extra_choice == "no":
            units = [u for u in units if not u.get("optional_r")]
            pk = dict(pk, marker=[mk for mk in pk.get("marker", []) if not mk.get("optional_r")])
        else:
            prot.append(f"R# {band}: {extra} added [8.3 p.62]")
    return units, pk


def _package_r_placement(package, pk, units, o, prot):
    """Placement mode of the units placed by R# (--r) [Normandy M1 p.19]."""
    rp = pk["r_place"]
    r = o.get("--r")
    if not r:
        raise rules.Violation(
            f"Package {package}: placement by R# column {rp.get('column', 10)} ({', '.join(f'{b}: {m}' for b, m in rp.items() if b != 'column')}); --r=<R#>"
        )
    r = rules.int_value(r, "--r")
    mode = next((m for b, m in rp.items() if b != "column" and events.r_matches(b, r)), None)
    if mode is None:
        raise rules.Violation(
            f"R# {r} is outside every band of the placement table ({', '.join(b for b in rp if b != 'column')})"
        )
    for u in units:
        if u.get("place") == "r":
            u["place"] = mode
    prot.append(f"R# {r}: placement {mode} [Normandy M1 p.19]")


def resolve_package_units(s, package, pk, o, prot):
    """Units of a package: random choice (--choice), optional extra on an R# band (--extra), only-if-available units,
    R#-dependent placement (--r) [8.3, Normandy M1 p.19]. Returns (units, pk); pk loses an optional marker on --extra=no."""
    if pk.get("choice"):
        w = o.get("--choice")
        if w not in pk["choice"]:
            raise rules.Violation(
                f"Package {package}: choice by R# ({' or '.join(pk['choice'])}) and --choice=<{'|'.join(pk['choice'])}> [8.3 p.62]"
            )
        units = copy.deepcopy(pk["choice"][w])
        prot.append(f"Random package choice: {w} [8.3 p.62]")
    else:
        units = copy.deepcopy(pk.get("units", []))
    units, pk = _package_extra(package, pk, units, o, prot)
    # only if available (leader)
    for u in list(units):
        if u.get("only_if_available") and in_play_count(s, u["unit"]) >= state.countermix_count(s, u["unit"]):
            units.remove(u)
            prot.append(f"{u['unit']} not available, omitted (p.19 'only if available')")
    if any(u.get("place") == "r" for u in units):
        _package_r_placement(package, pk, units, o, prot)
    return units, pk


def package_variant(s, package, pk, o, units, prot):
    """Variant of an Incoming package (Artillery/Mortar, --variant; R# bands of the mission table). Returns
    (variant or None, units)."""
    var = None
    if pk.get("variants"):
        variant = o.get("--variant")
        if variant is None and len(pk["variants"]) == 1:
            variant = next(
                iter(pk["variants"])
            )  # a single variant needs no draw (Normandy M7: Incoming only as Mortar)
        if variant not in pk["variants"]:
            names = list(pk["variants"])
            bands = [pk["variants"][x].get("r") for x in names]
            if all(bands):
                # the mission table gives R# bands (Naktong S.18: R#1-4/10 Artillery, R#5-10/10 Mortar)
                hint = ", ".join(f"R# {b} = {x}" for x, b in zip(names, bands))
                raise rules.Violation(
                    f"Package {package}: draw an Action card, {hint} (mission table); --variant=<{'|'.join(names)}>"
                )
            raise rules.Violation(
                f"Package {package}: draw a card, 1 = {names[0]}, 2 = {names[1]} (BGG B4); --variant=<{'|'.join(names)}>"
            )
        var = pk["variants"][variant]
        prot.append(f"Variant {variant} (Incoming {var['value']:+d}) [Normandy M1 p.19]")
        # (E60): count spotter counters per firing agency (Arty Spotter / Mortar Spotter)
        if "Arty Spotter" in s.get("countermix", {}):  # only if the game keeps separate spotter counters (M4+)
            units = [
                dict(u, unit=("Arty Spotter" if variant == "Artillery" else "Mortar Spotter"))
                if u.get("spotter") or u.get("unit") == "Spotter"
                else u
                for u in units
            ]
        if var.get("no_units"):
            units = []
            prot.append("without Spotter (Normandy M2 p.23: 'Artillery -4 with no Spotter')")
    return var, units


def package_counter_types(s, package, o, units, prot):
    """Counter of each unit from the countermix (8.3; several free: --type), VOF and range read from the counter where
    the setup does not know them (--vof, --range), A-rated ammo and FJ last steps [Normandy p.48]. Changes units."""
    needed, types_ = {}, []
    type_list, vof_list, range_list = (
        options.list_option(o, "--type"),
        options.list_option(o, "--vof"),
        options.list_option(o, "--range"),
    )
    for u in units:
        names = u.get("unit_choice") or [u["unit"]]
        free = [x for x in names if in_play_count(s, x) + needed.get(x, 0) < state.countermix_count(s, x)]
        if not free:
            raise rules.Violation(
                f"Package {package} cannot be placed: no free counter for {'/'.join(names)}; redraw the package (8.3 p.62, Normandy p.19 'Redraw', E6)"
            )
        if len(free) > 1:
            if not type_list:
                raise rules.Violation(
                    f"Choose the counter randomly (R#/{len(free)}) from {', '.join(free)}; --type=<name>[,<name> for further squads] [Normandy M1 p.16]"
                )
            w = type_list.pop(0)
            if w not in free:
                raise rules.Violation(f"{w} not free; free: {', '.join(free)}")
            free = [w]
        needed[free[0]] = needed.get(free[0], 0) + 1
        types_.append(free[0])
    for u, t in zip(units, types_):
        u.update(u.get("variants", {}).get(t, {}))
        u["type_name"] = t
        if u.get("vof_rating", "x") is None and u["type"] not in ("Spotter", "HQ"):
            known = (s.get("counter_vof") or {}).get(t)
            if known:
                u["vof_rating"] = known
                prot.append(f"{t}: VOF {known} per counter (recorded)")
            else:
                if not vof_list:
                    raise rules.Violation(
                        f"{t}: VOF rating not recorded (UNVERIFIED); read it from the counter: --vof=<A|S|H..>[,...] [Normandy p.48]"
                    )
                u["vof_rating"] = vof_list.pop(0)
                s.setdefault("counter_vof", {})[t] = u["vof_rating"]
                prot.append(f"{t}: VOF {u['vof_rating']} per counter (recorded for future contacts)")
        if u.get("vof_rating") == "A" and u.get("ammo_if_a") and not u.get("ammo"):
            u["ammo"] = copy.deepcopy(u["ammo_if_a"])
            u["last_step_values"] = {"vof_rating": "A", "range": "C"}
        if u.get("vof_rating") == "A/S" and u.get("fj_breakdown") and not u.get("last_step_values"):
            u["last_step_values"] = {
                "vof_rating": "A/S",
                "range": "C",
            }  # [Normandy p.48] A/S FJ: last step Fire Team A/S • C
        if u.get("range", "x") is None:
            if not range_list:
                raise rules.Violation(
                    f"{t}: range not recorded (UNVERIFIED); read it from the counter: --range=<C|L|V>[,...]"
                )
            u["range"] = range_list.pop(0)
            prot.append(f"{t}: range {u['range']} per counter")


def package_places(s, units, card_id, o, pk, prot):
    """Cards of the units: direction per unit (--direction, Unit Placement Table) and Max LOS / Close / Point Blank
    placement [8.4.2, 8.4.3]."""
    direction_list = [
        {"Left": "Left Front", "Right": "Right Front"}.get(x, x) for x in options.list_option(o, "--direction")
    ]
    place_list = options.list_option(o, "--place")
    places = []
    own = [u for u in units if u["place"] in ("max", "close", "max_los")]
    if len(set(direction_list)) < len(direction_list) and not pk.get("human_wave"):
        raise rules.Violation(
            "Duplicate direction: redraw (FM2 p.10, 8.4.3 'Redraw if an invalid Direction is chosen')"
        )
    rt = s.get("direction_table", {})
    contact_choose_places(s, own, units, card_id, o, pk, places, place_list, prot, direction_list, rt)
    return places


def package_mine_check(s, card_id, pk, prot):
    """Mines package: mine check for the units on the trigger card; Engineers draw only one card [Normandy CSR 10]."""
    if any(mk["type"] == "Mines" for mk in pk.get("marker", [])):
        request_mine_check(s, state.units_on(s, card_id), card_id, prot, "Mines package")
        _eng = [
            n
            for n in state.units_on(s, card_id)
            if s["units"][n].get("engineer") and state.good_order(s["units"][n]) and state.steps(s["units"][n]) >= 2
        ]
        if _eng:
            prot.append(
                f"{', '.join(_eng)}: Engineers draw only 1 action card instead of 3 for this mine check [Normandy CSR 10 'Mine Detection'] (L74)"
            )


def pc_contact_campaign(s, card_id, package, pk, o):
    """[RULE 8.3 p.62, 8.4 p.63-65, Normandy M1 p.19] Package with direction (Unit Placement Table), distance, cover, Place PDF/VOF, Spotted."""
    c = state.card(s, card_id)
    prot = []
    trigger = state.units_on(s, card_id, "US")
    if pk.get("mine_redraw") and mines_on(s, card_id):
        raise rules.Violation(
            f"Mines! package on {card_id}, mines already lie there: redraw the package [Normandy M4 MSR 1 p.30]"
        )
    units, pk = resolve_package_units(s, package, pk, o, prot)  # one function per step
    var, units = package_variant(s, package, pk, o, units, prot)
    package_counter_types(s, package, o, units, prot)
    places = package_places(s, units, card_id, o, pk, prot)
    # ---- markers (Mines, Incoming) onto the trigger card
    contact_place_markers(s, c, card_id, o, pk, prot, var)
    # ---- place units
    new_units = contact_place_units(s, c, units, card_id, o, package, pk, places, prot, trigger, var)
    contact_tail(s, new_units, prot)  # fired-over PC markers (8.4.4), Point Blank shift, return fire
    package_mine_check(s, card_id, pk, prot)
    state.clear_pc(c)  # campaign: availability only via the countermix (8.3); a second marker stays
    prot.append(f"Remove PC marker from {card_id} [8.2.4]")
    activity_note = fire.update_activity(s)
    if activity_note:
        prot.append(activity_note)
    state.save_state(
        s, f"Contact on {card_id}: package {package} {pk['name']}; " + "; ".join(prot), "8.3 p.62, 8.4 p.63"
    )
    print("CONTACT [RULE 8.3 p.62, 8.4.3 p.63]")
    briefing.print_board(prot, s)
