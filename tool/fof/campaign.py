"""Campaign layer: experience, mission end, combat patrols, reattempts, reconstitution."""

import copy

from . import briefing, combat, comms, fire, geometry, options, rules, setup, state


def book_xp(s, points, reason, prot=None):
    """[RULE 12.1 p.80] Experience Points of the mission; table Normandy p.13."""
    if not state.is_campaign(s) or not points:
        return
    s.setdefault("xp", []).append(
        {"turn": s["turn"], "attempt": s["campaign"].get("attempt", 1), "points": points, "reason": reason}
    )
    if prot is not None:
        sum_ = sum(x["points"] for x in s["xp"])
        if points < 0:  # spending between patrols/missions
            prot.append(f"Experience {points} spent: {reason} (remaining {sum_}) [12.3 p.81]")
        else:
            prot.append(f"Experience +{points}: {reason} (total {sum_}) [12.1 p.80, Normandy p.13]")


def xp_table(s, key):
    return s.get("campaign", {}).get("xp_table", {}).get(key, 0)


def is_cleared(s, k):
    """[RULE 12.1 p.81] Cleared: the card started with a PC marker and now has neither enemies (except casualties) nor a PC marker."""
    c = state.card(s, k)
    return bool(s.get("pc_start", {}).get(k)) and not c.get("pc") and not state.units_on(s, k, "Enemy")


def is_secured(s, k):
    return is_cleared(s, k) and bool(state.units_on(s, k, "US"))


def secured_for_reattempt(s, k):
    """[RULE 3.9 step 5, Lesart U42]: the secured cards of the reattempt are those secured at the end of the attempt
    (snapshot 'reattempt_secured'), not the momentary occupation: LATs used up in step 3 and units repositioned in
    step 5 would otherwise make the result depend on the order of the setup commands. Without a snapshot: momentary."""
    snap = s.get("reattempt_secured")
    if snap is None:
        return is_secured(s, k)
    return k in snap and is_cleared(s, k)


def campaign_objective_status(s):
    objectives = s.get("objectives", {})
    zr = s["objective_rules"]
    parts, ok = [], True
    for key in zr.get("secure", []):
        k = objectives.get(key)
        g = bool(k) and is_secured(s, k)
        ok &= g
        parts.append(
            f"{ {'primary': 'Primary', 'secondary': 'Secondary'}.get(key, key) } {k or '-'} {'secured' if g else 'open'}"
        )
    for r in zr.get("clear_rows", []):
        ks = [k for k, c in s["cards"].items() if c["row"] == r and not c.get("outside") and not c.get("staging")]
        open_ = [k for k in ks if not is_cleared(s, k)]
        ok &= not open_
        parts.append(f"Row {r} " + ("cleared" if not open_ else "open (" + ", ".join(open_) + ")"))
    return ok, "; ".join(parts)


def xp_mission_end(s, prot):
    """Card points at the end of an attempt, no card twice per mission (3.9 step 1 note, 12.1; Errata 4)."""
    tab = s["campaign"].get("xp_table", {})
    assigned = s.setdefault("xp_cards", [])
    objectives = s.get("objectives", {})
    special = {
        objectives.get("primary"): ("primary", "Primary Objective secured"),
        objectives.get("secondary"): ("secondary", "Secondary Objective secured"),
        objectives.get("ap"): ("ap", "Attack Position secured"),
    }
    for k in sorted(s["cards"]):
        c = s["cards"][k]
        if c.get("staging") or c.get("outside") or k in assigned:
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
                tab.get("pc_a_card", 2) if pc == "A" else tab.get("pc_bc_card", 1),
                f"Card {k} with PC {pc} cleared",
                prot,
            )
            assigned.append(k)


def guards_returning(s, prot):
    """[RULE 8.15 p.69] Guard steps return between missions at their original Experience Level and are not LATs;
    replacements (12.4 p.81) only for steps lost as casualties or prisoners (K35)."""
    guards = s.get("guards", [])
    if guards:
        prot.append(
            "Guard steps returning between missions (8.15 p.69, original Experience Level, not LATs): "
            + ", ".join(f"{g['unit']} 1 step {g['experience']} (guard since turn {g['turn']})" for g in guards)
        )
    lost = s.get("us_casualties_total", 0) + s.get("us_captured", 0)
    prot.append(
        f"Replacements only for steps lost as casualties or prisoners ({lost} this mission); surplus replacement "
        f"steps are lost [12.4 p.81]"
    )


def campaign_mission_end(s, prot):
    if s.get("patrol_mission"):
        return patrol_end(s, prot)
    ok, txt = campaign_objective_status(s)
    xp_mission_end(s, prot)
    s["mission_end"] = True
    k = s["campaign"]
    prot.append("Mission objective: " + txt + (" ACHIEVED" if ok else " NOT achieved"))
    if ok:
        vet = s.get("us_casualties_total", 0) // k.get("veteran_per_casualties", 4)
        prot.append(
            f"Mission successful. Between missions (12.2 p.81): spend {sum(x['points'] for x in s.get('xp', []))} Experience points, "
            f"replacements {k.get('replacement_green', 6)} Green plus {vet} Veteran ({s.get('us_casualties_total', 0)} casualty steps over the whole mission, 1 per 4) [12.4 p.81, Normandy p.13]; "
            "replace ammo and assets completely (BGG E14)"
        )
        guards_returning(s, prot)
        lost = [f"{n} ({', '.join(e['skills'])})" for n, e in s["units"].items() if e.get("skills")]
        if lost:
            prot.append(
                "Skills not used by the end of the mission are lost: "
                + "; ".join(lost)
                + " (remove the markers) [RULE 12.7 p.82]"
            )
            for e in s["units"].values():
                e.pop("skills", None)
    elif k.get("attempt", 1) < k.get("attempts_max", 1) and state.option(s, "U9_reattempt"):
        prot.append(f"Reattempt possible (attempt {k['attempt']} of {k['attempts_max']}): fof.py reattempt [3.9 p.17]")
    else:
        prot.append(
            "No attempts left: mission failed (12.8 standard: the commander is relieved; Survivor mode: continue with the next mission) [12.8 p.82]"
        )


