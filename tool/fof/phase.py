"""Sequence of play: new game, phase changes, clean up, capture and retreat (3.x)."""

import copy
import json
import os
import pathlib
import sys

from . import briefing, campaign, combat, commands, comms, contact, enemy, events, fire, geometry, rules, setup, state


def cmd_new(args):
    if not args:
        sys.exit("fof.py new <setup.json> [game]")

    setup_data = json.loads(pathlib.Path(args[0]).read_text(encoding="utf-8"))
    name = args[1] if len(args) > 1 else "partie1"
    test_run = bool(os.environ.get("FOF_PARTIE"))
    if test_run:
        name = os.environ["FOF_PARTIE"]  # test run: .aktuelle_partie stays unchanged
    for k in [k for k in setup_data if k.startswith("_")]:
        setup_data.pop(k)  # comment fields of the setup do not go into the game state
    s = copy.deepcopy(setup_data)
    for k, v in {
        "zug": 1,
        "phase": state.sop(s)[0][0],
        "aktiver_hq": None,
        "impuls_aktionen": {},
        "impuls_ausgegeben": {},
        "protokoll": [],
        "kommandos": {},
        "removed_from_play": [],
        "kampf_offen": [],
    }.items():
        s.setdefault(k, v)
    for n, e in s["einheiten"].items():
        e.setdefault("status", [])
        e.setdefault("seite", "US")
        e.setdefault("bereich", "offen")
        e.setdefault("ziel", None)
        if state.is_hq(e):
            s["kommandos"].setdefault(n, {"verfuegbar": 0, "gespart": 0, "aktiviert": False, "fertig": False})
    for k in s["karten"].values():
        k.setdefault("cover", [])
        k.setdefault("extern", [])
    if s.get("fm_werte"):
        s.setdefault("target_marker", {})
    if state.is_v4(s):
        # v4: record initial state for Reattempt (3.9), Experience (12.1) and Replacements (12.4)
        s["aufbau_einheiten"] = copy.deepcopy({**s["einheiten"], **s.get("reserve_einheiten", {})})
        s["pc_start"] = {k: c.get("pc") for k, c in s["karten"].items() if c.get("pc")}
        s["fm_start"] = copy.deepcopy(s.get("feuermissionen"))
        s["assets_start"] = copy.deepcopy(s.get("assets_pool", {}))
        s.setdefault("xp", [])
        s.setdefault("us_casualties_gesamt", 0)
    setup.check_new_game(s)  # review M5 (L348): validate before .aktuelle_partie is switched or anything is written
    if not test_run:
        (state.ROOT / ".aktuelle_partie").write_text(name, encoding="utf-8")
    (state.ROOT / name).mkdir(exist_ok=True)
    state.save_state(s, f"Game {name} created: {s['mission']}", None)
    print(briefing.briefing(s))
    if "optionen" in s:
        print("Open rules questions with chosen reading: fof.py options")


def segment_note(s, row_id):
    """Who acts in initiative segment 3.3.2a-c (or: skipped) [RULE 3.3.2 p.16]."""
    if not state.company(s):
        return ""
    k = s["kommandos"]
    if row_id == "3.3.2a":
        co = s["co_hq"]
        if co not in s["einheiten"]:
            return "skipped: CO HQ not on the board [RULE 3.3.2a p.16]"
        if k.get(co, {}).get("aktiviert"):
            return "skipped: CO HQ was activated in 3.3.1, no Initiative draw [RULE 3.3.2a p.16]"
        return f"{co} draws Initiative (modified; star number, not the helmet number) plus saved {k.get(co, {}).get('gespart', 0)} [RULE 3.3.2a p.16]"
    if row_id == "3.3.2b":
        n = [
            h
            for h, c in k.items()
            if h in s["einheiten"]
            and s["einheiten"][h].get("ebene") == "PLT"
            and not c["aktiviert"]
            and not c.get("fertig")
        ]
        return (
            (
                "draw Initiative (star number, not the helmet number), in any order you choose (one impulse after the other, hq <name>): "
                + ", ".join(n)
                + " [RULE 3.3.2b p.16 'Select a PLT HQ', K39]"
            )
            if n
            else "skipped: no non-activated PLT HQ on the board [RULE 3.3.2b p.16]"
        )
    if row_id == "3.3.2c":
        n = [
            f"{h} 1 + saved {c.get('gespart', 0)}"
            for h, c in k.items()
            if h in s["einheiten"]
            and s["einheiten"][h]["typ"] == "Staff"
            and not c["aktiviert"]
            and not c.get("fertig")
        ]
        return (
            (
                "1 Command each without draw, in any order you choose: "
                + "; ".join(n)
                + " [RULE 3.3.2c p.16 'Select a CO Staff', K39]"
            )
            if n
            else "done or skipped: no open non-activated CO Staff [RULE 3.3.2c p.16]"
        )
    if row_id == "3.3.2d":  # L212
        return "draw an Action card for General Initiative: small number in the star (not the helmet), unmodified, cannot be saved; fof.py gi <no> <star number> [RULE 3.3.2d p.16]"
    return ""


