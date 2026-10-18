"""Potential contact, enemy packages and placement, external VOF markers, mines (8.1 to 8.4, 8.7)."""

import copy

from . import briefing, combat, commands, enemy, events, fire, geometry, options, rules, state


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
    v3 = state.company(s) or "optionen" in s
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
    if args and args[0] in ("aufdecken", "setzen") and cmd_pc_v4(s, args):
        return
    if not args:
        open_ = [k for k, c in s["karten"].items() if c.get("pc") and state.units_on(s, k, "US")]
        print(
            "PC markers with friendly units: "
            + (", ".join(f"{k} (PC {s['karten'][k]['pc']})" for k in open_) if open_ else "none")
        )
        return
    if args[0] not in ("kontakt", "frei"):
        kid = args[0]
        c = state.card(s, kid)
        if not c.get("pc"):
            raise rules.Violation(f"{kid} has no PC marker")
        if not state.units_on(s, kid, "US"):
            raise rules.Violation(
                f"{kid}: a PC marker is only resolved with a friendly unit on the card [RULE 8.2.4 p.62]"
            )
        if s["phase"] != "3.7.2":
            print(f"Note: PC resolution belongs in 3.7.2, currently {s['phase']}")
        # E39 (the player 07.10.2026): reveal ?-markers only on cards with friendly units (8.2.4; developer AAR BGG 2585005)
        if "?" in (c.get("pc"), c.get("pc2")) or any(
            "?" in (cc.get("pc"), cc.get("pc2")) for kk, cc in s["karten"].items() if state.units_on(s, kk, "US")
        ):
            raise rules.Violation(
                "First reveal the PC markers showing '?' on cards with friendly units: fof.py pc reveal <card> <A|B|C> [RULE 8.2.4 p.62, E39]"
            )
        higher = [
            k for k, cc in s["karten"].items() if cc.get("pc") and state.units_on(s, k, "US") and cc["pc"] < c["pc"]
        ]
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
        return
    if args[0] == "frei":
        kid = args[1]
        c = state.card(s, kid)
        if not c.get("pc"):
            raise rules.Violation(f"{kid} has no PC marker")
        old = c["pc"]
        c["pc"] = None
        state.save_state(s, f"PC {old} on {kid}: no contact, PC marker removed", "8.2.4 p.62")
        print(f"No contact on {kid}. Remove the PC marker [8.2.4].")
        print(briefing.check_stamp(s))
        return
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
        # determine the counter type for each unit
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
        new_units = []
        for u, type_name in zip(units, types_):
            values_ = dict(u)
            values_.update(u.get("varianten", {}).get(type_name, {}))
            fname = commands.new_name(s, type_name)
            cid = None
            if values_.get("cover"):
                cid = commands.new_cover_marker(s, place, values_["cover"], values_.get("cover_wert", 1))
                cv = [x for x in state.card(s, place)["cover"] if x["id"] == cid][0]
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
            new_units.append(fname)
        for between in geometry.line_between(s, place, kid) or []:
            if state.card(s, between).get("pc") and state.card(s, between).get("elevation", 1) == state.card(
                s, place
            ).get("elevation", 1):
                state.card(s, between)["pc"] = None
                prot.append(f"PC marker on {between} removed (fired over) [8.4.4]")
        if s["einheiten"][new_units[0]]["spotted"]:
            for m, f in s["einheiten"].items():
                if (
                    f["seite"] == "US"
                    and f["karte"] == place
                    and fire.is_firing(f)
                    and f["ziel"] != place
                    and not geometry.no_point_blank(s, f)
                ):
                    f["ziel"] = place
                    f.pop("konzentriert", None)
                    prot.append(f"{m} shifts fire to its own card (Point Blank), the old PDF lapses [6.1.2]")
            fire.open_fire(s, prot)
        else:
            prot.append("Enemy Unspotted: no return fire, spot it first [8.5, 6.1.1]")
    else:
        c.setdefault("extern", []).append(
            {"typ": "Incoming", "wert": pk.get("wert", -3), "quelle": pk["name"], "seite": "Feind"}
        )
        prot.append(
            f"{pk['name']}: Incoming marker (VOF {pk.get('wert', -3)}) active on {kid}, takes effect in this Combat Effects Segment; blocks LOS out of {kid} [8.10, 5.4]"
        )
        fire.cease_fire_on_los_loss(s, prot)  # L95: also fire THROUGH the card (5.4)
    pk["im_spiel"] = True
    c["pc"] = None
    prot.append(f"Remove PC marker from {kid} [8.2.4]")
    ak = fire.update_activity(s)
    if ak:
        prot.append(ak)
    state.save_state(s, f"Contact on {kid}: package {package} {pk['name']}; " + "; ".join(prot), "8.3 p.62, 8.4.3 p.63")
    print("CONTACT [RULE 8.3 p.62, 8.4.3 p.63]")
    briefing.print_board(prot, s)


