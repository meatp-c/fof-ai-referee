"""Campaign layer: experience, mission end, combat patrols, reattempts, reconstitution."""

import copy

from . import briefing, combat, comms, fire, geometry, options, rules, setup, state


def book_xp(s, points, reason, prot=None):
    """[RULE 12.1 p.80] Experience Points of the mission; table Normandy p.13."""
    if not state.is_v4(s) or not points:
        return
    s.setdefault("xp", []).append(
        {"zug": s["zug"], "versuch": s["kampagne"].get("versuch", 1), "punkte": points, "grund": reason}
    )
    if prot is not None:
        sum_ = sum(x["punkte"] for x in s["xp"])
        if points < 0:  # L54: spending between patrols/missions
            prot.append(f"Experience {points} spent: {reason} (remaining {sum_}) [12.3 p.81]")
        else:
            prot.append(f"Experience +{points}: {reason} (total {sum_}) [12.1 p.80, Normandy p.13]")


def xp_table(s, key):
    return s.get("kampagne", {}).get("xp_tabelle", {}).get(key, 0)


def is_cleared(s, k):
    """[RULE 12.1 p.81] Cleared: the card started with a PC marker and now has neither enemies (except casualties) nor a PC marker."""
    c = state.card(s, k)
    return bool(s.get("pc_start", {}).get(k)) and not c.get("pc") and not state.units_on(s, k, "Feind")


def is_secured(s, k):
    return is_cleared(s, k) and bool(state.units_on(s, k, "US"))


def objective_status_v4(s):
    z = s.get("ziele", {})
    zr = s["ziel_regeln"]
    parts, ok = [], True
    for key in zr.get("sichern", []):
        k = z.get(key)
        g = bool(k) and is_secured(s, k)
        ok &= g
        parts.append(
            f"{ {'primaer': 'Primary', 'sekundaer': 'Secondary'}.get(key, key) } {k or '-'} {'secured' if g else 'open'}"
        )
    for r in zr.get("reihen_klaeren", []):
        ks = [k for k, c in s["karten"].items() if c["reihe"] == r and not c.get("ausserhalb") and not c.get("staging")]
        open_ = [k for k in ks if not is_cleared(s, k)]
        ok &= not open_
        parts.append(f"Row {r} " + ("cleared" if not open_ else "open (" + ", ".join(open_) + ")"))
    return ok, "; ".join(parts)


def xp_mission_end(s, prot):
    """Card points at the end of an attempt, no card twice per mission (3.9 step 1 note, 12.1; Errata 4)."""
    tab = s["kampagne"].get("xp_tabelle", {})
    assigned = s.setdefault("xp_karten", [])
    z = s.get("ziele", {})
    special = {
        z.get("primaer"): ("primaer", "Primary Objective secured"),
        z.get("sekundaer"): ("sekundaer", "Secondary Objective secured"),
        z.get("ap"): ("ap", "Attack Position secured"),
    }
    for k in sorted(s["karten"]):
        c = s["karten"][k]
        if c.get("staging") or c.get("ausserhalb") or k in assigned:
            continue
        if k in special and k:
            if is_secured(s, k):
                book_xp(s, tab.get(special[k][0], 0), f"{special[k][1]} ({k})", prot)
                assigned.append(k)
            continue
        if is_cleared(s, k):
            pc = s["pc_start"][k]
            book_xp(
                s,
                tab.get("pc_a_karte", 2) if pc == "A" else tab.get("pc_bc_karte", 1),
                f"Card {k} with PC {pc} cleared",
                prot,
            )
            assigned.append(k)


def guards_returning(s, prot):
    """[RULE 8.15 p.69] Guard steps return between missions at their original Experience Level and are not LATs;
    replacements (12.4 p.81) only for steps lost as casualties or prisoners (K35, L126)."""
    guards = s.get("wachen", [])
    if guards:
        prot.append(
            "Guard steps returning between missions (8.15 p.69, original Experience Level, not LATs): "
            + ", ".join(f"{g['einheit']} 1 step {g['erfahrung']} (guard since turn {g['zug']})" for g in guards)
        )
    lost = s.get("us_casualties_gesamt", 0) + s.get("us_gefangen", 0)
    prot.append(
        f"Replacements only for steps lost as casualties or prisoners ({lost} this mission); surplus replacement "
        f"steps are lost [12.4 p.81]"
    )


def mission_end_v4(s, prot):
    if s.get("patrouille_mission"):
        return patrol_end(s, prot)
    ok, txt = objective_status_v4(s)
    xp_mission_end(s, prot)
    s["missionsende"] = True
    k = s["kampagne"]
    prot.append("Mission objective: " + txt + (" ACHIEVED" if ok else " NOT achieved"))
    if ok:
        vet = s.get("us_casualties_gesamt", 0) // k.get("veteran_je_casualties", 4)
        prot.append(
            f"Mission successful. Between missions (12.2 p.81): spend {sum(x['punkte'] for x in s.get('xp', []))} Experience points, "
            f"replacements {k.get('ersatz_green', 6)} Green plus {vet} Veteran ({s.get('us_casualties_gesamt', 0)} casualty steps over the whole mission, 1 per 4) [12.4 p.81, Normandy p.13]; "
            "replace ammo and assets completely (BGG E14)"
        )
        guards_returning(s, prot)
        lost = [f"{n} ({', '.join(e['skills'])})" for n, e in s["einheiten"].items() if e.get("skills")]
        if lost:
            prot.append(
                "Skills not used by the end of the mission are lost: "
                + "; ".join(lost)
                + " (remove the markers) [RULE 12.7 p.82]"
            )
            for e in s["einheiten"].values():
                e.pop("skills", None)
    elif k.get("versuch", 1) < k.get("versuche_max", 1) and state.option(s, "U9_reattempt"):
        prot.append(f"Reattempt possible (attempt {k['versuch']} of {k['versuche_max']}): fof.py reattempt [3.9 p.17]")
    else:
        prot.append(
            "No attempts left: mission failed (12.8 standard: the commander is relieved; Survivor mode: continue with the next mission) [12.8 p.82]"
        )


