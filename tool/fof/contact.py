"""Potential contact, enemy packages and placement, external VOF markers, mines (8.1 to 8.4, 8.7)."""

import copy
import types

from . import briefing, combat, commands, enemy, events, fire, geometry, grenades, options, rules, state


def package_units(pk):
    """Units of a package: list 'einheiten' (v3, e.g. package 7 'Squad in Trench + LMG in Bunker') or flat package (v2)."""
    if pk.get("einheiten"):
        return pk["einheiten"]
    if pk.get("einheit") or pk.get("einheit_wahl"):
        return [pk]
    return []


def in_play_count(s, type_name):
    return sum(1 for e in s["einheiten"].values() if e["seite"] == "Feind" and e.get("typname") == type_name)


def cover_count(s, type_):
    return sum(1 for c in s["karten"].values() for cv in c.get("cover", []) if cv["typ"] == type_)


def type_free(s, u, needed=None):
    """Free counter types for a package unit; 'einheit_wahl' = choose the type at random [FM1 p.48], type in use: take another [RULE 8.3 p.62]."""
    cm, needed = s.get("countermix", {}), needed or {}
    names = u.get("einheit_wahl") or [u["einheit"]]
    return [
        n for n in names if in_play_count(s, n) + needed.get(n, 0) < (cm.get(n, 1) if cm.get(n, 1) is not None else 1)
    ]


def package_available(s, p, choice=None):
    """[RULE 8.3 p.62/63, FM1 p.48 'Respect the counter mix'] all counters and markers of the package must be free.
    Marker packages without a unit (Incoming) are occupied as long as their marker is on the board ('im_spiel')."""
    pk = s["pakete"][p]
    if pk.get("wahl"):
        return any(
            all(type_free(s, u) for u in opt_) for opt_ in pk["wahl"].values()
        )  # v4: package with a choice (Normandy package 5)
    units = [u for u in package_units(pk) if not u.get("optional_r") and not u.get("nur_wenn_verfuegbar")]
    if not units and "place_vof" in pk:
        return True
    if not units:
        return not pk.get("im_spiel")
    cm = s.get("countermix", {})
    needed, cover_needed = {}, {}
    for u in units:
        free = type_free(s, u, needed)
        if choice and u.get("einheit_wahl"):
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
    for n, e in s["einheiten"].items():
        if e["seite"] == "Feind" and fire.is_firing(e) and e["ziel"] != e["karte"]:
            if k in (geometry.line_between(s, e["karte"], e["ziel"]) or []) + [e["ziel"]]:
                return f"along the PDF of {n}"
    for x in state.card(s, k).get("extern", []):
        if x.get("seite") == "Feind" or any(pk.get("name") == x.get("quelle") for pk in s.get("pakete", {}).values()):
            return "enemy VOF marker"
    return None


def valid_places(s, pk, kid):
    out = []
    units = package_units(pk) or [pk]
    without_pb = all(u.get("cover") in rules.STRUCTURES for u in units)
    hi = min(rules.RANGE_CARDS.get((u.get("reichweite") or "L").split("-")[-1], 2) for u in units)
    v3 = enemy.series_rules(s)  # L262: one predicate for the series-rules placement restrictions
    for k, c in s["karten"].items():
        if pk.get("reihe") and c["reihe"] != pk["reihe"]:
            continue
        if c.get("staging") or state.units_on(s, k, "Feind"):
            continue
        if state.units_on(s, k, "US") and k != kid and not (v3 and without_pb):
            continue  # [RULE 8.4.3 p.63] '(unless Point Blank fire is not possible for the units in the package)'
        if v3 and without_pb and k == kid:
            continue  # a bunker cannot fire Point Blank, but must be able to open fire on the trigger card
        if k != kid:
            if (
                geometry.distance(s, k, kid) > hi
                or not geometry.los(s, k, kid, hb=geometry.card_height_bonus(s, kid, "US"))[0]
            ):
                continue
            if any(state.units_on(s, between, "US") for between in (geometry.line_between(s, k, kid) or [])):
                continue
        if v3 and enemy_pdf_or_vof(s, k):
            continue
        out.append(k)
    return out


def cmd_pc(s, args):
    """pc | pc <card> | pc reveal|set <card> <letter> | pc clear <card> | pc contact <card> <package> [..] (8.2-8.4).
    L557 (review E4): a switch over the sub-commands; each one is its own function."""
    if args and args[0] in ("aufdecken", "setzen") and cmd_pc_v4(s, args):
        return None
    if not args:
        return pc_overview(s)
    if args[0] not in ("kontakt", "frei"):
        return pc_draw_info(s, args[0])
    if args[0] == "frei":
        return pc_clear(s, args)
    return pc_contact(s, args)


def pc_overview(s):
    """pc: the PC markers on cards with friendly units, by letter (L516)."""
    open_ = sorted(
        (k for k, c in s["karten"].items() if c.get("pc") and state.units_on(s, k, "US")),
        key=lambda k: (str(s["karten"][k]["pc"]), k),
    )  # L516: by PC letter like the 3.7.2 list
    print(
        "PC markers with friendly units: "
        + (", ".join(f"{k} (PC {s['karten'][k]['pc']})" for k in open_) if open_ else "none")
    )


