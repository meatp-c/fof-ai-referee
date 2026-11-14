"""Sequence of play: new game, phase changes, clean up, capture and retreat (3.x)."""

import copy
import json
import os
import pathlib
import sys

from . import (
    briefing,
    campaign,
    combat,
    commands,
    comms,
    contact,
    enemy,
    events,
    fire,
    geometry,
    grenades,
    migrate,
    rules,
    setup,
    state,
)


def cmd_new(args):
    if not args:
        sys.exit("fof.py new <setup.json> [game]")

    try:
        setup_data = migrate.state(json.loads(pathlib.Path(args[0]).read_text(encoding="utf-8")))
    except ValueError as err:  # a damaged setup file is a Violation, not a traceback
        raise rules.Violation(f"{args[0]} is not valid JSON ({err})") from None
    missing = [k for k in ("units", "cards") if not isinstance(setup_data, dict) or k not in setup_data]
    if missing:
        raise rules.Violation(f"{args[0]} is not a setup file: missing {', '.join(missing)}")
    name = args[1] if len(args) > 1 else state.DEFAULT_GAME
    env_game = migrate.env("FOF_GAME", os.environ)
    test_run = bool(env_game)
    if test_run:
        name = env_game  # test run or step.py: .current_game stays unchanged
    for k in [k for k in setup_data if k.startswith("_")]:
        setup_data.pop(k)  # comment fields of the setup do not go into the game state
    s = copy.deepcopy(setup_data)
    for k, v in {
        "turn": 1,
        "phase": state.sop(s)[0][0],
        "active_hq": None,
        "impulse_actions": {},
        "impulse_spent": {},
        "protocol": [],
        "commands": {},
        "removed_from_play": [],
        "combat_open": [],
    }.items():
        s.setdefault(k, v)
    for n, e in s["units"].items():
        e.setdefault("status", [])
        e.setdefault("side", "US")
        e.setdefault("area", "open")
        e.setdefault("target", None)
        if state.is_hq(e):
            s["commands"].setdefault(n, {"available": 0, "saved": 0, "activated": False, "done": False})
    for k in s["cards"].values():
        k.setdefault("cover", [])
        k.setdefault("external", [])
    if s.get("fm_values"):
        s.setdefault("target_marker", {})
    if state.is_campaign(s):
        # campaign: record initial state for Reattempt (3.9), Experience (12.1) and Replacements (12.4)
        s["setup_units"] = copy.deepcopy({**s["units"], **s.get("reserve_units", {})})
        s["pc_start"] = {k: c.get("pc") for k, c in s["cards"].items() if c.get("pc")}
        s["fm_start"] = copy.deepcopy(s.get("fire_missions"))
        s["assets_start"] = copy.deepcopy(s.get("assets_pool", {}))
        s.setdefault("xp", [])
        s.setdefault("us_casualties_total", 0)
        campaign.apply_attempt_plan(s, [])  # turns, visibility and enemy values of attempt 1
    setup.check_new_game(s)  # validate before .current_game is switched or anything is written
    # create the folder (with parents) first and switch .current_game back if saving fails, so a
    # failed 'new' never leaves the pointer on a folder without a game
    (state.ROOT / name).mkdir(parents=True, exist_ok=True)
    pointer = state.ROOT / state.POINTER
    legacy = migrate.path(state.ROOT, state.POINTER)
    if legacy != pointer:
        legacy.rename(pointer)  # the pointer file of an earlier release gets the English name
    old_pointer = pointer.read_text(encoding="utf-8") if pointer.exists() else None
    if not test_run:
        pointer.write_text(name, encoding="utf-8")
    try:
        state.save_state(s, f"Game {name} created: {s['mission']}", None)
    except BaseException:
        if not test_run:
            if old_pointer is None:
                pointer.unlink(missing_ok=True)
            else:
                pointer.write_text(old_pointer, encoding="utf-8")
        raise
    print(briefing.briefing(s))
    if "options" in s:
        print("Open rules questions with chosen reading: fof.py options")