def patrol(s):
    return s.get("patrouille") or {}


def patrol_move(s, n, from_, target_card, prot):
    """[MSR 2] Route Points in order, pass the Primary, return across the MLR from row 2 to row 1."""
    p = patrol(s)
    if not p or p.get("erfolg"):
        return
    if n not in p.get("mitglieder", []):
        # [Normandy M3 p.24 'at least one unit'; BGG 3760839: also LAT, Staff, HQ of the patrol] LATs from patrol units count too
        if s["einheiten"].get(n, {}).get("herkunft") in p.get("mitglieder", []):
            p.setdefault("mitglieder", []).append(n)
        else:
            return
    z = s.get("ziele", {})
    route = [z.get("route", {}).get(str(i)) for i in (1, 2, 3, 4)]
    i = p.get("route_index", 0)
    if i < 4 and route[i] == target_card:
        p["route_index"] = i + 1
        prot.append(f"Route Point {i + 1} on {target_card} reached: remove marker [MSR 2]")
        book_xp(
            s, xp_table(s, "cp_route") or 1, f"Route Point {i + 1} ({target_card}), patrol Platoon {p['platoon']}", prot
        )
        # [BGG Shonai_Dweller 3552585, 3520262] if a patrol unit already stands on the next Route Point, it is taken at once as well
        while p["route_index"] < 4:
            j = p["route_index"]
            da = [
                m for m in p.get("mitglieder", []) if m in s["einheiten"] and s["einheiten"][m].get("karte") == route[j]
            ]
            if not da:
                break
            p["route_index"] = j + 1
            prot.append(
                f"Route Point {j + 1} on {route[j]}: {', '.join(da)} already there, remove marker [MSR 2, BGG 3552585]"
            )
            book_xp(
                s,
                xp_table(s, "cp_route") or 1,
                f"Route Point {j + 1} ({route[j]}), patrol Platoon {p['platoon']}",
                prot,
            )
    er = s.get("ereignis_route")
    if (
        er
        and er.get("zug") == s["zug"]
        and not er.get("erfuellt")
        and er.get("ziel")
        and geometry.distance(s, target_card, er["ziel"]) < geometry.distance(s, from_, er["ziel"])
    ):
        er["erfuellt"] = True
        prot.append(f"CO HQ is Screaming for Action fulfilled: {n} moves toward {er['ziel']} [Normandy M3 p.26]")
        book_xp(s, 1, "HQ event CO HQ is Screaming for Action fulfilled", prot)
    if target_card == z.get("primaer") and not p.get("primaer_besucht"):
        p["primaer_besucht"] = True
        prot.append(f"Primary Objective {target_card} passed [Normandy M3 p.24]")
    if (
        p.get("route_index", 0) == 4
        and p.get("primaer_besucht")
        and state.card(s, from_)["reihe"] == 2
        and state.card(s, target_card)["reihe"] == 1
    ):
        p["erfolg"] = True
        prot.append(f"Patrol successful: {n} crosses the MLR from row 2 to row 1 [Normandy M3 p.24]")
        book_xp(s, xp_table(s, "cp_erfolg") or 5, f"Patrol Platoon {p['platoon']} successful", prot)


def patrol_reserve(s, prot):
    """[MSR 1, MSR 4] Units not set up are missing from this patrol; set aside until the next patrol."""
    res = s.setdefault("patrouille_reserve", {})
    gone = [n for n, e in s["einheiten"].items() if e["seite"] == "US" and not e.get("karte")]
    for n in gone:
        res[n] = {"einheit": s["einheiten"].pop(n), "kommando": s["kommandos"].pop(n, None)}
    if gone:
        prot.append("Not set up, missing from this patrol: " + ", ".join(gone) + " [MSR 1, MSR 4]")


def patrol_reserve_back(s, prot):
    res = s.pop("patrouille_reserve", {})
    for n, x in res.items():
        s["einheiten"][n] = x["einheit"]
        if x.get("kommando") is not None:
            s["kommandos"][n] = x["kommando"]
    if res:
        prot.append("Back for the next patrol: " + ", ".join(res))