def patrol(s):
    return s.get("patrol") or {}


def patrol_move(s, n, from_, target_card, prot):
    """[MSR 2] Route Points in order, pass the Primary, return across the MLR from row 2 to row 1."""
    p = patrol(s)
    if not p or p.get("success"):
        return
    if n not in p.get("members", []):
        # [Normandy M3 p.24 'at least one unit'; BGG 3760839: also LAT, Staff, HQ of the patrol] LATs from patrol units count too
        if s["units"].get(n, {}).get("origin") in p.get("members", []):
            p.setdefault("members", []).append(n)
        else:
            return
    objectives = s.get("objectives", {})
    route = [objectives.get("route", {}).get(str(i)) for i in (1, 2, 3, 4)]
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
            da = [m for m in p.get("members", []) if m in s["units"] and s["units"][m].get("card") == route[j]]
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
    event_route = s.get("event_route")
    if (
        event_route
        and event_route.get("turn") == s["turn"]
        and not event_route.get("fulfilled")
        and event_route.get("target")
        and geometry.distance(s, target_card, event_route["target"])
        < geometry.distance(s, from_, event_route["target"])
    ):
        event_route["fulfilled"] = True
        prot.append(
            f"CO HQ is Screaming for Action fulfilled: {n} moves toward {event_route['target']} [Normandy M3 p.26]"
        )
        book_xp(s, 1, "HQ event CO HQ is Screaming for Action fulfilled", prot)
    if target_card == objectives.get("primary") and not p.get("primary_visited"):
        p["primary_visited"] = True
        prot.append(f"Primary Objective {target_card} passed [Normandy M3 p.24]")
    if (
        p.get("route_index", 0) == 4
        and p.get("primary_visited")
        and state.card(s, from_)["row"] == 2
        and state.card(s, target_card)["row"] == 1
    ):
        p["success"] = True
        prot.append(f"Patrol successful: {n} crosses the MLR from row 2 to row 1 [Normandy M3 p.24]")
        book_xp(s, xp_table(s, "cp_success") or 5, f"Patrol Platoon {p['platoon']} successful", prot)


def patrol_reserve(s, prot):
    """[MSR 1, MSR 4] Units not set up are missing from this patrol; set aside until the next patrol."""
    res = s.setdefault("patrol_reserve", {})
    gone = [n for n, e in s["units"].items() if e["side"] == "US" and not e.get("card")]
    for n in gone:  # set aside, not removed from play: patrol_reserve_back returns them (no combat.remove_from_play)
        res[n] = {"unit": s["units"].pop(n), "command": s["commands"].pop(n, None)}
    if gone:
        prot.append("Not set up, missing from this patrol: " + ", ".join(gone) + " [MSR 1, MSR 4]")


def patrol_reserve_back(s, prot):
    res = s.pop("patrol_reserve", {})
    for n, x in res.items():
        s["units"][n] = x["unit"]
        if x.get("command") is not None:
            s["commands"][n] = x["command"]
    if res:
        prot.append("Back for the next patrol: " + ", ".join(res))


def patrol_end(s, prot):
    """End of a patrol (10 turns): Primary cleared (+4), next patrol or mission end [MSR 1, Normandy p.13]."""
    p = patrol(s)
    objectives = s.get("objectives", {})
    pk = objectives.get("primary")
    assigned = s.setdefault("xp_cards", [])
    if pk and pk not in assigned and is_cleared(s, pk):
        book_xp(
            s,
            xp_table(s, "cp_primary") or 4,
            f"Primary Objective {pk} cleared (patrol Platoon {p.get('platoon')})",
            prot,
        )
        assigned.append(pk)
    s["mission_end"] = True
    done_platoons = p.setdefault("completed", [])
    if p.get("platoon") and p["platoon"] not in done_platoons:
        done_platoons.append(p["platoon"])
    # [RULE 12.3.1 p.81]: remember who took part, for promotions after this and later patrols
    tg = p.setdefault("took_part", [])
    tg.extend(m for m in p.get("members", []) if m not in tg)
    remainder = [x for x in ("1", "2", "3") if x not in done_platoons]
    prot.append(
        f"Patrol {len(done_platoons)} (Platoon {p.get('platoon')}) ended: "
        + (
            "SUCCESSFUL"
            if p.get("success")
            else f"not successful (Route Points {p.get('route_index', 0)}/4, Primary {'passed' if p.get('primary_visited') else 'not passed'})"
        )
        + "; XP only for the patrol platoon [MSR 1]"
    )
    if remainder:
        prot.append(
            f"Next patrol: fof.py patrol next <{'|'.join(remainder)}> (3.9 sequence, new PCs, cover and mines remain) [MSR 1, MSR 3]"
        )
    else:
        prot.append(
            f"All three patrols played: Mission {s.get('campaign', {}).get('mission_no') or '?'} ended; Combat Patrols carry no penalty on failure (standard mode) [MSR 1]"
        )


def _usage(command):
    from . import cli  # lazy: the usage texts live in the command table

    return cli.usage(command)


def check_patrol_choice(units, plt, with_):
    """Platoon and --with of a patrol against the units {name: unit} [2.6.1, MSR 1]; returns the PLT HQs by platoon."""
    hqs = {x.get("platoon"): m for m, x in units.items() if x.get("level") == "PLT" and x["side"] == "US"}
    if plt not in hqs:
        raise rules.Violation(f"Platoon {plt} unknown; available: {', '.join(sorted(k for k in hqs if k))}")
    for m in with_:
        if m not in units:
            raise rules.Violation(f"Unit '{m}' unknown. Known: {', '.join(units)}")
        x = units[m]
        if x.get("level") == "PLT" or (x["type"] == "Squad" and x.get("platoon") != plt):
            raise rules.Violation(f"{m}: only Weapons Teams, FOs and Company Staff may join the patrol [2.6.1]")
    return hqs


