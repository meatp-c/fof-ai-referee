"""Higher HQ events, friendly and enemy (3.1, 3.4.1)."""

import copy

from . import briefing, campaign, combat, commands, comms, enemy, fire, geometry, options, rules, state


def r_matches(area, r):
    if "-" in area:
        a, b = area.split("-")
        return int(a) <= r <= int(b)
    return r == int(area)


def find_event(s, item_list, r):
    for ev in item_list:
        for turns, rb in ev["r"].items():
            za, zb = (turns.split("-") + [turns])[:2]
            if int(za) <= s["turn"] <= int(zb) and r_matches(rb, r):
                return ev
    return None


def cmd_heat(s, args):
    """[Naktong M1 p.17] heat <unit> yes|no: the Heat Casualties draw (R#1/4) of a unit just marked Exposed.
    also heat <unit> <R#/4 value 1-4>; 1 is the loss, 2-4 none (a read-off value was once taken for yes)."""
    if len(args) >= 2 and args[1] in ("1", "2", "3", "4"):
        args = [args[0], "yes" if args[1] == "1" else "no", *args[2:]]
    if len(args) < 2 or args[1] not in ("yes", "no"):
        raise rules.Violation('heat "<unit>" <R#/4 value 1-4>|yes|no (only R#/4 = 1 is a loss)')
    n = args[0]
    if n not in (s.get("heat_open") or []):
        raise rules.Violation(f"No Heat Casualties draw open for {n}")
    s["heat_open"].remove(n)
    if not s["heat_open"]:
        s.pop("heat_open")
    prot = []
    if args[1] == "yes" and n in s["units"]:
        combat.reduce_unit(s, n, "C", prot)
        if n in s["units"]:
            combat.last_step_conversion(s, n, prot, pin=False)  # a 2-step squad ends as a generic Fire Team
        fire.open_fire(s, prot)  # [RULE 6.1.1 p.39]: a new team (or a freed target) opens fire at once
        prot.insert(0, f"Heat Casualties: {n} loses one step (R#1/4) [Naktong M1 p.17]")
    else:
        prot.append(f"Heat Casualties: {n} without loss")
    state.save_state(s, "; ".join(prot), "Naktong M1 p.17")
    briefing.print_board(prot, s)


def planned_counter_attack(s):
    """(attempt, turn) if the attempt plan has a planned counter attack in this turn (attempt_plan.planned_counterattack)."""
    p = campaign.attempt_plan(s)
    t = p.get("planned_counterattack")
    if t and t == s["turn"]:
        return (s.get("campaign", {}).get("attempt", 1), t)
    return None


def bn_leader(s):
    return [n for n, e in s["units"].items() if e.get("level") == "BN" and e["side"] == "US"]