def _enter_3_3_1a(s, prot):
    if events.bn_leader(s):
        # [RULE 4.1.1 p.18/19] BN HQ 'on the map': highest-ranking Higher HQ leader receives 6 (night 4) Commands, cannot be saved
        bn = sorted(events.bn_leader(s), key=lambda x: 0 if x.startswith("Rgt") else 1)[0]
        s["kommandos"][bn].update(verfuegbar=rules.MAX_PER_IMPULSE[s["sicht"]], aktiviert=True, fertig=False)
        s["aktiver_hq"] = bn
        prot.append(
            f'BN HQ is on the board: {bn} receives {rules.MAX_PER_IMPULSE[s["sicht"]]} Commands (cannot be saved); activate {s["co_hq"]} only with communication (activate "{s["co_hq"]}"), then done [4.1.1 p.18/19]'
        )
    elif state.company(s) and s.get("bn_hq") == "off-map" and s.get("bn_nicht_verfuegbar") == s["zug"]:
        prot.append(
            f"Comm Trouble: BN HQ does not activate {s['co_hq']} this turn; {s['co_hq']} draws Initiative in 3.3.2a [Normandy M1 p.18, 4.1.1 p.19]"
        )
    elif state.company(s) and s.get("bn_hq") == "off-map":
        co = s["co_hq"]
        kc = s["kommandos"].get(co, {"aktiviert": False})
        ok, reason = comms.bn_link(s)
        if co not in s["einheiten"]:
            prot.append(
                f"{co} not in play: BN HQ activates no one; 3.3.2a is skipped; reconstitution of a CO HQ per 6.5.2 p.49/50 [3.3.1a p.15]"
            )
        elif kc["aktiviert"]:
            pass
        elif state.fire_team_side(state.unit(s, co)):
            prot.append(
                f"{co} is on its Fire Team side and cannot be activated; it draws Initiative in 3.3.2a [4.1.4 p.20]"
            )
        elif ok:
            kc["aktiviert"] = True
            prot.append(
                f"BN HQ (off-map) activates {co} ({reason}); flip Command marker {co} to Commands Available [3.3.1a p.15, 4.1.1 p.18]"
            )
        else:
            prot.append(
                f"BN HQ not available: {reason}; {co} is not activated and draws Initiative in 3.3.2a [4.1.1 p.19]"
            )


def _enter_3_3_1b(s, prot):
    if any(e["typ"] == "Runner" for e in s["einheiten"].values()):
        comms.deliver_runner(s, prot)


def _enter_enemy_check(s, prot):
    """3.4.2 / 3.2.2 (enemy.enemy_segments, L320): Cease Fire without target, open the Activity Checks."""
    event_seg = enemy.enemy_segments(s)[0]
    fire.enemy_cease_fire(s, prot)
    enemy.prepare_enemy_check(s, prot)
    if s.get("ereignis_erledigt") == [s["zug"], event_seg]:
        for n in s.get("ereignis_einheiten", []):
            if n in s["einheiten"]:
                s["einheiten"][n]["check_offen"] = False  # [RULE 3.4.1 p.16] no further check


def _enter_3_6(s, prot):
    if any(e.get("fahrzeug") or e.get("at_waffe") or e.get("panzerfaust") for e in s["einheiten"].values()):
        from . import vehicles  # L187

        vehicles.enter_3_6(s, prot)


def _enter_3_7_1(s, prot):
    flipped = False
    for kid, c in s["karten"].items():
        for x in list(c.get("extern", [])):
            if x["typ"] in ("Incoming", "AirStrike"):
                c["extern"].remove(x)
                prot.append(f"{kid}: remove {rules.VOF_NAME[x['typ']]} marker [3.7.1]")
                for pk in s.get("pakete", {}).values():
                    if not pk.get("einheit") and pk.get("im_spiel") and pk["name"] == x.get("quelle"):
                        pk["im_spiel"] = False
                        prot.append(f"Package '{pk['name']}' available again [8.3]")
        for x in c.get("extern", []):
            if x["typ"] == "Pending":
                x["typ"] = "Incoming"
                flipped = True
                prot.append(
                    f"{kid}: flip Pending Fire Mission to its active side (Incoming {x['wert']}); units there lose LOS out of the card [3.7.1, 5.4]"
                )
    if flipped:
        # L95: also fire THROUGH the card (5.4); once after all flips and removals (review LOW: was once per flip,
        # against a half-updated board)
        fire.cease_fire_on_los_loss(s, prot)
    fire.open_fire(s, prot)


def _enter_3_7_2(s, prot):
    open_reading = [k for k, c in s["karten"].items() if c.get("pc") and state.units_on(s, k, "US")]
    if any(c.get("pc") == "?" for c in s["karten"].values()):
        prot.append("Reveal PC markers with '?' on cards with friendly units before resolving [8.2.4, E39]")
    if open_reading:
        prot.append(
            "PC markers to resolve (alphabetically, equal letters by R#): "
            + ", ".join(f"{k} (PC {s['karten'][k]['pc']})" for k in open_reading)
            + " [8.2.4]"
        )
        for letter in sorted({s["karten"][k]["pc"] for k in open_reading if s["karten"][k]["pc"] != "?"}):
            same = [k for k in open_reading if s["karten"][k]["pc"] == letter]
            if len(same) > 1:  # L134 [RULE 8.2.4 p.62] 'resolve them in a random order'
                prot.append(
                    f"{len(same)} cards with PC {letter} ({', '.join(same)}): draw the order by R#, column {len(same)}, note it with fof.py note [8.2.4]"
                )
    else:
        prot.append("no PC markers with friendly units")