def patrol_end(s, prot):
    """End of a patrol (10 turns): Primary cleared (+4), next patrol or mission end [MSR 1, Normandy p.13]."""
    p = patrol(s)
    z = s.get("ziele", {})
    pk = z.get("primaer")
    assigned = s.setdefault("xp_karten", [])
    if pk and pk not in assigned and is_cleared(s, pk):
        book_xp(
            s,
            xp_table(s, "cp_primaer") or 4,
            f"Primary Objective {pk} cleared (patrol Platoon {p.get('platoon')})",
            prot,
        )
        assigned.append(pk)
    s["missionsende"] = True
    erl = p.setdefault("erledigt", [])
    if p.get("platoon") and p["platoon"] not in erl:
        erl.append(p["platoon"])
    # L166 [RULE 12.3.1 p.81]: remember who took part, for promotions after this and later patrols
    tg = p.setdefault("teilgenommen", [])
    tg.extend(m for m in p.get("mitglieder", []) if m not in tg)
    remainder = [x for x in ("1", "2", "3") if x not in erl]
    prot.append(
        f"Patrol {len(erl)} (Platoon {p.get('platoon')}) ended: "
        + (
            "SUCCESSFUL"
            if p.get("erfolg")
            else f"not successful (Route Points {p.get('route_index', 0)}/4, Primary {'passed' if p.get('primaer_besucht') else 'not passed'})"
        )
        + "; XP only for the patrol platoon [MSR 1]"
    )
    if remainder:
        prot.append(
            f"Next patrol: fof.py patrol next <{'|'.join(remainder)}> (3.9 sequence, new PCs, cover and mines remain) [MSR 1, MSR 3]"
        )
    else:
        prot.append(
            "All three patrols played: Mission 3 ended; Combat Patrols carry no penalty on failure (standard mode) [MSR 1]"
        )


def cmd_patrol(s, args):
    """patrol | patrol start <platoon> [--with=a,b] | patrol next <platoon> [--with=a,b]"""
    if not s.get("patrouille_mission"):
        raise rules.Violation("Not a Combat Patrol mission")
    p = s.setdefault("patrouille", {})
    if not args:
        z = s.get("ziele", {})
        print(
            f"Patrol {len(p.get('erledigt', [])) + (0 if s.get('missionsende') else 1)}: Platoon {p.get('platoon') or '-'}; members: {', '.join(p.get('mitglieder', [])) or '-'}"
        )
        print(
            "Route: "
            + ", ".join(f"{i} {z.get('route', {}).get(str(i)) or '-'}" for i in (1, 2, 3, 4))
            + f"; reached {p.get('route_index', 0)}/4; Primary {z.get('primaer') or '-'} {'passed' if p.get('primaer_besucht') else 'open'}; success {'yes' if p.get('erfolg') else 'no'}"
        )
        print(f"Done: {', '.join(p.get('erledigt', [])) or 'none'}")
        return
    o = options.parse_opts(args[2:])
    prot = []
    if args[0] == "naechste":
        if not s.get("missionsende"):
            raise rules.Violation("First finish the current patrol (10 turns) [MSR 1]")
        if args[1] in p.get("erledigt", []):
            raise rules.Violation(f"Platoon {args[1]} has already done its patrol [MSR 1]")
        s["patrouille_wechsel"] = True
        cmd_reattempt(s, [])
        s = state.load_state()
        s.pop("patrouille_wechsel", None)
        patrol_reserve_back(s, prot)
        s["licht"] = None
        s.pop("konzentration_gesetzt", None)
        prot.append(
            "New visibility for this patrol: draw R#4 (1=+2 ... 4=+5), fof.py visibility <light>; place units with setup on row 1 or in the COP, then fof.py reattempt done [Normandy M3 p.24, MSR 1]"
        )
        p = s.setdefault("patrouille", {})
    elif args[0] != "start":
        raise rules.Violation("patrol | patrol start <platoon> [--with=..] | patrol next <platoon> [--with=..]")
    if not state.in_setup(s):
        raise rules.Violation("Set the patrol only before turn 1 [MSR 1]")
    plt = args[1]
    hqs = {x.get("platoon"): m for m, x in s["einheiten"].items() if x.get("ebene") == "PLT" and x["seite"] == "US"}
    if plt not in hqs:
        raise rules.Violation(f"Platoon {plt} unknown; available: {', '.join(sorted(k for k in hqs if k))}")
    with_ = options.list_option(o, "--mit")
    for m in with_:
        x = state.unit(s, m)
        if x.get("ebene") == "PLT" or (x["typ"] == "Squad" and x.get("platoon") != plt):
            raise rules.Violation(f"{m}: only Weapons Teams, FOs and Company Staff may join the patrol [2.6.1]")
    members = [m for m, x in s["einheiten"].items() if x["seite"] == "US" and (x.get("platoon") == plt or m in with_)]
    for m, x in s["einheiten"].items():
        if x["seite"] != "US":
            continue
        if m in members:
            x.pop("stationaer", None)
        else:
            x["stationaer"] = True
    p.update(platoon=plt, mitglieder=members, route_index=0, primaer_besucht=False, erfolg=False)
    s["einzelzug"] = True
    row1 = sorted(
        k for k, c in s["karten"].items() if c["reihe"] == 1 and not c.get("staging") and not c.get("ausserhalb")
    )
    prot.append(
        f"Patrol Platoon {plt}: {', '.join(members)}; setup on row 1 (setup <unit> <{row1[0]}-{row1[-1]}>)"
    )  # L159: row 1 from the map (M5 has six columns)
    without = [
        m
        for m in members
        if s["einheiten"][m]["typ"] not in ("Staff",)
        and s["einheiten"][m].get("ebene") not in ("CO", "BN")
        and not s["einheiten"][m].get("platoon")
    ]
    if without:
        prot.append(
            f"Unassigned: {', '.join(without)}; without assignment only the CO HQ and Staff can order them (2.3.3). Assign for the whole mission: "
            f"setup <unit> --platoon={plt} [RULE 2.3.3 p.10, K25]"
        )
    prot.append(
        "Other units: into the fortifications of row 1 or into the Combat Outpost (at most one platoon); they fire and accept orders but do not move; units not set up are missing from this patrol [MSR 1, MSR 4]"
    )
    prot.append(
        "Before turn 1: objective primary <row 4>, objective route 1-4 <rows 2-4>, Artillery Concentration (fof.py note), visibility <light> (R4: 1=+2 ... 4=+5); GI draw halved [3.3.2d]"
    )
    state.save_state(s, "; ".join(prot), "2.6 p.12, MSR 1")
    briefing.print_board(prot, s)