def cmd_event(s, args):
    """[RULE 3.1 p.15, 3.4.1 p.16] Action card: HQ radio symbol? Then a second card, R# on the mission's event table."""
    tab = s.get("event_tables")
    if not tab:
        raise rules.Violation("This mission has no event tables")
    event_seg = enemy.enemy_segments(s)[0]  # 3.4.1 offensive, 3.2.1 defensive
    if s["phase"] not in ("3.1", event_seg) or s["turn"] < 2:
        raise rules.Violation(
            f"Events only in 3.1 (Friendly) and {event_seg} (Enemy), from turn 2 on [RULE 3.1 p.15, 3.4.1 p.16]"
        )
    if s.get("events_done") == [s["turn"], s["phase"]]:
        raise rules.Violation("The event of this segment has already been resolved")
    friend = s["phase"] == "3.1"
    if len(args) < 2:  # short input ('event no') gave a traceback
        raise rules.Violation("event <card no> yes <R#> [--who=..] | event <card no> no (card no unknown: ?)")
    num, icon = args[0], args[1]
    o = options.parse_opts(args[2:])
    prot = []
    planned = planned_counter_attack(s)
    if not friend and planned:
        # [Naktong M1 MSR 1 p.19] 'do not draw for an Enemy Higher HQ Event on Turn 7; it is automatically a Counter Attack'
        ev = next((x for x in tab["enemy"] if x["id"] == "counter_attack"), None)
        if ev is None:
            raise rules.Violation("Planned Counter Attack, but the enemy event table has no counter_attack entry")
        prot.append(f"No draw: Planned Counter Attack in attempt {planned[0]}, turn {planned[1]} [MSR 1]")
        enemy_event(s, ev, o, prot)
        icon = "planned"
    if icon == "planned":
        pass
    elif icon == "no":
        prot.append(
            f"Action card #{num} without HQ radio symbol: no {'Friendly' if friend else 'Enemy'} Higher HQ Event"
        )
    elif icon == "yes":
        if len(args) < 3 or args[2].startswith("--"):
            raise rules.Violation(
                f"HQ symbol: draw a second Action card, give R# column {tab.get('column', 10)}: event {num} yes <R#>"
            )
        r = rules.int_value(args[2], "R#")
        ev = find_event(s, tab["friendly" if friend else "enemy"], r)
        if ev is None:
            raise rules.Violation(f"R# {r} in turn {s['turn']} not in the table")
        prot.append(f"Action card #{num} with HQ symbol, R# {r}: {ev['text']}")
        (friendly_event if friend else enemy_event)(s, ev, o, prot)
    else:
        raise rules.Violation("event <cardno> yes <R#> | event <cardno> no")
    s["events_done"] = [s["turn"], s["phase"]]
    activity_note = fire.update_activity(s)
    if activity_note:
        prot.append(activity_note)
    state.save_state(s, "Event: " + "; ".join(prot), "3.1 p.15" if friend else f"{event_seg} p.16")
    briefing.print_board(prot, s)


def _friendly_situation_report(s, ev, o, prot, i):
    co = s.get("co_hq")
    n = 3 if i == "situation_report" else 2
    s["event_task"] = {"id": i, "commands": n, "turn": s["turn"], "star": ev.get("star")}
    if i == "comm_trouble":
        s["bn_unavailable"] = s["turn"]
        prot.append(f"BN HQ does not activate {co} this turn; {co} draws Initiative in 3.3.2a [4.1.1 p.19]")
    prot.append(
        f"{co} must spend its first {n} Commands on it; the tool deducts them at {co}'s first card draw"
        + state.open_reading(s, "U16_first_commands_with_saved")
        + "; no penalty if Commands are short [Normandy M1 p.18]"
    )


def _friendly_tank_support(s, ev, o, prot, i):
    # [Normandy M6 p.39] 'Enter a tank platoon (4 tanks + tank HQ) of M5s on to any cards of your choice on Row 1. Each has 5 ammo.'
    pool = s.get("event_supply", {}).get("tank_support", {})
    if not pool:
        prot.append("Tank Support: no tank platoon defined for this mission, event lapses")
        return
    cards = [x.strip() for x in (o.get("--place") or "").split(",") if x.strip()]
    row1 = geometry.first_card_row(s)
    if len(cards) == 1:
        cards = cards * len(pool)
    if len(cards) != len(pool):
        raise rules.Violation(
            f"Tank Support: --place=<card>[,<card>..] on row {row1}, one card for all or one per vehicle in this order: {', '.join(pool)} [Normandy M6 p.39]"
        )
    for k in cards:
        if state.card(s, k)["row"] != row1 or state.card(s, k).get("staging"):
            raise rules.Violation(f"{k} is not on row {row1} [Normandy M6 p.39]")
    for (n, d), k in zip(pool.items(), cards):
        e = copy.deepcopy(d)
        e.update(card=k, area="open", status=[], target=None)
        s["units"][n] = e
        if state.is_hq(e):
            s["commands"][n] = {"available": 0, "saved": 0, "activated": False, "done": False}
        prot.append(f"Tank Support: {n} ({e.get('vehicle')}, ammo {(e.get('ammo') or {}).get('points')}) enters on {k}")
    s["event_supply"]["tank_support"] = {}
    fire.open_fire(s, prot)


