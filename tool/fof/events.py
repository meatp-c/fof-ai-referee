"""Higher HQ events, friendly and enemy (3.1, 3.4.1)."""

from . import briefing, campaign, combat, commands, comms, contact, enemy, fire, geometry, options, rules, state


def r_matches(area, r):
    if "-" in area:
        a, b = area.split("-")
        return int(a) <= r <= int(b)
    return r == int(area)


def find_event(s, item_list, r):
    for ev in item_list:
        for turns, rb in ev["r"].items():
            za, zb = (turns.split("-") + [turns])[:2]
            if int(za) <= s["zug"] <= int(zb) and r_matches(rb, r):
                return ev
    return None


def bn_leader(s):
    return [n for n, e in s["einheiten"].items() if e.get("ebene") == "BN" and e["seite"] == "US"]


def cmd_event(s, args):
    """[RULE 3.1 p.15, 3.4.1 p.16] Action card: HQ radio symbol? Then a second card, R# on the mission's event table."""
    tab = s.get("ereignistabellen")
    if not tab:
        raise rules.Violation("This mission has no event tables")
    if s["phase"] not in ("3.1", "3.4.1", "3.2.1") or s["zug"] < 2:
        raise rules.Violation(
            "Events only in 3.1 (Friendly) and 3.4.1 (Enemy), from turn 2 on [RULE 3.1 p.15, 3.4.1 p.16]"
        )
    if s.get("ereignis_erledigt") == [s["zug"], s["phase"]]:
        raise rules.Violation("The event of this segment has already been resolved")
    friend = s["phase"] == "3.1"
    nr, icon = args[0], args[1]
    o = options.parse_opts(args[2:])
    prot = []
    if icon == "nein":
        prot.append(
            f"Action card #{nr} without HQ radio symbol: no {'Friendly' if friend else 'Enemy'} Higher HQ Event"
        )
    elif icon == "ja":
        if len(args) < 3 or args[2].startswith("--"):
            raise rules.Violation(
                f"HQ symbol: draw a second Action card, give R# column {tab.get('spalte', 10)}: event {nr} yes <R#>"
            )
        r = int(args[2])
        ev = find_event(s, tab["freund" if friend else "feind"], r)
        if ev is None:
            raise rules.Violation(f"R# {r} in turn {s['zug']} not in the table")
        prot.append(f"Action card #{nr} with HQ symbol, R# {r}: {ev['text']}")
        (friendly_event if friend else enemy_event)(s, ev, o, prot)
    else:
        raise rules.Violation("event <cardno> yes <R#> | event <cardno> no")
    s["ereignis_erledigt"] = [s["zug"], s["phase"]]
    ak = fire.update_activity(s)
    if ak:
        prot.append(ak)
    state.save_state(s, "Event: " + "; ".join(prot), "3.1 p.15" if friend else "3.4.1 p.16")
    briefing.print_board(prot, s)