def _enter_3_7_3(s, prot):
    for n, e in s["einheiten"].items():
        if state.pinned(e) and fire.vof_against(s, e["karte"], e["seite"]) is None:
            e["status"].remove(rules.PINNED)
            prot.append(
                f"{n}: remove Pinned marker (no VOF on {e['karte']}); if the unit fires, its VOF becomes Basic again [3.7.3]"
            )


def _enter_3_7_4(s, prot):
    if any(enemy.is_sniper(e) for e in s["einheiten"].values()):
        enemy.choose_sniper_targets(s, prot)
    with fire.cached(s):  # read-only until the NCM rows and groups are recorded (review Effizienz)
        _open_combat_effects(s, prot)
    combat.ammo_3_7_4(s, prot)  # [RULE 7.18.4 p.61] ammo of the firing units
    if any(c.get("leitungen") for c in s["karten"].values()):
        comms.line_checks_3_7_4(s, prot)


def _open_combat_effects(s, prot):
    """3.7.4 entry: who takes Combat Effects, NCM rows frozen on entry, NCM groups (no board change in here)."""
    s["kampf_offen"] = [
        n
        for n, e in s["einheiten"].items()
        if not e.get("fahrzeug")  # L187 [RULE 10.5.3 p.72] VOF against vehicles is resolved in 3.6
        and (
            fire.vof_against(s, e["karte"], e["seite"], ignore_mines=True) is not None
            or e.get("grenade")
            or state.card(s, e["karte"]).get("grenade_miss")
            or e.get("mine_hit")
        )
    ]
    prot.append(
        "Combat Effects for: "
        + (", ".join(s["kampf_offen"]) if s["kampf_offen"] else "no one (no VOF)")
        + "; VOF, PDF and level stay frozen until 3.8 [3.7.4]"
    )
    # [RULE 3.7.4 p.17] 'do not update PDF or VOF markers until the Clean Up Phase': record NCM rows on entry
    s["kampf_ncm"] = {}
    for n in s["kampf_offen"]:
        try:
            s["kampf_ncm"][n] = [list(z) for z in combat.ncm_rows(s, n)]
        except rules.Violation:
            pass
    g = combat.ncm_groups(s)
    if g:
        prot.append(
            f"{len(g)} NCM group(s) on {len({x[0] for x in g})} card(s); next group: fof.py ncm next (numbered list, cards to draw) [V18, L155]"
        )


# review Struktur 7: entry hook per segment; the enemy check segment (3.4.2 or 3.2.2) is added from the SOP
ENTER_HOOKS = {
    "3.3.1b": _enter_3_3_1b,
    "3.5.1": lambda s, prot: check_capture(s, prot),
    "3.5.2": lambda s, prot: check_retreat(s, prot),
    "3.6": _enter_3_6,
    "3.7.1": _enter_3_7_1,
    "3.7.2": _enter_3_7_2,
    "3.7.3": _enter_3_7_3,
    "3.7.4": _enter_3_7_4,
}


def enter_segment(s, new, prot):
    """Entry actions of the new segment (part of cmd_phase)."""
    if new == "3.3.1a":
        _enter_3_3_1a(s, prot)  # before the flank check, as always
    if state.is_v4(s) and s.get("_phase_alt") == "3.3.2d":
        events.check_event_flank(s, prot)
    hook = {**ENTER_HOOKS, enemy.enemy_segments(s)[1]: _enter_enemy_check}.get(new)
    if hook:
        hook(s, prot)


# ---- leaving a segment ('phase next'): checks in this order; each raises a Violation if the segment is not finished


def _leave_impulse_done(s, prot):
    if s["phase"] in rules.PLT_IMPULSES | {"3.3.2d", "3.3.1b", "3.3.2a", "3.3.2c", "3.3.1a"} and s.get("aktiver_hq"):
        raise rules.Violation(f"{s['aktiver_hq']} has not yet ended the impulse with 'done'")


def _leave_mines(s, prot):
    contact.mine_lock(s)


def _leave_capture(s, prot):
    open_caps = [n for n in s.get("capture_offen", []) if n in s["einheiten"]]
    if s["phase"] == "3.5.1" and open_caps:
        raise rules.Violation(f'Capture still open: fof.py capture "{open_caps[0]}" <guard> [3.5.1, 8.15] (L208)')
    s.pop("capture_offen", None)


def _leave_reattempt(s, prot):
    if s.get("reattempt_setup"):
        raise rules.Violation("Reattempt preparation in progress: first fof.py reattempt done [3.9 p.18]")