def _friendly_displacing(s, ev, o, prot, i):
    # artillery_displacing, cannon_displacing, mortar_displacing: the firing agency of the event is unavailable
    s["fm_blocked"] = {"turn": s["turn"], "group": ev.get("group", "15th FA")}
    prot.append(f"{ev.get('group', '15th FA')} not available this turn (no Call for Fire)")


def _friendly_checking_up(s, ev, o, prot, i):
    co = s.get("co_hq")
    who = o.get("--who")
    if who not in ("Rgt", "Bn"):
        raise rules.Violation(
            "Checking Up: choose Higher HQ Staff by R#/2 (Rgt Cmdr or Bn Cmdr) and --who=Rgt|Bn [Normandy M1 p.18]"
        )
    if co not in s["units"]:
        prot.append(f"{co} not in play: event not possible, no event [3.1 p.15]")
        return
    name = "Rgt Cmdr" if who == "Rgt" else "Bn Cmdr"
    c = s["units"][co]
    s["units"][name] = {
        "type": "HQ",
        "level": "BN",
        "platoon": None,
        "side": "US",
        "experience": "Line",
        "card": c["card"],
        "area": c.get("area", "open"),
        "status": [],
        "steps": 1,
        "vof_rating": None,
        "range": "L",
        "target": None,
        "fire_team_side": True,
        "ft_vof": "S",
        "radio": [],
        "until_turn": s["turn"] + 1,
        "note": "Higher HQ Staff (Line, 4.1.1); no radio, activates the CO HQ only by Visual-Verbal (BGG 3549109, 3234087: 'BN HQ isn't equipped with a radio')",
    }
    s["commands"][name] = {"available": 0, "saved": 0, "activated": False, "done": False}
    prot.append(
        f"{name} on {c['card']} (with {co}) through turn {s['turn'] + 1}; BN HQ counts as 'on the map': in the BN HQ impulse {name} receives "
        f"{rules.MAX_PER_IMPULSE[s['sight']]} Commands and must activate {co} itself (communication required) [4.1.1 p.18/19]"
    )


def _friendly_trouble_flank(s, ev, o, prot, i):
    s["event_flank"] = {"id": i, "turn": s["turn"]}
    prot.append(
        f"No unit may move this turn onto a new row ahead of the foremost US unit (now row {state.us_front(s)})"
    )


def _friendly_company_ahead(s, ev, o, prot, i):
    if state.us_front(s) >= state.top_row(s):
        prot.append(f"already on row {state.top_row(s)}: event lapses [Normandy M1 p.18]")
        return
    if i == "screaming" and not any(c.get("pc") for c in s["cards"].values() if c["row"] == state.us_front(s) + 1):
        s.setdefault("_hints", []).append(
            "Screaming for Action: check whether a PC marker in the next row is reachable; otherwise the event lapses"
        )
    s["event_flank"] = {
        "id": i,
        "turn": s["turn"],
        "row": state.us_front(s),
        "star": ev.get("star"),
        "fulfilled": False,
    }
    prot.append(
        f"Mandatory (if Commands suffice): at least one unit onto a new row {state.us_front(s) + 1}"
        + (" with a PC marker" if i == "screaming" else "")
        + "; fulfilled = 1 Experience Point [Normandy M1 p.18]"
    )


def _friendly_hold_up(s, ev, o, prot, i):
    s["hold_up"] = s["turn"]
    prot.append("Hold up!: no friendly unit may move onto an unoccupied card this turn [Normandy M3 p.26]")


def _friendly_raining(s, ev, o, prot, i):
    s["weather"], s["weather_this_turn_only"] = 2, True
    geometry.update_visibility(s)
    prot.append(
        f"Rain marker: visibility +2 this turn (total {sum(geometry.light_weather(s)):+d}), Limited Visibility; no card counts as illuminated (9.2.1); remove in Clean Up [Normandy M3 p.26]"
    )