def units_after_reattempt(s):
    """The units a 'patrol next' will see after the reattempt reset: BN units leave, enemy Paralyzed/Litter Teams are
    removed, the units set aside for the last patrol come back (M6: checked before anything is saved)."""
    units = {
        n: e
        for n, e in s["units"].items()
        if not (e.get("level") == "BN" and e["side"] == "US")
        and not (e["side"] == "Enemy" and e["type"] in ("Paralyzed Team", "Litter Team"))
        and not (e["side"] == "US" and e.get("attempt_only"))  # as remove_leaving_units
    }
    for n, x in (s.get("patrol_reserve") or {}).items():
        units[n] = x["unit"]
    return units


def _print_patrol(s, p):
    """The current patrol: platoon, members, route and what is done."""
    objectives = s.get("objectives", {})
    print(
        f"Patrol {len(p.get('completed', [])) + (0 if s.get('mission_end') else 1)}: Platoon {p.get('platoon') or '-'}; members: {', '.join(p.get('members', [])) or '-'}"
    )
    print(
        "Route: "
        + ", ".join(f"{i} {objectives.get('route', {}).get(str(i)) or '-'}" for i in (1, 2, 3, 4))
        + f"; reached {p.get('route_index', 0)}/4; Primary {objectives.get('primary') or '-'} {'passed' if p.get('primary_visited') else 'open'}; success {'yes' if p.get('success') else 'no'}"
    )
    print(f"Done: {', '.join(p.get('completed', [])) or 'none'}")