def _leave_setup(s, prot):
    if s["zug"] == 1 and not s.get("aufstellung_fertig"):
        fa = setup.check_setup_v4(s)
        if fa:
            raise rules.Violation("Still open before turn 1: " + "; ".join(fa))
        for h in setup.setup_notes_v4(s):
            prot.append("Note (lapses from now on): " + h)
        if s.get("patrouille_mission"):
            campaign.patrol_reserve(s, prot)


def _leave_event_draw(s, prot):
    if s.get("ereignistabellen") and s["zug"] >= 2 and s.get("ereignis_erledigt") != [s["zug"], s["phase"]]:
        raise rules.Violation(
            f"First the Higher HQ Event of this segment: draw an Action card, fof.py event <cardno> yes <R#> | no [RULE {'3.1 S.15' if s['phase'] == '3.1' else '3.4.1 S.16'}]"
        )


def _leave_ammo_resupply(s, prot):
    if s.get("ereignis_munition") == s["zug"]:
        raise rules.Violation("Ammo Resupply not yet placed: fof.py ammo depot <card> <type> 4 [Normandy M1 p.18]")


def _leave_rally(s, prot):
    if s.get("rally_offen"):
        raise rules.Violation(
            "Rally event open for: " + ", ".join(s["rally_offen"]) + " (enemyaction <n> Rally --success=yes|no)"
        )


def _leave_snipers_lines(s, prot):
    if s.get("sniper_offen") or s.get("leitung_checks"):
        raise rules.Violation(
            "Open: "
            + ", ".join(
                [f"Sniper target {n}" for n in s.get("sniper_offen", {})]
                + [f"phone line {k}" for k in s.get("leitung_checks", {})]
            )
        )


def _leave_3_3_1c(s, prot):
    open_reading = [
        n
        for n, k in s["kommandos"].items()
        if k["aktiviert"] and not k["fertig"] and s["einheiten"].get(n, {}).get("ebene") != "CO"
    ]
    if open_reading:
        raise rules.Violation(f"Activated HQs without impulse: {', '.join(open_reading)} [RULE 3.3.1c p.15]")


def _leave_3_3_1b(s, prot):
    if not state.company(s):
        return
    co, kc = s["co_hq"], s["kommandos"].get(s["co_hq"], {})
    if kc.get("aktiviert") and not kc.get("fertig"):
        raise rules.Violation(
            f"{co} is activated and must draw an Action card in the CO HQ Impulse (hq, card, done) [RULE 3.3.1b p.15]"
        )


def _leave_3_3_2a(s, prot):
    if not state.company(s):
        return
    co, kc = s["co_hq"], s["kommandos"].get(s["co_hq"], {})
    if co in s["einheiten"] and not kc.get("aktiviert") and not kc.get("fertig"):
        raise rules.Violation(
            f"{co} was not activated and now draws Initiative Commands (hq, card <no> <star number>, done) [RULE 3.3.2a p.16]"
        )


def _leave_3_3_2b(s, prot):
    if not state.company(s):
        return
    open_reading = [
        n
        for n, k in s["kommandos"].items()
        if n in s["einheiten"] and s["einheiten"][n].get("ebene") == "PLT" and not k["aktiviert"] and not k["fertig"]
    ]
    if open_reading:
        raise rules.Violation(f"Non-activated PLT HQs draw Initiative: {', '.join(open_reading)} [RULE 3.3.2b p.16]")


def _leave_3_6(s, prot):
    if s.get("at36"):
        from . import vehicles  # L187

        vehicles.leave_3_6(s, prot)


def _leave_3_7_2(s, prot):
    open_reading = [k for k, c in s["karten"].items() if c.get("pc") and state.units_on(s, k, "US")]
    if open_reading:
        raise rules.Violation(
            f"PC markers with friendly units not yet resolved: {', '.join(open_reading)} [RULE 3.7.2 p.17]"
        )


def _leave_enemy_check(s, prot):
    if any(e["seite"] == "Feind" and e.get("check_offen") for e in s["einheiten"].values()):
        raise rules.Violation(
            "Enemy Activity Check not yet completed for all enemies (enemycheck / enemyaction) [RULE 3.4.2 p.16]"
        )


def _leave_combat_effects(s, prot):
    if s.get("kampf_offen"):
        raise rules.Violation(
            "Combat Effects still open for: " + ", ".join(s["kampf_offen"]) + " (ncm / hit) [RULE 3.7.4 p.17]"
        )


def _leave_fire_targets(s, prot):
    off = [n for n, e in s["einheiten"].items() if e.get("ziel_offen")]
    if off:
        raise rules.Violation("Set open fire targets first with 'fire': " + ", ".join(off))