def _friendly_lost_dark(s, ev, o, prot, i):
    who, to_ = o.get("--who"), o.get("--to")
    with_ = campaign.patrol(s).get("members", [])
    if not who or not to_:
        raise rules.Violation(
            f"Lost in the Dark: choose a patrol unit by R# ({', '.join(m for m in with_ if m in s['units'])}), direction by R#8, --who=<unit> --to=<card> "
            "(if the card lies outside: first extend <row> <column> <type> and pc set <card> <letter of the row, row 5 = A>) [Normandy M3 p.26]"
        )
    if who not in with_:
        raise rules.Violation(f"{who} is not part of the patrol")
    state.card(s, to_)
    if not geometry.adjacent(s, s["units"][who]["card"], to_):
        raise rules.Violation(f"{to_} is not adjacent to {s['units'][who]['card']}")
    commands.move_unit(s, who, to_, "open", True, prot)
    prot.append("Lost in the Dark: unit moved one card in a random direction and Exposed [Normandy M3 p.26]")


def _friendly_screaming_route(s, ev, o, prot, i):
    objectives = s.get("objectives", {})
    idx = campaign.patrol(s).get("route_index", 0)
    if idx >= 4:
        prot.append("All four Route Points visited: event lapses [Normandy M3 p.26]")
        return
    s["event_route"] = {
        "turn": s["turn"],
        "target": objectives.get("route", {}).get(str(idx + 1)),
        "star": ev.get("star"),
        "fulfilled": False,
    }
    prot.append(
        f"Mandatory (if Commands suffice): at least one unit toward Route Point {idx + 1} ({s['event_route']['target']}); fulfilled = 1 Experience Point [Normandy M3 p.26]"
    )


def _friendly_heat(s, ev, o, prot, i):
    # [Naktong M1 p.17] 'Until the end of next turn, each time a unit is marked Exposed, draw a card; on R#1/4,
    # remove 1 step from the unit as a casualty. Ignore during Rain.'
    if (s.get("weather") or 0) >= 2:
        prot.append("Heat Casualties: ignored during Rain [Naktong M1 p.17]")
        return
    s["heat"] = {"until_turn": s["turn"] + 1}
    prot.append(
        f"Heat Casualties through turn {s['turn'] + 1}: every time a friendly unit is marked Exposed, draw a card, R#/4 = 1 (only 1) = 1 step Casualty (fof.py heat <unit> <R#/4>) [Naktong M1 p.17]"
    )


def _friendly_units_enter(s, ev, o, prot, i):
    # [Naktong M1 p.17] '.50 cal HMG Team: Place a .50 cal HMG team with 6 ammo in the Staging Area under the
    # command of the HMG HQ. It remains until the end of the current Attempt'
    pool = s.get("event_supply", {}).get(ev["supply"], {})
    if not pool:
        prot.append(f"{ev['text'].split(':')[0]}: unit already in play or not available, event lapses")
        return
    k = o.get("--place")
    if not k or not state.card(s, k).get(ev.get("place", "staging")):
        raise rules.Violation(f"--place=<card of the Staging Area> [{ev.get('source', 'mission event')}]")
    for n, d in pool.items():
        e = copy.deepcopy(d)
        e.update(card=k, area="open", status=[], target=None, attempt_only=ev["supply"])
        s["units"][n] = e
        prot.append(
            f"{n} enters on {k}" + (f" ({e['ammo']['points']} {e['ammo']['type']} ammo)" if e.get("ammo") else "")
        )
    s["event_supply"][ev["supply"]] = {}
    fire.open_fire(s, prot)


def _friendly_ammo_resupply(s, ev, o, prot, i):
    s["event_ammo"] = s["turn"]
    prot.append(
        "Four ammo of one type onto a card of mission row 1 of your choice: fof.py ammo depot <card> MG|MTR|RKT 4 [Normandy M1 p.18]"
    )


FRIENDLY_EVENTS = (
    (lambda i, ev: i in ("situation_report", "comm_trouble"), _friendly_situation_report),
    (lambda i, ev: i == "tank_support", _friendly_tank_support),
    (lambda i, ev: i.endswith("_displacing"), _friendly_displacing),
    (lambda i, ev: i == "checking_up", _friendly_checking_up),
    (lambda i, ev: i == "trouble_flank", _friendly_trouble_flank),
    (lambda i, ev: i in ("company_ahead", "screaming"), _friendly_company_ahead),
    (lambda i, ev: i == "hold_up", _friendly_hold_up),
    (lambda i, ev: i == "raining", _friendly_raining),
    (lambda i, ev: i == "lost_dark", _friendly_lost_dark),
    (lambda i, ev: i == "screaming_route", _friendly_screaming_route),
    (lambda i, ev: i == "heat", _friendly_heat),
    (lambda i, ev: ev.get("supply"), _friendly_units_enter),
    (lambda i, ev: i == "ammo_resupply", _friendly_ammo_resupply),
)