def friendly_event(s, ev, o, prot):
    i = ev["id"]
    co = s.get("co_hq")
    if i in ("situation_report", "comm_trouble"):
        n = 3 if i == "situation_report" else 2
        s["ereignis_pflicht"] = {"id": i, "commands": n, "zug": s["zug"], "stern": ev.get("stern")}
        if i == "comm_trouble":
            s["bn_nicht_verfuegbar"] = s["zug"]
            prot.append(f"BN HQ does not activate {co} this turn; {co} draws Initiative in 3.3.2a [4.1.1 p.19]")
        prot.append(
            f"{co} must spend its first {n} Commands on it; the tool deducts them at {co}'s first card draw"
            + state.open_reading(s, "U16_erste_commands_mit_gespart")
            + "; no penalty if Commands are short [Normandy M1 p.18]"
        )
    elif i == "artillery_displacing":
        s["fm_gesperrt"] = {"zug": s["zug"], "gruppe": ev.get("gruppe", "15th FA")}
        prot.append(f"{ev.get('gruppe', '15th FA')} not available this turn (no Call for Fire)")
    elif i == "checking_up":
        who = o.get("--wer")
        if who not in ("Rgt", "Bn"):
            raise rules.Violation(
                "Checking Up: choose Higher HQ Staff by R#/2 (Rgt Cmdr or Bn Cmdr) and --who=Rgt|Bn [Normandy M1 p.18]"
            )
        if co not in s["einheiten"]:
            prot.append(f"{co} not in play: event not possible, no event [3.1 p.15]")
            return
        name = "Rgt Cmdr" if who == "Rgt" else "Bn Cmdr"
        c = s["einheiten"][co]
        s["einheiten"][name] = {
            "typ": "HQ",
            "ebene": "BN",
            "platoon": None,
            "seite": "US",
            "erfahrung": "Line",
            "karte": c["karte"],
            "bereich": c.get("bereich", "offen"),
            "status": [],
            "steps": 1,
            "vof_rating": None,
            "reichweite": "L",
            "ziel": None,
            "fire_team_seite": True,
            "ft_vof": "S",
            "funk": [],
            "bis_zug": s["zug"] + 1,
            "hinweis": "Higher HQ Staff (Line, 4.1.1); no BN TAC radio, activates the CO HQ only by Visual-Verbal (BGG E30)",
        }
        s["kommandos"][name] = {"verfuegbar": 0, "gespart": 0, "aktiviert": False, "fertig": False}
        prot.append(
            f"{name} on {c['karte']} (with {co}) through turn {s['zug'] + 1}; BN HQ counts as 'on the map': in the BN HQ impulse {name} receives "
            f"{rules.MAX_PER_IMPULSE[s['sicht']]} Commands and must activate {co} itself (communication required) [4.1.1 p.18/19]"
        )
    elif i == "trouble_flank":
        s["ereignis_flanke"] = {"id": i, "zug": s["zug"]}
        prot.append(
            f"No unit may move this turn onto a new row ahead of the foremost US unit (now row {state.us_front(s)})"
        )
    elif i in ("company_ahead", "screaming"):
        if state.us_front(s) >= state.top_row(s):
            prot.append("already on row 3: event lapses [Normandy M1 p.18]")
            return
        if i == "screaming" and not any(
            c.get("pc") for c in s["karten"].values() if c["reihe"] == state.us_front(s) + 1
        ):
            s.setdefault("_hinweise", []).append(
                "Screaming for Action: check whether a PC marker in the next row is reachable; otherwise the event lapses"
            )
        s["ereignis_flanke"] = {
            "id": i,
            "zug": s["zug"],
            "reihe": state.us_front(s),
            "stern": ev.get("stern"),
            "erfuellt": False,
        }
        prot.append(
            f"Mandatory (if Commands suffice): at least one unit onto a new row {state.us_front(s) + 1}"
            + (" with a PC marker" if i == "screaming" else "")
            + "; fulfilled = 1 Experience Point [Normandy M1 p.18]"
        )
    elif i == "hold_up":
        s["hold_up"] = s["zug"]
        prot.append("Hold up!: no friendly unit may move onto an unoccupied card this turn [Normandy M3 p.26]")
    elif i == "raining":
        s["wetter"], s["wetter_nur_zug"] = 2, True
        geometry.update_visibility(s)
        prot.append(
            f"Rain marker: visibility +2 this turn (total {sum(geometry.light_weather(s)):+d}), Limited Visibility; no card counts as illuminated (9.2.1); remove in Clean Up [Normandy M3 p.26]"
        )
    elif i == "lost_dark":
        who, to_ = o.get("--wer"), o.get("--nach")
        with_ = campaign.patrol(s).get("mitglieder", [])
        if not who or not to_:
            raise rules.Violation(
                f"Lost in the Dark: choose a patrol unit by R# ({', '.join(m for m in with_ if m in s['einheiten'])}), direction by R#8, --who=<unit> --to=<card> "
                "(if the card lies outside: first extend <row> <column> <type> and pc set <card> <letter of the row, row 5 = A>) [Normandy M3 p.26]"
            )
        if who not in with_:
            raise rules.Violation(f"{who} is not part of the patrol")
        state.card(s, to_)
        if not geometry.adjacent(s, s["einheiten"][who]["karte"], to_):
            raise rules.Violation(f"{to_} is not adjacent to {s['einheiten'][who]['karte']}")
        commands.move_unit(s, who, to_, "offen", True, prot)
        prot.append("Lost in the Dark: unit moved one card in a random direction and Exposed [Normandy M3 p.26]")
    elif i == "screaming_route":
        z = s.get("ziele", {})
        idx = campaign.patrol(s).get("route_index", 0)
        if idx >= 4:
            prot.append("All four Route Points visited: event lapses [Normandy M3 p.26]")
            return
        s["ereignis_route"] = {
            "zug": s["zug"],
            "ziel": z.get("route", {}).get(str(idx + 1)),
            "stern": ev.get("stern"),
            "erfuellt": False,
        }
        prot.append(
            f"Mandatory (if Commands suffice): at least one unit toward Route Point {idx + 1} ({s['ereignis_route']['ziel']}); fulfilled = 1 Experience Point [Normandy M3 p.26]"
        )
    elif i == "ammo_resupply":
        s["ereignis_munition"] = s["zug"]
        prot.append(
            "Four ammo of one type onto a card of mission row 1 of your choice: fof.py ammo depot <card> MG|MTR|RKT 4 [Normandy M1 p.18]"
        )