def segment_note(s, row_id):
    """Who acts in initiative segment 3.3.2a-c (or: skipped) [RULE 3.3.2 p.16]."""
    if not state.company(s):
        return ""
    k = s["commands"]
    if row_id == "3.3.2a":
        co = s["co_hq"]
        if co not in s["units"]:
            return "skipped: CO HQ not on the board [RULE 3.3.2a p.16]"
        if k.get(co, {}).get("activated"):
            return "skipped: CO HQ was activated in 3.3.1, no Initiative draw [RULE 3.3.2a p.16]"
        return f"{co} draws Initiative (modified; star number, not the helmet number) plus saved {k.get(co, {}).get('saved', 0)} [RULE 3.3.2a p.16]"
    if row_id == "3.3.2b":
        n = [
            h
            for h, c in k.items()
            if h in s["units"] and s["units"][h].get("level") == "PLT" and not c["activated"] and not c.get("done")
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
            f"{h} 1 + saved {c.get('saved', 0)}"
            for h, c in k.items()
            if h in s["units"] and s["units"][h]["type"] == "Staff" and not c["activated"] and not c.get("done")
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
    if row_id == "3.3.2d":
        return "draw an Action card for General Initiative: small number in the star (not the helmet), unmodified, cannot be saved; fof.py gi <no> <star number> [RULE 3.3.2d p.16]"
    return ""


def _enter_3_3_1a(s, prot):
    if events.bn_leader(s):
        # [RULE 4.1.1 p.18/19] BN HQ 'on the map': highest-ranking Higher HQ leader receives 6 (night 4) Commands, cannot be saved
        bn = sorted(events.bn_leader(s), key=lambda x: 0 if x.startswith("Rgt") else 1)[0]
        s["commands"][bn].update(available=rules.MAX_PER_IMPULSE[s["sight"]], activated=True, done=False)
        s["active_hq"] = bn
        prot.append(
            f'BN HQ is on the board: {bn} receives {rules.MAX_PER_IMPULSE[s["sight"]]} Commands (cannot be saved); activate {s["co_hq"]} only with communication (activate "{s["co_hq"]}"), then done [4.1.1 p.18/19]'
        )
    elif state.company(s) and s.get("bn_reconstituting") == s["turn"]:
        prot.append(
            f"The BN HQ is being reconstituted and does not activate {s['co_hq']} this turn; {s['co_hq']} draws Initiative in 3.3.2a [6.5.2 p.50, 4.1.1 p.19]"
        )
    elif state.company(s) and s.get("bn_hq") == "off-map" and s.get("bn_unavailable") == s["turn"]:
        prot.append(
            f"Comm Trouble: BN HQ does not activate {s['co_hq']} this turn; {s['co_hq']} draws Initiative in 3.3.2a [Normandy M1 p.18, 4.1.1 p.19]"
        )
    elif state.company(s) and s.get("bn_hq") == "off-map":
        co = s["co_hq"]
        co_record = s["commands"].get(co, {"activated": False})
        ok, reason = comms.bn_link(s)
        if co not in s["units"]:
            prot.append(
                f"{co} not in play: BN HQ activates no one; 3.3.2a is skipped; reconstitution of a CO HQ per 6.5.2 p.49/50 [3.3.1a p.15]"
            )
        elif co_record["activated"]:
            pass
        elif state.fire_team_side(state.unit(s, co)):
            prot.append(
                f"{co} is on its Fire Team side and cannot be activated; it draws Initiative in 3.3.2a [4.1.4 p.20]"
            )
        elif ok:
            co_record["activated"] = True
            prot.append(
                f"BN HQ (off-map) activates {co} ({reason}); flip Command marker {co} to Commands Available [3.3.1a p.15, 4.1.1 p.18]"
            )
        else:
            prot.append(
                f"BN HQ not available: {reason}; {co} is not activated and draws Initiative in 3.3.2a [4.1.1 p.19]"
            )


def _enter_3_3_1b(s, prot):
    if any(e["type"] == "Runner" for e in s["units"].values()):
        comms.deliver_runner(s, prot)


def _enter_enemy_check(s, prot):
    """3.4.2 / 3.2.2 (enemy.enemy_segments): Cease Fire without target, open the Activity Checks."""
    event_seg = enemy.enemy_segments(s)[0]
    fire.enemy_cease_fire(s, prot)
    enemy.prepare_enemy_check(s, prot)
    if s.get("events_done") == [s["turn"], event_seg]:
        for n in s.get("event_units", []):
            if n in s["units"]:
                s["units"][n]["check_open"] = False  # [RULE 3.4.1 p.16] no further check


def _enter_3_6(s, prot):
    if any(e.get("vehicle") or e.get("at_weapon") or e.get("panzerfaust") for e in s["units"].values()):
        from . import vehicles

        vehicles.enter_3_6(s, prot)


def _enter_3_7_1(s, prot):
    changed = False  # a Pending flipped or an Incoming/AirStrike removed: LOS through and out of cards changes
    for card_id, c in s["cards"].items():
        for x in list(c.get("external", [])):
            if x["type"] in ("Incoming", "AirStrike"):
                c["external"].remove(x)
                changed = True  # units under the lifted marker get their old target back
                prot.append(f"{card_id}: remove {rules.VOF_NAME[x['type']]} marker [3.7.1]")
                for pk in s.get("packages", {}).values():
                    if not pk.get("unit") and pk.get("in_play") and pk["name"] == x.get("source"):
                        pk["in_play"] = False
                        prot.append(f"Package '{pk['name']}' available again [8.3]")
        for x in c.get("external", []):
            if x["type"] == "Pending":
                x["type"] = "Incoming"
                changed = True
                prot.append(
                    f"{card_id}: flip Pending Fire Mission to its active side (Incoming {x['value']}); units there lose LOS out of the card [3.7.1, 5.4]"
                )
    if changed:
        # also fire THROUGH the card (5.4); once after all flips and removals (was once per flip,
        # against a half-updated board); the removal of a marker counts too
        fire.cease_fire_on_los_loss(s, prot)
    fire.open_fire(s, prot)


def _enter_3_7_2(s, prot):
    # [RULE 8.2.4 p.62] listed alphabetically by PC letter (A before B before C), card number only within a letter
    open_reading = sorted(
        (k for k, c in s["cards"].items() if c.get("pc") and state.units_on(s, k, "US")),
        key=lambda k: (str(s["cards"][k]["pc"]), k),
    )
    if any(c.get("pc") == "?" for c in s["cards"].values()):
        prot.append("Reveal PC markers with '?' on cards with friendly units before resolving [8.2.4, E39]")
    if open_reading:
        prot.append(
            "PC markers to resolve (alphabetically, equal letters by R#): "
            + ", ".join(f"{k} (PC {s['cards'][k]['pc']})" for k in open_reading)
            + " [8.2.4]"
        )
        for letter in sorted({s["cards"][k]["pc"] for k in open_reading if s["cards"][k]["pc"] != "?"}):
            same = [k for k in open_reading if s["cards"][k]["pc"] == letter]
            if len(same) > 1:  # [RULE 8.2.4 p.62] 'resolve them in a random order'
                prot.append(
                    f"{len(same)} cards with PC {letter} ({', '.join(same)}): draw the order by R#, column {len(same)}, note it with fof.py note [8.2.4]"
                )
    else:
        prot.append("no PC markers with friendly units")


def _enter_3_7_3(s, prot):
    for n, e in s["units"].items():
        if state.pinned(e) and fire.vof_against(s, e["card"], e["side"]) is None:
            e["status"].remove(rules.PINNED)
            prot.append(
                f"{n}: remove Pinned marker (no VOF on {e['card']}); if the unit fires, its VOF becomes Basic again [3.7.3]"
            )


def _enter_3_7_4(s, prot):
    if any(enemy.is_sniper(e) for e in s["units"].values()):
        enemy.choose_sniper_targets(s, prot)
    with fire.cached(s):  # read-only until the NCM rows and groups are recorded
        _open_combat_effects(s, prot)
    combat.ammo_3_7_4(s, prot)  # [RULE 7.18.4 p.61] ammo of the firing units
    if any(c.get("lines") for c in s["cards"].values()):
        comms.line_checks_3_7_4(s, prot)


def _open_combat_effects(s, prot):
    """3.7.4 entry: who takes Combat Effects, NCM rows frozen on entry, NCM groups (no board change in here)."""
    s["combat_open"] = [
        n
        for n, e in s["units"].items()
        if not e.get("vehicle")  # [RULE 10.5.3 p.72] VOF against vehicles is resolved in 3.6
        and (
            fire.vof_against(s, e["card"], e["side"], ignore_mines=True) is not None
            or e.get("grenade")
            or state.card(s, e["card"]).get("grenade_miss")
            or e.get("mine_hit")
        )
    ]
    prot.append(
        "Combat Effects for: "
        + (", ".join(s["combat_open"]) if s["combat_open"] else "no one (no VOF)")
        + "; VOF, PDF and level stay frozen until 3.8 [3.7.4]"
    )
    # [RULE 3.7.4 p.17] 'do not update PDF or VOF markers until the Clean Up Phase': record NCM rows on entry
    s["combat_ncm"] = {}
    for n in s["combat_open"]:
        try:
            s["combat_ncm"][n] = [list(row) for row in combat.ncm_rows(s, n)]
        except rules.Violation:
            pass
    g = combat.ncm_groups(s)
    if g:
        prot.append(
            f"{len(g)} NCM group(s) on {len({x[0] for x in g})} card(s); next group: fof.py ncm next (numbered list, cards to draw) [V18, L155]"
        )


# entry hook per segment; the enemy check segment (3.4.2 or 3.2.2) is added from the SOP
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
    if state.is_campaign(s) and s.get("_phase_before") == "3.3.2d":
        events.check_event_flank(s, prot)
    if new == enemy.enemy_segments(s)[0] and events.planned_counter_attack(s):
        prot.append("Planned Counter Attack this turn: no draw, book it with fof.py event ? no [MSR 1]")
    hook = {**ENTER_HOOKS, enemy.enemy_segments(s)[1]: _enter_enemy_check}.get(new)
    if hook:
        hook(s, prot)


# ---- leaving a segment ('phase next'): checks in this order; each raises a Violation if the segment is not finished


def _leave_impulse_done(s, prot):
    if s["phase"] in rules.PLT_IMPULSES | {"3.3.2d", "3.3.1b", "3.3.2a", "3.3.2c", "3.3.1a"} and s.get("active_hq"):
        raise rules.Violation(f"{s['active_hq']} has not yet ended the impulse with 'done'")


def _leave_mines(s, prot):
    contact.mine_lock(s)


def _leave_capture(s, prot):
    open_caps = [n for n in s.get("capture_open", []) if n in s["units"]]
    if s["phase"] == "3.5.1" and open_caps:
        raise rules.Violation(f'Capture still open: fof.py capture "{open_caps[0]}" <guard> [3.5.1, 8.15] (L208)')
    s.pop("capture_open", None)


def _leave_reattempt(s, prot):
    if s.get("reattempt_setup"):
        raise rules.Violation("Reattempt preparation in progress: first fof.py reattempt done [3.9 p.18]")


def _leave_setup(s, prot):
    if s["turn"] == 1 and not s.get("setup_done"):
        fa = setup.check_campaign_setup(s)
        if fa:
            raise rules.Violation("Still open before turn 1: " + "; ".join(fa))
        for h in setup.campaign_setup_notes(s):
            prot.append("Note (lapses from now on): " + h)
        if s.get("patrol_mission"):
            campaign.patrol_reserve(s, prot)


def _leave_event_draw(s, prot):
    if s.get("event_tables") and s["turn"] >= 2 and s.get("events_done") != [s["turn"], s["phase"]]:
        if s["phase"] != "3.1" and events.planned_counter_attack(s):
            raise rules.Violation(
                "Planned Counter Attack this turn, no draw: fof.py event ? no (booked automatically as Counter Attack) [MSR 1]"
            )
        raise rules.Violation(
            f"First the Higher HQ Event of this segment: draw an Action card, fof.py event <cardno> yes <R#> | no [RULE {'3.1 p.15' if s['phase'] == '3.1' else '3.4.1 p.16'}]"
        )


def _leave_ammo_resupply(s, prot):
    if s.get("event_ammo") == s["turn"]:
        raise rules.Violation("Ammo Resupply not yet placed: fof.py ammo depot <card> <type> 4 [Normandy M1 p.18]")


def _leave_rally(s, prot):
    if s.get("rally_open"):
        raise rules.Violation(
            "Rally event open for: " + ", ".join(s["rally_open"]) + " (enemyaction <n> Rally --success=yes|no)"
        )


def _leave_snipers_lines(s, prot):
    if s.get("sniper_open") or s.get("line_checks"):
        raise rules.Violation(
            "Open: "
            + ", ".join(
                [f"Sniper target {n}" for n in s.get("sniper_open", {})]
                + [f"phone line {k}" for k in s.get("line_checks", {})]
            )
        )


def _leave_3_3_1c(s, prot):
    open_reading = [
        n
        for n, k in s["commands"].items()
        if k["activated"] and not k["done"] and s["units"].get(n, {}).get("level") != "CO"
    ]
    if open_reading:
        raise rules.Violation(f"Activated HQs without impulse: {', '.join(open_reading)} [RULE 3.3.1c p.15]")


def _leave_3_3_1b(s, prot):
    if not state.company(s):
        return
    co, co_record = s["co_hq"], s["commands"].get(s["co_hq"], {})
    if co_record.get("activated") and not co_record.get("done"):
        raise rules.Violation(
            f"{co} is activated and must draw an Action card in the CO HQ Impulse (hq, card, done) [RULE 3.3.1b p.15]"
        )


def _leave_3_3_2a(s, prot):
    if not state.company(s):
        return
    co, co_record = s["co_hq"], s["commands"].get(s["co_hq"], {})
    if co in s["units"] and not co_record.get("activated") and not co_record.get("done"):
        raise rules.Violation(
            f"{co} was not activated and now draws Initiative Commands (hq, card <no> <star number>, done) [RULE 3.3.2a p.16]"
        )


def _leave_3_3_2b(s, prot):
    if not state.company(s):
        return
    open_reading = [
        n
        for n, k in s["commands"].items()
        if n in s["units"] and s["units"][n].get("level") == "PLT" and not k["activated"] and not k["done"]
    ]
    if open_reading:
        raise rules.Violation(f"Non-activated PLT HQs draw Initiative: {', '.join(open_reading)} [RULE 3.3.2b p.16]")


def _leave_3_6(s, prot):
    if s.get("at36"):
        from . import vehicles

        vehicles.leave_3_6(s, prot)


def _leave_3_7_2(s, prot):
    open_reading = [k for k, c in s["cards"].items() if c.get("pc") and state.units_on(s, k, "US")]
    if open_reading:
        raise rules.Violation(
            f"PC markers with friendly units not yet resolved: {', '.join(open_reading)} [RULE 3.7.2 p.17]"
        )


def _leave_enemy_check(s, prot):
    if any(e["side"] == "Enemy" and e.get("check_open") for e in s["units"].values()):
        raise rules.Violation(
            "Enemy Activity Check not yet completed for all enemies (enemycheck / enemyaction) [RULE 3.4.2 p.16]"
        )


def _leave_combat_effects(s, prot):
    if s.get("combat_open"):
        raise rules.Violation(
            "Combat Effects still open for: " + ", ".join(s["combat_open"]) + " (ncm / hit) [RULE 3.7.4 p.17]"
        )


def _leave_fire_targets(s, prot):
    off = [n for n, e in s["units"].items() if e.get("target_open")]
    if off:
        raise rules.Violation("Set open fire targets first with 'fire': " + ", ".join(off))


# (segments the check applies to, campaign only, check), evaluated in this order.
# Segments: None = every segment; a callable gives the segment from the SOP (first segment, enemy segments).
LEAVE_CHECKS = (
    (None, False, _leave_impulse_done),
    (None, True, _leave_mines),
    (None, True, _leave_capture),  # 3.5.1 check, then capture_open lapses in every segment
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
    for segments, campaign_only, check in LEAVE_CHECKS:
        if campaign_only and not state.is_campaign(s):
            continue
        if segments is not None and s["phase"] not in (segments(s) if callable(segments) else segments):
            continue
        check(s, prot)


def check_next_phase(s, args, ids, prot):
    """The segment after 'phase next' (after the leave checks) or the named segment (corrections)."""
    if args[0] == "next":
        i = ids.index(s["phase"])
        leave_segment(s, prot)
        if i + 1 >= len(ids):
            raise rules.Violation("Last phase reached; use 'endturn' [RULE 3.8 p.17]")
        new = ids[i + 1]
        if new in rules.FROM_TURN_2 and s["turn"] == 1:
            prot.append(f"{new} does not apply in turn 1, skipped")
            new = ids[i + 2]
        elif new in rules.FROM_TURN_2 and s.get("no_events"):
            prot.append(f"{new} does not apply, no events in this mission (FM1 p.38/p.40), skipped")
            new = ids[i + 2]
        if s["phase"] == "3.1" and s["turn"] == 1:
            s["setup_done"] = True
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
        open_ = [n for n, e in s["units"].items() if must_retreat(s, e)]
        if open_:
            raise rules.Violation(
                f"3.5.2 not finished: retreat first {', '.join(open_)} (fof.py retreat <unit> [<card>]) [RULE 3.5.2 p.16] (L123)"
            )
    if not args:
        i = ids.index(s["phase"])
        print(f"Turn {s['turn']}  Phase {s['phase']} {state.phase_name(s)}")
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
    s["_phase_before"] = s["phase"]
    s["phase"] = new
    if segment_note(s, new):
        prot.append(segment_note(s, new))
    s["active_hq"] = None
    s["impulse_actions"] = {}
    enter_segment(s, new, prot)
    s.pop("_phase_before", None)
    activity_note = fire.update_activity(s)
    if activity_note:
        prot.append(activity_note)
    state.save_state(s, f"Phase {new} {state.phase_name(s)}" + ("; " + "; ".join(prot) if prot else ""), None)
    print(f"Phase {new} {state.phase_name(s)}")
    briefing.print_board(prot, s)


def check_capture(s, prot):
    """3.5.1 / 8.15: enemy Casualties automatically captured (8.15.1); Litter/Paralyzed alone with opponents: note."""
    for card_id, c in s["cards"].items():
        if (
            c.get("casualties_enemy")
            and not state.units_on(s, card_id, "Enemy")
            and (not c.get("pc") or state.units_on(s, card_id, "US"))
        ):
            s["prisoners"] = s.get("prisoners", 0) + c["casualties_enemy"]
            prot.append(f"{card_id}: {c['casualties_enemy']} enemy Casualties captured, remove marker [8.15.1]")
            campaign.book_xp(
                s,
                c["casualties_enemy"] * (campaign.xp_table(s, "enemy_casualty_step") or 1),
                f"{c['casualties_enemy']} enemy Casualties captured ({card_id})",
                prot,
            )
            c["casualties_enemy"] = 0
        for n in state.units_on(s, card_id):
            e = s["units"][n]
            # K33: "alone" also when the other same-side units on the card are only Paralyzed/Litter Teams
            if e["type"] in ("Paralyzed Team", "Litter Team") and not [
                m
                for m in state.units_on(s, card_id, e["side"])
                if m != n and s["units"][m]["type"] not in ("Paralyzed Team", "Litter Team")
            ]:
                opp = [
                    m
                    for m in state.units_on(s, card_id, state.opponent_of_side(e["side"]))
                    if can_capture(s["units"][m])
                ]
                if opp and not takes_prisoners(s, state.opponent_of_side(e["side"])):
                    # [RULE 8.15 p.69] 'If a side does not take prisoners per the campaign instructions,
                    # automatically convert any captured units to casualties' (Naktong p.13: the North Koreans do not)
                    for _ in range(state.steps(e)):
                        combat.make_casualty(s, e, prot, n)
                    combat.remove_from_play(
                        s, n, prot, "captors take no prisoners, converted to casualties [8.15]", True
                    )
                elif opp:
                    if state.is_campaign(s):
                        s.setdefault("capture_open", []).append(n)  # phase next waits for fof.py capture
                        prot.append(
                            f'{card_id}: {n} ({e["type"]}, {e["side"]}) is captured ({prisoner_source(s)}): fof.py capture "{n}" <guard> [3.5.1, 8.15]'
                        )
                    else:
                        prot.append(
                            f"{card_id}: {n} ({e['type']}, {e['side']}) is captured: one guard step with VOF value goes along (both Removed from Play); enemies take no prisoners, US team then becomes a Casualty. Afterwards fof.py enemy/order to correct [8.15]"
                        )


def prisoner_source(s):
    """wording for the capture note from the setup ('take_prisoners'), not a fixed Normandy text."""
    g = s.get("take_prisoners")
    if not g:
        return "both sides take prisoners, Normandy p.13"
    who = [side for side in ("US", "Enemy") if g.get(side, True)]
    if len(who) == 2:
        return "both sides take prisoners"
    return f"only {who[0]} takes prisoners (campaign rules)" if who else "no side takes prisoners"


def takes_prisoners(s, side):
    """setup 'take_prisoners' {US|Enemy: bool}; without it both sides take prisoners (Normandy p.13)."""
    return (s.get("take_prisoners") or {}).get(side, True)


def can_capture(x):
    """one predicate for captors and the guard step: combat.can_capture."""
    return combat.can_capture(x)


def must_retreat(s, e):
    """[RULE 3.5.2 p.16] Unpinned, non-Exposed Paralyzed Team under VOF, or such a Litter Team with a Casualty (carried or on the card)."""
    if state.pinned(e) or rules.EXPOSED in e["status"] or not fire.vof_against(s, e["card"], e["side"]):
        return False
    if e["type"] == "Paralyzed Team":
        return True
    if e["type"] == "Litter Team":
        c = state.card(s, e["card"])
        return bool(e.get("carries_casualties") or c.get("casualties" if e["side"] == "US" else "casualties_enemy"))
    return False


def retreat_cards(s, e):
    """[RULE 3.5.2 p.16] One card towards the own edge: first cards without VOF, then the best C&C value. Returns the ties."""
    cur = state.card(s, e["card"])
    step = -1 if e["side"] == "US" else 1
    cands = [
        k
        for k, c in s["cards"].items()
        if c["row"] == cur["row"] + step
        and geometry.adjacent(s, e["card"], k)
        and not (e["side"] == "US" and c.get("outside"))
    ]
    if not cands:
        return []
    free = [k for k in cands if not fire.vof_against(s, k, e["side"])] or cands
    best = max(state.card(s, k).get("cc", 0) for k in free)
    return sorted(k for k in free if state.card(s, k).get("cc", 0) == best)


def cmd_retreat(s, args):
    """3.5.2: carry out the retreat of a Paralyzed or Litter Team."""
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
    origin = e["card"]
    if e["type"] == "Litter Team" and not e.get("carries_casualties"):
        c = state.card(s, origin)
        key = "casualties" if e["side"] == "US" else "casualties_enemy"
        c[key] -= 1
        e["carries_casualties"] = 1
        prot.append(f"{n} picks up a Casualty on {origin} (Casualty marker goes with it) [3.5.2 p.16]")
    # through the one move path of each side (Grenade VOF becomes a Grenade Miss, mines, ammo surplus,
    # phone line, fire after the move) instead of moving the counter by hand
    prot.append(f"{n} retreats from {origin} [3.5.2 p.16]")
    if e["side"] == "US":
        commands.move_unit(s, n, target, "open", exposed=True, prot=prot)
    else:
        enemy.move_enemy(s, n, target, prot, cover=False, how="retreats", rule="3.5.2")
    note = fire.update_activity(s)  # the VOF the team left behind may have been the second occupied card under fire
    if note:
        prot.append(note)
    state.save_state(s, f"Retreat {n}: " + "; ".join(prot), "3.5.2 p.16")
    briefing.print_board(prot, s)


def check_retreat(s, prot):
    """3.5.2: Paralyzed Teams (unpinned, not Exposed) and Litter Teams with a Casualty under VOF retreat one card."""
    gone = []
    for n, e in s["units"].items():
        if (
            e["type"] in ("Paralyzed Team", "Litter Team")
            and must_retreat(s, e)
            and e["side"] == "Enemy"
            and state.card(s, e["card"])["row"] >= state.top_row(s)
        ):
            # [RULE 3.5.2 p.16] "Enemy units who retreat from a card at their side's edge of the map will retreat off the
            # map. Remove them from play. Do not extend the map." Litter Teams too, with their Casualty
            if e["type"] == "Litter Team" and not e.get("carries_casualties"):
                c = state.card(s, e["card"])
                c["casualties_enemy"] = max(0, c.get("casualties_enemy", 0) - 1)
                prot.append(f"{n} takes a Casualty off the map from {e['card']} [3.5.2]")
            gone.append(n)
            continue
        if e["type"] == "Paralyzed Team" and must_retreat(s, e):
            prot.append(
                f'{n} ({e["side"]}) must retreat one card (priority: no VOF, then best cover, random on a tie), Exposed [3.5.2]: fof.py retreat "{n}" [<card>]'
            )
        if must_retreat(s, e) and e["type"] == "Litter Team":
            prot.append(
                f'{n} ({e["side"]}) retreats one card with a Casualty, Exposed [3.5.2]: fof.py retreat "{n}" [<card>]'
            )
    for n in gone:  # one removal path (removed_from_play, package back to the pool, markers)
        grenades.grenade_expires(s, s["units"][n], n, prot)  # [RULE 7.10.4]
        combat.remove_from_play(
            s, n, prot, "(enemy) retreats off-map from the map edge, counter back to the pool [3.5.2]"
        )


def campaign_clean_up(s, prot):
    """Clean Up (3.8) for the campaign elements: mines, snipers, ammo, G! PDF, Place-VOF-No, events, Checking Up, counterattack."""
    for n, e in list(s["units"].items()):
        if e.pop("mine_hit", None):
            prot.append(f"{n}: remove from the Mine marker [3.8 p.17]")
        if e.get("ammo_empty"):
            combat.out_of_ammo(s, n, e, prot)
        if e.get("pdf_only"):
            fire.cease_fire(e)
            prot.append(f"{n}: remove the Grenade Attack PDF [7.3.2 p.53]")
        if e.pop("no_fire_until_clean_up", None):
            prot.append(f"{n} may now open fire (Place PDF/VOF No) [8.3 p.63]")
        if e.get("until_turn") == s["turn"] and e.get("level") == "BN":
            del s["units"][n]  # the BN HQ goes back off-map (Checking Up can bring it again), not a removal from play
            s["commands"].pop(n, None)
            prot.append(f"{n} (Checking Up) leaves the board; BN HQ off-map again [Normandy M1 p.18]")
    for card_id, c in s["cards"].items():
        for x in c.get("external", []):
            if x["type"] == "Mines" and x.get("active"):
                x["active"] = False
                prot.append(f"{card_id}: Mine marker back to the Draw 3 side [3.8 p.17]")
        if c.pop("pyro", None):
            prot.append(f"{card_id}: remove pyrotechnics [3.8 p.17]")
    for k in (
        "sniper_targets",
        "sniper_open",
        "event_units",
        "rally_open",
        "line_checks",
        "event_task",
        "event_flank",
        "fm_blocked",
        "bn_unavailable",
        "event_ammo",
        "hold_up",  # a turn-stamped event lives for its turn only
    ):
        s.pop(k, None)
    ga = s.get("counterattack")
    if ga and ga.get("until_turn") == s["turn"]:
        s["enemy_tactic"] = ga.get("tactic_before") or s.get("enemy_tactic")
        s.pop("counterattack")
        prot.append(f"Counterattack ends: enemy tactic back to {s['enemy_tactic']} [Normandy M1 MSR 1 p.19]")


def cmd_end_turn(s, args):
    if s["phase"] != "3.8":
        raise rules.Violation(f"End of turn only in phase 3.8, currently {s['phase']} [RULE 3.8 p.17]")
    prot = []
    if s.pop("grenade_responses", None):  # free responses lapse with the turn [7.10.5]
        prot.append("Open Grenade responses lapse at the end of the turn [7.10.5]")
    clean_up_vehicles(s, prot)
    clean_up_units(s, prot)
    clean_up_cards(s, prot)
    for e in s["units"].values():
        if e.get("indirect"):
            e.pop("indirect")
    if s.get("weather_this_turn_only"):
        s["weather"] = 0
        s.pop("weather_this_turn_only")
        geometry.update_visibility(s)
        prot.append("Remove Rain marker, weather back to +0 [Event It's Raining]")
    if state.is_campaign(s):
        campaign_clean_up(s, prot)
    fire.cease_fire_on_los_loss(s, prot)
    fire.enemy_cease_fire(s, prot)
    # [RULE 3.8 p.17] 'Adjust VOF, PDF and Activity Levels resulting from the Combat Effects Segment and Clean Up';
    # e.g. mortars after removing Exposed [FM1 p.44]
    fire.open_fire(s, prot)
    reset_commands(s, prot)
    if end_of_mission(s, prot):
        return
    s["turn"] += 1
    s["phase"] = state.sop(s)[0][0]
    campaign.apply_turn_visibility(s, prot)
    # [RULE 9.1 p.70, 6.1.2]: the new turn's visibility can shorten LOS (Moon: adjacent cards only); PDFs that now
    # reach beyond it lapse, and units open fire anew on what they can still see
    fire.cease_fire_on_los_loss(s, prot)
    fire.enemy_cease_fire(s, prot)
    fire.open_fire(s, prot)
    activity_note = fire.update_activity(s)
    if activity_note:
        prot.append(activity_note)
    state.save_state(s, f"Clean Up; turn {s['turn']} begins; " + "; ".join(prot), "3.8 p.17")
    print(f"Turn {s['turn']} begins with phase {s['phase']} {state.phase_name(s)}.")
    briefing.print_board(prot, s)


def clean_up_vehicles(s, prot):
    """3.8: vehicle markers and wrecks (10.4), only when vehicles, AT36 or wrecks are in the game."""
    if (
        s.get("at36")
        or any(e.get("vehicle") for e in s["units"].values())
        or any(x.get("wreck") for c in s["cards"].values() for x in c.get("external", []))
    ):
        from . import vehicles

        vehicles.clean_up(s, prot)


def clean_up_units(s, prot):
    """3.8: Exposed, Concentrated Fire, Grenade VOF and Critical Hit markers off the units; Unspotted enemy teams that
    flipped because they are Out of Ammo leave play (8.11.1)."""
    for n in [
        n
        for n, e in s["units"].items()
        if e["side"] == "Enemy" and e.get("ooa_fallback") and state.fire_team_side(e) and not e.get("spotted")
    ]:
        # [RULE 8.11.1 p.68] 'In the Clean Up Phase, remove from play any such team if it is Unspotted'
        enemy.remove_enemy(s, n, prot, reason="Out of Ammo and Unspotted [8.11.1 p.68]")
    for n, e in s["units"].items():
        for m in (rules.EXPOSED,):  # Moved/Fired is cleared in vehicles.clean_up
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
            prot.append(f"{n}: remove Critical Hit Concentrated Fire marker [7.11.4]")
        e.pop("concentrated", None)
        e.pop("cf_on", None)


def clean_up_cards(s, prot):
    """3.8: Illumination, Grenade Miss, Smoke and Indirect Lay off the cards; CCP evacuation; PC markers (defensive)."""
    for card_id, c in s["cards"].items():
        if c.get("illum"):
            c["illum"] = []
            prot.append(f"{card_id}: remove Illumination marker [RULE 9.2 p.70]")
        if c.get("grenade_miss"):
            c["grenade_miss"] = False
            prot.append(f"{card_id}: remove Grenade Miss")
        for x in list(c.get("external", [])):
            if x["type"] == "Smoke":
                c["external"].remove(x)
                prot.append(f"{card_id}: remove Smoke/Pyro")
            if x["type"] == "Incoming":
                prot.append(f"{card_id}: Incoming stays until 3.7.1 of the next turn (blocks LOS)")
            if x["type"] == "Indirect":
                c["external"].remove(x)
                prot.append(
                    f"{card_id}: remove Heavy Weapons VOF (Indirect Lay from {x.get('source')}) [RULE 7.3.2 p.53]"
                )
        if s.get("ccp") == card_id and c.get("casualties"):
            s["evacuated"] = s.get("evacuated", 0) + c["casualties"]
            prot.append(
                f"{card_id}: {c['casualties']} casualties evacuated at the CCP, markers to the Holding Box [RULE 3.8 p.17, 5.1.7 p.34]"
            )
            campaign.book_xp(
                s,
                c["casualties"] * (campaign.xp_table(s, "evacuated") or 1),
                f"{c['casualties']} casualties evacuated ({card_id})",
                prot,
            )
            c["casualties"] = 0
        if s["type"] == "defensive" and c.get("pc") and not state.units_on(s, card_id, "US"):
            state.clear_pc(c, promote=False)
            prot.append(f"{card_id}: unresolved PC marker removed (defensive mission)")


def reset_commands(s, prot):
    """3.8: Command markers and the per-turn order bookkeeping back to the start of a turn [4.1.1]."""
    for k in s["commands"].values():
        k["activated"], k["done"], k["available"] = False, False, 0
        k.pop("drawn", None)
        k.pop("skill_for", None)
    s["impulse_spent"] = {}
    s["combat_open"] = []
    s["last_attempt"] = None
    s.pop("combat_ncm", None)
    s.pop("exhort_free", None)
    prot.append(
        "Command markers from the Saved zone to the Tracking zone (value stays), Zero Commands marker to the Holding Box [4.1.1]"
    )
    prot.append(
        "Check VOF markers on the board against the briefing: pinned shooters 'All Pinned' +2, unpinned back to Basic VOF [3.8, 4.2.5]"
    )


def end_of_mission(s, prot):
    """Last turn played: save the mission end and return True (campaign: campaign mission end, 3.9)."""
    if s["turn"] >= s["max_turns"] and state.is_campaign(s):
        campaign.campaign_mission_end(s, prot)
        state.save_state(s, f"Turn {s['turn']} ended: end of mission reached; " + "; ".join(prot), "3.8 p.17, 3.9 p.17")
        print("End of mission: last turn played.")
        briefing.print_board(prot, s)
        return True
    if s["turn"] >= s["max_turns"]:
        if s.get("objective_rules"):
            prot.append("Objective status: " + briefing.objective_status(s))
            if "options" in s:
                prot.append(
                    (
                        "Reattempt per 3.9 provided for by option U9"
                        if state.option(s, "U9_reattempt")
                        else "no Reattempt (FM1 names none)"
                    )
                    + state.open_reading(s, "U9_reattempt")
                    + " [RULE 3.9 p.17]"
                )
        state.save_state(s, f"Turn {s['turn']} ended: end of mission reached; " + "; ".join(prot), "3.8 p.17")
        print("End of mission: last turn played.")
        briefing.print_board(prot, s)
        return True
    return False