def friendly_event(s, ev, o, prot):
    """Dispatch to the handler of the event id (FRIENDLY_EVENTS); one function per event."""
    i = ev["id"]
    for match, handler in FRIENDLY_EVENTS:
        if match(i, ev):
            return handler(s, ev, o, prot, i)
    raise rules.Violation(f"Friendly event id '{i}' is not implemented; nothing booked (L277)")


def _enemy_evacuate(s, ev, o, prot, i, without_us):
    for k in without_us:
        c = s["cards"][k]
        if c.get("casualties_enemy"):
            prot.append(f"{k}: {c['casualties_enemy']} enemy Casualties removed")
            c["casualties_enemy"] = 0


def _enemy_displace(s, ev, o, prot, i, without_us):
    test = {
        "displace_mortars": state.is_mortar,
        "displace_leaders": lambda e: bool(e.get("leader")),
        "displace_hmgs": lambda e: "HMG" in (e.get("type_name") or ""),  # German HMG, NKPA HMG
    }[i]
    for n, e in list(s["units"].items()):
        if e["side"] == "Enemy" and e["card"] in without_us and test(e):
            enemy.remove_enemy(s, n, prot, reason=ev["text"].split(":")[0])
    if len(prot) == 1:
        prot.append("no affected unit on a card without US troops")


def _enemy_displace_tanks(s, ev, o, prot, i, without_us):
    # [Naktong M1 p.18] 'Displace Tanks: Remove all tanks.'
    for n, e in list(s["units"].items()):
        if e["side"] == "Enemy" and e.get("vehicle"):
            enemy.remove_enemy(s, n, prot, reason="Displace Tanks")
    if len(prot) == 1:
        prot.append("no enemy tank on the map")


def _enemy_rally(s, ev, o, prot, i, without_us):
    for n, e in s["units"].items():
        if e["side"] != "Enemy" or not (state.pinned(e) or state.is_lat(e) or state.fire_team_side(e)):
            continue
        s["event_units"].append(n)  # no Activity Check in the check segment (prepare_enemy_check)
        if fire.vof_against(s, e["card"], "Enemy") is None:
            if state.pinned(e):
                e["status"].remove(rules.PINNED)
                prot.append(f"{n}: Pinned removed (no VOF, automatic) [6.5.1]")
            elif state.is_lat(e) and e["type"] in ("Paralyzed Team", "Litter Team", "Fire Team"):
                nearest = {
                    "Paralyzed Team": "Litter Team",
                    "Litter Team": "Fire Team",
                    "Fire Team": "Assault Team",
                }[e["type"]]
                e["type"] = nearest
                combat.set_lat_values(e, nearest)
                prot.append(f"{n} becomes {nearest} (no VOF, automatic) [6.5.1]")
            elif state.fire_team_side(e):
                e["status"].remove(rules.FIRE_TEAM_SIDE)
                prot.append(f"{n}: back to the front side (no VOF) [4.2.3f]")
            elif e["type"] == "Assault Team":
                prot.append(
                    f"{n}: Assault Team is already the highest LAT, no upgrade [6.5.1 'Rallying Generic LATs', L165]"
                )
        elif e["type"] == "Assault Team" and not state.pinned(e):
            prot.append(
                f"{n}: Assault Team is already the highest LAT, no upgrade [6.5.1 'Rallying Generic LATs', L165]"
            )
        else:
            s.setdefault("rally_open", []).append(n)
            prot.append(
                f'{n}: Rally under VOF: {comms.enemy_rally_cards(e)[0]} cards (base 2, experience {e.get("experience")}), word Rally; fof.py enemyaction "{n}" Rally --success=yes|no'
            )
    prot.append(f"These units make no further Activity Check in {enemy.enemy_segments(s)[1]} [3.4.1 p.16]")