def pc_draw_info(s, kid):
    """pc <card>: legality of resolving the PC marker and the draw instructions [8.2.4, 8.3]."""
    c = state.card(s, kid)
    if not c.get("pc"):
        raise rules.Violation(f"{kid} has no PC marker")
    if not state.units_on(s, kid, "US"):
        raise rules.Violation(f"{kid}: a PC marker is only resolved with a friendly unit on the card [RULE 8.2.4 p.62]")
    if s["phase"] != "3.7.2":
        print(f"Note: PC resolution belongs in 3.7.2, currently {s['phase']}")
    # E39 (the player 07.10.2026): reveal ?-markers only on cards with friendly units (8.2.4; developer AAR BGG 2585005)
    if "?" in (c.get("pc"), c.get("pc2")) or any(
        "?" in (cc.get("pc"), cc.get("pc2")) for kk, cc in s["karten"].items() if state.units_on(s, kk, "US")
    ):
        raise rules.Violation(
            "First reveal the PC markers showing '?' on cards with friendly units: fof.py pc reveal <card> <A|B|C> [RULE 8.2.4 p.62, E39]"
        )
    higher = [k for k, cc in s["karten"].items() if cc.get("pc") and state.units_on(s, k, "US") and cc["pc"] < c["pc"]]
    if higher:
        raise rules.Violation(f"First resolve the higher letters: {', '.join(higher)} [RULE 8.2.4 p.62]")
    n = rules.PC_DRAWS[c["pc"]][s["aktivitaet"] or "No Contact"]
    print(
        f"PC {c['pc']} on {kid} at {s['aktivitaet']}: "
        + (
            "Auto, contact without a draw"
            if n == 0
            else f"draw {n} Action cards (all), contact if one shows 'Contact' at the top"
        )
        + " [8.2.4, Charts 1]"
    )
    tab = s.get("paket_tabelle", {}).get("PC " + c["pc"], {})
    if (
        s.get("gegenangriff")
        and c["pc"] == "A"
        and s.get("paket_tabelle_gegenangriff")
        and state.option(s, "U28_gegenangriff_alle_pc_a")
    ):
        tab = s["paket_tabelle_gegenangriff"]["PC A"]
        print(
            "Counter-attack active: PC A uses the Counter-Attack list"
            + state.open_reading(s, "U28_gegenangriff_alle_pc_a")
            + " [Normandy M1 MSR 1 p.19]"
        )
    print(
        "On contact: draw an Action card, column PC "
        + c["pc"]
        + ": "
        + "; ".join(
            f"R# {v} = package {p} ({s['pakete'][p]['name']}, {'free' if package_available(s, p) else 'IN USE'})"
            for p, v in tab.items()
            if p in s["pakete"]
        )
    )
    if state.is_v4(s):
        rt = s.get("richtung_tabelle", {})
        print(
            f"Package that cannot be placed: draw again (8.3 p.63, Normandy p.19; E6); if none can be placed, no contact. Direction per unit on the friendly card: R# column {rt.get('spalte', 8)}: "
            + ", ".join(f"{b} {v}" for b, v in rt.items() if b != "spalte")
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
    rules.need(args, 2, "pc clear <card>")  # L269 (review H12); L550: usage names the English word the CLI knows
    kid = args[1]
    c = state.card(s, kid)
    if not c.get("pc"):
        raise rules.Violation(f"{kid} has no PC marker")
    old = c["pc"]
    state.clear_pc(c)  # L550
    state.save_state(s, f"PC {old} on {kid}: no contact, PC marker removed", "8.2.4 p.62")
    print(f"No contact on {kid}. Remove the PC marker [8.2.4].")
    print(briefing.check_stamp(s))


def pc_contact(s, args):
    """pc contact <card> <package> [--place=..] [--direction=..]: place the package (v4: pc_contact_v4) [8.3, 8.4]."""
    rules.need(args, 3, "pc contact <card> <package> [--place=..] [--direction=..]")  # L269 (review H12)
    kid, package = args[1], args[2]
    o = options.parse_opts(args[3:])
    c = state.card(s, kid)
    if not c.get("pc"):
        raise rules.Violation(f"{kid} has no PC marker")
    pk = s.get("pakete", {}).get(package)
    if not pk:
        raise rules.Violation(f"Package {package} unknown")
    if not state.units_on(s, kid, "US"):
        raise rules.Violation(
            f"{kid}: a PC marker is only resolved with a friendly unit on the card [RULE 8.2.4 p.62, 3.7.2 p.17]"
        )
    if "place_vof" in pk:
        if c.get("pc") == "?":
            raise rules.Violation("Reveal the PC marker first: fof.py pc reveal <card> <A|B|C>")
        return pc_contact_v4(s, kid, package, pk, o)
    if not package_available(s, package):
        raise rules.Violation(f"Package {package} not available (counter mix); ignore the draw [8.3 p.63, FM1 p.26]")
    prot = []
    pc_old = c["pc"]
    units = package_units(pk)
    if units:
        place = o.get("--platz", kid if pk["platz"].startswith("trigger") else None)
        valid = valid_places(s, pk, kid)
        if not place:
            raise rules.Violation(
                f"Package {package} ('{pk['platz']}'): valid cards {', '.join(valid) if valid else 'NONE (redraw the package; if none can be placed, remove the PC marker without contact)'}; draw a random card, column {len(valid)}, and --place=<card> [8.4.3]"
            )
        state.card(s, place)
        if place not in valid:
            raise rules.Violation(
                f"{place} is not a valid place (row, LOS, range, enemies, friendly units in between, enemy PDF/VOF). Valid: {', '.join(valid) or 'none'} [8.4.3 p.63]"
            )
        types_ = v3_counter_types(s, units, o, prot)  # L557: split for readability (review E4)
        new_units = [
            v3_place_unit(s, u, type_name, place, kid, package, pk, pc_old, prot) for u, type_name in zip(units, types_)
        ]
        contact_tail(s, new_units, prot, pdf_needs_vof=False)
    else:
        c.setdefault("extern", []).append(
            {"typ": "Incoming", "wert": pk.get("wert", -3), "quelle": pk["name"], "seite": "Feind"}
        )
        prot.append(
            f"{pk['name']}: Incoming marker (VOF {pk.get('wert', -3)}) active on {kid}, takes effect in this Combat Effects Segment; blocks LOS out of {kid} [8.10, 5.4]"
        )
        fire.cease_fire_on_los_loss(s, prot)  # L95: also fire THROUGH the card (5.4)
    pk["im_spiel"] = True
    state.clear_pc(c)  # L550: a second marker on the card stays
    prot.append(f"Remove PC marker from {kid} [8.2.4]")
    ak = fire.update_activity(s)
    if ak:
        prot.append(ak)
    state.save_state(s, f"Contact on {kid}: package {package} {pk['name']}; " + "; ".join(prot), "8.3 p.62, 8.4.3 p.63")
    print("CONTACT [RULE 8.3 p.62, 8.4.3 p.63]")
    briefing.print_board(prot, s)


def v3_counter_types(s, units, o, prot):
    """v3 packages: the counter type of each unit (a free one; several free: random by --type, FM1 p.48)."""
    needed, types_ = {}, []
    for u in units:
        free = type_free(s, u, needed)
        if u.get("einheit_wahl") and len(free) > 1:
            w = o.get("--typ")
            if w not in free:
                raise rules.Violation(
                    f"Choose the squad type at random (R#/{len(free)}): {', '.join(free)}; then --type=<counter name> [FM1 p.48]"
                )
            prot.append(f"Squad type at random: {w} [FM1 p.48]")
            free = [w]
        elif u.get("einheit_wahl") and len(free) == 1 and len(u["einheit_wahl"]) > 1:
            prot.append(f"Squad type: only {free[0]} is free, this one is taken [RULE 8.3 p.62]")
        needed[free[0]] = needed.get(free[0], 0) + 1
        types_.append(free[0])
    return types_


def v3_place_unit(s, u, type_name, place, kid, package, pk, pc_old, prot):
    """v3 packages: one enemy unit on its card, with cover marker and fire at the trigger card [8.3, 8.4.3]."""
    values_ = dict(u)
    values_.update(u.get("varianten", {}).get(type_name, {}))
    fname = commands.new_name(s, type_name, reuse_removed=True)  # L215
    cid = None
    if values_.get("cover"):
        cid = commands.new_cover_marker(s, place, values_["cover"], values_.get("cover_wert", 1))
        cv = next(x for x in state.card(s, place)["cover"] if x["id"] == cid)
        if values_.get("cover_kapazitaet"):
            cv["kapazitaet"] = values_["cover_kapazitaet"]
        if values_["cover"] in rules.STRUCTURES and place != kid:
            cv["richtung"] = list(geometry.direction(s, place, kid))
        prot.append(f"{values_['cover']} marker {cid} (+{values_.get('cover_wert', 1)}) on {place}")
    e = {
        "typ": values_.get("typ", "Weapons Team"),
        "typname": type_name,
        "seite": "Feind",
        "erfahrung": values_.get("erfahrung", "Line"),
        "karte": place,
        "bereich": cid or "offen",
        "status": [],
        "steps": values_.get("steps", 1),
        "vof_rating": values_["vof_rating"],
        "reichweite": values_.get("reichweite", "L"),
        "spotted": bool(pk.get("spotted", values_.get("spotted"))),
        "paket": package,
        "pc_herkunft": pc_old,
        "fire_team_seite": values_.get("fire_team_seite", values_.get("steps", 1) == 1),
        "ft_vof": values_.get("ft_vof", "S"),
        "letzter_step": values_.get("letzter_step"),
        "ziel": None,
        "kein_point_blank": values_.get("cover") in rules.STRUCTURES,
    }
    if values_.get("breakdown_hinweis"):
        e["breakdown_hinweis"] = values_["breakdown_hinweis"]
    s["einheiten"][fname] = e
    if values_.get("cover") in rules.STRUCTURES:
        e["bunker_richtung"] = kid
        prot.append(
            f"Point the bunker arrow at {kid}; fires only in this direction, never Point Blank; redraw Shift Fire results [5.3.2]"
        )
    prot.append(
        f"Enemy {fname} ({type_name}, VOF {values_['vof_rating']}, {values_.get('steps', 1)} steps) on {place}"
        + (f" under {cid}" if cid else " without cover")
        + (", Spotted" if e["spotted"] else ", place an Unspotted marker")
    )
    e["ziel"] = kid
    prot.append(
        f"{fname} opens fire on {kid}"
        + ("" if place == kid else f", PDF from {place} to {kid}" + fire.pdf_note(s, place, kid, fname))
        + " [8.4.3]"
    )
    return fname


def contact_tail(s, new_units, prot, pdf_needs_vof=True):
    """After the units of a package are placed (L276, structure 9: one function for the former v3 and v4 copies):
    PC markers their PDFs fire over are removed [RULE 8.4.4], friendly units on a placement card with a Spotted enemy shift
    to Point Blank [RULE 6.1.2] and return fire opens [RULE 6.1.1]; Unspotted enemies draw no fire [RULE 8.5].
    pdf_needs_vof=False keeps the v3 reading: every placed PDF counts, also one without a VOF (G! unit, Deep Bunker)."""
    for fname in new_units:
        e = s["einheiten"][fname]
        has_pdf = fire.is_firing(e) if pdf_needs_vof else e.get("ziel") is not None
        if has_pdf and e["ziel"] != e["karte"]:
            for between in geometry.line_between(s, e["karte"], e["ziel"]) or []:
                cb = state.card(s, between)
                if cb.get("pc") and cb.get("elevation", 1) == state.card(s, e["karte"]).get("elevation", 1):
                    state.clear_pc(cb, promote=False)  # L550
                    prot.append(f"PC marker on {between} removed (fired over) [8.4.4]")
    for fname in new_units:
        e = s["einheiten"][fname]
        if not e["spotted"]:
            continue
        for m, f in s["einheiten"].items():
            if (
                f["seite"] == "US"
                and f["karte"] == e["karte"]
                and fire.is_firing(f)
                and f["ziel"] != e["karte"]
                and not geometry.no_point_blank(s, f)
            ):
                # L280 (review LOW): the old PDF ceases (the v4 copy kept the Concentrated Fire flag and the other
                # fire fields of the old target), then the unit fires Point Blank
                fire.cease_fire(f)
                f["ziel"] = e["karte"]
                prot.append(f"{m} shifts fire to its own card (Point Blank), the old PDF lapses [6.1.2]")
    if any(s["einheiten"][f]["spotted"] for f in new_units):
        fire.open_fire(s, prot)
    elif new_units:
        prot.append("Enemy Unspotted: no return fire, spot it first [8.5, 6.1.1]")


def cmd_external(s, args):
    rules.need(
        args, 2, "external <card> <Incoming|Mines|AirStrike|Smoke|Pending> <value> [<source>] | external <card> remove"
    )
    kid = args[0]
    c = state.card(s, kid)
    prot = []
    if args[1] in ("weg", "remove", "away"):  # L550 (review E10): the words the usage and the CLI name
        c["extern"] = []
        prot.append(f"external VOF on {kid} removed")
    else:
        rules.need(args, 3, "external <card> <type> <value> [<source>]")  # L269 (review H12)
        type_, value = args[1], rules.int_value(args[2], "VOF value")
        if type_ not in ("Incoming", "Mines", "AirStrike", "Smoke", "Pending"):
            raise rules.Violation("Type: Incoming | Mines | AirStrike | Smoke | Pending")
        c.setdefault("extern", []).append({"typ": type_, "wert": value, "quelle": args[3] if len(args) > 3 else type_})
        prot.append(f"{type_} {value} on {kid}")
        if type_ in ("Incoming", "AirStrike", "Smoke"):
            fire.cease_fire_on_los_loss(s, prot)  # L95: also fire THROUGH the card (5.4)
    ak = fire.update_activity(s)
    if ak:
        prot.append(ak)
    state.save_state(s, "; ".join(prot), "5.4 p.38")
    briefing.print_board(prot, s)


def cmd_enemy(s, args):
    rules.need(args, 1, "enemy <unit> spotted|unspotted|pinned|unpinned|remove|card=<card>|cover=<id>|steps=<n>")
    name = args[0]
    f = state.unit(s, name)
    if f["seite"] != "Feind":
        raise rules.Violation(f"{name} is not an enemy unit")
    prot = []
    for a in args[1:]:
        a = "weg" if a in ("remove", "away") else ("karte=" + a[5:] if a.startswith("card=") else a)  # L550 (E10)
        if a == "spotted":
            for m in state.units_on(s, f["karte"], "Feind"):
                s["einheiten"][m]["spotted"] = True
            prot.append(f"Enemies on {f['karte']} Spotted (per card) [8.5]")
            fire.open_fire(s, prot)
        elif a == "unspotted":
            if f.get("typname") != "Sniper" and not f.get("out_of_ammo"):
                prot.append("WARNING: only snipers and Out-of-Ammo Fire Teams become Unspotted again [8.8, 8.11.1]")
            for m in state.units_on(s, f["karte"], "Feind"):
                s["einheiten"][m]["spotted"] = False
            prot.append(f"Enemies on {f['karte']} Unspotted")
        elif a == "pinned":
            commands.mark(f, rules.PINNED)
            prot.append(f"{name} Pinned (its VOF becomes 'All Pinned' +2)")
        elif a == "unpinned":
            f["status"] = [x for x in f["status"] if x != rules.PINNED]
            prot.append(f"{name} Pinned removed")
        elif a == "weg":
            enemy.remove_enemy(s, name, prot, reason="correction/removal")
            break
        elif a.startswith("karte="):
            state.card(s, a[6:])
            # L264: the one enemy move path (ammo surplus, Deep Bunker left, fire after move, mine check); the
            # correction command leaves the unit in the open, cover= sets the marker explicitly
            enemy.move_enemy(s, name, a[6:], prot, cover=False)
        elif a.startswith("cover="):
            grenades.grenade_expires(s, f, name, prot)
            commands.set_area(s, f, a[6:])
            prot.append(f"{name} under {a[6:]}")
        elif a.startswith("steps="):
            f["steps"] = rules.int_value(a[6:], "steps")  # L269
            prot.append(f"{name} {f['steps']} steps")
        else:
            raise rules.Violation(f"Unknown entry {a}")
    ak = fire.update_activity(s)
    if ak:
        prot.append(ak)
    state.save_state(s, "; ".join(prot), None)
    briefing.print_board(prot, s)


def mines_on(s, kid):
    return [x for x in state.card(s, kid).get("extern", []) if x["typ"] == "Mines"]


def engineers_clear(s, e):
    """L82 [Normandy CSR 10 p.16]: Good Order Engineers with 2 or 3 steps clear paths (1 card after a successful infiltration)."""
    return bool(e.get("engineer")) and state.good_order(e) and state.steps(e) >= 2


def request_mine_check(s, names, kid, prot, reason, cards=3, path_=False):
    if not mines_on(s, kid):
        return
    names = [n for n in names if n in s["einheiten"] and s["einheiten"][n]["typ"] not in ("Casualty",)]
    if not names:
        return
    s.setdefault("minen_checks", [])
    info = s.setdefault("minen_check_info", {})
    for n in names:
        if n not in s["minen_checks"]:
            s["minen_checks"].append(n)
        info[n] = {"karten": cards, "pfad": path_}
    if path_:
        prot.append(
            f"mine check on {kid} ({reason}) for {', '.join(names)}: {cards} action card(s), hit on a Burst icon; without a hit the path is marked and the Mines marker comes off; then fof.py mine <unit> yes|no [CSR 10 p.16, 7.9.1 p.54]"
        )
    else:
        prot.append(
            f"mine check on {kid} ({reason}) for {', '.join(names)}: {cards} action card(s) per unit, hit on a Burst icon (also multi-burst and Short); then fof.py mine <unit> yes|no [7.9.1 p.54]"
        )


def cmd_mine(s, args):
    rules.need(args, 2, "mine <unit> yes|no")  # L269 (review H12)
    n, result = args[0], args[1]
    if n not in s.get("minen_checks", []):
        raise rules.Violation(f"No mine check pending for {n}")
    e = state.unit(s, n)
    s["minen_checks"].remove(n)
    info = s.get("minen_check_info", {}).pop(n, {})
    prot = []
    if result == "ja":
        e["mine_hit"] = True
        for x in mines_on(s, e["karte"]):
            x["aktiv"] = True
        prot.append(
            f"{n} hit by a mine: flip the Mines marker to its explosion side, {n} under it; Mines! VOF -4 in 3.7.4; may not move within the card or to an adjacent card this turn [7.9.1 p.54]"
            + ("; path marking failed, the mines stay [CSR 10 p.16]" if info.get("pfad") else "")
        )
    elif result == "nein":
        if info.get("pfad"):
            k = state.card(s, e["karte"])
            k["extern"] = [x for x in k.get("extern", []) if x["typ"] != "Mines"]
            prot.append(f"{n}: no mine hit, path marked: remove the Mines marker from {e['karte']} [CSR 10 p.16]")
        else:
            prot.append(f"{n}: no mine hit")
    else:
        raise rules.Violation("yes | no")
    if s["phase"] == "3.6" and s.get("at36"):
        from . import vehicles  # L187: the vehicle action continues after the mine check

        vehicles.resume(s, prot)  # L322: purge, advance and name the next step (review LOW)
    ak = fire.update_activity(s)
    if ak:
        prot.append(ak)
    state.save_state(s, "; ".join(prot), "7.9.1 p.54")
    briefing.print_board(prot, s)


def mine_lock(s):
    reveal_lock(s)
    if s.get("hitze_offen"):
        raise rules.Violation(
            "First the Heat Casualties draws: "
            + ", ".join(s["hitze_offen"])
            + " (fof.py heat <unit> <R#/4 value>, only 1 is a loss) [Naktong M1 p.17]"
        )
    if s.get("minen_checks"):
        raise rules.Violation(
            "First resolve the pending mine checks: "
            + ", ".join(s["minen_checks"])
            + " (fof.py mine <unit> yes|no) [7.9.1 p.54, 8.7.1 p.67]"
        )


def reveal_lock(s):
    """L481 [RULE 5.2 p.34]: the next step waits until the face-down cards in LOS are flipped (terrain entered)."""
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


def cmd_pc_v4(s, args):
    if args[0] == "aufdecken":
        rules.need(args, 3, "pc reveal <card> <A|B|C>")  # L269 (review H12)
        kid, b = args[1], args[2]
        c = state.card(s, kid)
        if b not in ("A", "B", "C"):
            raise rules.Violation("Letter A|B|C")
        prot = []
        if c.get("pc") == "?":
            c["pc"] = b
        elif c.get("pc2") == "?":
            c["pc2"] = b
        else:
            raise rules.Violation(f"{kid} has no face-down PC marker")
        prot.append(f"PC marker on {kid} revealed: {b}")
        if c.get("pc2") and c["pc"] != "?" and c["pc2"] != "?":
            high, deep = min(c["pc"], c["pc2"]), max(c["pc"], c["pc2"])
            c["pc"] = high
            c.pop("pc2")
            prot.append(f"two PC markers on {kid}: the lower one ({deep}) is removed, {high} stays [8.2.3 p.62]")
        state.save_state(s, "; ".join(prot), "8.2.3 p.62")
        briefing.print_board(prot, s)
        return True
    if args[0] == "setzen":
        rules.need(args, 3, "pc set <card> <A|B|C|?>")  # L269 (review H12)
        kid, b = args[1], args[2]
        c = state.card(s, kid)
        if b not in ("A", "B", "C", "?"):
            raise rules.Violation("A|B|C|?")
        prot = [f"PC marker {b} on {kid} (correction/event)"]
        if c.get("pc") and c["pc"] != "?" and b != "?":
            # L550 (review E12): two face-up markers on one card at once: 8.2.3 applies now, the lower one goes
            high, deep = min(c["pc"], b), max(c["pc"], b)
            c["pc"] = high
            prot.append(f"two PC markers on {kid}: the lower one ({deep}) is removed, {high} stays [8.2.3 p.62]")
        elif c.get("pc"):
            c["pc2"] = b
        else:
            c["pc"] = b
        state.save_state(s, "; ".join(prot), "8.2.3 p.62")
        briefing.print_board(prot, s)
        return True
    return False


DIRECTION = {"Front": (1, 0), "Left Front": (1, -1), "Right Front": (1, 1), "Links": (1, -1), "Rechts": (1, 1)}


def check_place_v4(s, u, k, kid, pk):
    """Placement restrictions 8.4.3 for a package unit on card k (trigger kid)."""
    if state.units_on(s, k, "Feind") and not u.get("_gleiche_karte_ok"):
        return f"{k}: enemies already there (8.4.3 'Other Enemy Units')"
    without_pb = (u.get("cover") in rules.STRUCTURES) or state.is_mortar(u)
    no_pdf = u.get("platz") == "max_los" or not pk.get("place_vof", True) or not u.get("vof_rating")
    if k != kid and state.units_on(s, k, "US") and not without_pb and not no_pdf:
        return f"{k}: friendly units there (8.4.3)"  # L151: only units that place a PDF (8.4.3 example 2: Spotter with US units)
    if k != kid and not no_pdf and not state.is_mortar(u):
        between = geometry.line_between(s, k, kid) or []
        overhead = (u.get("vof_rating") == "H" or u.get("tripod")) and all(
            fire.overhead_possible(s, k, b, kid) for b in between if state.units_on(s, b)
        )
        grazing = u.get("tripod") and all(
            state.card(s, b).get("elevation", 1) == state.card(s, k).get("elevation", 1) for b in between + [kid]
        )
        if any(state.units_on(s, b, "US") for b in between) and not (overhead or grazing):
            return f"{k}: friendly units between {k} and {kid} (8.4.3, no Grazing/Overhead Fire)"
        if any(state.units_on(s, b, "Feind") for b in between) and not overhead:
            return f"{k}: own enemy units between {k} and {kid} (8.4.3 example 1: only with Overhead Fire)"  # L151
    if enemy_pdf_or_vof(s, k):
        return f"{k}: {enemy_pdf_or_vof(s, k)} (8.4.3)"
    return None


def range_of(u, pk):
    if u.get("platz") == "max_los":
        return 3  # [RULE 8.4.3 p.63] Spotter/Patrol: Max LOS up to Very Long
    r = u.get("reichweite") or "V"
    return rules.RANGE_CARDS.get(r.split("-")[-1], 3)


def building_table_ref(s, place):
    """L494: R# column and source of the campaign's building table (Normandy CSR 8 p.15 column 8, Naktong CSR 6 p.14
    column 5), taken from the table itself instead of a fixed Normandy text."""
    tab = s.get("gebaeude_tabelle", {}).get(state.card(s, place).get("gebaeude_tabelle"), {})
    col = max((int(str(b).split("-")[-1]) for b in tab if str(b).split("-")[-1].isdigit()), default=8)
    ref = (s.get("gebaeude_tabelle", {}).get("_quelle") or "CSR 8 S.15").split(",")[0].replace(" S.", " p.")
    return col, ref


def building_cover(s, place, u, r8, value_opt):
    """[CSR 8 p.15 Normandy, CSR 6 p.14 Naktong] Package in cover on Village/Farm/Cemetery/Church: R# on the building table; if the
    building value is equal to or better than the package cover, the unit goes inside; a worse result stays behind as a marker (BGG E21)."""
    tab = s.get("gebaeude_tabelle", {}).get(state.card(s, place).get("gebaeude_tabelle"), {})
    col, ref = building_table_ref(s, place)
    r8 = rules.int_value(r8, f"--building (R# column {col})")  # L269 (review H12)
    type_ = next((t for b, t in tab.items() if events.r_matches(b, r8)), None)
    if type_ is None:
        raise rules.Violation(f"R# {r8} not in the building table (column {col}) [{ref}]")
    upper_ = type_.endswith("*")
    type_ = type_.rstrip("*")
    w = s.get("cover_werte", {}).get(type_)
    if w is None:
        if value_opt is None:
            raise rules.Violation(
                f"{type_}: cover value not recorded (UNVERIFIED); read it from the marker and give --building-value=<n> [{ref}]"
            )
        w = rules.int_value(value_opt, "--building-value")
    return type_, w, upper_


MORTAR_NO_FIRE_COVER = ("Light Building", "Strong Building", "Building", "Upper Story", "Church Tower")  # 7.3.1


def package_cover(s, u, idx, place, kid, pk, o, building_list, cid_before, prot):
    """Cover marker of one package unit: with the previous/random squad, the package cover (building table, an existing
    free marker of the same kind), or none [8.4.3, CSR 8, E58]. L557: split from contact_place_units (review E4)."""
    t = u["typname"]
    cid = None
    if u["platz"] == "mit_vorigem" and cid_before.get(idx - 1) and not u.get("eigene_deckung"):
        cid = cid_before[idx - 1]
    elif u["platz"] == "mit_zufaelligem" and cid_before.get(u.get("_ref")) and not u.get("eigene_deckung"):
        cid = cid_before[u["_ref"]]  # L522
    elif u.get("cover") and not u.get("ohne_deckung") and not u.get("infiltration"):
        cover_type = u["cover"]
        cover_value = u.get("cover_wert")
        if cover_value is None:  # L135: take the value from the setup table instead of a silent +1 (audit C3)
            cover_value = s.get("cover_werte", {}).get(cover_type)
        if cover_value is None:
            raise rules.Violation(
                f"Package unit {u.get('einheit') or u.get('einheit_wahl')}: no value for cover marker {cover_type} (cover_wert in the package or cover_werte table)"
            )
        if state.card(s, place).get("gebaeude_tabelle") and cover_type not in rules.STRUCTURES:
            if not building_list:
                col, ref = building_table_ref(s, place)
                raise rules.Violation(
                    f"{t} in cover on {state.card(s, place)['terrain']}: R# column {col} on the building table, --building=<R#>[,..] [{ref}]"
                )
            gt, gw, upper_ = building_cover(s, place, u, building_list.pop(0), o.get("--gebaeude_wert"))
            no_fire = u.get("moerser") and pk.get("place_vof", True) and gt in MORTAR_NO_FIRE_COVER
            if gw >= cover_value and no_fire:
                # E87/L204 [8.4.3 p.63, 7.3.1 p.52, BGG 3782765]: the package must be able to Open Fire on the trigger;
                # a mortar may not fire from building cover, so it keeps the cover of the package list
                prot.append(
                    f"Building table gives {gt} (+{gw}), but a mortar may not fire from it (7.3.1): stays in {u['cover']} (8.4.3, E87)"
                )
                gid = commands.new_cover_marker(s, place, gt, gw)
                prot.append(f"{gt} marker {gid} (+{gw}) stays empty on {place} [CSR 8 p.15]")
            elif gw >= cover_value:
                cover_type, cover_value = gt, gw
                prot.append(
                    f"Building cover {gt} (+{gw}) instead of {u['cover']} [CSR 8 p.15]"
                    + (
                        " (Upper Story/Church Tower for Sniper/Spotter)"
                        if upper_ and u["typ"] in ("Sniper", "Spotter")
                        else ""
                    )
                )
            else:
                gid = commands.new_cover_marker(s, place, gt, gw)
                prot.append(f"Building {gt} (+{gw}) worse than {u['cover']}: marker {gid} stays on {place} (BGG E21)")
        # L90 (E58): the same building/cover marker already lies free on the card: move in instead of a duplicate marker (5.3.3 Cover Potential)
        free = [
            x
            for x in state.free_cover(s, place, side="Feind")
            if x["typ"] == cover_type and x["wert"] == cover_value and cover_type not in rules.STRUCTURES
        ]
        if free:
            cid = free[0]["id"]
            prot.append(
                f"{t} into the existing {cover_type} {cid} (+{cover_value}) on {place} (no second marker) [E58]"
            )
        else:
            cid = commands.new_cover_marker(s, place, cover_type, cover_value)
        cv = next(x for x in state.card(s, place)["cover"] if x["id"] == cid)
        if u.get("cover_kapazitaet"):
            cv["kapazitaet"] = u["cover_kapazitaet"]
        if cover_type in rules.STRUCTURES and place != kid:
            cv["richtung"] = list(geometry.direction(s, place, kid))
        if not free:
            prot.append(f"{cover_type} marker {cid} (+{cover_value}) on {place}")
    return cid


def package_unit(s, u, c, place, kid, package, pk, cid, var, o, prot):
    """The unit record of one package unit: values of the package, attempt experience and ammo, spotter, infiltration
    attempt, Exposed [8.3, 8.4.3, L477, L497]. L557: split from contact_place_units."""
    t = u["typname"]
    spotted = bool(u.get("spotted", pk.get("spotted")))
    e = {
        "typ": u.get("typ", "Weapons Team"),
        "typname": t,
        "seite": "Feind",
        # L477: the attempt plan may set the enemy experience (Naktong M1 p.15: Veteran, Veteran, Line, Green)
        "erfahrung": s.get("feind_erfahrung_versuch") or u.get("erfahrung", "Line"),
        "karte": place,
        "bereich": cid or "offen",
        "status": [],
        "steps": u.get("steps", 1),
        "vof_rating": u.get("vof_rating"),
        "reichweite": u.get("reichweite") or "L",
        "spotted": spotted,
        "paket": package,
        "pc_herkunft": c.get("pc"),
        "fire_team_seite": u.get("fire_team_seite", u.get("steps", 1) == 1),
        "ft_vof": u.get("ft_vof") or "S",
        "letzter_step": u.get("letzter_step"),
        "ziel": None,
        "kein_point_blank": u.get("cover") in rules.STRUCTURES,
    }
    if pk.get("human_wave"):
        e["human_wave"] = True  # L487 [RULE 8.14 p.68]
    for f in (
        "munition",
        "letzter_step_werte",
        "ft_reichweite",
        "moerser",
        "grenade_ranged",
        "tripod",
        "leader",
        "unbeweglich",
        "breakdown_hinweis",
        "spotter",
        "fj_breakdown",
        "breakdown",
        "rifle_grenades",
        "at_waffe",  # L187: AT weapon (Vehicle and AT Weapons Chart) and Panzerfaust shots (Normandy M6 p.40)
        "panzerfaust",
        "fahrzeug",  # L488: enemy tank (Naktong M1 package 10)
        "ambush",
    ):
        if u.get(f) is not None:
            e[f] = copy.deepcopy(u[f])
    from . import campaign  # local: campaign imports setup, which needs contact at import time

    _pm = (s.get("paket_munition") or {}).get(campaign.package_ammo_key(e))
    if _pm is not None and e.get("munition"):  # L477: package ammo per attempt (Naktong M1 p.18)
        e["munition"]["punkte"] = e["munition"]["start"] = _pm
    if e.get("spotter") or u.get("typ") == "Spotter":
        e["spotter"] = True
        e["missionen"] = (var or {}).get("missionen", 2) - 1  # [BGG E19] the automatic first mission counts
        e["karten_folge"] = (var or {}).get("karten_folge", 3)
        e["fm_wert"] = (var or {}).get("wert", -3)
        s.setdefault("feind_target", {})[t] = kid
    if u.get("infiltration"):
        # L497: base 2 cards adjusted for Experience (4.2: Veteran +1, Green -1); source per campaign
        # (Normandy CSR 6 p.14, Naktong CSR 3 p.13: 'drawing two cards (adjusted for Experience)')
        ref = pk.get("infiltration_regel") or "CSR 6 p.14"
        n_inf = 2 + {"Green": -1, "Veteran": 1}.get(e.get("erfahrung"), 0)
        if o.get("--erfolg") not in ("ja", "nein"):
            raise rules.Violation(
                f"Infiltrate Attempt of the package: {n_inf} Action cards (2, experience {e['erfahrung']}), success on the "
                f"Infiltrate symbol; --success=yes|no [{ref}, 4.2 p.21]"
            )
        if o["--erfolg"] == "ja":
            free = state.free_cover(s, place, side="Feind", steps=state.steps(e))  # L534
            if free:
                e["bereich"] = max(free, key=lambda x: x["wert"])["id"]
            prot.append(
                "Infiltrate Attempt successful: not Exposed"
                + (f", under {e['bereich']}" if e["bereich"] != "offen" else ", no free cover marker on the card")
                + f" [{ref}]"
            )
        else:
            commands.mark(e, rules.EXPOSED)
            prot.append(f"Infiltrate Attempt failed: without cover and Exposed [{ref}]")
    if u.get("exposed"):
        commands.mark(e, rules.EXPOSED)
        prot.append(f"{t}: Exposed, without cover [Normandy M3 p.27 'Squad marked Exposed out of cover']")
    return e


def package_structure(s, e, fname, cid, place, kid, prot):
    """Deep Bunker (no VOF until it leaves, CSR 5) and Bunker/Pillbox fire arc of a placed unit [5.3.2]."""
    if cid and next(x for x in state.card(s, place)["cover"] if x["id"] == cid)["typ"] == "Deep Bunker":
        e["deep_bunker"] = cid
        prot.append(
            f"{fname} in Deep Bunker {cid}: no VOF, no spotting, no Pyro, no grenades; leaves it on Fall Back or Grenade Attack in 3.4.2 (then --area=open) [CSR 5 p.14]"
        )
    if cid and next(x for x in state.card(s, place)["cover"] if x["id"] == cid)["typ"] in rules.STRUCTURES:
        e["bunker_richtung"] = kid
        prot.append(
            f"Arrow toward {kid}; fires only in this direction, never Point Blank; redraw Shift results [5.3.2]"
        )


def package_open_fire(s, e, fname, place, kid, pk, o, c, trigger, prot):
    """Place PDF/VOF of a placed unit [8.3, 8.4.3]: Place VOF No, Deep Bunker, forbidden position, the G! opening Grenade
    Attack, or fire at the trigger card. False if the weapon jammed (the unit left play). L557: split from
    contact_place_units."""
    # Place PDF/VOF
    if not pk.get("place_vof", True):
        e["kein_feuer_bis_clean_up"] = True
        prot.append(f"{fname}: Place PDF/VOF No, opens fire only in Clean Up [8.3 p.63]")
    elif e.get("deep_bunker"):  # L533 (review E6): no VOF and no target until it leaves the Deep Bunker (CSR 5)
        prot.append(f"{fname} does not open fire from the Deep Bunker; it opens fire when it leaves [CSR 5 p.14]")
    elif fire.fire_position_forbidden(s, e):  # L203: e.g. mortar placed in building cover (7.3.1)
        prot.append(f"{fname} does not open fire: {fire.fire_position_forbidden(s, e)}")
    elif e.get("vof_rating") == "G":
        g = o.get("--granate")
        if g not in ("ja", "nein"):
            n_cards = max(
                1, 2 + {"Green": -1, "Veteran": 1}.get(e.get("erfahrung"), 0)
            )  # L519: 4.2 base 2 +/- experience
            raise rules.Violation(
                f"{fname} (G!) opens with a Grenade Attack on {kid}: draw {n_cards} cards (base 2, experience {e.get('erfahrung')}), Grenade symbol (watch for Jam); --grenade=yes|no [--unit=<target>] [--critical=yes] [--jam=yes] [8.4.3 p.63, 7.3.2]"
            )
        e["ziel"], e["nur_pdf"] = kid, True
        combat.ammo_use(s, fname, e, 1, "Grenade Attack at range", prot)
        if o.get("--jam") == "ja" and grenades.jam_prone(e):  # L542 (review E4): Jam as in the Activity Check path
            grenades.jam(s, fname, prot)
            return False  # jammed: the weapon is out of play, its steps became Fire Teams
        if g == "ja":
            ze = o.get("--einheit") or (trigger[0] if len(trigger) == 1 else None)
            if not ze:
                raise rules.Violation(
                    "--unit=<target of the Grenade Attack> (stack under cover or random unit without cover)"
                )
            z = enemy.grenade_target_check(s, kid, ze, e)  # L265 (review M11)
            prot.append(f"{fname}: PDF to {kid} [7.3.2 p.53]")
            # L542 (review E4): the whole stack under the cover marker, Critical Hit and 7.10.5 notes, as enemyaction
            enemy._apply_grenade_hit(s, types.SimpleNamespace(o=o, n=fname, e=e, prot=prot), kid, ze, z)
        else:
            c["grenade_miss"] = True
            prot.append(f"{fname}: PDF to {kid}, Grenade Miss (-1) on {kid} [7.10.4]")
    elif e.get("vof_rating"):
        e["ziel"] = kid
        prot.append(
            f"{fname} opens fire on {kid}"
            + ("" if place == kid else f", PDF from {place} to {kid}" + fire.pdf_note(s, place, kid, fname))
            + (" (Small Arms on the card, Sniper VOF -3 on one target in 3.7.4)" if enemy.is_sniper(e) else "")
            + " [8.4.3]"
        )
    return True


def contact_place_units(s, c, units, kid, o, package, pk, places, prot, trigger, var):
    """Part of pc_kontakt_v4 (extracted)."""
    new_units, cid_before = [], {}
    building_list = options.list_option(o, "--gebaeude")
    for idx, (u, place) in enumerate(zip(units, places)):
        t = u["typname"]
        cid = package_cover(s, u, idx, place, kid, pk, o, building_list, cid_before, prot)
        cid_before[idx] = cid
        e = package_unit(s, u, c, place, kid, package, pk, cid, var, o, prot)
        fname = commands.new_name(s, t, reuse_removed=True)  # L215
        s["einheiten"][fname] = e
        package_structure(s, e, fname, cid, place, kid, prot)
        prot.append(
            f"Enemy {fname} ({t}, VOF {e['vof_rating']}, {e['steps']} step(s)"
            + (f", {e['munition']['punkte']} {e['munition']['typ']}" if e.get("munition") else "")
            + f") on {place}"
            + (f" under {e['bereich']}" if e["bereich"] != "offen" else " without cover")
            + (", Spotted" if e["spotted"] else ", place Unspotted marker")
        )
        if package_open_fire(s, e, fname, place, kid, pk, o, c, trigger, prot):
            new_units.append(fname)
    return new_units


def contact_place_markers(s, c, kid, o, pk, prot, var):
    """Part of pc_kontakt_v4 (extracted)."""
    for mk in pk.get("marker", []):
        if mk["typ"] == "Illum":
            # [Normandy M3 p.27, 9.2 p.70] Mortar Illumination on the trigger card
            iv = (s.get("illum_werte") or {}).get(mk.get("quelle", "Mortar Illum"))
            if o.get("--illum"):
                top_value, _, un = o["--illum"].partition("/")
                iv = {
                    "oben": rules.int_value(top_value, "--illum top value"),
                    "unten": rules.int_value(un, "--illum bottom value") if un else None,
                }
            if not iv:
                raise rules.Violation(
                    "Read the illumination values (Mortar Illumination) from the marker: --illum=<top>/<bottom> [9.2]"
                )
            c.setdefault("illum", []).append(
                {"oben": iv["oben"], "unten": iv.get("unten"), "quelle": f"Feind {mk.get('quelle', 'Mortar Illum')}"}
            )
            prot.append(
                f"Illumination marker {iv['oben']:+d}"
                + (f"/{iv['unten']:+d}" if iv.get("unten") is not None else "")
                + f" on {kid} (enemy, Mortar Illumination) [9.2]"
            )
            continue
        value = mk["wert"] if mk["wert"] is not None else (var or {}).get("wert", -3)
        c.setdefault("extern", []).append(
            {"typ": mk["typ"], "wert": value, "quelle": pk["name"], "seite": "Feind", "aktiv": mk["typ"] != "Mines"}
        )
        if mk["typ"] == "Mines":
            prot.append(
                f"Mines! marker (Draw 3 side, VOF {value}) on {kid}; every unit on {kid} checks immediately [8.7.1 p.67]"
            )
        else:
            prot.append(
                f"Incoming! marker (active, VOF {value}) on {kid}; first fire mission automatic, blocks LOS out of {kid} [8.10 p.68, 5.4]"
            )
            fire.cease_fire_on_los_loss(s, prot)  # L95: also fire THROUGH the card (5.4)


def contact_choose_places(s, own, units, kid, o, pk, places, place_list, prot, direction_list, rt):
    """Part of pc_kontakt_v4 (extracted)."""
    for idx, u in enumerate(units):
        m = u["platz"]
        if m in ("pb", "trigger"):
            places.append(kid)
            continue
        if m == "mit_zufaelligem":
            # L522 [Naktong S.18 'place Leader with one random squad'] the Leader joins a squad drawn by R#
            squads = [i for i in range(idx) if units[i].get("typ") == "Squad"]
            if not squads:
                raise rules.Violation(f"{u.get('einheit')}: no squad in the package to join")
            pick = o.get("--leader-squad")
            if len(squads) == 1:
                reference = squads[0]
            elif pick and pick.isdigit() and 1 <= int(pick) <= len(squads):
                reference = squads[int(pick) - 1]
            else:
                raise rules.Violation(
                    f"{u.get('einheit')} joins a random squad: draw R# column {len(squads)} "
                    f"(1-{len(squads)} = squad in the order of --direction); --leader-squad=<n>"
                )
            u["_ref"] = reference
            places.append(places[reference])
            continue
        if m in ("mit_vorigem", "bei_squad"):
            reference = 0
            if m == "bei_squad":
                b = o.get("--bei")
                if b not in ("1", "2"):
                    raise rules.Violation("HMG in bunker on the card of a squad: --at=1|2 (random) [Normandy M1 p.19]")
                reference = int(b) - 1
            else:
                reference = idx - 1
            places.append(places[reference])
            continue
        j = next(i for i, x in enumerate(own) if x is u)  # L275 (review H3): by identity, two equal units differ
        if j >= len(direction_list):
            raise rules.Violation(
                f"Direction per unit on its own card by R# column {rt.get('spalte', 8)} ({', '.join(f'{b} {v}' for b, v in rt.items() if b != 'spalte')}): --direction=Front|Left|Right[,..] [8.4.2 p.63]"
            )
        dir_name = direction_list[j]
        if dir_name not in DIRECTION:
            raise rules.Violation("Direction Front | Left | Right")
        hi = range_of(u, pk)
        if u.get("spotter") or u.get("typ") == "Spotter":
            hi = 3
        if place_list and j < len(place_list):
            k = place_list[j]
            state.card(s, k)
            if k == kid and m != "close":
                # [RULE 8.4.3 p.64] Point Blank placement on the trigger card if no card in the direction is valid
                if not (u.get("spotter") or u.get("typ") == "Spotter") and not (
                    u.get("cover") in rules.STRUCTURES or state.is_mortar(u)
                ):
                    places.append(k)
                    continue
                raise rules.Violation(
                    f"{u['einheit']}: Point Blank placement on {kid} not possible (spotter/structure/mortar) [8.4.3]"
                )
            if (
                geometry.direction(s, kid, k) != DIRECTION[dir_name]
                or geometry.distance(s, kid, k) > hi
                or (m == "close" and geometry.distance(s, kid, k) != 1)
                or not geometry.los(s, k, kid, hb=geometry.card_height_bonus(s, kid, "US"))[0]
            ):
                raise rules.Violation(
                    f"{k} is not in direction {dir_name} within LOS/range of {kid} [8.4.2/8.4.3 p.63]"
                )
        else:
            candidates, missing = [], None
            dr, dc = DIRECTION[dir_name]
            kt = state.card(s, kid)
            los_ok, last = True, kid  # LOS still open up to the last existing card?
            for d in [1] if m == "close" else range(1, hi + 1):
                kk = geometry.card_at(s, kt["reihe"] + dr * d, kt["spalte"] + dc * d)
                if kk is None:
                    # extension only if a new card there could have LOS: chain so far in LOS and
                    # (reading a: always, Hill possible) or (reading b: the last card lets LOS pass through it) [8.4.5, U19]
                    if los_ok and (
                        d == 1
                        or state.option(s, "U19_erweitern_bis_reichweite")
                        or geometry.see_through(state.card(s, last), (-dr, -dc), (dr, dc)) is not False
                    ):
                        missing = (kt["reihe"] + dr * d, kt["spalte"] + dc * d)
                    break
                last = kk
                los_ok = geometry.los(s, kk, kid, hb=geometry.card_height_bonus(s, kid, "US"))[0]
                if not los_ok and not pk.get("place_vof", True) and not (u.get("spotter") or u.get("typ") == "Spotter"):
                    # L525 [RULE 8.4.3 p.63 'Max LOS for these units refers to the LOS of the triggering unit', 5.4]
                    # a package without PDF counts the trigger's view INTO the card (Incoming/Smoke only block the view out)
                    los_ok = geometry.los(s, kid, kk, ha=geometry.card_height_bonus(s, kid, "US"))[0]
                if not los_ok and d > 1:
                    break
                if los_ok and not check_place_v4(s, u, kk, kid, pk) and not state.card(s, kk).get("staging"):
                    candidates.append(kk)
            if missing and (m == "close" or not candidates or state.option(s, "U19_erweitern_bis_reichweite")):
                raise rules.Violation(
                    f"Direction {dir_name}: card row {missing[0]} column {missing[1]} missing; draw a terrain card and fof.py extend {missing[0]} {missing[1]} <type>, then repeat the contact"
                    + ("" if m == "close" else state.open_reading(s, "U19_erweitern_bis_reichweite"))
                    + " [8.4.5 p.65]"
                )
            if not candidates:
                raise rules.Violation(
                    f"Direction {dir_name}: no valid card (LOS/range/8.4.3); redraw the direction, if none is possible, redraw the package [8.4.3 p.64]"
                )
            k = candidates[-1]
        reason = check_place_v4(s, u, k, kid, pk) if k not in places else None
        if reason:
            raise rules.Violation(reason + "; redraw the direction or the package [8.4.3 p.64]")
        places.append(k)
        prot.append(
            f"{u['typname']}: direction {dir_name}, {'Close Range' if m == 'close' else 'Max LOS/Range' if m == 'max' else 'Max LOS'} = card {k} [8.4.1-8.4.3 p.63]"
        )


def package_units_v4(s, package, pk, o, prot):
    """Units of a package: random choice (--choice), optional extra on an R# band (--extra), only-if-available units,
    R#-dependent placement (--r) [8.3, Normandy M1 p.19]. Returns (units, pk); pk loses an optional marker on --extra=no."""
    if pk.get("wahl"):
        w = o.get("--wahl")
        if w not in pk["wahl"]:
            raise rules.Violation(
                f"Package {package}: choice by R# ({' or '.join(pk['wahl'])}) and --choice=<{'|'.join(pk['wahl'])}> [8.3 p.62]"
            )
        units = copy.deepcopy(pk["wahl"][w])
        prot.append(f"Random package choice: {w} [8.3 p.62]")
    else:
        units = copy.deepcopy(pk.get("einheiten", []))
    opt_units = [u for u in units if u.get("optional_r")]
    opt_markers = [
        mk for mk in pk.get("marker", []) if mk.get("optional_r")
    ]  # L452: e.g. Sniper 'On R#1/3 also place Mines'
    if opt_units or opt_markers:
        z = o.get("--zusatz")
        extra = opt_units[0]["einheit"] if opt_units else opt_markers[0]["typ"]
        band = (opt_units or opt_markers)[0]["optional_r"]
        if z not in ("ja", "nein"):
            raise rules.Violation(
                f"Package {package}: extra {extra} on R# {band} (random number column {band.rsplit('/', 1)[-1] if '/' in band else 2}, BGG B4): --extra=yes|no"
            )
        if z == "nein":
            units = [u for u in units if not u.get("optional_r")]
            pk = dict(pk, marker=[mk for mk in pk.get("marker", []) if not mk.get("optional_r")])
        else:
            prot.append(f"R# {band}: {extra} added [8.3 p.62]")
    # only if available (leader)
    for u in list(units):
        if u.get("nur_wenn_verfuegbar") and in_play_count(s, u["einheit"]) >= state.countermix_count(s, u["einheit"]):
            units.remove(u)
            prot.append(f"{u['einheit']} not available, omitted (p.19 'only if available')")
    # R#-dependent placement
    if any(u.get("platz") == "r" for u in units):
        rp = pk["r_platz"]
        r = o.get("--r")
        if not r:
            raise rules.Violation(
                f"Package {package}: placement by R# column {rp.get('spalte', 10)} ({', '.join(f'{b}: {m}' for b, m in rp.items() if b != 'spalte')}); --r=<R#>"
            )
        r = rules.int_value(r, "--r")  # L269 (review H12)
        mode = next((m for b, m in rp.items() if b != "spalte" and events.r_matches(b, r)), None)
        if mode is None:
            raise rules.Violation(
                f"R# {r} is outside every band of the placement table ({', '.join(b for b in rp if b != 'spalte')})"
            )
        for u in units:
            if u.get("platz") == "r":
                u["platz"] = mode
        prot.append(f"R# {r}: placement {mode} [Normandy M1 p.19]")
    return units, pk


def package_variant(s, package, pk, o, units, prot):
    """Variant of an Incoming package (Artillery/Mortar, --variant; R# bands of the mission table, L521). Returns
    (variant or None, units)."""
    var = None
    if pk.get("varianten"):
        vn = o.get("--variante")
        if vn is None and len(pk["varianten"]) == 1:
            vn = next(
                iter(pk["varianten"])
            )  # L452: a single variant needs no draw (Normandy M7: Incoming only as Mortar)
        if vn not in pk["varianten"]:
            names = list(pk["varianten"])
            bands = [pk["varianten"][x].get("r") for x in names]
            if all(bands):
                # L521: the mission table gives R# bands (Naktong S.18: R#1-4/10 Artillery, R#5-10/10 Mortar)
                hint = ", ".join(f"R# {b} = {x}" for x, b in zip(names, bands))
                raise rules.Violation(
                    f"Package {package}: draw an Action card, {hint} (mission table); --variant=<{'|'.join(names)}>"
                )
            raise rules.Violation(
                f"Package {package}: draw a card, 1 = {names[0]}, 2 = {names[1]} (BGG B4); --variant=<{'|'.join(names)}>"
            )
        var = pk["varianten"][vn]
        prot.append(f"Variant {vn} (Incoming {var['wert']:+d}) [Normandy M1 p.19]")
        # L91 (E60): count spotter counters per firing agency (Arty Spotter / Mortar Spotter)
        if "Arty Spotter" in s.get("countermix", {}):  # only if the game keeps separate spotter counters (M4+)
            units = [
                dict(u, einheit=("Arty Spotter" if vn == "Artillery" else "Mortar Spotter"))
                if u.get("spotter") or u.get("einheit") == "Spotter"
                else u
                for u in units
            ]
        if var.get("ohne_einheiten"):
            units = []
            prot.append("without Spotter (Normandy M2 p.23: 'Artillery -4 with no Spotter')")
    return var, units


def package_counter_types(s, package, o, units, prot):
    """Counter of each unit from the countermix (8.3; several free: --type), VOF and range read from the counter where
    the setup does not know them (--vof, --range), A-rated ammo and FJ last steps [Normandy p.48]. Changes units."""
    needed, types_ = {}, []
    type_list, vof_list, range_list = (
        options.list_option(o, "--typ"),
        options.list_option(o, "--vof"),
        options.list_option(o, "--reichweite"),
    )
    for u in units:
        names = u.get("einheit_wahl") or [u["einheit"]]
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
        u.update(u.get("varianten", {}).get(t, {}))
        u["typname"] = t
        if u.get("vof_rating", "x") is None and u["typ"] not in ("Spotter", "HQ"):
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
        if u.get("vof_rating") == "A" and u.get("munition_wenn_a") and not u.get("munition"):
            u["munition"] = copy.deepcopy(u["munition_wenn_a"])
            u["letzter_step_werte"] = {"vof_rating": "A", "reichweite": "C"}
        if u.get("vof_rating") == "A/S" and u.get("fj_breakdown") and not u.get("letzter_step_werte"):
            u["letzter_step_werte"] = {
                "vof_rating": "A/S",
                "reichweite": "C",
            }  # [Normandy p.48] A/S FJ: last step Fire Team A/S • C
        if u.get("reichweite", "x") is None:
            if not range_list:
                raise rules.Violation(
                    f"{t}: range not recorded (UNVERIFIED); read it from the counter: --range=<C|L|V>[,...]"
                )
            u["reichweite"] = range_list.pop(0)
            prot.append(f"{t}: range {u['reichweite']} per counter")


def package_places(s, units, kid, o, pk, prot):
    """Cards of the units: direction per unit (--direction, Unit Placement Table) and Max LOS / Close / Point Blank
    placement [8.4.2, 8.4.3]."""
    direction_list = [
        {"Links": "Left Front", "Rechts": "Right Front"}.get(x, x) for x in options.list_option(o, "--richtung")
    ]
    place_list = options.list_option(o, "--platz")
    places = []
    own = [u for u in units if u["platz"] in ("max", "close", "max_los")]
    if len(set(direction_list)) < len(direction_list) and not pk.get("human_wave"):
        raise rules.Violation(
            "Duplicate direction: redraw (FM2 p.10, 8.4.3 'Redraw if an invalid Direction is chosen')"
        )
    rt = s.get("richtung_tabelle", {})
    contact_choose_places(s, own, units, kid, o, pk, places, place_list, prot, direction_list, rt)
    return places


def package_mine_check(s, kid, pk, prot):
    """Mines package: mine check for the units on the trigger card; Engineers draw only one card [Normandy CSR 10]."""
    if any(mk["typ"] == "Mines" for mk in pk.get("marker", [])):
        request_mine_check(s, state.units_on(s, kid), kid, prot, "Mines package")
        _eng = [
            n
            for n in state.units_on(s, kid)
            if s["einheiten"][n].get("engineer")
            and state.good_order(s["einheiten"][n])
            and state.steps(s["einheiten"][n]) >= 2
        ]
        if _eng:
            prot.append(
                f"{', '.join(_eng)}: Engineers draw only 1 action card instead of 3 for this mine check [Normandy CSR 10 'Mine Detection'] (L74)"
            )


def pc_contact_v4(s, kid, package, pk, o):
    """[RULE 8.3 p.62, 8.4 p.63-65, Normandy M1 p.19] Package with direction (Unit Placement Table), distance, cover, Place PDF/VOF, Spotted."""
    c = state.card(s, kid)
    prot = []
    trigger = state.units_on(s, kid, "US")
    if pk.get("minen_redraw") and mines_on(s, kid):
        raise rules.Violation(
            f"Mines! package on {kid}, mines already lie there: redraw the package [Normandy M4 MSR 1 p.30]"
        )
    units, pk = package_units_v4(s, package, pk, o, prot)  # L557: one function per step (review E4)
    var, units = package_variant(s, package, pk, o, units, prot)
    package_counter_types(s, package, o, units, prot)
    places = package_places(s, units, kid, o, pk, prot)
    # ---- markers (Mines, Incoming) onto the trigger card
    contact_place_markers(s, c, kid, o, pk, prot, var)
    # ---- place units
    new_units = contact_place_units(s, c, units, kid, o, package, pk, places, prot, trigger, var)
    contact_tail(s, new_units, prot)  # fired-over PC markers (8.4.4), Point Blank shift, return fire
    package_mine_check(s, kid, pk, prot)
    state.clear_pc(c)  # v4: availability only via the countermix (8.3); L550: a second marker stays
    prot.append(f"Remove PC marker from {kid} [8.2.4]")
    ak = fire.update_activity(s)
    if ak:
        prot.append(ak)
    state.save_state(s, f"Contact on {kid}: package {package} {pk['name']}; " + "; ".join(prot), "8.3 p.62, 8.4 p.63")
    print("CONTACT [RULE 8.3 p.62, 8.4.3 p.63]")
    briefing.print_board(prot, s)