def enemy_event(s, ev, o, prot):
    i = ev["id"]
    without_us = [k for k in s["karten"] if not state.units_on(s, k, "US")]
    s["ereignis_einheiten"] = []
    if i == "evacuate":
        for k in without_us:
            c = s["karten"][k]
            if c.get("casualties_feind"):
                prot.append(f"{k}: {c['casualties_feind']} enemy Casualties removed")
                c["casualties_feind"] = 0
    elif i in ("displace_mortars", "displace_leaders", "displace_hmgs"):
        test = {
            "displace_mortars": lambda e: state.is_mortar(e),
            "displace_leaders": lambda e: bool(e.get("leader")),
            "displace_hmgs": lambda e: e.get("typname") == "German HMG",
        }[i]
        for n, e in list(s["einheiten"].items()):
            if e["seite"] == "Feind" and e["karte"] in without_us and test(e):
                enemy.remove_enemy(s, n, prot, reason=ev["text"].split(":")[0])
        if len(prot) == 1:
            prot.append("no affected unit on a card without US troops")
    elif i == "rally":
        for n, e in s["einheiten"].items():
            if e["seite"] != "Feind" or not (state.pinned(e) or state.is_lat(e) or state.fire_team_side(e)):
                continue
            s["ereignis_einheiten"].append(n)
            e["check_offen"] = False
            if fire.vof_against(s, e["karte"], "Feind") is None:
                if state.pinned(e):
                    e["status"].remove("Pinned")
                    prot.append(f"{n}: Pinned removed (no VOF, automatic) [6.5.1]")
                elif state.is_lat(e) and e["typ"] in ("Paralyzed Team", "Litter Team", "Fire Team"):
                    nearest = {
                        "Paralyzed Team": "Litter Team",
                        "Litter Team": "Fire Team",
                        "Fire Team": "Assault Team",
                    }[e["typ"]]
                    e["typ"] = nearest
                    combat.set_lat_values(e, nearest)
                    prot.append(f"{n} becomes {nearest} (no VOF, automatic) [6.5.1]")
                elif state.fire_team_side(e):
                    e["status"].remove("Fire Team side")
                    prot.append(f"{n}: back to the front side (no VOF) [4.2.3f]")
            else:
                s.setdefault("rally_offen", []).append(n)
                prot.append(
                    f'{n}: Rally under VOF: {comms.enemy_rally_cards(e)[0]} cards (base 2, experience {e.get("erfahrung")}), word Rally; fof.py enemyaction "{n}" Rally --success=yes|no'
                )
        prot.append("These units make no further Activity Check in 3.4.2 [3.4.1 p.16]")
    elif i == "fall_back":
        for n, e in list(s["einheiten"].items()):
            if e["seite"] != "Feind" or state.pinned(e):
                continue
            if e.get("unbeweglich"):
                prot.append(f"{n} is immobile (AT gun), stays [8.12 p.68]")
                continue
            c = state.card(s, e["karte"])
            target = geometry.card_at(s, c["reihe"] + 1, c["spalte"])
            s["ereignis_einheiten"].append(n)
            if target is None:
                if state.option(s, "U18_fall_back_rand_offmap"):
                    enemy.remove_enemy(
                        s,
                        n,
                        prot,
                        reason="Fall Back over the map edge" + state.open_reading(s, "U18_fall_back_rand_offmap"),
                    )
                continue
            commands.grenade_expires(s, e, n, prot)
            e["karte"], e["bereich"] = target, "offen"
            commands.mark(e, "Exposed")
            free = [
                cv
                for cv in state.card(s, target).get("cover", [])
                if not any(
                    s["einheiten"][m]["seite"] == "US" and s["einheiten"][m].get("bereich") == cv["id"]
                    for m in state.units_on(s, target)
                )
            ]
            if free:
                e["bereich"] = max(free, key=lambda x: x["wert"])["id"]
            prot.append(
                f"{n} falls straight back to {target}"
                + (f" under {e['bereich']}" if e["bereich"] != "offen" else "")
                + ", Exposed [8.6.1C, Normandy M1 p.18]"
            )
            fire.fire_after_move(s, n, prot)
            contact.request_mine_check(s, [n], target, prot, "enemy enters a mined card")
        for n in s["ereignis_einheiten"]:
            if n in s["einheiten"]:
                s["einheiten"][n]["check_offen"] = False
    elif i == "shifting_lines":
        top = state.top_row(s)
        ks = sorted(k for k, c in s["karten"].items() if c["reihe"] == top and c.get("pc") and not c.get("ausserhalb"))
        for k in ks:
            s["karten"][k]["pc"] = "?"
        prot.append(
            f"Shifting Lines: remove unresolved PC markers of row 4 ({', '.join(ks) or 'none'}), redraw randomly from A, B and C, '?' side up; "
            "letter when revealed: pc reveal <card> <A|B|C> [Normandy M3 p.26]"
        )
    elif i == "counter_attack":
        ga = s.get("sonderregeln", {}).get("gegenangriff", {})
        us_cards = sorted(
            {
                e["karte"]
                for e in s["einheiten"].values()
                if e["seite"] == "US"
                and e.get("karte") in s["karten"]
                and (state.option(s, "U17_gegenangriff_staging") or not state.card(s, e["karte"]).get("staging"))
            }
        )
        if ga.get("modus") == "m4":
            # L74 [Normandy M4 MSR 4 p.30] PC A on US cards next to a card with an unrevealed PC or on Row 4
            unrevealed = [
                kk
                for kk, cc in s["karten"].items()
                if cc.get("pc") == "?" or (cc.get("pc") and not cc.get("pc_aufgedeckt"))
            ]
            us_cards = [
                kk
                for kk in us_cards
                if state.card(s, kk)["reihe"] == 4 or any(geometry.distance(s, kk, u) == 1 for u in unrevealed)
            ]
            replaced = []
            for kk in us_cards:
                cc = s["karten"][kk]
                if cc.get("pc") == "?":
                    cc["pc2"] = "A"  # face down: compare only when revealed (8.2.3)
                elif cc.get("pc") == "A":
                    pass  # already A: a second A marker would be the lower one of the same level, nothing changes (8.2.3)
                elif cc.get("pc"):
                    replaced.append(
                        f"{kk} ({cc['pc']} removed)"
                    )  # L88 [RULE 8.2.3 p.62] both face up: the lower letter is removed at once
                    cc["pc"] = "A"
                else:
                    cc["pc"] = "A"
            if replaced:
                prot.append(
                    "two face-up PC markers: the lower one is removed on " + ", ".join(replaced) + " [RULE 8.2.3 p.62]"
                )
            until = s["zug"] + ga.get("zuege", 3) - 1
            if not s.get("gegenangriff"):
                s["gegenangriff"] = {"taktik_vorher": s.get("feind_taktik"), "bis_zug": until}
            else:
                s["gegenangriff"]["bis_zug"] = until
            s["feind_taktik"] = ga.get("taktik", "Offensive Assault")
            prot.append(
                f"PC marker A on {', '.join(us_cards) or 'no card'} (US cards next to an unrevealed PC or on Row 4) [Normandy M4 MSR 4 p.30]"
            )
            prot.append(
                f"enemy tactic Offensive Assault up to and including turn {until}; 'Counter Attack Ends' marker on turn {until + 1}; PC A with the Counter Attack list [MSR 4]"
            )
            return
        for k in us_cards:
            c = s["karten"][k]
            if c.get("pc"):
                c["pc2"] = "?"
            else:
                c["pc"] = "?"
        until = s["zug"] + ga.get("zuege", 3) - 1
        if not s.get("gegenangriff"):
            s["gegenangriff"] = {"taktik_vorher": s.get("feind_taktik"), "bis_zug": until}
        else:
            s["gegenangriff"]["bis_zug"] = until
        s["feind_taktik"] = ga.get("taktik", "Offensive Assault")
        prot.append(
            f"Draw PC markers randomly from all not yet placed, '?' side up, onto {', '.join(us_cards) or 'no card'}"
            + ("" if state.option(s, "U17_gegenangriff_staging") else state.open_reading(s, "U17_gegenangriff_staging"))
            + "; if one is already there, the lower one is removed after revealing (8.2.3 p.62)"
        )
        prot.append(
            f"Enemy tactic Offensive Assault through turn {until}; 'Counter Attack Ends' marker on turn {until + 1}; PC A with the Counter Attack list"
            + state.open_reading(s, "U28_gegenangriff_alle_pc_a")
            + " [Normandy M1 MSR 1 p.19]"
        )