# review Struktur 7: (segments the check applies to, v4 only, check) in the order of the former if-chain.
# Segments: None = every segment; a callable gives the segment from the SOP (first segment, enemy segments, L320).
LEAVE_CHECKS = (
    (None, False, _leave_impulse_done),
    (None, True, _leave_mines),
    (None, True, _leave_capture),  # 3.5.1 check, then capture_offen lapses in every segment
    (None, True, _leave_reattempt),
    (lambda s: {state.sop(s)[0][0]}, True, _leave_setup),
    ({"3.1", "3.4.1", "3.2.1"}, True, _leave_event_draw),
    ({"3.1"}, True, _leave_ammo_resupply),
    (lambda s: {enemy.enemy_segments(s)[0]}, True, _leave_rally),
    ({"3.7.4"}, True, _leave_snipers_lines),
    ({"3.3.1c"}, False, _leave_3_3_1c),
    ({"3.3.1b"}, False, _leave_3_3_1b),
    ({"3.3.2a"}, False, _leave_3_3_2a),
    ({"3.3.2b"}, False, _leave_3_3_2b),
    ({"3.6"}, False, _leave_3_6),
    ({"3.7.2"}, False, _leave_3_7_2),
    (lambda s: {enemy.enemy_segments(s)[1]}, False, _leave_enemy_check),
    ({"3.7.4"}, False, _leave_combat_effects),
    (None, False, _leave_fire_targets),
)


def leave_segment(s, prot):
    """Run every LEAVE_CHECKS entry that applies to the current segment."""
    for segments, v4_only, check in LEAVE_CHECKS:
        if v4_only and not state.is_v4(s):
            continue
        if segments is not None and s["phase"] not in (segments(s) if callable(segments) else segments):
            continue
        check(s, prot)


def check_next_phase(s, args, ids, prot):
    """The segment after 'phase next' (after the leave checks) or the named segment (corrections)."""
    if args[0] == "weiter":
        i = ids.index(s["phase"])
        leave_segment(s, prot)
        if i + 1 >= len(ids):
            raise rules.Violation("Last phase reached; use 'endturn' [RULE 3.8 p.17]")
        new = ids[i + 1]
        if new in rules.FROM_TURN_2 and s["zug"] == 1:
            prot.append(f"{new} does not apply in turn 1, skipped")
            new = ids[i + 2]
        elif new in rules.FROM_TURN_2 and s.get("keine_ereignisse"):
            prot.append(f"{new} does not apply, no events in this mission (FM1 p.38/p.40), skipped")
            new = ids[i + 2]
        if s["phase"] == "3.1" and s["zug"] == 1:
            s["aufstellung_fertig"] = True
    else:
        if args[0] not in ids:
            raise rules.Violation(f"Phase {args[0]} not in the sequence of play: {', '.join(ids)}")
        new = args[0]
        if ids.index(new) < ids.index(s["phase"]):
            prot.append("WARNING: jumping back in the sequence of play, for corrections only")
    return new


def cmd_phase(s, args):
    ids = [p for p, _ in state.sop(s)]
    if args and s["phase"] == "3.5.2":
        open_ = [n for n, e in s["einheiten"].items() if must_retreat(s, e)]
        if open_:
            raise rules.Violation(
                f"3.5.2 not finished: retreat first {', '.join(open_)} (fof.py retreat <unit> [<card>]) [RULE 3.5.2 p.16] (L123)"
            )
    if not args:
        i = ids.index(s["phase"])
        print(f"Turn {s['zug']}  Phase {s['phase']} {state.phase_name(s)}")
        if i + 1 < len(ids):
            print(f"Next: {ids[i + 1]} {state.phase_name(s, ids[i + 1])}")
            h = segment_note(s, ids[i + 1])
            if h:
                print(f"  {h}")
        h = segment_note(s, s["phase"])
        if h:
            print(f"Now: {h}")
        return
    prot = []
    new = check_next_phase(s, args, ids, prot)
    s["_phase_alt"] = s["phase"]
    s["phase"] = new
    if segment_note(s, new):
        prot.append(segment_note(s, new))
    s["aktiver_hq"] = None
    s["impuls_aktionen"] = {}
    enter_segment(s, new, prot)
    s.pop("_phase_alt", None)
    ak = fire.update_activity(s)
    if ak:
        prot.append(ak)
    state.save_state(s, f"Phase {new} {state.phase_name(s)}" + ("; " + "; ".join(prot) if prot else ""), None)
    print(f"Phase {new} {state.phase_name(s)}")
    briefing.print_board(prot, s)