def cmd_external(s, args):
    kid = args[0]
    c = state.card(s, kid)
    prot = []
    if args[1] == "weg":
        c["extern"] = []
        prot.append(f"external VOF on {kid} removed")
    else:
        type_, value = args[1], int(args[2])
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
    name = args[0]
    f = state.unit(s, name)
    if f["seite"] != "Feind":
        raise rules.Violation(f"{name} is not an enemy unit")
    prot = []
    for a in args[1:]:
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
            commands.mark(f, "Pinned")
            prot.append(f"{name} Pinned (its VOF becomes 'All Pinned' +2)")
        elif a == "unpinned":
            f["status"] = [x for x in f["status"] if x != "Pinned"]
            prot.append(f"{name} Pinned removed")
        elif a == "weg":
            enemy.remove_enemy(s, name, prot, reason="correction/removal")
            break
        elif a.startswith("karte="):
            state.card(s, a[6:])
            commands.grenade_expires(s, f, name, prot)
            f["karte"], f["bereich"] = a[6:], "offen"
            commands.mark(f, "Exposed")
            prot.append(f"{name} to {f['karte']}, Exposed [8.6.1C]")
            fire.fire_after_move(s, name, prot)
            if state.is_v4(s):
                request_mine_check(s, [name], f["karte"], prot, "enemy enters a mined card")
        elif a.startswith("cover="):
            commands.grenade_expires(s, f, name, prot)
            commands.set_area(s, f, name, a[6:])
            prot.append(f"{name} under {a[6:]}")
        elif a.startswith("steps="):
            f["steps"] = int(a[6:])
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
    ak = fire.update_activity(s)
    if ak:
        prot.append(ak)
    state.save_state(s, "; ".join(prot), "7.9.1 p.54")
    briefing.print_board(prot, s)


def mine_lock(s):
    if s.get("minen_checks"):
        raise rules.Violation(
            "First resolve the pending mine checks: "
            + ", ".join(s["minen_checks"])
            + " (fof.py mine <unit> yes|no) [7.9.1 p.54, 8.7.1 p.67]"
        )


def cmd_pc_v4(s, args):
    if args[0] == "aufdecken":
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
        kid, b = args[1], args[2]
        c = state.card(s, kid)
        if b not in ("A", "B", "C", "?"):
            raise rules.Violation("A|B|C|?")
        if c.get("pc"):
            c["pc2"] = b
        else:
            c["pc"] = b
        prot = [f"PC marker {b} on {kid} (correction/event)"]
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