def _between_missions(s):
    return state.in_setup(s) or s.get("missionsende") or s.get("reattempt_setup")


def _promoted_steps(s):
    """L166: promoted steps per unit in this between-mission/patrol window (old list format = whole unit counted)."""
    b = s.get("befoerdert") or {}
    if isinstance(b, list):
        b = {n: 99 for n in b}
    return b


def cmd_xp_promote(s, args):
    """xp promote <unit> --from=Green|Line --steps=<n> [--result=<level>]: 12.3 one level per step, 1 XP Green to Line, 3 XP
    Line to Veteran, one level per mission, no attachments, Combat Patrol: only patrol members (12.3.1). L146"""
    if not _between_missions(s):
        raise rules.Violation("Promotions only between missions or patrols (12.2, 3.9)")
    n = args[0]
    o = options.parse_opts(args[1:])
    e = state.unit(s, n)
    frm = o.get("--aus")
    if frm not in rules.PROMOTION_COST:
        raise rules.Violation("--from=Green|Line (a step rises one level per mission) [RULE 12.3 p.81]")
    steps = int(o.get("--steps", 1))
    if e.get("attachment"):
        raise rules.Violation(f"{n} is an attachment: no promotion with Experience Points [RULE 12.3 p.81]")
    # L166 [RULE 12.3 p.81] 'You may only increase a step by one Level': counted per step, not per unit
    done_steps = _promoted_steps(s).get(n, 0)
    if done_steps + steps > max(1, state.steps(e)):
        raise rules.Violation(
            f"{n}: {done_steps} of {state.steps(e)} step(s) already promoted this time; one level per step and mission [RULE 12.3 p.81]"
        )
    p = s.get("patrouille") or {}
    if s.get("patrouille_mission"):
        # L166 [RULE 12.3.1 p.81] 'only units that participated in a patrol may be promoted': members of finished patrols
        erl = p.get("erledigt", [])
        took_part = set(p.get("teilgenommen", [])) | {
            m for m, x in s["einheiten"].items() if x["seite"] == "US" and x.get("platoon") in erl
        }
        if n not in took_part and e.get("herkunft") not in took_part:
            raise rules.Violation(
                f"{n} has not yet taken part in a patrol of this mission: no promotion [RULE 12.3.1 p.81, Normandy MSR 1]"
            )
    if state.is_lat(e) and e["typ"] != "Fire Team":
        raise rules.Violation("LATs are reconstituted first (12.2), promotion then on the squad")
    cost = rules.PROMOTION_COST[frm] * steps
    if sum(x["punkte"] for x in s.get("xp", [])) < cost:
        raise rules.Violation(f"Not enough Experience Points ({cost} needed) [RULE 12.3 p.81]")
    new = o.get("--ergebnis") or ("Line" if frm == "Green" else "Veteran")
    prot = []
    book_xp(
        s,
        -cost,
        f"promotion {n}: {steps} step(s) {frm} to {'Line' if frm == 'Green' else 'Veteran'}, unit now {new}",
        prot,
    )
    e["erfahrung"] = new
    pr = _promoted_steps(s)
    pr[n] = pr.get(n, 0) + steps
    s["befoerdert"] = pr
    prot.append(f"{n}: experience {new} (12.6 table for mixed steps: --result=)")
    state.save_state(s, "; ".join(prot), "12.3 p.81, 12.6 p.82")
    briefing.print_board(prot, s)


def skill_markers_fit(markers, wanted):
    """L158 [RULE 12.7 p.82 'Skills are limited by what is available in the counter mix']: can every wanted skill get its own
    two-sided marker (one face per marker)? Small backtracking matching."""

    def place(i, used):
        if i == len(wanted):
            return True
        for j, m in enumerate(markers):
            if j not in used and wanted[i] in m and place(i + 1, used | {j}):
                return True
        return False

    return place(0, frozenset())