def check_capture(s, prot):
    """3.5.1 / 8.15: enemy Casualties automatically captured (8.15.1); Litter/Paralyzed alone with opponents: note."""
    for kid, c in s["karten"].items():
        if (
            c.get("casualties_feind")
            and not state.units_on(s, kid, "Feind")
            and (not c.get("pc") or state.units_on(s, kid, "US"))
        ):
            s["gefangene"] = s.get("gefangene", 0) + c["casualties_feind"]
            prot.append(f"{kid}: {c['casualties_feind']} enemy Casualties captured, remove marker [8.15.1]")
            campaign.book_xp(
                s,
                c["casualties_feind"] * (campaign.xp_table(s, "feind_casualty_step") or 1),
                f"{c['casualties_feind']} enemy Casualties captured ({kid})",
                prot,
            )
            c["casualties_feind"] = 0
        for n in state.units_on(s, kid):
            e = s["einheiten"][n]
            # K33: "alone" also when the other same-side units on the card are only Paralyzed/Litter Teams
            if e["typ"] in ("Paralyzed Team", "Litter Team") and not [
                m
                for m in state.units_on(s, kid, e["seite"])
                if m != n and s["einheiten"][m]["typ"] not in ("Paralyzed Team", "Litter Team")
            ]:
                opp = [
                    m
                    for m in state.units_on(s, kid, state.opponent_of_side(e["seite"]))
                    if can_capture(s["einheiten"][m])
                ]
                if opp:
                    if state.is_v4(s):
                        s.setdefault("capture_offen", []).append(n)  # L208: phase next waits for fof.py capture
                        prot.append(
                            f'{kid}: {n} ({e["typ"]}, {e["seite"]}) is captured (both sides take prisoners, Normandy p.13): fof.py capture "{n}" <guard> [3.5.1, 8.15]'
                        )
                    else:
                        prot.append(
                            f"{kid}: {n} ({e['typ']}, {e['seite']}) is captured: one guard step with VOF value goes along (both Removed from Play); enemies take no prisoners, US team then becomes a Casualty. Afterwards fof.py enemy/order to correct [8.15]"
                        )


def can_capture(x):
    """L199; one predicate for captors and the guard step: combat.can_capture (review LOW)."""
    return combat.can_capture(x)


def must_retreat(s, e):
    """[RULE 3.5.2 p.16] Unpinned, non-Exposed Paralyzed Team under VOF, or such a Litter Team with a Casualty (carried or on the card)."""
    if state.pinned(e) or rules.EXPOSED in e["status"] or not fire.vof_against(s, e["karte"], e["seite"]):
        return False
    if e["typ"] == "Paralyzed Team":
        return True
    if e["typ"] == "Litter Team":
        c = state.card(s, e["karte"])
        return bool(e.get("traegt_casualties") or c.get("casualties" if e["seite"] == "US" else "casualties_feind"))
    return False


def retreat_cards(s, e):
    """[RULE 3.5.2 p.16] One card towards the own edge: first cards without VOF, then the best C&C value. Returns the ties."""
    cur = state.card(s, e["karte"])
    step = -1 if e["seite"] == "US" else 1
    cands = [
        k
        for k, c in s["karten"].items()
        if c["reihe"] == cur["reihe"] + step
        and geometry.adjacent(s, e["karte"], k)
        and not (e["seite"] == "US" and c.get("ausserhalb"))
    ]
    if not cands:
        return []
    free = [k for k in cands if not fire.vof_against(s, k, e["seite"])] or cands
    best = max(state.card(s, k).get("cc", 0) for k in free)
    return sorted(k for k in free if state.card(s, k).get("cc", 0) == best)


def cmd_retreat(s, args):
    """3.5.2: carry out the retreat of a Paralyzed or Litter Team (L110)."""
    if s["phase"] != "3.5.2":
        raise rules.Violation(f"Retreat only in 3.5.2, currently {s['phase']} [RULE 3.5.2 p.16]")
    rules.need(args, 1, 'retreat "<unit>" [<card>]')
    n = args[0]
    e = state.unit(s, n)
    if not must_retreat(s, e):
        raise rules.Violation(
            f"{n} does not retreat (only unpinned, non-Exposed Paralyzed/Litter Teams under VOF) [RULE 3.5.2 p.16]"
        )
    best = retreat_cards(s, e)
    if not best:
        raise rules.Violation(
            f"{n}: no card towards the own edge; fof.py correct to handle it by hand [RULE 3.5.2 p.16]"
        )
    target = args[1] if len(args) > 1 else None
    if target is None:
        if len(best) > 1:
            raise rules.Violation(
                f'{n}: tie between {", ".join(best)} (no VOF, same C&C): random choice by R#, then fof.py retreat "{n}" <card> [RULE 3.5.2 p.16]'
            )
        target = best[0]
    if target not in best:
        raise rules.Violation(
            f"{n} must retreat to {' or '.join(best)} (priority: no VOF, then best C&C) [RULE 3.5.2 p.16]"
        )
    prot = []
    origin = e["karte"]
    if e["typ"] == "Litter Team" and not e.get("traegt_casualties"):
        c = state.card(s, origin)
        key = "casualties" if e["seite"] == "US" else "casualties_feind"
        c[key] -= 1
        e["traegt_casualties"] = 1
        prot.append(f"{n} picks up a Casualty on {origin} (Casualty marker goes with it) [3.5.2 p.16]")
    e["karte"], e["bereich"] = target, "offen"
    commands.mark(e, rules.EXPOSED)
    prot.append(f"{n} retreats from {origin} to {target} (open), Exposed [3.5.2 p.16]")
    fire.fire_after_move(s, n, prot, origin=origin)
    state.save_state(s, f"Retreat {n}: " + "; ".join(prot), "3.5.2 p.16")
    briefing.print_board(prot, s)