def building_cover(s, place, u, r8, value_opt):
    """[CSR 8 p.15] Package in cover on Village/Farm/Cemetery/Church: R# on the building table; if the building value is equal to or better
    than the package cover, the unit goes inside; a worse result stays behind as a marker (BGG E21)."""
    tab = s.get("gebaeude_tabelle", {}).get(state.card(s, place).get("gebaeude_tabelle"), {})
    type_ = next((t for b, t in tab.items() if events.r_matches(b, int(r8))), None)
    if type_ is None:
        raise rules.Violation(f"R# {r8} not in the building table (column 8)")
    upper_ = type_.endswith("*")
    type_ = type_.rstrip("*")
    w = s.get("cover_werte", {}).get(type_)
    if w is None:
        if value_opt is None:
            raise rules.Violation(
                f"{type_}: cover value not recorded (UNVERIFIED); read it from the marker and give --building-value=<n> [CSR 8 p.15]"
            )
        w = int(value_opt)
    return type_, w, upper_


def contact_place_units(s, c, units, kid, o, package, pk, places, prot, trigger, var):
    """Part of pc_kontakt_v4 (extracted)."""
    new_units, cid_before = [], {}
    building_list = options.list_option(o, "--gebaeude")
    for idx, (u, place) in enumerate(zip(units, places)):
        t = u["typname"]
        cid = None
        if u["platz"] == "mit_vorigem" and cid_before.get(idx - 1) and not u.get("eigene_deckung"):
            cid = cid_before[idx - 1]
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
                    raise rules.Violation(
                        f"{t} in cover on {state.card(s, place)['terrain']}: R# column 8 on the building table, --building=<R#>[,..] [CSR 8 p.15]"
                    )
                gt, gw, upper_ = building_cover(s, place, u, building_list.pop(0), o.get("--gebaeude_wert"))
                if gw >= cover_value:
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
                    prot.append(
                        f"Building {gt} (+{gw}) worse than {u['cover']}: marker {gid} stays on {place} (BGG E21)"
                    )
            # L90 (E58): the same building/cover marker already lies free on the card: move in instead of a duplicate marker (5.3.3 Cover Potential)
            free = [
                x
                for x in state.card(s, place)["cover"]
                if x["typ"] == cover_type
                and x["wert"] == cover_value
                and cover_type not in rules.STRUCTURES
                and not [
                    m
                    for m in state.units_on(s, place)
                    if s["einheiten"][m].get("bereich") == x["id"] and s["einheiten"][m]["seite"] == "US"
                ]
            ]
            if free:
                cid = free[0]["id"]
                prot.append(
                    f"{t} into the existing {cover_type} {cid} (+{cover_value}) on {place} (no second marker) [E58]"
                )
            else:
                cid = commands.new_cover_marker(s, place, cover_type, cover_value)
            cv = [x for x in state.card(s, place)["cover"] if x["id"] == cid][0]
            if u.get("cover_kapazitaet"):
                cv["kapazitaet"] = u["cover_kapazitaet"]
            if cover_type in rules.STRUCTURES and place != kid:
                cv["richtung"] = list(geometry.direction(s, place, kid))
            if not free:
                prot.append(f"{cover_type} marker {cid} (+{cover_value}) on {place}")
        cid_before[idx] = cid
        spotted = bool(u.get("spotted", pk.get("spotted")))
        e = {
            "typ": u.get("typ", "Weapons Team"),
            "typname": t,
            "seite": "Feind",
            "erfahrung": u.get("erfahrung", "Line"),
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
        ):
            if u.get(f) is not None:
                e[f] = copy.deepcopy(u[f])
        if e.get("spotter") or u.get("typ") == "Spotter":
            e["spotter"] = True
            e["missionen"] = (var or {}).get("missionen", 2) - 1  # [BGG E19] the automatic first mission counts
            e["karten_folge"] = (var or {}).get("karten_folge", 3)
            e["fm_wert"] = (var or {}).get("wert", -3)
            s.setdefault("feind_target", {})[t] = kid
        if u.get("infiltration"):
            if o.get("--erfolg") not in ("ja", "nein"):
                raise rules.Violation(
                    f"Patrol (CSR 6): Infiltrate Attempt, 2 cards (experience {e['erfahrung']}), Infiltrate symbol; --success=yes|no [CSR 6 p.14]"
                )
            if o["--erfolg"] == "ja":
                free = [
                    x
                    for x in state.card(s, place).get("cover", [])
                    if not any(
                        s["einheiten"][m]["seite"] == "US" and s["einheiten"][m].get("bereich") == x["id"]
                        for m in state.units_on(s, place)
                    )
                ]
                if free:
                    e["bereich"] = max(free, key=lambda x: x["wert"])["id"]
                prot.append(
                    "patrol successful: not Exposed"
                    + (f", under {e['bereich']}" if e["bereich"] != "offen" else "")
                    + " [CSR 6 p.14]"
                )
            else:
                commands.mark(e, "Exposed")
                prot.append("Patrol failed: without cover and Exposed [CSR 6 p.14]")
        if u.get("exposed"):
            commands.mark(e, "Exposed")
            prot.append(f"{t}: Exposed, without cover [Normandy M3 p.27 'Squad marked Exposed out of cover']")
        fname = commands.new_name(s, t)
        s["einheiten"][fname] = e
        if cid and [x for x in state.card(s, place)["cover"] if x["id"] == cid][0]["typ"] == "Deep Bunker":
            e["deep_bunker"] = cid
            prot.append(
                f"{fname} in Deep Bunker {cid}: no VOF, no spotting, no Pyro, no grenades; leaves it on Fall Back or Grenade Attack in 3.4.2 (then --area=open) [CSR 5 p.14]"
            )
        if cid and [x for x in state.card(s, place)["cover"] if x["id"] == cid][0]["typ"] in rules.STRUCTURES:
            e["bunker_richtung"] = kid
            prot.append(
                f"Arrow toward {kid}; fires only in this direction, never Point Blank; redraw Shift results [5.3.2]"
            )
        prot.append(
            f"Enemy {fname} ({t}, VOF {e['vof_rating']}, {e['steps']} step(s)"
            + (f", {e['munition']['punkte']} {e['munition']['typ']}" if e.get("munition") else "")
            + f") on {place}"
            + (f" under {e['bereich']}" if e["bereich"] != "offen" else " without cover")
            + (", Spotted" if spotted else ", place Unspotted marker")
        )
        # Place PDF/VOF
        if not pk.get("place_vof", True):
            e["kein_feuer_bis_clean_up"] = True
            prot.append(f"{fname}: Place PDF/VOF No, opens fire only in Clean Up [8.3 p.63]")
        elif e.get("vof_rating") == "G":
            g = o.get("--granate")
            if g not in ("ja", "nein"):
                raise rules.Violation(
                    f"{fname} (G!) opens with a Grenade Attack on {kid}: 2 cards (experience), Grenade symbol (watch for Jam); --grenade=yes|no [--unit=<target>] [8.4.3 p.63, 7.3.2]"
                )
            e["ziel"], e["nur_pdf"] = kid, True
            combat.ammo_use(s, fname, e, 1, "Grenade Attack at range", prot)
            if g == "ja":
                ze = o.get("--einheit") or (trigger[0] if len(trigger) == 1 else None)
                if not ze:
                    raise rules.Violation(
                        "--unit=<target of the Grenade Attack> (stack under cover or random unit without cover)"
                    )
                state.unit(s, ze).setdefault("grenade", []).append(s.get("granate_vof", -4))
                prot.append(f"{fname}: PDF to {kid}, Grenade VOF {s.get('granate_vof', -4)} on {ze} [7.3.2 p.53, 7.10]")
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
                iv = {"oben": int(top_value), "unten": int(un) if un else None}
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
        j = own.index(u)
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