def cmd_xp_skill(s, args):
    """xp skill <HQ> <skill>: buy a skill marker (12.7): cost from the Skills chart, at most three per HQ/Staff, counter mix. L146"""
    if not _between_missions(s):
        raise rules.Violation("Skills are bought between missions or patrols [RULE 12.7 p.82]")
    n, skill = args[0], " ".join(args[1:]).split("--")[0].strip()
    o = options.parse_opts([a for a in args[1:] if a.startswith("--")])
    e = state.unit(s, n)
    if not (state.is_hq(e) or e["typ"] == "Staff"):
        raise rules.Violation("Skill markers go to a PLT HQ, CO Staff or the CO HQ [RULE 12.7 p.82]")
    if skill not in rules.SKILL_COST:
        raise rules.Violation(f"Skill unknown; known: {', '.join(rules.SKILL_COST)}")
    if len(e.get("skills") or []) >= rules.SKILLS_MAX_PER_HQ:
        raise rules.Violation(f"{n} already holds {rules.SKILLS_MAX_PER_HQ} Skill markers [RULE 12.7 p.82]")
    in_play = [sk for x in s["einheiten"].values() for sk in (x.get("skills") or [])]
    markers = s.get("skill_marker") or rules.SKILL_MARKERS_NORMANDY
    if not skill_markers_fit(markers, in_play + [skill]):
        raise rules.Violation(
            f"Skill {skill}: no free marker with this face (two-sided markers, in play: {', '.join(in_play) or 'none'}) [RULE 12.7 p.82, E67]"
        )
    cost = int(o.get("--kosten", rules.SKILL_COST[skill]))
    if sum(x["punkte"] for x in s.get("xp", [])) < cost:
        raise rules.Violation(f"Not enough Experience Points ({cost} needed) [RULE 12.7 p.82]")
    prot = []
    book_xp(s, -cost, f"Skill {skill} for {n}", prot)
    e.setdefault("skills", []).append(skill)
    prot.append(
        f"{n}: Skill marker {skill} ({len(e['skills'])} of {rules.SKILLS_MAX_PER_HQ}); PLT HQ: usable by its platoon, CO HQ/Staff: only by that unit [12.7 p.82]"
    )
    state.save_state(s, "; ".join(prot), "12.7 p.82")
    briefing.print_board(prot, s)


def cmd_xp(s, args):
    if not state.is_v4(s):
        raise rules.Violation("Experience only in campaign missions")
    if args and args[0] in ("befoerdern", "promote"):
        return cmd_xp_promote(s, args[1:])
    if args and args[0] in ("skill",):
        return cmd_xp_skill(s, args[1:])
    if args and args[0] in ("plus", "ausgeben"):
        n = int(args[1]) * (1 if args[0] == "plus" else -1)
        reason = " ".join(args[2:]) or ("manual" if n > 0 else "spent")
        prot = []
        if n < 0 and sum(x["punkte"] for x in s.get("xp", [])) + n < 0:
            raise rules.Violation("Not enough Experience Points")
        book_xp(s, n, reason, prot)
        state.save_state(s, "; ".join(prot), "12.1 p.80, 12.3 p.81")
        briefing.print_board(prot, s)
        return
    for x in s.get("xp", []):
        print(f"- T{x['zug']} A{x['versuch']}: {x['punkte']:+d} {x['grund']}")
    print(
        f"Total {sum(x['punkte'] for x in s.get('xp', []))}; cards already scored: {', '.join(s.get('xp_karten', [])) or 'none'}"
    )
    ok, txt = objective_status_v4(s)
    print("Status now: " + txt)