def check_retreat(s, prot):
    """3.5.2: Paralyzed Teams (unpinned, not Exposed) and Litter Teams with a Casualty under VOF retreat one card."""
    gone = []
    for n, e in s["einheiten"].items():
        if e["typ"] == "Paralyzed Team" and must_retreat(s, e):
            if e["seite"] == "Feind" and state.card(s, e["karte"])["reihe"] >= state.top_row(s):
                # [RULE 3.5.2 p.16] "Enemy units who retreat from a card at their side's edge of the map will retreat off the map. Remove them from play. Do not extend the map."
                gone.append(n)
                continue
            prot.append(
                f'{n} ({e["seite"]}) must retreat one card (priority: no VOF, then best cover, random on a tie), Exposed [3.5.2]: fof.py retreat "{n}" [<card>]'
            )
        if must_retreat(s, e) and e["typ"] == "Litter Team":
            prot.append(
                f'{n} ({e["seite"]}) retreats one card with a Casualty, Exposed [3.5.2]: fof.py retreat "{n}" [<card>]'
            )
    for n in gone:  # review M39: one removal path (removed_from_play, package back to the pool, markers)
        combat.remove_from_play(
            s, n, prot, "(enemy) retreats off-map from the map edge, counter back to the pool [3.5.2]"
        )


def end_turn_v4(s, prot):
    """Clean Up (3.8) for the v4 elements: mines, snipers, ammo, G! PDF, Place-VOF-No, events, Checking Up, counterattack."""
    for n, e in list(s["einheiten"].items()):
        if e.pop("mine_hit", None):
            prot.append(f"{n}: remove from the Mine marker [3.8 p.17]")
        if e.get("munition_leer"):
            combat.out_of_ammo(s, n, e, prot)
        if e.get("nur_pdf"):
            fire.cease_fire(e)
            prot.append(f"{n}: remove the Grenade Attack PDF [7.3.2 p.53]")
        if e.pop("kein_feuer_bis_clean_up", None):
            prot.append(f"{n} may now open fire (Place PDF/VOF No) [8.3 p.63]")
        if e.get("bis_zug") == s["zug"] and e.get("ebene") == "BN":
            del s["einheiten"][
                n
            ]  # the BN HQ goes back off-map (Checking Up can bring it again), not a removal from play
            s["kommandos"].pop(n, None)
            prot.append(f"{n} (Checking Up) leaves the board; BN HQ off-map again [Normandy M1 p.18]")
    for kid, c in s["karten"].items():
        for x in c.get("extern", []):
            if x["typ"] == "Mines" and x.get("aktiv"):
                x["aktiv"] = False
                prot.append(f"{kid}: Mine marker back to the Draw 3 side [3.8 p.17]")
        if c.pop("pyro", None):
            prot.append(f"{kid}: remove pyrotechnics [3.8 p.17]")
    for k in (
        "sniper_ziele",
        "sniper_offen",
        "ereignis_einheiten",
        "rally_offen",
        "leitung_checks",
        "ereignis_pflicht",
        "ereignis_flanke",
        "fm_gesperrt",
        "bn_nicht_verfuegbar",
        "ereignis_munition",
    ):
        s.pop(k, None)
    ga = s.get("gegenangriff")
    if ga and ga.get("bis_zug") == s["zug"]:
        s["feind_taktik"] = ga.get("taktik_vorher") or s.get("feind_taktik")
        s.pop("gegenangriff")
        prot.append(f"Counterattack ends: enemy tactic back to {s['feind_taktik']} [Normandy M1 MSR 1 p.19]")


def cmd_end_turn(s, args):
    if s["phase"] != "3.8":
        raise rules.Violation(f"End of turn only in phase 3.8, currently {s['phase']} [RULE 3.8 p.17]")
    prot = []
    if s.pop("granate_antworten", None):  # L321 (review H9): free responses lapse with the turn [7.10.5]
        prot.append("Open Grenade responses lapse at the end of the turn [7.10.5]")
    clean_up_vehicles(s, prot)
    clean_up_units(s, prot)
    clean_up_cards(s, prot)
    for n, e in s["einheiten"].items():
        if e.get("indirekt"):
            e.pop("indirekt")
    if s.get("wetter_nur_zug"):
        s["wetter"] = 0
        s.pop("wetter_nur_zug")
        geometry.update_visibility(s)
        prot.append("Remove Rain marker, weather back to +0 [Event It's Raining]")
    if state.is_v4(s):
        end_turn_v4(s, prot)
    fire.cease_fire_on_los_loss(s, prot)
    fire.enemy_cease_fire(s, prot)
    # [RULE 3.8 p.17] 'Adjust VOF, PDF and Activity Levels resulting from the Combat Effects Segment and Clean Up';
    # e.g. mortars after removing Exposed [FM1 p.44]
    fire.open_fire(s, prot)
    reset_commands(s, prot)
    if end_of_mission(s, prot):
        return
    s["zug"] += 1
    s["phase"] = state.sop(s)[0][0]
    ak = fire.update_activity(s)
    if ak:
        prot.append(ak)
    state.save_state(s, f"Clean Up; turn {s['zug']} begins; " + "; ".join(prot), "3.8 p.17")
    print(f"Turn {s['zug']} begins with phase {s['phase']} {state.phase_name(s)}.")
    briefing.print_board(prot, s)