def pc_contact_v4(s, kid, package, pk, o):
    """[RULE 8.3 p.62, 8.4 p.63-65, Normandy M1 p.19] Package with direction (Unit Placement Table), distance, cover, Place PDF/VOF, Spotted."""
    c = state.card(s, kid)
    prot = []
    trigger = [n for n in state.units_on(s, kid, "US")]
    if pk.get("minen_redraw") and mines_on(s, kid):
        raise rules.Violation(
            f"Mines! package on {kid}, mines already lie there: redraw the package [Normandy M4 MSR 1 p.30]"
        )
    # ---- determine the package's units
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
    if opt_units:
        z = o.get("--zusatz")
        if z not in ("ja", "nein"):
            raise rules.Violation(
                f"Package {package}: extra unit on R# {opt_units[0]['optional_r']} (random number column 2, BGG B4): --extra=yes|no"
            )
        if z == "nein":
            units = [u for u in units if not u.get("optional_r")]
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
        mode = next(m for b, m in rp.items() if b != "spalte" and events.r_matches(b, int(r)))
        for u in units:
            if u.get("platz") == "r":
                u["platz"] = mode
        prot.append(f"R# {r}: placement {mode} [Normandy M1 p.19]")
    # variant (Incoming Artillery/Mortar)
    var = None
    if pk.get("varianten"):
        vn = o.get("--variante")
        if vn not in pk["varianten"]:
            raise rules.Violation(
                f"Package {package}: draw a card, 1 = {list(pk['varianten'])[0]}, 2 = {list(pk['varianten'])[1]} (BGG B4); --variant=<{'|'.join(pk['varianten'])}>"
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
    # ---- counter types (countermix, 8.3)
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
    # ---- determine cards
    direction_list = [
        {"Links": "Left Front", "Rechts": "Right Front"}.get(x, x) for x in options.list_option(o, "--richtung")
    ]
    place_list = options.list_option(o, "--platz")
    places = []
    own = [u for u in units if u["platz"] in ("max", "close", "max_los")]
    if len(set(direction_list)) < len(direction_list):
        raise rules.Violation(
            "Duplicate direction: redraw (FM2 p.10, 8.4.3 'Redraw if an invalid Direction is chosen')"
        )
    rt = s.get("richtung_tabelle", {})
    contact_choose_places(s, own, units, kid, o, pk, places, place_list, prot, direction_list, rt)
    # ---- markers (Mines, Incoming) onto the trigger card
    contact_place_markers(s, c, kid, o, pk, prot, var)
    # ---- place units
    new_units = contact_place_units(s, c, units, kid, o, package, pk, places, prot, trigger, var)
    # PC markers overshot (8.4.4)
    for fname in new_units:
        e = s["einheiten"][fname]
        if fire.is_firing(e) and e["ziel"] != e["karte"]:
            for between in geometry.line_between(s, e["karte"], kid) or []:
                if state.card(s, between).get("pc") and state.card(s, between).get("elevation", 1) == state.card(
                    s, e["karte"]
                ).get("elevation", 1):
                    state.card(s, between)["pc"] = None
                    prot.append(f"PC marker on {between} removed (overshot) [8.4.4]")
    # Point Blank fire of friendly units on the placement card, return fire on Spotted
    for fname in new_units:
        e = s["einheiten"][fname]
        if e["spotted"]:
            for m, f in s["einheiten"].items():
                if (
                    f["seite"] == "US"
                    and f["karte"] == e["karte"]
                    and fire.is_firing(f)
                    and f["ziel"] != e["karte"]
                    and not geometry.no_point_blank(s, f)
                ):
                    f["ziel"] = e["karte"]
                    prot.append(f"{m} shifts fire onto its own card (Point Blank) [6.1.2]")
    if any(s["einheiten"][f]["spotted"] for f in new_units):
        fire.open_fire(s, prot)
    elif new_units:
        prot.append("Enemy Unspotted: no return fire, spot first [8.5, 6.1.1]")
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
    c["pc"] = None  # v4: availability only via the countermix (8.3)
    prot.append(f"Remove PC marker from {kid} [8.2.4]")
    ak = fire.update_activity(s)
    if ak:
        prot.append(ak)
    state.save_state(s, f"Contact on {kid}: package {package} {pk['name']}; " + "; ".join(prot), "8.3 p.62, 8.4 p.63")
    print("CONTACT [RULE 8.3 p.62, 8.4.3 p.63]")
    briefing.print_board(prot, s)