def cmd_reattempt(s, args):
    """[RULE 3.9 p.17/18] Reattempt preparation, steps 1-14."""
    k = s.get("kampagne", {})
    if args and args[0] == "fertig":
        if not s.get("reattempt_setup"):
            raise rules.Violation("No reattempt preparation pending")
        prot = []
        s.pop("befoerdert", None)  # L146: one promotion level per mission/patrol
        for n, e in list(s["einheiten"].items()):
            if e["seite"] == "US" and state.is_lat(e) and e["typ"] != "Fire Team":
                e["typ"], e["erfahrung"] = "Fire Team", "Green"
                combat.set_lat_values(e, "Fire Team")
                prot.append(f"{n} becomes a Fire Team (step 4)")
            if e["seite"] == "US":
                e["status"] = []
        wrong = [
            n
            for n, e in s["einheiten"].items()
            if e["seite"] == "US"
            and e.get("karte")
            and not state.card(s, e["karte"]).get("staging")
            and not is_secured(s, e["karte"])
            and not (
                s.get("patrouille_mission")
                and (state.card(s, e["karte"])["reihe"] == 1 or e["karte"] == s.get("ziele", {}).get("cop"))
            )
        ]
        if wrong:
            raise rules.Violation(
                "Friendly units only in the Staging Area or on secured cards (step 5): " + ", ".join(wrong)
            )
        if s.get("patrouille_mission"):
            open_steps = [
                n
                for n, e in s["einheiten"].items()
                if e["seite"] == "US"
                and e.get("stationaer")
                and e.get("karte")
                and state.card(s, e["karte"]).get("cover")
                and e.get("bereich", "offen") == "offen"
            ]  # L55
            if open_steps:
                raise rules.Violation(
                    "Place non-patrol units in the fortifications (setup <unit> <card> --area=C1|C2): "
                    + ", ".join(open_steps)
                    + " [Normandy M3 p.26 MSR 1]"
                )
            fa = [x for x in setup.check_setup_v4(s) if not x.startswith("Terrain")]
            if (
                s.get("assets_start")
                and not any(e.get("assets") for e in s["einheiten"].values() if e["seite"] == "US")
                and not s.get("assets_bewusst_leer")
            ):  # L57: step 12 puts all assets into the pool
                fa.append(
                    "Distribute assets: setup <unit> --asset=<type> (pool: "
                    + ", ".join(f"{a} {b}" for a, b in s.get("assets_pool", {}).items() if b)
                    + ") [3.9 step 12, 2.3.4 p.10]"
                )
            if s.get("fm_werte") and not s.get("konzentration_gesetzt"):  # L56
                fa.append(
                    "Artillery Concentration: objective concentration <card> <firing agency> [Normandy M3 p.24, 7.16.5]"
                )
            if fa:
                raise rules.Violation("Still open before turn 1 of the patrol: " + "; ".join(fa))
            patrol_reserve(s, prot)
        s["reattempt_setup"] = False
        s["aufstellung_fertig"] = True
        fire.open_fire(s, prot)
        ak = fire.update_activity(s)
        if ak:
            prot.append(ak)
        prot.append(
            f"Attempt {k.get('versuch')} starts with turn 1 (steps 13/14); no new PC markers, Spotted status remains [3.9 p.18]"
        )
        state.save_state(s, "Reattempt: " + "; ".join(prot), "3.9 p.18")
        briefing.print_board(prot, s)
        return
    if not s.get("missionsende"):
        raise rules.Violation(
            "Reattempt only after the last turn (Clean Up of turn {}) [3.9 p.17]".format(s.get("max_zuege"))
        )
    if not s.get("patrouille_mission"):
        ok, txt = objective_status_v4(s)
        if ok:
            raise rules.Violation("Mission objective achieved, no reattempt needed")
        if k.get("versuch", 1) >= k.get("versuche_max", 1) or not state.option(s, "U9_reattempt"):
            raise rules.Violation("No more reattempts allowed [3.9 p.17]")
    elif not s.get("patrouille_wechsel"):
        raise rules.Violation("Combat Patrol: next patrol with fof.py patrol next <platoon> [MSR 1]")
    prot = [f"Experience so far {sum(x['punkte'] for x in s.get('xp', []))} (step 1; cards not counted twice)"]
    for n, e in s["einheiten"].items():
        if e["seite"] == "US" and state.fire_team_side(e):
            e["status"] = [x for x in e["status"] if x != "Fire Team side"]
            prot.append(f"{n} to the Good Order side (step 2)")
    for kid, c in s["karten"].items():
        if c.get("casualties") or c.get("casualties_feind"):
            prot.append(f"{kid}: casualties removed (step 6)")
            c["casualties"] = c["casualties_feind"] = 0
        c["extern"] = [x for x in c.get("extern", []) if x["typ"] == "Mines"]
        for x in c["extern"]:
            x["aktiv"] = False
        c.pop("grenade_miss", None)
        c["assets"] = []
        c["munition"] = {}
    for n, e in list(s["einheiten"].items()):
        if e["seite"] == "Feind" and e["typ"] in ("Paralyzed Team", "Litter Team"):
            del s["einheiten"][n]
            prot.append(f"{n} removed (step 6)")
        if e.get("ebene") == "BN" and e["seite"] == "US":
            del s["einheiten"][n]
            s["kommandos"].pop(n, None)
            prot.append(f"{n} (Checking Up) leaves the board; events end with the attempt (turn counter restarts)")
    for n, e in s["einheiten"].items():
        if e["seite"] == "Feind" and e.get("bereich", "offen") == "offen":
            free = [
                cv
                for cv in state.card(s, e["karte"]).get("cover", [])
                if not any(
                    s["einheiten"][m]["seite"] == "US" and s["einheiten"][m].get("bereich") == cv["id"]
                    for m in state.units_on(s, e["karte"])
                )
            ]
            if free:
                e["bereich"] = max(free, key=lambda x: x["wert"])["id"]
                prot.append(f"{n} under {e['bereich']} (step 8; if there is too little cover, distribute randomly)")
        e["status"] = [x for x in e["status"] if x not in ("Pinned", "Exposed")]
        e["ziel"] = None
        for f in (
            "ziel_offen",
            "konzentriert",
            "cf",
            "grenade",
            "grenade_critical",
            "cf_critical",
            "mine_hit",
            "nur_pdf",
            "indirekt",
            "munition_leer",
            "kein_feuer_bis_clean_up",
        ):
            e.pop(f, None)
        m = e.get("munition")
        if m and m.get("start") is not None:
            m["punkte"] = m["start"]
            e.pop("out_of_ammo", None)
        if e.get("spotter"):
            e["missionen"] = 2
        if e["seite"] == "US" and e.get("attachment") is None:
            orig = s.get("aufbau_einheiten", {}).get(n, {})
            if orig.get("funk") is not None:
                e["funk"] = copy.deepcopy(orig["funk"])
                if s.get("co_tac_mittel") == "telefon":
                    for g in e["funk"]:
                        if g["netz"] == "CO TAC":
                            g["typ"] = "EE8"
        e.pop("assets", None)
    prot.append(
        "Pinned, PDF and VOF removed, ammo and assets replenished, dropped assets off the board (steps 10-12); cover markers and mines remain (step 7)"
    )
    for kk in s["kommandos"].values():
        kk.update(verfuegbar=0, gespart=0, aktiviert=False, fertig=False)
    s["feuermissionen"] = copy.deepcopy(s.get("fm_start", s.get("feuermissionen")))
    s["target_marker"] = {}
    s["assets_pool"] = copy.deepcopy(s.get("assets_start", s.get("assets_pool", {})))
    # L58: turn-based event flags apply only in the attempt in which they were drawn (turn counter restarts, 3.9 step 13)
    for _f in ("hold_up", "ereignis_pflicht", "ereignis_flanke", "ereignis_route", "fm_gesperrt", "ereignis_erledigt"):
        s.pop(_f, None)
    if s.get("gegenangriff"):
        s["feind_taktik"] = s["gegenangriff"].get("taktik_vorher", s.get("feind_taktik"))
        s.pop("gegenangriff")
        prot.append("Counterattack ends with the last turn (BGG E16)")
    if s.get("patrouille_mission"):
        new_pc = []
        for kid, letter in s.get("pc_start", {}).items():
            c = state.card(s, kid)
            if not c.get("pc") and kid != s.get("ziele", {}).get("cop"):
                c["pc"] = letter
                new_pc.append(kid)
        z = s.setdefault("ziele", {})
        z["primaer"], z["route"] = None, {}
        s["target_marker"] = {}
        prot.append(
            ("New PC markers on " + ", ".join(sorted(new_pc)) if new_pc else "No PC markers to replace")
            + "; place Primary, Route Points and Artillery Concentration again (objective primary/route) [2.6.3, MSR 1, Normandy M3 p.24]"
        )
    k["versuch"] = k.get("versuch", 1) + 1
    s["zug"], s["phase"] = 1, state.sop(s)[0][0]
    s["reattempt_setup"] = True
    s.pop("missionsende", None)
    s["aktiver_hq"] = None
    ak = fire.update_activity(s)
    if ak:
        prot.append(ak)
    lats = [n for n, e in s["einheiten"].items() if e["seite"] == "US" and state.is_lat(e)]
    prot.append(
        f"Attempt {k['versuch']}: reconstitute now (reconstitute <unit> --from=<LAT,..>; LATs: {', '.join(lats) or 'none'}; 1 Green step per LAT, new HQs Green), "
        "spend Experience (xp spend <n> <reason>, set <unit> erfahrung=..), distribute assets (setup --asset), "
        "place units on secured cards or in Staging (setup <unit> <card> [--area=<cover>]), then fof.py reattempt done [3.9 p.17/18]"
    )
    state.save_state(s, "Reattempt preparation: " + "; ".join(prot), "3.9 p.17")
    briefing.print_board(prot, s)