def event_pay_commands(s, hq, prot):
    """Situation Report / Comm Trouble: the first N Commands of the CO HQ go to the event (Normandy M1 p.18) [open U16]."""
    ev = s.get("ereignis_pflicht")
    if not ev or ev["zug"] != s["zug"] or hq != s.get("co_hq") or ev.get("bezahlt") is not None:
        return
    k = s["kommandos"][hq]
    pool = k["verfuegbar"] + (k["gespart"] if state.option(s, "U16_erste_commands_mit_gespart") else 0)
    n = min(ev["commands"], pool)
    remainder = n
    ab = min(remainder, k["verfuegbar"])
    k["verfuegbar"] -= ab
    remainder -= ab
    k["gespart"] -= remainder
    ev["bezahlt"] = n
    s.setdefault("impuls_ausgegeben", {})[hq] = s["impuls_ausgegeben"].get(hq, 0) + n
    prot.append(
        f"{hq}: {n} Command(s) spent on '{ev['id'].replace('_', ' ')}'"
        + (" (fewer than required, no penalty)" if n < ev["commands"] else "")
        + f", remaining {k['verfuegbar']}+{k['gespart']}"
        + state.open_reading(s, "U16_erste_commands_mit_gespart")
        + " [Normandy M1 p.18]"
    )
    if n == ev["commands"] and ev.get("stern"):
        campaign.book_xp(s, campaign.xp_table(s, "hq_ereignis_stern") or 1, f"HQ event {ev['id']} fulfilled", prot)