def clean_up_vehicles(s, prot):
    """3.8: vehicle markers and wrecks (10.4), only when vehicles, AT36 or wrecks are in the game."""
    if (
        s.get("at36")
        or any(e.get("fahrzeug") for e in s["einheiten"].values())
        or any(x.get("wrack") for c in s["karten"].values() for x in c.get("extern", []))
    ):
        from . import vehicles  # L187

        vehicles.clean_up(s, prot)


def clean_up_units(s, prot):
    """3.8: Exposed, Concentrated Fire, Grenade VOF and Critical Hit markers off the units."""
    for n, e in s["einheiten"].items():
        for m in (rules.EXPOSED, "Moved", "Fired"):
            if m in e["status"]:
                e["status"].remove(m)
                prot.append(f"{n}: remove {m}")
        if e.get("cf"):
            e["cf"] = 0
            prot.append(f"{n}: remove Concentrated Fire")
        if e.get("grenade"):
            e["grenade"] = []
            prot.append(f"{n}: remove Grenade VOF")
        if e.pop("grenade_critical", None):
            prot.append(f"{n}: remove Critical Hit Grenade marker [7.10.3]")
        if e.pop("cf_critical", None):
            prot.append(f"{n}: remove Critical Hit Concentrated Fire marker [7.11.4]")  # L154
        e.pop("konzentriert", None)


def clean_up_cards(s, prot):
    """3.8: Illumination, Grenade Miss, Smoke and Indirect Lay off the cards; CCP evacuation; PC markers (defensive)."""
    for kid, c in s["karten"].items():
        if c.get("illum"):
            c["illum"] = []
            prot.append(f"{kid}: remove Illumination marker [RULE 9.2 p.70]")
        if c.get("grenade_miss"):
            c["grenade_miss"] = False
            prot.append(f"{kid}: remove Grenade Miss")
        for x in list(c.get("extern", [])):
            if x["typ"] == "Smoke":
                c["extern"].remove(x)
                prot.append(f"{kid}: remove Smoke/Pyro")
            if x["typ"] == "Incoming":
                prot.append(f"{kid}: Incoming stays until 3.7.1 of the next turn (blocks LOS)")
            if x["typ"] == "Indirect":
                c["extern"].remove(x)
                prot.append(f"{kid}: remove Heavy Weapons VOF (Indirect Lay from {x.get('quelle')}) [RULE 7.3.2 p.53]")
        if s.get("ccp") == kid and c.get("casualties"):
            s["evakuiert"] = s.get("evakuiert", 0) + c["casualties"]
            prot.append(
                f"{kid}: {c['casualties']} casualties evacuated at the CCP, markers to the Holding Box [RULE 3.8 p.17, 5.1.7 p.34]"
            )
            campaign.book_xp(
                s,
                c["casualties"] * (campaign.xp_table(s, "evakuiert") or 1),
                f"{c['casualties']} casualties evacuated ({kid})",
                prot,
            )
            c["casualties"] = 0
        if s["typ"] == "defensiv" and c.get("pc") and not state.units_on(s, kid, "US"):
            c["pc"] = None
            prot.append(f"{kid}: unresolved PC marker removed (defensive mission)")


def reset_commands(s, prot):
    """3.8: Command markers and the per-turn order bookkeeping back to the start of a turn [4.1.1]."""
    for n, k in s["kommandos"].items():
        k["aktiviert"], k["fertig"], k["verfuegbar"] = False, False, 0
        k.pop("gezogen", None)
    s["impuls_ausgegeben"] = {}
    s["kampf_offen"] = []
    s["letzter_versuch"] = None
    s.pop("kampf_ncm", None)
    s.pop("exhort_frei", None)
    prot.append(
        "Command markers from the Saved zone to the Tracking zone (value stays), Zero Commands marker to the Holding Box [4.1.1]"
    )
    prot.append(
        "Check VOF markers on the board against the briefing: pinned shooters 'All Pinned' +2, unpinned back to Basic VOF [3.8, 4.2.5]"
    )


def end_of_mission(s, prot):
    """Last turn played: save the mission end and return True (v4: campaign mission end, 3.9)."""
    if s["zug"] >= s["max_zuege"] and state.is_v4(s):
        campaign.mission_end_v4(s, prot)
        state.save_state(s, f"Turn {s['zug']} ended: end of mission reached; " + "; ".join(prot), "3.8 p.17, 3.9 p.17")
        print("End of mission: last turn played.")
        briefing.print_board(prot, s)
        return True
    if s["zug"] >= s["max_zuege"]:
        if s.get("ziel_regeln"):
            prot.append("Objective status: " + briefing.objective_status(s))
            if "optionen" in s:
                prot.append(
                    (
                        "Reattempt per 3.9 provided for by option U9"
                        if state.option(s, "U9_reattempt")
                        else "no Reattempt (FM1 names none)"
                    )
                    + state.open_reading(s, "U9_reattempt")
                    + " [RULE 3.9 p.17]"
                )
        state.save_state(s, f"Turn {s['zug']} ended: end of mission reached; " + "; ".join(prot), "3.8 p.17")
        print("End of mission: last turn played.")
        briefing.print_board(prot, s)
        return True
    return False