def _enemy_fall_back(s, ev, o, prot, i, without_us):
    for n, e in list(s["units"].items()):
        if e["side"] != "Enemy" or state.pinned(e):
            continue
        if e.get("immobile"):
            prot.append(f"{n} is immobile (AT gun), stays [8.12 p.68]")
            continue
        c = state.card(s, e["card"])
        target = geometry.card_at(s, c["row"] + 1, c["column"])
        s["event_units"].append(n)  # no Activity Check in the check segment (prepare_enemy_check)
        if target is None:
            if state.option(s, "U18_fall_back_edge_offmap"):
                enemy.remove_enemy(
                    s,
                    n,
                    prot,
                    reason="Fall Back over the map edge" + state.open_reading(s, "U18_fall_back_edge_offmap"),
                )
            else:
                prot.append(f"{n}: no card behind {e['card']}, stays (map edge) [8.6.3]")
            continue
        if enemy.restricted_mover(e) and fire.vof_against(s, target, "Enemy") is not None:
            # = E90 [RULE 4.2.5 p.26]: Paralyzed/Litter Teams only onto a card without VOF
            prot.append(f"{n} ({e['type']}): VOF on {target}, no Fall Back possible, stays [RULE 4.2.5 p.26, E90]")
            continue
        # the one enemy move path (ammo surplus, Deep Bunker left, best free cover, Exposed, mine check)
        enemy.move_enemy(s, n, target, prot, how="falls straight back", rule="8.6.1C, Normandy M1 p.18")


def _enemy_shifting_lines(s, ev, o, prot, i, without_us):
    top = state.top_row(s)
    ks = sorted(k for k, c in s["cards"].items() if c["row"] == top and c.get("pc") and not c.get("outside"))
    for k in ks:
        s["cards"][k]["pc"] = "?"
    prot.append(
        f"Shifting Lines: remove unresolved PC markers of row 4 ({', '.join(ks) or 'none'}), redraw randomly from A, B and C, '?' side up; "
        "letter when revealed: pc reveal <card> <A|B|C> [Normandy M3 p.26]"
    )


def _counter_attack_cards(s, ga, us_cards):
    """The US-occupied cards that get a PC A marker, by the mission's rule: (cards, source text)."""
    pc_cards = [k for k, c in s["cards"].items() if c.get("pc")]

    def next_to_pc(k):
        return any(geometry.distance(s, k, u) == 1 for u in pc_cards)

    if ga.get("mode") == "naktong":
        # [Naktong CSR 5 p.13] PC A on all US-occupied cards that are a) adjacent to a card with a PC marker
        # (BGG 3516351: any PC marker), b) adjacent to a card not occupied by US forces, or c) in the top row; all cards
        # are determined first and get their marker at the same time (BGG 3542710)
        occupied = {e["card"] for e in s["units"].values() if e["side"] == "US" and e.get("card")}
        top = state.top_row(s)
        cards = [
            k
            for k in us_cards
            if state.card(s, k)["row"] == top
            or next_to_pc(k)
            or any(
                geometry.distance(s, k, u) == 1 and u not in occupied and not state.card(s, u).get("staging")
                for u in s["cards"]
            )
        ]
        return cards, (
            "(US cards next to a PC marker, next to a card without US troops, or on the top row) [Naktong CSR 5 p.13]"
        )
    # [Normandy M4 MSR 4 p.30] PC A on US cards next to a card with an unrevealed PC or on Row 4
    # 'unrevealed PC' = a PC marker still on the board: its package is not drawn until a friendly unit
    # resolves it [RULE 8.2.4]; the '?' side and the letter side both count
    last_row = ga.get("row", 4)  # last mission row from the setup (M6: card row 6)
    cards = [k for k in us_cards if state.card(s, k)["row"] == last_row or next_to_pc(k)]
    return cards, "(US cards next to an unrevealed PC or on Row 4) [Normandy M4 MSR 4 p.30]"