def check_event_flank(s, prot):
    """At the end of the Friendly Command Phase: Company on the Flank / Screaming for Action fulfilled? (Normandy M1 p.18)"""
    ev = s.get("ereignis_flanke")
    if not ev or ev["zug"] != s["zug"] or ev["id"] == "trouble_flank" or ev.get("geprueft"):
        return
    ev["geprueft"] = True
    if ev.get("erfuellt"):
        prot.append(f"Event '{ev['id'].replace('_', ' ')}' fulfilled")
        if ev.get("stern"):
            campaign.book_xp(s, campaign.xp_table(s, "hq_ereignis_stern") or 1, f"HQ event {ev['id']} fulfilled", prot)
    else:
        prot.append(
            f"Event '{ev['id'].replace('_', ' ')}' not fulfilled: mandatory if the Commands would have sufficed; no penalty for lack of Commands [3.1 p.15, Normandy M1 p.18]"
        )


def event_move(s, e, target_card, prot):
    """Trouble on the Flank forbids, Company ahead/Screaming require the step onto a new row."""
    ev = s.get("ereignis_flanke")
    if not ev or ev["zug"] != s["zug"] or e["seite"] != "US" or s["phase"] not in rules.IMPULSES:
        return
    zr = state.card(s, target_card)["reihe"]
    if ev["id"] == "trouble_flank" and zr > state.us_front(s):
        raise rules.Violation(
            f"Trouble on the Flank: no movement onto a new row ahead of row {state.us_front(s)} this turn [Normandy M1 p.18]"
        )
    if ev["id"] in ("company_ahead", "screaming") and zr > ev["reihe"] and not ev.get("erfuellt"):
        if ev["id"] == "company_ahead" or state.card(s, target_card).get("pc"):
            ev["erfuellt"] = True
            prot.append(
                f"Event '{ev['id'].replace('_', ' ')}' fulfilled (new row {zr}"
                + (", PC marker" if ev["id"] == "screaming" else "")
                + ")"
            )