def experience_from_steps(levels):
    """[RULE 12.6 p.82] experience of a multi-step unit from its steps (table 12.6, read from the rulebook layout):
    2 steps: V+L/G Line, L+G Green; 3 steps: VVG Line, VVL Veteran, LL+any Line, GGV Line, GGL Green, VLG Line;
    4 steps: VVV+any Veteran, VV+any+any Line, LLL+any Line, LLVG Line, LLGG Green, GGG+any Green. None = not in the table. L152"""
    order = {"Veteran": 0, "Line": 1, "Green": 2}
    lv = sorted(levels, key=lambda x: order.get(x, 1))
    if not lv or any(x not in order for x in lv):
        return None
    if len(set(lv)) == 1:
        return lv[0]
    c = {x: lv.count(x) for x in order}
    if len(lv) == 2:
        return "Line" if c["Veteran"] else "Green"
    if len(lv) == 3:
        if c["Veteran"] == 2:
            return "Veteran" if c["Line"] else "Line"
        if c["Line"] >= 2:
            return "Line"
        if c["Green"] == 2:
            return "Line" if c["Veteran"] else "Green"
        return "Line"  # V L G
    if len(lv) == 4:
        if c["Veteran"] >= 3:
            return "Veteran"
        if c["Veteran"] == 2:
            return "Line"
        if c["Line"] >= 3:
            return "Line"
        if c["Green"] >= 3:
            return "Green"
        if c["Line"] == 2:
            return "Green" if c["Green"] == 2 else "Line"  # LLGG Green, LLVG Line
        return None  # V L G G: not in the table
    return None