def _place_pc_a(s, cards, prot):
    """A PC A marker on each card; an existing marker is compared with it [RULE 8.2.3 p.62]."""
    replaced = []
    for k in cards:
        c = s["cards"][k]
        if c.get("pc") == "?":
            c["pc2"] = "A"  # face down: compare only when revealed
        elif c.get("pc") != "A":  # a second A would be the lower one of the same level, nothing changes
            if c.get("pc"):
                replaced.append(f"{k} ({c['pc']} removed)")  # both face up: the lower letter is removed at once
            c["pc"] = "A"
    if replaced:
        prot.append("two face-up PC markers: the lower one is removed on " + ", ".join(replaced) + " [RULE 8.2.3 p.62]")


def _enemy_counter_attack(s, ev, o, prot, i, without_us):
    ga = s.get("special_rules", {}).get("counterattack", {})
    us_cards = sorted(
        {
            e["card"]
            for e in s["units"].values()
            if e["side"] == "US"
            and e.get("card") in s["cards"]
            and (state.option(s, "U17_counterattack_staging") or not state.card(s, e["card"]).get("staging"))
        }
    )
    if ga.get("mode") in ("naktong", "m4"):
        cards, source = _counter_attack_cards(s, ga, us_cards)
        _place_pc_a(s, cards, prot)
        until = start_counter_attack(s, dict(ga, mode="m4"))  # the same counter attack in both modes
        prot.append(f"PC marker A on {', '.join(cards) or 'no card'} {source}")
        prot.append(
            f"enemy tactic Offensive Assault up to and including turn {until}; 'Counter Attack Ends' marker on turn {until + 1}; PC A with the Counter Attack list [MSR 4]"
        )
        return
    for k in us_cards:
        c = s["cards"][k]
        if c.get("pc"):
            c["pc2"] = "?"
        else:
            c["pc"] = "?"
    until = start_counter_attack(s, ga)
    prot.append(
        f"Draw PC markers randomly from all not yet placed, '?' side up, onto {', '.join(us_cards) or 'no card'}"
        + ("" if state.option(s, "U17_counterattack_staging") else state.open_reading(s, "U17_counterattack_staging"))
        + "; if one is already there, the lower one is removed after revealing (8.2.3 p.62)"
    )
    prot.append(
        f"Enemy tactic Offensive Assault through turn {until}; 'Counter Attack Ends' marker on turn {until + 1}; PC A with the Counter Attack list"
        + state.open_reading(s, "U28_counterattack_all_pc_a")
        + " [Normandy M1 MSR 1 p.19]"
    )


ENEMY_EVENTS = (
    (lambda i, ev: i == "evacuate", _enemy_evacuate),
    (lambda i, ev: i in ("displace_mortars", "displace_leaders", "displace_hmgs"), _enemy_displace),
    (lambda i, ev: i == "displace_tanks", _enemy_displace_tanks),
    (lambda i, ev: i == "rally", _enemy_rally),
    (lambda i, ev: i == "fall_back", _enemy_fall_back),
    (lambda i, ev: i == "shifting_lines", _enemy_shifting_lines),
    (lambda i, ev: i == "counter_attack", _enemy_counter_attack),
)


def enemy_event(s, ev, o, prot):
    """Dispatch to the handler of the event id (ENEMY_EVENTS); one function per event."""
    i = ev["id"]
    s["event_units"] = []
    without_us = [k for k in s["cards"] if not state.units_on(s, k, "US")]
    for match, handler in ENEMY_EVENTS:
        if match(i, ev):
            return handler(s, ev, o, prot, i, without_us)
    raise rules.Violation(f"Enemy event id '{i}' is not implemented; nothing booked (L277)")


def start_counter_attack(s, ga):
    """Counter-attack bookkeeping: the enemy tactic switches to the counter-attack tactic for
    ga['turns'] turns including this one; a running counter-attack is extended. Returns the last turn."""
    until = s["turn"] + ga.get("turns", 3) - 1
    if not s.get("counterattack"):
        s["counterattack"] = {"tactic_before": s.get("enemy_tactic"), "until_turn": until}
    else:
        s["counterattack"]["until_turn"] = until
    s["enemy_tactic"] = ga.get("tactic", "Offensive Assault")
    return until