def _patrol_setup_notes(s, plt, members, prot):
    """What is to be set up before turn 1 of a patrol [MSR 1, MSR 4]."""
    row1 = sorted(k for k, c in s["cards"].items() if c["row"] == 1 and not c.get("staging") and not c.get("outside"))
    prot.append(
        f"Patrol Platoon {plt}: {', '.join(members)}; setup on row 1 (setup <unit> <{row1[0]}-{row1[-1]}>)"
    )  # row 1 from the map (M5 has six columns)
    without = [
        m
        for m in members
        if s["units"][m]["type"] not in ("Staff",)
        and s["units"][m].get("level") not in ("CO", "BN")
        and not s["units"][m].get("platoon")
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


def cmd_patrol(s, args):
    """patrol | patrol start <platoon> [--with=a,b] | patrol next <platoon> [--with=a,b]"""
    if not s.get("patrol_mission"):
        raise rules.Violation("Not a Combat Patrol mission")
    p = s.setdefault("patrol", {})
    if not args:
        _print_patrol(s, p)
        return
    if args[0] not in ("next", "start"):
        raise rules.Violation(f"Usage: {_usage('patrol')}")
    rules.need([a for a in args if not a.startswith("--")], 2, _usage("patrol"))
    o = options.parse_opts(args[2:])
    plt = args[1]
    with_ = options.list_option(o, "--with")
    prot = []
    if args[0] == "next":
        if not s.get("mission_end"):
            raise rules.Violation("First finish the current patrol (10 turns) [MSR 1]")
        if plt in p.get("completed", []):
            raise rules.Violation(f"Platoon {plt} has already done its patrol [MSR 1]")
        # platoon and --with are checked before the reattempt reset is saved, or a wrong platoon would block
        # 'patrol next' for good
        check_patrol_choice(units_after_reattempt(s), plt, with_)
        s = next_patrol_reset(s, prot)
        p = s.setdefault("patrol", {})
    if not state.in_setup(s):
        raise rules.Violation("Set the patrol only before turn 1 [MSR 1]")
    check_patrol_choice(s["units"], plt, with_)
    members = [m for m, x in s["units"].items() if x["side"] == "US" and (x.get("platoon") == plt or m in with_)]
    for m, x in s["units"].items():
        if x["side"] != "US":
            continue
        if m in members:
            x.pop("stationary", None)
        else:
            x["stationary"] = True
    p.update(platoon=plt, members=members, route_index=0, primary_visited=False, success=False)
    s["single_platoon"] = True
    _patrol_setup_notes(s, plt, members, prot)
    state.save_state(s, "; ".join(prot), "2.6 p.12, MSR 1")
    briefing.print_board(prot, s)


def next_patrol_reset(s, prot):
    """'patrol next': the 3.9 reset (saved by cmd_reattempt), then the state reloaded with the reserve back and a new
    visibility to draw [MSR 1, Normandy M3 p.24]. Returns the reloaded state."""
    s["patrol_change"] = True
    cmd_reattempt(s, [])
    s = state.load_state()
    s.pop("patrol_change", None)
    patrol_reserve_back(s, prot)
    s["light"] = None
    s.pop("concentrations_placed", None)
    prot.append(
        "New visibility for this patrol: draw R#4 (1=+2 ... 4=+5), fof.py visibility <light>; place units with setup on row 1 or in the COP, then fof.py reattempt done [Normandy M3 p.24, MSR 1]"
    )
    return s


def _between_missions(s):
    return state.in_setup(s) or s.get("mission_end") or s.get("reattempt_setup")


def _promoted_steps(s):
    """promoted steps per unit in this between-mission/patrol window (old list format = whole unit counted)."""
    b = s.get("promoted") or {}
    if isinstance(b, list):
        b = {n: 99 for n in b}
    return b


def cmd_xp_promote(s, args):
    """xp promote <unit> --from=Green|Line --steps=<n> [--result=<level>]: 12.3 one level per step, 1 XP Green to Line, 3 XP
    Line to Veteran, one level per mission, no attachments, Combat Patrol: only patrol members (12.3.1)."""
    if not _between_missions(s):
        raise rules.Violation("Promotions only between missions or patrols (12.2, 3.9)")
    rules.need([a for a in args[:1] if not a.startswith("--")], 1, _usage("xp"))
    n = args[0]
    o = options.parse_opts(args[1:])
    e = state.unit(s, n)
    frm = o.get("--from")
    if frm not in rules.PROMOTION_COST:
        raise rules.Violation("--from=Green|Line (a step rises one level per mission) [RULE 12.3 p.81]")
    steps = options.int_opt(o, "--steps", "xp promote --steps", 1)
    if steps < 1:
        raise rules.Violation(f"--steps={steps}: at least one step is promoted")
    if e.get("attachment"):
        raise rules.Violation(f"{n} is an attachment: no promotion with Experience Points [RULE 12.3 p.81]")
    # [RULE 12.3 p.81] 'You may only increase a step by one Level': counted per step, not per unit
    done_steps = _promoted_steps(s).get(n, 0)
    if done_steps + steps > max(1, state.steps(e)):
        raise rules.Violation(
            f"{n}: {done_steps} of {state.steps(e)} step(s) already promoted this time; one level per step and mission [RULE 12.3 p.81]"
        )
    p = s.get("patrol") or {}
    if s.get("patrol_mission"):
        # [RULE 12.3.1 p.81] 'only units that participated in a patrol may be promoted': members of finished patrols
        done_platoons = p.get("completed", [])
        took_part = set(p.get("took_part", [])) | {
            m for m, x in s["units"].items() if x["side"] == "US" and x.get("platoon") in done_platoons
        }
        if n not in took_part and e.get("origin") not in took_part:
            raise rules.Violation(
                f"{n} has not yet taken part in a patrol of this mission: no promotion [RULE 12.3.1 p.81, Normandy MSR 1]"
            )
    if state.is_lat(e) and e["type"] != "Fire Team":
        raise rules.Violation("LATs are reconstituted first (12.2), promotion then on the squad")
    cost = rules.PROMOTION_COST[frm] * steps
    if sum(x["points"] for x in s.get("xp", [])) < cost:
        raise rules.Violation(f"Not enough Experience Points ({cost} needed) [RULE 12.3 p.81]")
    target = "Line" if frm == "Green" else "Veteran"
    new = options.text_opt(o, "--result", _usage("xp"))
    e_steps = max(1, state.steps(e))
    mix = e.get("step_levels") or []
    if len(mix) != e_steps:
        mix = [e.get("experience")] * e_steps  # [RULE 12.4 p.81] all steps count as the unit's level
    if new:
        e.pop("step_levels", None)
    elif mix.count(frm) < steps:
        raise rules.Violation(
            f"{n} has {mix.count(frm)} {frm} step(s) ({'+'.join(str(x)[0] for x in mix)}): give the resulting unit level with --result= [RULE 12.6 p.82]"
        )
    else:
        for _ in range(steps):
            mix[mix.index(frm)] = target
        e["step_levels"], new = mix, experience_from_steps(mix)  # [RULE 12.6 p.82]
    prot = []
    book_xp(s, -cost, f"promotion {n}: {steps} step(s) {frm} to {target}, unit now {new}", prot)
    e["experience"] = new
    pr = _promoted_steps(s)
    pr[n] = pr.get(n, 0) + steps
    s["promoted"] = pr
    prot.append(f"{n}: experience {new} (table 12.6; a different step mix: --result=)")
    state.save_state(s, "; ".join(prot), "12.3 p.81, 12.6 p.82")
    briefing.print_board(prot, s)


def skill_markers_fit(markers, wanted):
    """[RULE 12.7 p.82 'Skills are limited by what is available in the counter mix']: can every wanted skill get its own
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
    """xp skill <HQ> <skill>: buy a skill marker (12.7): cost from the Skills chart, at most three per HQ/Staff, counter mix."""
    if not _between_missions(s):
        raise rules.Violation("Skills are bought between missions or patrols [RULE 12.7 p.82]")
    rules.need([a for a in args if not a.startswith("--")], 2, _usage("xp"))
    n, skill = args[0], " ".join(args[1:]).split("--")[0].strip()
    o = options.parse_opts([a for a in args[1:] if a.startswith("--")])
    e = state.unit(s, n)
    if not (state.is_hq(e) or e["type"] == "Staff"):
        raise rules.Violation("Skill markers go to a PLT HQ, CO Staff or the CO HQ [RULE 12.7 p.82]")
    if skill not in rules.SKILL_COST:
        raise rules.Violation(f"Skill unknown; known: {', '.join(rules.SKILL_COST)}")
    if len(e.get("skills") or []) >= rules.SKILLS_MAX_PER_HQ:
        raise rules.Violation(f"{n} already holds {rules.SKILLS_MAX_PER_HQ} Skill markers [RULE 12.7 p.82]")
    in_play = [sk for x in s["units"].values() for sk in (x.get("skills") or [])]
    markers = s.get("skill_marker") or rules.SKILL_MARKERS_NORMANDY
    if not skill_markers_fit(markers, in_play + [skill]):
        raise rules.Violation(
            f"Skill {skill}: no free marker with this face (two-sided markers, in play: {', '.join(in_play) or 'none'}) [RULE 12.7 p.82, E67]"
        )
    cost = options.int_opt(o, "--cost", "xp skill --cost", rules.SKILL_COST[skill])
    if sum(x["points"] for x in s.get("xp", [])) < cost:
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
    if not state.is_campaign(s):
        raise rules.Violation("Experience only in campaign missions")
    if args and args[0] == "promote":
        return cmd_xp_promote(s, args[1:])
    if args and args[0] in ("skill",):
        return cmd_xp_skill(s, args[1:])
    if args and args[0] in ("add", "spend"):
        rules.need(args, 2, _usage("xp"))
        n = rules.int_value(args[1], f"xp {'add' if args[0] == 'add' else 'spend'} <n>") * (
            1 if args[0] == "add" else -1
        )
        reason = " ".join(args[2:]) or ("manual" if n > 0 else "spent")
        prot = []
        if n < 0 and sum(x["points"] for x in s.get("xp", [])) + n < 0:
            raise rules.Violation("Not enough Experience Points")
        book_xp(s, n, reason, prot)
        state.save_state(s, "; ".join(prot), "12.1 p.80, 12.3 p.81")
        briefing.print_board(prot, s)
        return
    for x in s.get("xp", []):
        print(f"- T{x['turn']} A{x['attempt']}: {x['points']:+d} {x['reason']}")
    print(
        f"Total {sum(x['points'] for x in s.get('xp', []))}; cards already scored: {', '.join(s.get('xp_cards', [])) or 'none'}"
    )
    _, txt = campaign_objective_status(s)
    print("Status now: " + txt)


def attempt_plan(s):
    """[Naktong M1 p.15 'Duration and Visibility']: the plan of the current attempt from the setup (attempt_plan):
    max_turns, visibility {turns: {light, weather, text}}, enemy_experience, package_ammo {HMG|Mortar: points}."""
    return (s.get("attempt_plan") or {}).get(str(s.get("campaign", {}).get("attempt", 1))) or {}


def _plan_entry(table, turn):
    for key, v in (table or {}).items():
        lo, _, hi = key.partition("-")
        if int(lo) <= turn <= int(hi or lo):
            return v
    return None


def apply_turn_visibility(s, prot):
    """[RULE 9.0 p.69 'Each Mission lists the visibility conditions, which may vary per turn']: light and weather of
    the current turn from the attempt plan; announced when they change (and on turn 1)."""
    v = _plan_entry(attempt_plan(s).get("sight"), s["turn"])
    if v is None:
        return
    li, weather = v.get("light", 0), v.get("weather", 0)
    if s["turn"] != 1 and (s.get("light"), s.get("weather")) == (li, weather):
        return
    s["light"], s["weather"] = li, weather
    geometry.update_visibility(s)
    prot.append(
        f"Visibility turn {s['turn']}: {v.get('text') or ''} light {li:+d}, weather {weather:+d} = {li + weather:+d}"
        + (" (Limited Visibility, 9.1)" if li + weather >= 2 else "")
        + " [9.0 p.69, mission chart]"
    )


def apply_attempt_plan(s, prot):
    """turns, enemy experience and package ammo of the attempt; enemy ammo on the board is resupplied to the new
    values (3.9 step 12); then the visibility of turn 1."""
    p = attempt_plan(s)
    if not p:
        return
    v = s.get("campaign", {}).get("attempt", 1)
    if p.get("max_turns"):
        s["max_turns"] = p["max_turns"]
    if p.get("enemy_experience"):
        s["enemy_experience_attempt"] = p["enemy_experience"]
    s["package_ammo"] = p.get("package_ammo") or {}
    for n, e in s["units"].items():
        key = package_ammo_key(e)
        if e["side"] == "Enemy" and key in s["package_ammo"] and e.get("ammo"):
            e["ammo"]["points"] = e["ammo"]["start"] = s["package_ammo"][key]
            prot.append(f"{n}: ammo {s['package_ammo'][key]} for attempt {v} (3.9 step 12)")
    prot.append(
        f"Attempt {v}: {s['max_turns']} turns"
        + (f", new enemy units {p['enemy_experience']}" if p.get("enemy_experience") else "")
        + (", package ammo " + ", ".join(f"{a} {b}" for a, b in s["package_ammo"].items()) if s["package_ammo"] else "")
        + " [mission chart]"
    )
    apply_turn_visibility(s, prot)


def package_ammo_key(e):
    """which per-attempt package ammo line applies to an enemy unit (HMG Teams, Mortar Teams)."""
    if state.is_mortar(e):
        return "Mortar"
    if "HMG" in (e.get("type_name") or "") or e.get("tripod"):
        return "HMG"
    return None


def cmd_reattempt(s, args):
    """[RULE 3.9 p.17/18] Reattempt preparation, steps 1-14: 'reattempt' resets the board, 'reattempt done' starts it."""
    if args and args[0] == "done":
        return reattempt_done(s)
    if args:
        raise rules.Violation(f"Usage: {_usage('reattempt')}")
    return reattempt_start(s)


def reattempt_done(s):
    """'reattempt done': LATs become Fire Teams (step 4), positions checked (step 5), turn 1 of the new attempt."""
    k = s.get("campaign", {})
    if not s.get("reattempt_setup"):
        raise rules.Violation("No reattempt preparation pending")
    prot = []
    s.pop("promoted", None)  # one promotion level per mission/patrol
    for e in s["units"].values():
        e.pop("step_levels", None)  # [RULE 12.4 p.81] from here on every step counts as the unit's level
    for n, e in list(s["units"].items()):
        if e["side"] == "US" and state.is_lat(e) and e["type"] != "Fire Team":
            e["type"], e["experience"] = "Fire Team", "Green"
            combat.set_lat_values(e, "Fire Team")
            prot.append(f"{n} becomes a Fire Team (step 4)")
        if e["side"] == "US":
            e["status"] = []
    wrong = [
        n
        for n, e in s["units"].items()
        if e["side"] == "US"
        and e.get("card")
        and not state.card(s, e["card"]).get("staging")
        and not secured_for_reattempt(s, e["card"])
        and not (
            s.get("patrol_mission")
            and (state.card(s, e["card"])["row"] == 1 or e["card"] == s.get("objectives", {}).get("cop"))
        )
    ]
    if wrong:
        raise rules.Violation(
            "Friendly units only in the Staging Area or on secured cards (step 5): " + ", ".join(wrong)
        )
    if s.get("patrol_mission"):
        check_patrol_ready(s)
        patrol_reserve(s, prot)
    enemy_into_cover(s, prot)
    s["reattempt_setup"] = False
    s.pop("reattempt_secured", None)
    s["setup_done"] = True
    fire.open_fire(s, prot)
    activity_note = fire.update_activity(s)
    if activity_note:
        prot.append(activity_note)
    prot.append(
        f"Attempt {k.get('attempt')} starts with turn 1 (steps 13/14); no new PC markers, Spotted status remains [3.9 p.18]"
    )
    state.save_state(s, "Reattempt: " + "; ".join(prot), "3.9 p.18")
    briefing.print_board(prot, s)


def check_patrol_ready(s):
    """Before turn 1 of the next patrol: fortifications, setup choices, assets, Artillery Concentration [MSR 1]."""
    open_steps = [
        n
        for n, e in s["units"].items()
        if e["side"] == "US"
        and e.get("stationary")
        and e.get("card")
        and state.card(s, e["card"]).get("cover")
        and e.get("area", "open") == "open"
    ]
    if open_steps:
        raise rules.Violation(
            "Place non-patrol units in the fortifications (setup <unit> <card> --area=C1|C2): "
            + ", ".join(open_steps)
            + " [Normandy M3 p.26 MSR 1]"
        )
    fa = [x for x in setup.check_campaign_setup(s) if not x.startswith("Terrain")]
    if (
        s.get("assets_start")
        and not any(e.get("assets") for e in s["units"].values() if e["side"] == "US")
        and not s.get("assets_empty_on_purpose")
    ):  # step 12 puts all assets into the pool
        fa.append(
            "Distribute assets: setup <unit> --asset=<type> (pool: "
            + ", ".join(f"{a} {b}" for a, b in s.get("assets_pool", {}).items() if b)
            + ") [3.9 step 12, 2.3.4 p.10]"
        )
    if s.get("fm_values") and not s.get("concentrations_placed"):
        fa.append("Artillery Concentration: objective concentration <card> <firing agency> [Normandy M3 p.24, 7.16.5]")
    if fa:
        raise rules.Violation("Still open before turn 1 of the patrol: " + "; ".join(fa))


def check_reattempt_allowed(s, k):
    if not s.get("mission_end"):
        raise rules.Violation(
            "Reattempt only after the last turn (Clean Up of turn {}) [3.9 p.17]".format(s.get("max_turns"))
        )
    if not s.get("patrol_mission"):
        ok, _ = campaign_objective_status(s)
        if ok:
            raise rules.Violation("Mission objective achieved, no reattempt needed")
        if k.get("attempt", 1) >= k.get("attempts_max", 1) or not state.option(s, "U9_reattempt"):
            raise rules.Violation("No more reattempts allowed [3.9 p.17]")
    elif not s.get("patrol_change"):
        raise rules.Violation("Combat Patrol: next patrol with fof.py patrol next <platoon> [MSR 1]")


def reattempt_start(s):
    """'reattempt' after the last turn: the 3.9 reset of board and units (steps 1-12), then the preparation."""
    k = s.get("campaign", {})
    check_reattempt_allowed(s, k)
    prot = [f"Experience so far {sum(x['points'] for x in s.get('xp', []))} (step 1; cards not counted twice)"]
    s["reattempt_secured"] = sorted(k for k in s["cards"] if is_secured(s, k))  # snapshot for step 5
    prot.append("Secured cards for the setup (step 5): " + ", ".join(s["reattempt_secured"]))
    for n, e in s["units"].items():
        if e["side"] == "US" and state.fire_team_side(e):
            e["status"] = [x for x in e["status"] if x != rules.FIRE_TEAM_SIDE]
            prot.append(f"{n} to the Good Order side (step 2)")
    reset_cards(s, prot)
    remove_leaving_units(s, prot)
    reset_units(s, prot)
    prot.append(
        "Pinned, PDF and VOF removed, ammo and assets replenished, dropped assets off the board (steps 10-12); cover markers and mines remain (step 7)"
    )
    reset_pools_and_events(s, prot)
    if s.get("patrol_mission"):
        replace_patrol_markers(s, prot)
    k["attempt"] = k.get("attempt", 1) + 1
    s["turn"], s["phase"] = 1, state.sop(s)[0][0]
    s.pop("fortifications_placed", None)
    apply_attempt_plan(s, prot)
    if s.get("fortify_between_attempts"):
        prot.append(
            "Fortify: objective fortify <secured card> foxholes (2 Foxholes) and objective fortify <other secured card> deepbunker [Naktong M1 p.15]"
        )
    s["reattempt_setup"] = True
    s.pop("mission_end", None)
    s["active_hq"] = None
    activity_note = fire.update_activity(s)
    if activity_note:
        prot.append(activity_note)
    lats = [n for n, e in s["units"].items() if e["side"] == "US" and state.is_lat(e)]
    prot.append(
        f"Attempt {k['attempt']}: reconstitute now (reconstitute <unit> --from=<LAT,..>; LATs: {', '.join(lats) or 'none'}; 1 Green step per LAT, new HQs Green), "
        "spend Experience (xp spend <n> <reason>, set <unit> experience=..), distribute assets (setup --asset), "
        "place units on secured cards or in Staging (setup <unit> <card> [--area=<cover>]), then fof.py reattempt done [3.9 p.17/18]"
    )
    state.save_state(s, "Reattempt preparation: " + "; ".join(prot), "3.9 p.17")
    briefing.print_board(prot, s)


def reset_cards(s, prot):
    """Step 6 casualties off, external markers except Mines (inactive again), dropped assets and ammo off the board."""
    for card_id, c in s["cards"].items():
        if c.get("casualties") or c.get("casualties_enemy"):
            prot.append(f"{card_id}: casualties removed (step 6)")
            c["casualties"] = c["casualties_enemy"] = 0
        c["external"] = [x for x in c.get("external", []) if x["type"] == "Mines"]
        for x in c["external"]:
            x["active"] = False
        c.pop("grenade_miss", None)
        c["assets"] = []
        c.pop("assets_ground", None)  # dropped Assets go back to the pool, which is refilled
        c["ammo"] = {}


def remove_leaving_units(s, prot):
    """Step 6: enemy Paralyzed/Litter Teams removed; the BN HQ (Checking Up) leaves the board."""
    for n, e in list(s["units"].items()):
        if e["side"] == "Enemy" and e["type"] in ("Paralyzed Team", "Litter Team"):
            del s["units"][n]  # reattempt reset (3.9 step 6), not a removal from play
            prot.append(f"{n} removed (step 6)")
        if e.get("attempt_only") and e["side"] == "US":
            # an event unit 'remains until the end of the current Attempt' (Naktong M1 p.17); it can come again
            d = copy.deepcopy(e)
            d.update(card=None, status=[], target=None, area="open")
            d.pop("attempt_only")
            s.setdefault("event_supply", {}).setdefault(e["attempt_only"], {})[n] = d
            del s["units"][n]
            prot.append(f"{n} leaves at the end of the attempt (event unit) [Naktong M1 p.17]")
            continue
        if e.get("level") == "BN" and e["side"] == "US":
            del s["units"][n]  # the visiting BN HQ goes back off-map (it can return), not a removal from play
            s["commands"].pop(n, None)
            prot.append(f"{n} (Checking Up) leaves the board; events end with the attempt (turn counter restarts)")


# per-unit fields of the last attempt that end with it (3.9 steps 8-11)
REATTEMPT_DROPPED_FIELDS = (
    "target_open",
    "concentrated",
    "cf",
    "grenade",
    "grenade_critical",
    "cf_critical",
    "mine_hit",
    "pdf_only",
    "indirect",
    "ammo_empty",
    "no_fire_until_clean_up",
)


def enemy_into_cover(s, prot):
    """[RULE 3.9 step 8] An enemy unit out of cover goes under the best cover marker on its card that is free for use.
    run again in 'reattempt done', because step 3 (LATs used up) and step 5 (units repositioned) come before
    step 8 and can free a cover marker that a friendly unit still held at the reset."""
    for n, e in s["units"].items():
        if e["side"] == "Enemy" and e.get("area", "open") == "open":
            free = state.free_cover(s, e["card"], "Enemy", steps=state.steps(e))  # no US units under them, room
            if free:
                best = max(free, key=lambda x: x["value"])
                e["area"] = best["id"]
                prot.append(f"{n} under {e['area']} (step 8; if there is too little cover, distribute randomly)")
                if best["type"] == "Deep Bunker":  # [Naktong CSR 7] no VOF until it leaves (Fall Back/Grenade Attack)
                    e["deep_bunker"] = best["id"]
                    fire.cease_fire(e)
                    prot.append(
                        f"{n} in Deep Bunker {best['id']}: no VOF, no spotting, no grenades until it leaves [{rules.DEEP_BUNKER_REF}]"
                    )


def reset_units(s, prot):
    """Steps 8-12: enemies under cover, Pinned/Exposed and fire off, ammo, spotter missions and radios replenished."""
    enemy_into_cover(s, prot)
    for n, e in s["units"].items():
        e["status"] = [x for x in e["status"] if x not in (rules.PINNED, rules.EXPOSED)]
        e["target"] = None
        for f in REATTEMPT_DROPPED_FIELDS:
            e.pop(f, None)
        m = e.get("ammo")
        if m and m.get("start") is not None:
            m["points"] = m["start"]
            e.pop("out_of_ammo", None)
        if e.get("spotter"):
            e["missions"] = 2
        if e["side"] == "US" and e.get("attachment") is None:
            orig = s.get("setup_units", {}).get(n, {})
            if orig.get("radio") is not None:
                e["radio"] = copy.deepcopy(orig["radio"])
                if s.get("co_tac_medium") == "phone":
                    for g in e["radio"]:
                        if g["net"] == "CO TAC":
                            g["type"] = "EE8"
        e.pop("assets", None)


def reset_pools_and_events(s, prot):
    """Commands, fire missions, Target markers and the asset pool from the start; turn-based events end."""
    if any(record.get("saved") for record in s["commands"].values()):
        prot.append("Saved Commands removed: all Command markers to 0 (step 11)")
    for record in s["commands"].values():
        record.update(available=0, saved=0, activated=False, done=False)
    s["fire_missions"] = copy.deepcopy(s.get("fm_start", s.get("fire_missions")))
    s["target_marker"] = {}
    s["assets_pool"] = copy.deepcopy(s.get("assets_start", s.get("assets_pool", {})))
    # turn-based event flags apply only in the attempt in which they were drawn (turn counter restarts, 3.9 step 13)
    # Heat Casualties (Naktong, 'heat' until turn n) ended with the attempt too; turn 1 of the new attempt re-armed it
    for _f in (
        "hold_up",
        "event_task",
        "event_flank",
        "event_route",
        "fm_blocked",
        "events_done",
        "heat",
        "heat_open",
    ):
        if s.pop(_f, None) and _f == "heat":
            prot.append("Heat Casualties end with the attempt [L58, Naktong M1 p.17]")
    if s.get("counterattack"):
        s["enemy_tactic"] = s["counterattack"].get("tactic_before", s.get("enemy_tactic"))
        s.pop("counterattack")
        prot.append("Counterattack ends with the last turn (BGG E16)")


def replace_patrol_markers(s, prot):
    """Combat Patrol: new PC markers where they were taken (not on the COP); Primary and Route Points again [2.6.3, MSR 1]."""
    new_pc = []
    for card_id, letter in s.get("pc_start", {}).items():
        c = state.card(s, card_id)
        if not c.get("pc") and card_id != s.get("objectives", {}).get("cop"):
            c["pc"] = letter
            new_pc.append(card_id)
    objectives = s.setdefault("objectives", {})
    objectives["primary"], objectives["route"] = None, {}
    s["target_marker"] = {}
    prot.append(
        ("New PC markers on " + ", ".join(sorted(new_pc)) if new_pc else "No PC markers to replace")
        + "; place Primary, Route Points and Artillery Concentration again (objective primary/route) [2.6.3, MSR 1, Normandy M3 p.24]"
    )


def experience_from_steps(levels):
    """[RULE 12.6 p.82] experience of a multi-step unit from its steps (table 12.6, read from the rulebook layout):
    2 steps: V+L/G Line, L+G Green; 3 steps: VVG Line, VVL Veteran, LL+any Line, GGV Line, GGL Green, VLG Line;
    4 steps: VVV+any Veteran, VV+any+any Line, LLL+any Line, LLVG Line, LLGG Green, GGG+any Green. None = not in the table."""
    order = {"Veteran": 0, "Line": 1, "Green": 2}
    ordered = sorted(levels, key=lambda x: order.get(x, 1))
    if not ordered or any(x not in order for x in ordered):
        return None
    if len(set(ordered)) == 1:
        return ordered[0]
    c = {x: ordered.count(x) for x in order}
    if len(ordered) == 2:
        return "Line" if c["Veteran"] else "Green"
    if len(ordered) == 3:
        if c["Veteran"] == 2:
            return "Veteran" if c["Line"] else "Line"
        if c["Line"] >= 2:
            return "Line"
        if c["Green"] == 2:
            return "Line" if c["Veteran"] else "Green"
        return "Line"  # V L G
    if len(ordered) == 4:
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
    if not _between_missions(s):  # also between missions (12.2), not only in the reattempt preparation
        raise rules.Violation(
            "reconstitute only between missions (12.2) or in the reattempt preparation (3.9); during the turn use 4.2.3i/4.2.1d"
        )
    if not args or args[0].startswith("--"):  # usage instead of a traceback
        raise rules.Violation(f"Usage: {_usage('reconstitute')} [RULE 3.9 p.17, 12.2 p.81]")
    n = args[0]
    o = options.parse_opts(args[1:])
    lats = options.list_option(o, "--from")
    if not lats:
        raise rules.Violation("Specify --from=<LAT>[,<LAT>..]")
    if len(set(lats)) != len(lats):  # a LAT named twice counted twice, then a KeyError
        raise rules.Violation(f"--from names a LAT more than once: {', '.join(lats)}")
    for t in lats:
        lat = state.unit(s, t)
        if lat["side"] != "US" or not state.is_lat(lat):
            raise rules.Violation(f"{t} is not a friendly LAT")
    orig = s.get("setup_units", {}).get(n)
    if not orig:
        raise rules.Violation(f"{n} is not part of the company according to the setup")
    if orig.get("attachment"):
        raise rules.Violation(f"{n} is an attachment, no reconstitution (3.9 step 3)")
    prot = []
    maxst = orig.get("steps", 1)
    old_level = s["units"][n].get("experience", "Line") if n in s["units"] else None
    if n in s["units"]:
        e = s["units"][n]
        if state.steps(e) + len(lats) > maxst:
            raise rules.Violation(f"{n} has at most {maxst} steps")
        e["steps"] = state.steps(e) + len(lats)
        prot.append(f"{n} at {e['steps']} steps")
    else:
        if len(lats) > maxst:
            raise rules.Violation(f"{n} has at most {maxst} steps")
        e = copy.deepcopy(orig)
        e.update(card=s["units"][lats[0]]["card"], area="open", status=[], steps=len(lats), target=None)
        if state.is_hq(e):
            e["experience"] = "Green"
        if n in s.get("removed_from_play", []):
            s["removed_from_play"].remove(n)
        s["units"][n] = e
        if state.is_hq(e):
            s["commands"].setdefault(n, {"available": 0, "saved": 0, "activated": False, "done": False})
        prot.append(
            f"{n} with {len(lats)} step(s) on {e['card']}"
            + (", Green (new HQs are always Green)" if state.is_hq(e) else "")
        )
    level = options.text_opt(o, "--experience", _usage("reconstitute"))
    if level:
        level = rules.experience_value(level, "--experience")
    if level and not state.is_hq(e):
        e["experience"] = level
        e.pop("step_levels", None)
        prot.append(f"Experience {level} (12.6 table, promotions via xp spend)")
    elif not state.is_hq(e):
        old_steps = state.steps(e) - len(lats)
        # [RULE 3.9 step 3, 12.2 'Reduce all other LAT units to Green']: each LAT counts as one Green step
        levels = [old_level] * old_steps + ["Green"] * len(lats)
        derived = experience_from_steps(levels)  # [RULE 12.6 p.82]
        if derived:
            e["experience"], e["step_levels"] = derived, levels  # the mix serves promotions in this window
            prot.append(
                f"Experience {derived} from the steps {'+'.join(x[0] for x in levels)} (table 12.6; set --experience= for a different step mix)"
            )
        else:
            s.setdefault("_hints", []).append(
                f"{n}: step mix {'+'.join(x[0] for x in levels)} is not in table 12.6; set the experience with --experience= or set"
            )
    for t in lats:
        del s["units"][t]  # merged into the reconstituted unit (3.9 step 3), not a removal from play
    prot.append(f"used up: {', '.join(lats)}")
    state.save_state(s, "Reconstitution: " + "; ".join(prot), "3.9 p.17, 12.6 p.82")
    briefing.print_board(prot, s)


def cmd_campaign(s, args):
    k = s.get("campaign")
    if not k:
        print("No campaign mission.")
        return
    print(
        f"# Mission Log {k.get('name')} Mission {k.get('mission_no')}, attempt {k.get('attempt')} of {k.get('attempts_max')}, turn {s['turn']}"
    )
    for a, b in k.get("log", {}).items():
        print(f"- {a}: {b}")
    print(
        f"- CO TAC: {s.get('co_tac_medium') or 'not chosen yet (CSR 1)'}; Mortar: {s.get('mortar_choice') or 'not chosen yet (CSR 2)'}"
    )
    print(
        "- Objectives: "
        + ", ".join(f"{a} {b}" for a, b in s.get("objectives", {}).items() if a != "phaselines")
        + (f", Phase Lines {s['objectives'].get('phaselines')}" if s.get("objectives", {}).get("phaselines") else "")
    )
    print(
        "- Pyro (Mission Log): "
        + (", ".join(f"{a}={b}" for a, b in s.get("pyro_codes", {}).items()) or "no assignment")
    )
    print("- Asset-Pool: " + ", ".join(f"{a} {b}" for a, b in s.get("assets_pool", {}).items() if b))
    print(f"- Fire Missions: {s.get('fire_missions')}")
    print(
        f"- Experience {sum(x['points'] for x in s.get('xp', []))}; US casualty steps {s.get('us_casualties_total', 0)}; prisoners {s.get('prisoners', 0)}; evacuated {s.get('evacuated', 0)}"
        + (
            "; guard steps returning between missions (8.15): "
            + ", ".join(f"{g['unit']} {g['experience']}" for g in s["guards"])
            if s.get("guards")
            else ""
        )
    )
    print("## Units")
    for n, e in s["units"].items():
        if e["side"] == "US":
            print(
                f"- {n}: {state.steps(e)} step(s) {comms.experience(e)}"
                + (f", {e['ammo']['type']} {e['ammo']['points']}" if e.get("ammo") else "")
                + (
                    f", Radio {'/'.join(g['type'] + ' ' + g['net'] for g in comms.radios_of(e))}"
                    if comms.radios_of(e)
                    else ""
                )
                + (f", Assets {', '.join(e['assets'])}" if e.get("assets") else "")
            )
    if s.get("removed_from_play"):
        print("- Removed from Play: " + ", ".join(s["removed_from_play"]))