def cmd_reconstitute(s, args):
    """[RULE 3.9 step 3 p.17] Squads, HQs and company weapons teams (no attachments) from LATs; each LAT = 1 Green step."""
    if not s.get("reattempt_setup"):
        raise rules.Violation("reconstitute only during reattempt preparation (3.9); during the turn use 4.2.3i/4.2.1d")
    n = args[0]
    o = options.parse_opts(args[1:])
    lats = options.list_option(o, "--aus")
    if not lats:
        raise rules.Violation("Specify --from=<LAT>[,<LAT>..]")
    for t in lats:
        te = state.unit(s, t)
        if te["seite"] != "US" or not state.is_lat(te):
            raise rules.Violation(f"{t} is not a friendly LAT")
    orig = s.get("aufbau_einheiten", {}).get(n)
    if not orig:
        raise rules.Violation(f"{n} is not part of the company according to the setup")
    if orig.get("attachment"):
        raise rules.Violation(f"{n} is an attachment, no reconstitution (3.9 step 3)")
    prot = []
    maxst = orig.get("steps", 1)
    old_level = s["einheiten"][n].get("erfahrung", "Line") if n in s["einheiten"] else None
    if n in s["einheiten"]:
        e = s["einheiten"][n]
        if state.steps(e) + len(lats) > maxst:
            raise rules.Violation(f"{n} has at most {maxst} steps")
        e["steps"] = state.steps(e) + len(lats)
        prot.append(f"{n} at {e['steps']} steps")
    else:
        if len(lats) > maxst:
            raise rules.Violation(f"{n} has at most {maxst} steps")
        e = copy.deepcopy(orig)
        e.update(karte=s["einheiten"][lats[0]]["karte"], bereich="offen", status=[], steps=len(lats), ziel=None)
        if state.is_hq(e):
            e["erfahrung"] = "Green"
        if n in s.get("removed_from_play", []):
            s["removed_from_play"].remove(n)
        s["einheiten"][n] = e
        if state.is_hq(e):
            s["kommandos"].setdefault(n, {"verfuegbar": 0, "gespart": 0, "aktiviert": False, "fertig": False})
        prot.append(
            f"{n} with {len(lats)} step(s) on {e['karte']}"
            + (", Green (new HQs are always Green)" if state.is_hq(e) else "")
        )
    if o.get("--erfahrung") and not state.is_hq(e):
        e["erfahrung"] = o["--erfahrung"]
        prot.append(f"Experience {o['--erfahrung']} (12.6 table, promotions via xp spend)")
    elif not state.is_hq(e):
        old_steps = state.steps(e) - len(lats)
        # L167 [RULE 3.9 step 3, 12.2 'Reduce all other LAT units to Green']: each LAT counts as one Green step
        levels = [old_level] * old_steps + ["Green"] * len(lats)
        derived = experience_from_steps(levels)  # L152 [RULE 12.6 p.82]
        if derived:
            e["erfahrung"] = derived
            prot.append(
                f"Experience {derived} from the steps {'+'.join(x[0] for x in levels)} (table 12.6; set --experience= for a different step mix)"
            )
        else:
            s.setdefault("_hinweise", []).append(
                f"{n}: step mix {'+'.join(x[0] for x in levels)} is not in table 12.6; set the experience with --experience= or set"
            )
    for t in lats:
        del s["einheiten"][t]
    prot.append(f"used up: {', '.join(lats)}")
    state.save_state(s, "Reconstitution: " + "; ".join(prot), "3.9 p.17, 12.6 p.82")
    briefing.print_board(prot, s)


def cmd_campaign(s, args):
    k = s.get("kampagne")
    if not k:
        print("No campaign mission.")
        return
    print(
        f"# Mission Log {k.get('name')} Mission {k.get('mission_nr')}, attempt {k.get('versuch')} of {k.get('versuche_max')}, turn {s['zug']}"
    )
    for a, b in k.get("log", {}).items():
        print(f"- {a}: {b}")
    print(
        f"- CO TAC: {s.get('co_tac_mittel') or 'not chosen yet (CSR 1)'}; Mortar: {s.get('moerser_wahl') or 'not chosen yet (CSR 2)'}"
    )
    print(
        "- Objectives: "
        + ", ".join(f"{a} {b}" for a, b in s.get("ziele", {}).items() if a != "phaselines")
        + (f", Phase Lines {s['ziele'].get('phaselines')}" if s.get("ziele", {}).get("phaselines") else "")
    )
    print(
        "- Pyro (Mission Log): "
        + (", ".join(f"{a}={b}" for a, b in s.get("pyro_belegung", {}).items()) or "no assignment")
    )
    print("- Asset-Pool: " + ", ".join(f"{a} {b}" for a, b in s.get("assets_pool", {}).items() if b))
    print(f"- Fire Missions: {s.get('feuermissionen')}")
    print(
        f"- Experience {sum(x['punkte'] for x in s.get('xp', []))}; US casualty steps {s.get('us_casualties_gesamt', 0)}; prisoners {s.get('gefangene', 0)}; evacuated {s.get('evakuiert', 0)}"
        + (
            "; guard steps returning between missions (8.15): "
            + ", ".join(f"{g['einheit']} {g['erfahrung']}" for g in s["wachen"])
            if s.get("wachen")
            else ""
        )
    )
    print("## Units")
    for n, e in s["einheiten"].items():
        if e["seite"] == "US":
            print(
                f"- {n}: {state.steps(e)} step(s) {comms.experience(e)}"
                + (f", {e['munition']['typ']} {e['munition']['punkte']}" if e.get("munition") else "")
                + (
                    f", Radio {'/'.join(g['typ'] + ' ' + g['netz'] for g in comms.radios_of(e))}"
                    if comms.radios_of(e)
                    else ""
                )
                + (f", Assets {', '.join(e['assets'])}" if e.get("assets") else "")
            )
    if s.get("removed_from_play"):
        print("- Removed from Play: " + ", ".join(s["removed_from_play"]))