def event_pay_commands(s, hq, prot):
    """Situation Report / Comm Trouble: the first N Commands of the CO HQ go to the event (Normandy M1 p.18) [open U16]."""
    ev = s.get("event_task")
    if not ev or ev["turn"] != s["turn"] or hq != s.get("co_hq") or ev.get("paid") is not None:
        return
    k = s["commands"][hq]
    pool = k["available"] + (k["saved"] if state.option(s, "U16_first_commands_with_saved") else 0)
    n = min(ev["commands"], pool)
    remainder = n
    ab = min(remainder, k["available"])
    k["available"] -= ab
    remainder -= ab
    k["saved"] -= remainder
    ev["paid"] = n
    s.setdefault("impulse_spent", {})[hq] = s["impulse_spent"].get(hq, 0) + n
    prot.append(
        f"{hq}: {n} Command(s) spent on '{ev['id'].replace('_', ' ')}'"
        + (" (fewer than required, no penalty)" if n < ev["commands"] else "")
        + f", remaining {k['available']}+{k['saved']}"
        + state.open_reading(s, "U16_first_commands_with_saved")
        + " [Normandy M1 p.18]"
    )
    if n == ev["commands"] and ev.get("star"):
        campaign.book_xp(s, campaign.xp_table(s, "hq_event_star") or 1, f"HQ event {ev['id']} fulfilled", prot)


def check_event_flank(s, prot):
    """At the end of the Friendly Command Phase: Company on the Flank / Screaming for Action fulfilled? (Normandy M1 p.18)"""
    ev = s.get("event_flank")
    if not ev or ev["turn"] != s["turn"] or ev["id"] == "trouble_flank" or ev.get("checked"):
        return
    ev["checked"] = True
    if ev.get("fulfilled"):
        prot.append(f"Event '{ev['id'].replace('_', ' ')}' fulfilled")
        if ev.get("star"):
            campaign.book_xp(s, campaign.xp_table(s, "hq_event_star") or 1, f"HQ event {ev['id']} fulfilled", prot)
    else:
        prot.append(
            f"Event '{ev['id'].replace('_', ' ')}' not fulfilled: mandatory if the Commands would have sufficed; no penalty for lack of Commands [3.1 p.15, Normandy M1 p.18]"
        )


def open_flank_note(s):
    """Reminder at the start of a Command impulse while 'Company ahead' / 'Screaming for Action' is not fulfilled."""
    ev = s.get("event_flank")
    if not ev or ev["turn"] != s["turn"] or ev["id"] not in ("company_ahead", "screaming") or ev.get("fulfilled"):
        return None
    return (
        f"Note: event '{ev['id'].replace('_', ' ')}' is still open: a unit has to enter a card beyond row {ev['row']}"
        + (" with a PC marker" if ev["id"] == "screaming" else "")
        + " if the Commands suffice [Normandy M1 p.18]"
    )


def event_move(s, e, target_card, prot):
    """Trouble on the Flank forbids, Company ahead/Screaming require the step onto a new row."""
    ev = s.get("event_flank")
    if not ev or ev["turn"] != s["turn"] or e["side"] != "US" or s["phase"] not in rules.IMPULSES:
        return
    zr = state.card(s, target_card)["row"]
    if ev["id"] == "trouble_flank" and zr > state.us_front(s):
        raise rules.Violation(
            f"Trouble on the Flank: no movement onto a new row ahead of row {state.us_front(s)} this turn [Normandy M1 p.18]"
        )
    if ev["id"] in ("company_ahead", "screaming") and zr > ev["row"] and not ev.get("fulfilled"):
        if ev["id"] == "company_ahead" or state.card(s, target_card).get("pc"):
            ev["fulfilled"] = True
            prot.append(
                f"Event '{ev['id'].replace('_', ' ')}' fulfilled (new row {zr}"
                + (", PC marker" if ev["id"] == "screaming" else "")
                + ")"
            )
