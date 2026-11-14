"""Net combat modifier, hit effects, unit reduction, ammunition, prisoners (6.4, 7.18, 8.15).

Import cycle: combat and commands, enemy, campaign import each other at module level (each uses the other's
functions only at call time, as module attributes such as commands.mark, never at import time)."""

import copy

from . import briefing, campaign, commands, comms, enemy, fire, geometry, rules, state


def cc_row(s, e):
    """[RULE 5.2.3 p.36] Two C&C values: the higher one if any fire comes across a dark edge; the lower one if all
    fire comes across white edges, as Incoming/indirect mortar fire, or from within the card itself."""
    card_id = e["card"]
    c = state.card(s, card_id)
    if c.get("cc2") is None:
        return (f"Terrain {c['terrain']}", c.get("cc", 0))
    dark = []
    for x in fire.vof_entries(s, card_id):
        if x[3] not in (None, e["side"]) or x[4] is None or x[4] == card_id:
            continue  # external (Incoming, Indirect), Point Blank, or does not hit this side
        if geometry.edge(c, geometry.direction(s, card_id, x[4])) != "white":
            dark.append(f"{x[2]} from {x[4]}")
    if dark:
        return (f"Terrain {c['terrain']} (higher value, fire across a dark edge: {', '.join(dark)})", c["cc"])
    return (
        f"Terrain {c['terrain']} (lower value: fire only across white edges, as Incoming/Indirect or from within the card)",
        c["cc2"],
    )


def _fire_effects(s, e, c, name):
    """All fire effects against the unit as (label, value, type): direct VOF, Incoming-like VOF, Mines!, Sniper, Grenade,
    Grenade Miss [RULE 6.4 p.45, 6.3.6 p.45]."""
    candidate = []
    tr = [x for x in fire.vof_entries(s, e["card"]) if x[3] in (None, e["side"]) and x[0] != "Mines"]
    ext = [x for x in tr if x[0] in rules.TERRAIN_LIKE_INCOMING]
    dir_ = [x for x in tr if x[0] not in rules.TERRAIN_LIKE_INCOMING]
    if ext:
        bx = min(ext, key=lambda x: x[1])
        candidate.append((f"VOF {rules.VOF_NAME.get(bx[0], bx[0])} ({bx[2]})", bx[1], bx[0]))
    if dir_:
        bd = min(dir_, key=lambda x: x[1])
        candidate.append(
            (
                f"VOF {rules.VOF_NAME.get(bd[0], bd[0])} from {','.join(x[2] for x in dir_ if x[1] == bd[1])}",
                bd[1],
                bd[0],
            )
        )
    if e.get("mine_hit"):
        mw = min([x["value"] for x in c.get("external", []) if x["type"] == "Mines"] or [-4])
        candidate.append(("Mines! VOF (mine check lost)", mw, "Mines"))  # [RULE 7.9.1 p.54, 6.3.6]
    for sn, sz in s.get("sniper_targets", {}).items():
        if sz == name and sn in s["units"]:
            candidate.append((f"Sniper VOF from {sn}", -3, "Sniper"))  # [RULE 7.15 p.57]
    if e.get("grenade"):
        candidate.append(("Grenade VOF (cumulative)", sum(e["grenade"]), "G"))
    if not candidate and c.get("grenade_miss"):
        candidate.append(("Grenade Miss as VOF", -1, "G"))
    return candidate


def _rows_for(s, e, c, base):
    """NCM rows for one fire effect as the base VOF [RULE 6.4 p.45, Charts & Tables 1]."""
    type_ = base[2]
    rows = [(base[0], base[1])]
    if c.get("grenade_miss") and base[0] != "Grenade Miss as VOF":
        rows.append(("Grenade Miss", -1))
    if fire.crossfire(s, e["card"], e["side"]):
        rows.append(("Crossfire (two PDF directions)", -1))
    for _ in range(e.get("cf", 0)):
        rows.append(("Concentrated Fire", -1))
    if type_ in rules.TERRAIN_LIKE_INCOMING and c.get("cc2") is not None:
        rows.append(
            (f"Terrain {c['terrain']} (lower value against {rules.VOF_NAME.get(type_, type_)}) [5.2.3]", c["cc2"])
        )
    else:
        rows.append(cc_row(s, e))
    cv = fire.cover_of(s, e)
    if cv and e.get("grenade_critical"):
        rows.append((f"Cover {cv['id']} {cv['type']} lost (Critical Hit Grenade) [7.10.3]", 0))
    elif cv and e.get("cf_critical"):
        rows.append((f"Cover {cv['id']} {cv['type']} lost (Critical Hit Concentrated Fire) [7.11.4]", 0))
    elif cv:
        rows.append((f"Cover {cv['id']} {cv['type']}", cv["value"]))
    if state.pinned(e):
        rows.append(("Pinned", +1))
    if rules.EXPOSED in e["status"]:
        rows.append(("Exposed", -2))
    if type_ in rules.TERRAIN_LIKE_INCOMING and c.get("burst") is not None:
        rows.append(("Burst symbol", c["burst"]))  # [RULE 5.2.3 p.36, Charts 1: only Incoming and indirect mortar fire]
    smoke = [x.get("value") or 0 for x in c.get("external", []) if x["type"] == "Smoke"]
    if smoke and type_ not in ("Incoming", "AirStrike", "Mines", "G") and max(smoke):
        rows.append(("Smoke (best value)", max(smoke)))  # [RULE 5.4 p.38]
    if cv and type_ in ("Incoming", "AirStrike", "G"):
        st = sum(
            state.steps(s["units"][m])
            for m in state.units_on(s, e["card"], e["side"])
            if s["units"][m].get("area") == cv["id"]
        )
        if st > 3:
            rows.append((f"Stacking {st} steps under cover", -(st - 3)))
    sk = geometry.visibility_on_card(s, e["card"])
    if sk and type_ not in ("Incoming", "AirStrike", "G", "Mines"):
        il = geometry.illumination_value(s, e["card"])
        rows.append(
            ("Visibility (ch. 9)" + (f", illumination {il:+d} included" if il is not None else ""), sk)
        )  # [RULE 9.0 p.69]
    return rows


def ncm_rows(s, name):
    """[RULE 6.4 p.45] 'When multiple VOF are affecting a card, take into account their value after modifiers ... Light levels
    (9.0) and cover modifiers (5.3) may modify different weapons in different ways' (Clarification 3): every fire effect is
    evaluated with its own modifiers, the strongest result counts (Incoming, all effects, e.g. Grenade at night)."""
    e = state.unit(s, name)
    c = state.card(s, e["card"])
    with fire.cached(s):  # read-only: every fire effect and C&C row reuses one fire map
        candidate = _fire_effects(s, e, c, name)
        if not candidate:
            raise rules.Violation(f"No VOF against {name} on {e['card']} [3.7.4]")
        best = None
        for cand in candidate:
            rows = _rows_for(s, e, c, cand)
            if best is None or sum(v for _, v in rows) < sum(v for _, v in best):
                best = rows
    return best


def _ncm_total(s, name):
    if s["phase"] == "3.7.4" and name in s.get("combat_ncm", {}):
        rows = [tuple(row) for row in s["combat_ncm"][name]]
    else:
        rows = ncm_rows(s, name)
    raw = sum(v for _, v in rows)
    return max(-4, min(6, raw)), raw, rows


def ncm_groups(s):
    """(V18): open Combat Effects card by card, per card one group per NCM value.
    Returns [(card, ncm, [units])] in board order (cards by number, groups by NCM, units in protocol order)."""
    by_card = {}
    with fire.cached(s):
        for n in s.get("combat_open", []):
            if n not in s["units"]:
                continue
            try:
                ncm, _raw, _rows = _ncm_total(s, n)
            except rules.Violation:
                continue
            by_card.setdefault(s["units"][n]["card"], {}).setdefault(ncm, []).append(n)
    out = []
    for k in sorted(by_card, key=lambda x: (state.card(s, x)["row"], state.card(s, x)["column"])):
        for ncm in sorted(by_card[k]):
            out.append((k, ncm, by_card[k][ncm]))
    return out


def print_next_group(s):
    """the next NCM group as a numbered list, so the player sees how many cards to draw at once."""
    with fire.cached(s):
        _print_next_group(s)


def _print_next_group(s):
    groups = ncm_groups(s)
    if not groups:
        return
    k, ncm, units = groups[0]
    same_card = [g for g in groups if g[0] == k]
    _n, raw, rows = _ncm_total(s, units[0])
    print(
        f"Combat Effects card {k}, group 1 of {len(same_card)} on this card: NCM {ncm:+d}"
        + (f" (raw {raw:+d})" if raw != ncm else "")
        + f". Draw {len(units)} Action card{'s' if len(units) > 1 else ''}, one per unit, in this order, Combat Resolution column {ncm:+d}:"
    )
    for i, n in enumerate(units, 1):
        e = s["units"][n]
        print(f"  {i}. {n} ({comms.experience(e)}, {state.steps(e)} step{'s' if state.steps(e) > 1 else ''})")
    per_unit = [(n, _ncm_total(s, n)[2]) for n in units]
    if all(r == rows for _, r in per_unit):
        print("  NCM rows:")
        for t_, v_ in rows:
            print(f"    {t_} {v_:+d}")  # one per line
    else:  # same NCM from different modifiers, rows per unit
        for n, r in per_unit:
            print(f"  NCM rows {n}:")
            for t_, v_ in r:
                print(f"    {t_} {v_:+d}")
    print(
        '  Then per unit in this order: fof.py hit "<unit>" HIT|PIN|MISS [letters under its experience] [RULE 3.7.4 p.17, 6.4.2]'
    )
    rest = groups[1:]
    if rest:
        cards = {}
        for g in rest:
            cards.setdefault(g[0], []).append(len(g[2]))
        print(
            "  Afterwards still open: "
            + "; ".join(f"card {c} {len(v)} group(s), {sum(v)} unit(s)" for c, v in cards.items())
        )


def cmd_ncm(s, args):
    if args and args[0] in ("next", "group"):
        if s["phase"] != "3.7.4":
            raise rules.Violation("ncm next only in the Combat Effects Segment 3.7.4")
        if not ncm_groups(s):
            print("No Combat Effects open [3.7.4]")
            return
        print_next_group(s)
        return
    rules.need(args, 1, "ncm <unit> | ncm next")
    name = args[0]
    state.unit(s, name)
    if s["phase"] == "3.7.4" and name in s.get("combat_ncm", {}):
        rows = [tuple(row) for row in s["combat_ncm"][name]]  # state on entering 3.7.4 [RULE 3.7.4 p.17]
    else:
        rows = ncm_rows(s, name)
    raw = sum(v for _, v in rows)
    ncm = max(-4, min(6, raw))
    print(f"NCM {name}:")
    for t, v in rows:
        print(f"- {t}: {v:+d}")
    print(
        f"- Total {raw:+d}" + (f", capped at {ncm:+d}" if ncm != raw else "") + "  [RULE 6.4 p.45, Charts & Tables 1]"
    )
    print(
        f'Draw an Action card, Combat Resolution at {ncm:+d}: HIT, PIN or MISS. Then fof.py hit "{name}" <HIT|PIN|MISS> [effect letters under {comms.experience(s["units"][name])}]'
    )


LAT_VALUES = {
    "Assault Team": ("A", "P"),
    "Fire Team": ("S", "C"),
    "Litter Team": (None, "C"),
    "Paralyzed Team": (None, "C"),
}  # Normandy Unit Breakdown p.47: Assault TM A/P, Fire Team S/C


def set_lat_values(e, lat):
    e["vof_rating"], e["range"] = LAT_VALUES[lat]


def new_lat(e, lat, origin):
    return {
        "type": lat,
        "side": e["side"],
        "platoon": e.get("platoon"),
        "experience": rules.LAT_EXPERIENCE[lat],
        "card": e["card"],
        "area": e.get("area", "open"),
        "status": [] if e.get("human_wave") else [rules.PINNED],  # [8.14] Human Waves are never Pinned
        "steps": 1,
        "origin": origin,
        "target": None,
        "vof_rating": LAT_VALUES[lat][0],
        "range": LAT_VALUES[lat][1],
        "spotted": e.get("spotted", True),
        "type_name": lat,
        **({"deep_bunker": e["deep_bunker"]} if e.get("deep_bunker") else {}),
        **({"human_wave": True} if e.get("human_wave") else {}),  # [8.14] the hit rule stays with the teams
    }  # LATs in a Deep Bunker also have no VOF


def make_casualty(s, e, prot, name):
    c = state.card(s, e["card"])
    key = "casualties" if e["side"] == "US" else "casualties_enemy"
    c[key] = c.get(key, 0) + 1
    if e["side"] == "US" and state.is_campaign(s):
        s["us_casualties_total"] = s.get("us_casualties_total", 0) + 1  # [RULE 12.4 p.81] all casualties of the mission
    prot.append(f"{name}: one step becomes a Casualty, Casualty marker on {e['card']} [6.4.3]")


def drop_assets(s, e, name, prot, as_casualty=False, successor=None):
    """Carried casualties and radios: [RULE 6.4.3 p.47] onto the card at the last step (5.1.6E);
    [RULE 4.3.5 p.30] casualty of the last step: radio destroyed on R# 1/2; LAT conversion per option U7."""
    c = state.card(s, e["card"])
    if e.get("carries_casualties"):
        c["casualties"] = c.get("casualties", 0) + e["carries_casualties"]
        prot.append(
            f"{name}: drop carried casualties ({e['carries_casualties']}) on {e['card']} [5.1.6E p.33, 6.4.3 p.47]"
        )
        e["carries_casualties"] = 0
    if e.get("lines"):
        c["line_assets"] = c.get("line_assets", 0) + e["lines"]
        prot.append(f"{name}: {e['lines']} Phone Line(s) remain as an asset on {e['card']} (BGG D3)")
        e["lines"] = 0
    if e.get("carries_ammo"):
        prot.append(f"{name}: carried ammo is lost (BGG C6)")
        e.pop("carries_ammo")
    if e.get("assets"):  # [RULE 5.1.6E p.33, 6.4.3 p.47] assets drop onto the card
        c.setdefault("assets_ground", []).extend(e["assets"])
        prot.append(f"{name}: Assets {', '.join(e['assets'])} lie on {e['card']} (Pick Up 4.2.2h) [5.1.6E p.33]")
        e["assets"] = []
    gs = comms.radios_of(e)
    if not gs:
        return
    if successor and not as_casualty and ("options" not in s or state.option(s, "U7_lat_keeps_radio")):
        s["units"][successor]["radio"] = [dict(g) for g in gs]
        prot.append(
            f"{successor} keeps {', '.join(g['type'] for g in gs)} (cannot give orders as a LAT){state.open_reading(s, 'U7_lat_keeps_radio')} [5.1.6E p.33]"
        )
    else:
        for g in gs:
            c.setdefault("assets", []).append({"type": g["type"], "net": g["net"], "damage_open": bool(as_casualty)})
        prot.append(
            f"{', '.join(g['type'] + ' ' + g['net'] for g in gs)} from {name} on {e['card']}"
            + (
                ": draw R# 1/2, destroyed on 1 (fof.py radio damage <card> <device> intact|destroyed) [RULE 4.3.5 p.30]"
                if as_casualty
                else f" dropped{state.open_reading(s, 'U7_lat_keeps_radio')} [5.1.6E p.33]"
            )
        )
    e["radio"] = []


def remove_from_play(s, name, prot, reason, as_casualty=False, successor=None, captured=False):
    """The one path that takes a counter off the board: assets/radios/ammo, Concentrated Fire and Grenade
    markers, removed_from_play (blocks the friendly counter name for new_name), saved Commands, enemy package.
    captured=True (prisoners, 8.15): assets, radios and carried casualties leave with the counter instead of dropping
    onto the card, and no own 'Removed from Play' line (the caller names the whole group)."""
    e = s["units"][name]
    if state.is_hq(e) and e["side"] == "US":
        s.setdefault("rfp_data", {})[name] = {k: e.get(k) for k in ("level", "platoon", "ft_vof")}  # for 6.5.2
    if e.get("level") == "BN" and e["side"] == "US" and not captured:
        # [RULE 6.5.2 p.50 C] 'BN HQ will be unavailable to give orders in the following turn while they reconstitute'
        s["bn_reconstituting"] = s["turn"] + 1
        prot.append(
            f"{name} eliminated on the map: the BN HQ gives no orders in turn {s['turn'] + 1}; put the counter on the "
            f"turn track at turn {s['turn'] + 2}, from then on it is available off-map again [6.5.2 p.50]"
        )
    if e.get("cf_on"):
        fire.drop_concentrated(s, e, f"{name} is off the board", prot)  # [RULE 7.11.5 p.56]
    for m, x in s["units"].items():  # embarked units stay on the card when their vehicle leaves play
        if x.get("on_board") == name:
            x.pop("on_board")
            prot.append(f"{m} dismounts on {e.get('card')} ({name} is gone) [10.8.1, open reading]")
    mounted = [g for g in e.get("radio", []) if g.get("mounted")]
    if mounted:  # a radio mounted in a vehicle does not drop onto the card as a manpack (CSR 1)
        e["radio"] = [g for g in e["radio"] if not g.get("mounted")]
        jeep = s["units"].get(mounted[0]["mounted"])
        if jeep is not None:
            jeep.setdefault("radio", []).extend(mounted)
    if not captured:
        drop_assets(s, e, name, prot, as_casualty, successor)
    if not (
        successor and (s["units"].get(successor) or {}).get("ammo")
    ):  # the successor (A fire team) inherits the ammo
        enemy.ammo_lost(e, name, prot)
    elif e.get("ammo"):
        prot.append(
            f"ammo marker ({e['ammo'].get('points')} {e['ammo'].get('type', '')}) stays with {successor} on {e.get('card')} [Normandy p.48, 7.18.1B]"
        )
    _mk = (["Concentrated Fire marker"] if e.get("cf") else []) + (["Grenade VOF marker"] if e.get("grenade") else [])
    if _mk:  # markers on the removed counter, otherwise only named in Clean Up
        prot.append(f"remove {' and '.join(_mk)} of {name} on {e.get('card')} (counter off the board) [3.8 p.17]")
    del s["units"][name]
    state.forget_pending(s, name)
    if e.get("on_board"):  # [10.8.8] the jeep's experience follows the units still on board
        from . import vehicles

        vehicles.update_jeep_experience(s, e["on_board"])
    s.setdefault("removed_from_play", []).append(name)
    if name in s["commands"]:
        s["commands"][name]["saved"] = 0
    if e["side"] == "Enemy":
        pk = s.get("packages", {}).get(str(e.get("package")))
        if pk:
            pk["in_play"] = False
    if not captured:
        prot.append(f"{name}: {reason}, Removed from Play [1.2.6, 6.4.3]")


def reduce_unit(s, name, code, prot):
    """6.4.3: one letter applied to one step."""
    e = s["units"][name]
    lat = rules.LAT_TYPES[code]
    if state.is_lat(e):
        if e["type"] == lat:
            commands.mark(e, rules.PINNED)
            prot.append(f"{name} is already {lat}: Pinned only [6.4.3]")
        elif code == "C":
            make_casualty(s, e, prot, name)
            # via remove_from_play, so removed_from_play and the markers stay consistent
            remove_from_play(s, name, prot, f"{e['type']} becomes a Casualty, remove counter", as_casualty=True)
        else:
            e["type"], e["experience"] = lat, rules.LAT_EXPERIENCE[lat]
            # [Normandy Unit Breakdown p.47, K12, E72 counter photo]: generic LAT counter values, Assault Team A • P, Fire Team S • C
            e["vof_rating"], e["range"] = LAT_VALUES[lat]
            if e["vof_rating"] is None:
                fire.cease_fire(e)
            commands.mark(e, rules.PINNED)
            prot.append(f"{name} becomes {lat} (swap counter), Pinned [6.4.3]")
        return
    if state.fire_team_side(e):
        if code in ("F", "A"):
            e.pop("ooa_flip", None)  # from now on the flip is HIT-caused, resupply does not undo it
            commands.mark(e, rules.PINNED)
            prot.append(f"{name} (named Fire Team): no further effect, Pinned [6.4.3]")
        elif code == "C":
            make_casualty(s, e, prot, name)
            remove_from_play(s, name, prot, "Casualty", as_casualty=True)
        else:
            new = commands.new_name(s, lat, side=e["side"], card=e["card"])
            s["units"][new] = new_lat(e, lat, name)
            prot.append(f"{name} becomes {lat} ({new})")
            remove_from_play(s, name, prot, "Fire Team side converted", successor=new)
        return
    if state.steps(e) == 1:
        if code in ("F", "A") and e.get("fire_team_side"):
            commands.mark(e, rules.FIRE_TEAM_SIDE)
            commands.mark(e, rules.PINNED)
            prot.append(
                f"{name}: flip to the Fire Team side (VOF {e.get('ft_vof', 'S')}), Pinned"
                + ("; saved Commands remain, orders only itself, cannot be activated [4.1.4]" if state.is_hq(e) else "")
                + " [6.4.3]"
            )
            return
        new = None
        if code == "C":
            make_casualty(s, e, prot, name)
        else:
            new = commands.new_name(s, lat, side=e["side"], card=e["card"])
            s["units"][new] = new_lat(e, lat, name)
            prot.append(f"{name}: step becomes {lat} ({new}) on {e['card']}, Pinned")
        remove_from_play(s, name, prot, "last step converted", as_casualty=(code == "C"), successor=new)
        return
    if breakdown_step(s, name, code, prot):
        pass  # Mortar Section: the hit step became a named Mortar Team
    elif code == "C":
        make_casualty(s, e, prot, name)
    else:
        new = commands.new_name(s, lat, side=e["side"], card=e["card"])
        s["units"][new] = new_lat(e, lat, name)
        if code == "F" and e.get("fj_breakdown") and state.steps(e) == 2 and e.get("vof_rating") == "A":
            fj = s.get("_fj_r")
            if fj not in ("1", "2"):
                raise rules.Violation(
                    f"{name}: F hit on the second step of an A-rated Fallschirmjaeger squad: draw an Action card, R# column 2: --fj=1 (two A Fire Teams) or --fj=2 (S and A) [CSR 3 p.14, Normandy p.48]"
                )
            if fj == "1":
                s["units"][new].update(vof_rating="A", range="C")
                if e.get("ammo"):
                    m = e["ammo"]
                    half = m.get("points", 0) // 2
                    s["units"][new]["ammo"] = dict(m, points=half)
                    m["points"] = m.get("points", 0) - half
                    prot.append(
                        f"{new}: A • C with {half} MG ammo, remaining {m['points']} with the last team (rounded up for the second team, 7.18.1B)"
                    )
                prot.append("FJ R#1/2: two A-rated Fire Teams [CSR 3 p.14]")
            else:
                prot.append("FJ R#2/2: one S-rated and one A-rated Fire Team [CSR 3 p.14]")
        prot.append(
            f"{name}: one step becomes {lat} ({new}) on {e['card']}, Pinned"
            + (state.open_reading(s, "U27_mtr_sec_not_fa") if e.get("breakdown") == "mtr_sec" else "")
        )
    e["steps"] = state.steps(e) - 1
    prot.append(f"{name}: flip to {e['steps']} steps")


def _mortar_section(s, e):
    """'US' for a US Mortar Section (campaign), 'DE' for a German 81mm Mortar Section, otherwise None."""
    if e.get("breakdown") == "mtr_sec" and state.is_campaign(s):
        return "US"
    if e.get("breakdown") == "mtr_sec_de":
        return "DE"
    return None


def last_step_conversion(s, name, prot, pin=True):
    """After a step loss: a Mortar Section's last step becomes the final Mortar Team; a unit without a 1-step side
    (squads) turns its last step into the generic team of 'last_step' [6.4.3 p.47]. True if one of them applied.
    shared by Combat Effects and Heat Casualties (Naktong M1)."""
    e = s["units"][name]
    if breakdown_step(s, name, None, prot):
        return True  # Mortar Section: the last step became the final Mortar Team
    if not (state.steps(e) == 1 and e.get("last_step") and not state.is_lat(e)):
        return False
    lat2 = e["last_step"]
    new2 = commands.new_name(s, lat2, side=e["side"], card=e["card"])
    s["units"][new2] = new_lat(e, lat2, name)
    if not pin and rules.PINNED not in e["status"]:
        # a step lost outside combat (Heat Casualties) is no HIT: the team takes over the squad's Pinned state only
        s["units"][new2]["status"] = [m for m in s["units"][new2]["status"] if m != rules.PINNED]
    if e.get("last_step_values"):
        s["units"][new2].update(e["last_step_values"])  # Normandy p.48: A squad ends as an A-rated Fire Team
        if e.get("ammo"):
            s["units"][new2]["ammo"] = copy.deepcopy(e["ammo"])
            # [RULE 7.18.2 p.61]: the last ammo point fired this turn passes its Out of Ammo state to the team
            for _k in ("ammo_empty", "out_of_ammo"):
                if e.get(_k):
                    s["units"][new2][_k] = True
            if not e["ammo"].get("points") and not e.get("out_of_ammo"):
                s["units"][new2]["ammo_empty"] = True
        prot.append(
            f"{new2}: {' • '.join(str(v) for v in e['last_step_values'].values()) if isinstance(e['last_step_values'], dict) else e['last_step_values']} with the remaining ammo [Normandy p.48, 7.18.1B]"
        )
    remove_from_play(
        s,
        name,
        prot,
        f"no 1-step side, last step becomes a generic {lat2} ({new2}); can be reconstituted from 2-3 teams [6.4.3 p.47, FM1 p.31]",
        successor=new2,
    )
    return True


def breakdown_step(s, name, code, prot):
    """Mortar Section breakdown, the one copy for reduce_unit and cmd_hit. Returns True if handled.
    code F/A: the hit step of a multi-step section becomes a named 1-step Mortar Team on its Fire Team side
    [CSR 2 p.13, CSR 4 p.14: German only from the last two steps]. code None: the last remaining step becomes the
    final 1-step team and the section is Removed from Play [CSR 2 p.13, CSR 4 p.14, Normandy p.47/48]."""
    e = s["units"][name]
    kind = _mortar_section(s, e)
    if kind is None:
        return False
    ammo_pts = (e.get("ammo") or {}).get("points")
    if code is None:
        if state.steps(e) != 1:
            return False
        if kind == "DE":
            team = mortar_team_de(s, e, "2/81mm Mtr")
            team["status"] = [rules.PINNED]
            team_name = commands.new_name(s, "2/81mm Mtr", side=e["side"])
            s["units"][team_name] = team
            remove_from_play(
                s,
                name,
                prot,
                f"last step becomes {team_name} (G! • C-V, ammo {(team.get('ammo') or {}).get('points')}) [CSR 4 p.14, Normandy p.48]",
                successor=team_name,
            )
        else:
            # [CSR 2 p.13] 'If only one step remains, place a 1-step mortar team'
            team_name = mortar_team_name(s, ("3/Mtr", "2/Mtr", "1/Mtr"))
            team = mortar_team(s, e, team_name)
            team["status"] = [rules.PINNED]
            team["radio"] = [dict(g) for g in comms.radios_of(e)]
            e["radio"] = []
            s["units"][team_name] = team
            remove_from_play(
                s,
                name,
                prot,
                f"last step becomes 1-step Mortar Team {team_name} (G! • C-L, ammo {(team.get('ammo') or {}).get('points')}) [CSR 2 p.13]",
            )
        return True
    if code not in ("F", "A") or (kind == "DE" and state.steps(e) != 2):
        return False
    if kind == "US":
        # [CSR 2 p.13, Normandy p.47] F/A hit on the Mortar Section: the step becomes a named 1-step Mortar Team (Fire Team side)
        team_name = mortar_team_name(s, ("1/Mtr", "2/Mtr", "3/Mtr"))
        team = mortar_team(s, e, team_name)
        team["status"] = [rules.FIRE_TEAM_SIDE, rules.PINNED]
        s["units"][team_name] = team
        prot.append(
            f"{name}: one step becomes {team_name} on the Fire Team side (S • C), Pinned, with the same ammo ({ammo_pts}) [CSR 2 p.13, 7.18.1B p.60]"
        )
    else:
        # [CSR 4 p.14, Normandy p.48] last two steps: 1/81mm Mtr (Fire Team side) and 2/81mm Mtr, full ammo
        team = mortar_team_de(s, e, "1/81mm Mtr")
        team["status"] = [rules.FIRE_TEAM_SIDE, rules.PINNED]
        s["units"][commands.new_name(s, "1/81mm Mtr", side=e["side"])] = team
        prot.append(
            f"{name}: one step becomes 1/81mm Mtr on the Fire Team side (S • C), Pinned, ammo {ammo_pts} [CSR 4 p.14, Normandy p.48]"
        )
    return True


def mortar_team_name(s, order_of):
    for team_name in order_of:
        if team_name not in s["units"] and team_name not in s.get("removed_from_play", []):
            return team_name
    return commands.new_name(s, "Mtr Team")


def mortar_team(s, section, team_name):
    """1-step Mortar Team from the Section: values from the setup data (CSR 2), ammo as the Section (7.18.1B)."""
    team = copy.deepcopy(s.get("setup_units", {}).get(team_name) or s.get("reserve_units", {}).get("1/Mtr", {}))
    team.update(
        card=section["card"],
        area=section.get("area", "open"),
        platoon=section.get("platoon"),
        attached_to=list(section.get("attached_to", [])),
        target=None,
        steps=1,
        side="US",
        experience=section.get("experience", "Line"),
    )
    team.setdefault("type", "Weapons Team")
    team["radio"] = []
    if section.get("ammo"):
        team["ammo"] = copy.deepcopy(section["ammo"])
    return team


def mortar_team_de(s, section, team_name):
    """[CSR 4 p.14, Normandy p.48] German 81mm Mortar Team from the Section, full ammo of the Section."""
    team = copy.deepcopy(s.get("mtr_team_de", {}).get(team_name, {}))
    team.update(
        card=section["card"],
        area=section.get("area", "open"),
        target=None,
        steps=1,
        side="Enemy",
        experience=section.get("experience", "Line"),
        spotted=section.get("spotted", True),
        type_name=team_name,
        package=section.get("package"),
        pc_origin=section.get("pc_origin"),
    )
    team.setdefault("type", "Weapons Team")
    team.setdefault("status", [])
    if section.get("ammo"):
        team["ammo"] = copy.deepcopy(section["ammo"])
    return team


def _human_wave_result(name, result, effect, prot):
    """[RULE 8.14 p.68] 'Human Waves are never Pinned'; 'All Hit results are treated as C (Casualty). (For example a
    result of "PL" should be read as "CC".)'"""
    if result == "PIN":
        prot.append(f"{name} is a Human Wave unit: never Pinned, PIN has no effect [8.14 p.68]")
        return "MISS", effect
    if result == "HIT" and effect:
        prot.append(f"{name} is a Human Wave unit: {effect} counts as {'C' * len(effect)} [8.14 p.68]")
        return result, "C" * len(effect)
    return result, effect


def _apply_hit(s, name, e, effect, prot):
    """A HIT: one letter per step lost (a 1-step unit reads the first only), then the unit is Pinned [6.4.3 p.47]."""
    if not effect:
        raise rules.Violation(
            f"HIT: draw a second Action card, read Hit Effects under {comms.experience(e)} and give the letters [RULE 6.4.3 p.47]"
        )
    codes = list(effect[:1]) if state.steps(e) == 1 else list(effect[:2])
    if e.get("breakdown_note") and any(c in "FA" for c in codes):
        prot.append(f"{name}: {e['breakdown_note']} [6.4.3 p.47]")
    for code in codes:
        if code not in rules.LAT_TYPES:
            raise rules.Violation(f"Unknown effect {code} (C P L F A)")
        if name in s["units"]:
            reduce_unit(s, name, code, prot)
    if name not in s["units"] or last_step_conversion(s, name, prot):
        return
    e = s["units"][name]
    if e.get("human_wave"):
        prot.append(f"{name} stays unpinned (Human Wave) [8.14 p.68]")
    else:
        commands.mark(e, rules.PINNED)
        prot.append(f"{name} Pinned (every HIT pins) [6.4.3]")


def cmd_hit(s, args):
    """hit <unit> <HIT|PIN|MISS> [letters] [--fj=<R#>]: the Combat Effects result of one unit [6.4.2, 6.4.3 p.47]."""
    fjo = [a for a in args if a.startswith("--fj=")]
    args = [a for a in args if not a.startswith("--fj=")]
    s["_fj_r"] = fjo[0].split("=", 1)[1] if fjo else None
    if len(args) < 2:
        raise rules.Violation("hit <unit> <HIT|PIN|MISS> [letters] (L118)")
    name, result = args[0], args[1].upper()
    effect = args[2].upper() if len(args) > 2 else ""
    if result not in ("HIT", "PIN", "MISS"):
        raise rules.Violation("Result must be HIT, PIN or MISS")
    e = state.unit(s, name)
    if e.get("vehicle"):
        # VOF against vehicles is resolved in 3.6 on the AT table, not with Combat Effects
        raise rules.Violation(f"{name} is a vehicle: VOF against vehicles is resolved with 'at' in 3.6 [10.5.3 p.72]")
    if e.pop("crew_hit_open", None) and result != "HIT":
        raise rules.Violation(f"{name} is a vehicle crew team and takes a HIT [10.7 Knocked Out]")
    prot = []
    human_wave = bool(e.get("human_wave"))
    if human_wave:
        result, effect = _human_wave_result(name, result, effect, prot)
    if result == "HIT":
        _apply_hit(s, name, e, effect, prot)
    elif result == "PIN":
        commands.mark(e, rules.PINNED)
        prot.append(
            f"{name} Pinned" + (" (its VOF becomes 'All Pinned' +2, adjust marker in 3.8)" if fire.is_firing(e) else "")
        )
    elif state.pinned(e) and not human_wave:
        e["status"].remove(rules.PINNED)
        prot.append(f"{name}: MISS, remove Pinned marker [6.4.2A]")
    else:
        prot.append(f"{name}: no effect")
    if s.get("combat_open") and name in s["combat_open"]:
        s["combat_open"].remove(name)
    s.pop("_fj_r", None)
    state.save_state(s, f"Combat Effects {name}: {result} {effect}; " + "; ".join(prot), "6.4.2 p.47, 6.4.3 p.47")
    briefing.print_board(prot, s)
    if s.get("combat_open"):
        print("Still open: " + ", ".join(s["combat_open"]))
        if s["phase"] == "3.7.4":
            print_next_group(s)


def ammo(e):
    return e.get("ammo")


def fire_ammo(e):
    """ammo used by direct fire (VOF, Concentrate Fire). Rockets serve Grenade Attacks only (7.18.1D), the S fire of
    rocket teams and AT guns with a Small Arms VOF tracks no ammo (Normandy CSR 7)."""
    m = ammo(e)
    if not m or m.get("type") == "RKT" or e.get("out_of_ammo"):
        return None
    if e.get("type") == "AT Gun" and e.get("vof_rating") == "S":
        return None
    return m


def ammo_capacity(e):
    m = ammo(e)
    if not m or e.get("ammo_carriers_abstract"):
        return None
    k = rules.AMMO_CAPACITY.get(m["type"])
    return None if k is None else k * state.steps(e)


def ammo_use(s, n, e, points, reason, prot):
    m = ammo(e)
    if not m:
        return
    old = m["points"]
    m["points"] = max(0, old - points)
    prot.append(f"{n}: {points} {m['type']} ammo ({reason}), {old} to {m['points']} [7.18 p.59]")
    if m["points"] == 0 and not e.get("out_of_ammo"):
        if state.option(s, "U22_ammo_empty_in_clean_up") and s["phase"] == "3.7.4":
            e["ammo_empty"] = True
            prot.append(
                f"{n}: last ammo fired; Out of Ammo effects in Clean Up{state.open_reading(s, 'U22_ammo_empty_in_clean_up')} [7.18.2 p.61]"
            )
        else:
            out_of_ammo(s, n, e, prot)


def cf_ammo_short(e):
    """[RULE 7.18.4 p.61] 'Don't allow a Concentrated Fire attempt if you know a unit doesn't have enough ammunition
    for the turn (one per attempt and one in the Combat Effects Segment). This applies to enemies too.'"""
    m = fire_ammo(e)
    return bool(m) and m.get("points", 0) < 2


def out_of_ammo(s, n, e, prot):
    """[RULE 7.18.2 p.61, 8.11 p.68] 1-step weapons team with S or A/S reverse: flip to the Fire Team side; otherwise Out of Ammo marker
    (VOF S, range Close). [RULE 7.18.1D p.60] SG! unit with rockets only loses the Close Range Grenade Attacks."""
    e.pop("ammo_empty", None)
    m = ammo(e)
    if e["side"] == "Enemy" and e.get("vehicle"):
        # (Stead BGG 3579993): 'An out of ammo tank is immediately removed from play'
        enemy.remove_enemy(s, n, prot, reason="out of ammo, the tank leaves (BGG 3579993)")
        return
    if m and m["type"] == "RKT" and e.get("grenade_ranged") and e.get("vof_rating") == "S":
        e["grenade_ranged"] = False
        e["rkt_empty"] = True
        prot.append(f"{n}: no rockets left, no Grenade Attacks at range; Basic VOF S remains [7.18.1D p.60]")
        return
    if state.steps(e) == 1 and e.get("fire_team_side") and e.get("ft_vof") in ("S", "A/S") and e["type"] != "Squad":
        commands.mark(e, rules.FIRE_TEAM_SIDE)
        e["ooa_flip"] = True  # only this flip is undone by resupply, not a HIT-caused one
        fire.cease_fire(e)
        prot.append(
            f"{n}: Out of Ammo, flip to the Fire Team side [7.18.2 p.61]"
            + (
                " (enemy: Spotted attempts Fall Back instead of the hierarchy in the Activity Check, 8.11)"
                if e["side"] == "Enemy"
                else ""
            )
        )
        if e["side"] == "Enemy":
            e["ooa_fallback"] = True
        return
    e["out_of_ammo"] = True
    prot.append(f"{n}: Out of Ammo marker: VOF S, range Close until resupply [7.18.2 p.61, 8.11 p.68]")
    los_now = (
        geometry.los(
            s,
            e["card"],
            e["target"],
            ha=geometry.height_bonus(s, e),
            hb=geometry.card_height_bonus(s, e["target"], geometry.opponent_of(e)),
        )[0]
        if e.get("target") and e["target"] in s["cards"] and e["target"] != e["card"]
        else False
    )
    if e.get("target") and e["target"] != e["card"] and los_now and not geometry.in_range(s, e, e["target"]):
        # without LOS (e.g. Illumination removed) the Cease Fire of cease_fire_on_los_loss follows; no VOF shift message
        # [RULE 6.3.2 p.43 example]: "The PDF stays the same ... but its VOF is moved to the adjacent card" (replaces)
        fire_card = fire.effective_fire_target(s, n)
        if (
            fire_card != e["card"]
            and state.units_on(s, fire_card, e["side"])
            and not state.valid_target(s, fire_card, e["side"])
        ):
            prot.append(
                f"{n}: target {e['target']} now out of range and own units on {fire_card} along the PDF: Cease Fire, reopens per 6.1.1 [6.3.2, 6.1.1]"
            )
            fire.cease_fire(e)
        else:
            e["_range_vof"] = fire_card
            prot.append(
                f"{n}: target {e['target']} now out of range (Close): PDF stays, VOF marker S moves to {fire_card} [6.3.2 p.43, 7.18.2]"
            )


def ammo_surplus(s, n, e, from_, prot):
    """[RULE 7.18 Note p.60, 8.11 p.68] A unit carrying more than its capacity leaves the rest behind when moving."""
    k = ammo_capacity(e)
    m = ammo(e)
    if k is None or not m or m["points"] <= k:
        return
    remainder = m["points"] - k
    m["points"] = k
    depot = state.card(s, from_).setdefault("ammo", {})
    depot[m["type"]] = depot.get(m["type"], 0) + remainder
    prot.append(f"{n} can only carry {k} {m['type']} ammo: {remainder} stay behind on {from_} [5.1.6A p.33, 7.18 p.60]")


def cmd_ammo(s, args):
    if args and args[0] == "depot":
        rules.need(args, 4, "ammo depot <card> <type> <n>")
        card_id, type_, number = args[1], args[2], rules.int_value(args[3], "ammo depot <n>")
        ev = s.get("event_ammo")
        if not ev:
            raise rules.Violation("Ammo on cards only via event (Ammo Resupply) or dropping (drop <unit> <type>:<n>)")
        if state.card(s, card_id)["row"] != geometry.first_card_row(s) or state.card(s, card_id).get("staging"):
            raise rules.Violation(
                "Ammo Resupply: a card of mission row 1 ("
                + ", ".join(
                    k for k, c in s["cards"].items() if c["row"] == geometry.first_card_row(s) and not c.get("staging")
                )
                + ") [Normandy M1 p.18]"
            )
        if number != 4 or type_ not in rules.AMMO_CAPACITY:
            raise rules.Violation("Ammo Resupply: 'four of any one type of ammo' (MG, MTR, RKT) [Normandy M1 p.18]")
        depot = state.card(s, card_id).setdefault("ammo", {})
        depot[type_] = depot.get(type_, 0) + 4
        s.pop("event_ammo", None)
        prot = [f"4 {type_} ammo on {card_id}; pick up with 4.2.2h --what={type_}:<n> [Normandy M1 p.18, 7.18.3 p.61]"]
        state.save_state(s, "; ".join(prot), "Normandy M1 p.18")
        briefing.print_board(prot, s)
        return
    for n, e in s["units"].items():
        m = ammo(e)
        if m:
            print(
                f"- {n} ({e['side']}): {m['type']} {m['points']}"
                + (f" of {m.get('start')}" if m.get("start") else "")
                + (" OUT OF AMMO" if e.get("out_of_ammo") else "")
                + (f", carries {ammo_capacity(e)}" if ammo_capacity(e) is not None else "")
            )
        if e.get("carries_ammo"):
            print(f"- {n} additionally carries {e['carries_ammo']['points']} {e['carries_ammo']['type']}")
    for k, c in s["cards"].items():
        if c.get("ammo"):
            print(f"- on {k}: " + ", ".join(f"{t} {v}" for t, v in c["ammo"].items() if v))


def ammo_pick_up(s, recipient, name, what, prot):
    """[RULE 5.1.6 p.32, 7.18.3 p.61] Pick up ammo from the card; an Out of Ammo unit is resupplied."""
    type_, number = ammo_spec(what)
    depot = state.card(s, recipient["card"]).setdefault("ammo", {})
    if depot.get(type_, 0) < number:
        raise rules.Violation(f"On {recipient['card']} there are only {depot.get(type_, 0)} {type_}")
    m = ammo(recipient)
    if m and m["type"] == type_:
        k = ammo_capacity(recipient)
        new = m["points"] + number if k is None else min(k, m["points"] + number)
        taken = new - m["points"]
        m["points"] = new
        depot[type_] -= taken
        prot.append(f"{name} picks up {taken} {type_} (now {new}) [7.18.3 p.61]")
        if recipient.get("out_of_ammo") or recipient.pop("ooa_flip", None):
            # a Fire-Team flip caused by a HIT (6.4.3) is not undone by resupply, only the Out-of-Ammo flip
            recipient.pop("out_of_ammo", None)
            recipient.pop("ooa_fallback", None)  # the O-A Fall Back belongs to the Out-of-Ammo flip
            if state.fire_team_side(recipient):
                recipient["status"].remove(rules.FIRE_TEAM_SIDE)
            prot.append(
                f"{name}: resupplied, Out of Ammo marker removed or back to the Good Order side, fires again with original VOF [7.18.3 p.61]"
            )
        if recipient.get("rkt_empty"):
            recipient["grenade_ranged"] = True
            recipient.pop("rkt_empty")
        return
    capacity = state.steps(recipient) * rules.AMMO_CAPACITY.get(type_, 1)
    tm = recipient.get("carries_ammo")
    if tm and tm["type"] != type_:
        raise rules.Violation(f"{name} already carries {tm['type']}; only one ammo type per unit [5.1.6A p.33]")
    if recipient.get("carries_casualties"):
        raise rules.Violation(f"{name} carries Casualties; Casualties or one ammo type [5.1.6A p.33]")
    have = tm["points"] if tm else 0
    if have + number > capacity:
        raise rules.Violation(
            f"{name} can carry at most {capacity} {type_} ({state.steps(recipient)} step(s)) [5.1.6A p.33]"
        )
    recipient["carries_ammo"] = {"type": type_, "points": have + number}
    depot[type_] -= number
    prot.append(f"{name} picks up {number} {type_} for transport [5.1.6 p.32]")


def ammo_spec(what):
    """'<type>:<n>' (e.g. MG:2) -> (type, n); a Violation instead of ValueError for user input."""
    type_, sep, number = str(what).partition(":")
    if not sep or not type_:
        raise rules.Violation(f"Ammo as <type>:<n> (e.g. MG:2), got '{what}' [7.18.3 p.61]")
    n = rules.int_value(number, f"ammo {type_}")
    if n < 1:
        raise rules.Violation(f"Ammo {type_}: at least 1 point, got {n} [7.18.3 p.61]")
    return type_, n


def ammo_drop(s, e, n, what, prot):
    type_, number = ammo_spec(what)
    tm = e.get("carries_ammo")
    if not tm or tm["type"] != type_ or tm["points"] < number:
        raise rules.Violation(f"{n} does not carry {number} {type_}")
    tm["points"] -= number
    if not tm["points"]:
        e.pop("carries_ammo")
    depot = state.card(s, e["card"]).setdefault("ammo", {})
    depot[type_] = depot.get(type_, 0) + number
    prot.append(f"{n} drops {number} {type_} on {e['card']} (no Command) [5.1.6B p.33, 7.18.3 p.61]")


def ammo_3_7_4(s, prot):
    """[RULE 3.7.4 p.17, 7.18.4 p.61, 8.1 p.61] Every ammo-dependent unit that exercises a VOF (even Pinned, even Indirect Lay)
    uses one point."""
    for n, e in list(s["units"].items()):
        if (
            ammo(e)
            and not e.get("out_of_ammo")
            and (fire.is_firing(e) or e.get("indirect"))
            and not e.get("pdf_only")
            and ammo(e)["points"] > 0
        ):
            if e.get("rkt_empty"):
                continue
            if ammo(e)["type"] == "RKT":
                continue  # rockets only for Grenade Attacks (7.18.1D), S fire without ammo
            if e.get("type") == "AT Gun" and e.get("vof_rating") == "S":
                continue  # [Normandy CSR 7 p.15] PAK40/75mm IG: Small Arms VOF 'for which ammo is not tracked'
            ammo_use(s, n, e, 1, "VOF this turn", prot)


PRISONER_TYPES = ("Paralyzed Team", "Litter Team")


def can_capture(x):
    """[RULE 3.5.1 p.16]: 'opposing, Unpinned infantry units with a VOF rating' (no vehicles, no HQs without VOF,
    no Paralyzed/Litter Teams). Also the condition for the guard step."""
    return (
        not x.get("vehicle")  # vehicles are no infantry captors
        and not state.pinned(x)
        and x.get("vof_rating") is not None
        and x["type"] not in (*PRISONER_TYPES, "Casualty")
    )


def _capture_group(s, g, captive, w, guard):
    """Checks of a capture; returns every Paralyzed/Litter Team on the card (one guard step takes them all)."""
    if captive["type"] not in PRISONER_TYPES:
        raise rules.Violation(f"{g} is not a Paralyzed/Litter Team [3.5.1]")
    # K33: all same-side units on the card are Paralyzed/Litter Teams; one guard step takes them all [8.15 p.69]
    group = state.units_on(s, captive["card"], captive["side"])
    if [m for m in group if s["units"][m]["type"] not in PRISONER_TYPES]:
        raise rules.Violation(
            f"{g} is not alone on {captive['card']} (other same-side units besides P/L teams) [3.5.1, K33]"
        )
    captor = [
        m
        for m in state.units_on(s, captive["card"], state.opponent_of_side(captive["side"]))
        if can_capture(s["units"][m])
    ]
    if not captor:
        raise rules.Violation(
            f"On {captive['card']} there is no Good Order unit and no unpinned Assault/Fire Team of the opposing side [RULE 8.15 p.69]"
        )
    if w not in captor or not guard.get("vof_rating"):
        # the guard step must itself satisfy the captor conditions (unpinned infantry with a VOF)
        raise rules.Violation(
            f"Guard {w}: one step of an opposing, unpinned infantry unit (no vehicle, no Paralyzed/Litter Team) with a "
            f"printed VOF on the same card; possible: {', '.join(captor)} [RULE 3.5.1 p.16, 8.15 p.69]"
        )
    return group


def _detach_guard(s, w, guard, captive, group, prot):
    """One step of the guard unit leaves play with the prisoners [RULE 8.15 p.69]."""
    if guard["side"] == "US":
        # [RULE 8.15 p.69] 'return between missions and retain their original Experience Level (it is not considered
        # an LAT). Make a note of the guard step and its Experience Level on your mission log.' (K35)
        s.setdefault("guards", []).append(
            {
                "unit": w,
                "experience": guard.get("experience"),
                "card": captive["card"],
                "turn": s["turn"],
                "prisoners": list(group),
            }
        )
        prot.append(
            f"{w}: guard step {guard.get('experience')} noted on the mission log, returns between missions with this "
            f"Experience Level, not an LAT [8.15 p.69]"
        )
    if state.steps(guard) > 1:
        guard["steps"] -= 1
        prot.append(f"{w} details one step as guard (now {guard['steps']} steps), guard Removed from Play [8.15]")
        if state.steps(guard) == 1 and guard.get("last_step"):
            new = commands.new_name(s, guard["last_step"], side=guard["side"])
            s["units"][new] = new_lat(guard, guard["last_step"], w)
            s["units"][new]["status"] = []
            remove_from_play(s, w, prot, f"last step becomes {guard['last_step']} ({new})", successor=new)
    else:
        remove_from_play(s, w, prot, "detached as guard [8.15]")


def _capture_casualties(s, captive, prot):
    """[RULE 3.5.1 p.16] enemy casualties on a friendly-occupied card are captured automatically."""
    c = state.card(s, captive["card"])
    if captive["side"] == "Enemy" and c.get("casualties_enemy") and not state.units_on(s, captive["card"], "Enemy"):
        # [RULE 3.5.1 p.16] enemy casualties on a friendly-occupied card are captured automatically
        n_cas = c["casualties_enemy"]
        s["prisoners"] = s.get("prisoners", 0) + n_cas
        c["casualties_enemy"] = 0
        prot.append(f"{captive['card']}: {n_cas} enemy Casualties captured, remove marker [3.5.1, 8.15.1]")
        campaign.book_xp(
            s,
            n_cas * (campaign.xp_table(s, "enemy_casualty_step") or 1),
            f"{n_cas} enemy Casualties captured ({captive['card']})",
            prot,
        )


def _cease_fire_after_capture(s, captive, prot):
    """Fire on the card whose only target were the prisoners: Cease Fire, then 6.1.1 anew [RULE 6.1.2, 6.3.3 p.43]."""
    # [RULE 6.1.2, 6.3.3 p.43]: fire on the card whose only target were the prisoners: Cease Fire, then 6.1.1 anew
    card_id, side = captive["card"], state.opponent_of_side(captive["side"])
    if not state.valid_target(s, card_id, side):
        for n, e in s["units"].items():
            if e["side"] == side and fire.is_firing(e) and fire.effective_fire_target(s, n) == card_id:
                fire.cease_fire(e)
                prot.append(
                    f"{n}: no target left on {card_id} after the capture: Cease Fire, opens fire anew per 6.1.1 [6.3.3]"
                )
        fire.open_fire(s, prot)


def cmd_capture(s, args):
    """[RULE 3.5.1 p.16, 8.15 p.69, Normandy p.13 'Both sides take prisoners'] Paralyzed/Litter Team alone with unpinned infantry with VOF:
    one guard step and the prisoners are Removed from Play."""
    if s["phase"] != "3.5.1":
        raise rules.Violation("Taking prisoners only in the Capture Segment 3.5.1")
    rules.need(args, 2, 'capture "<Paralyzed/Litter Team>" "<guard unit>"')
    g, w = args[0], args[1]
    captive, guard = state.unit(s, g), state.unit(s, w)
    group = _capture_group(s, g, captive, w, guard)
    prot = []
    st = sum(state.steps(s["units"][m]) for m in group)
    # name the markers that leave the board with the prisoners (e.g. Pinned)
    marks = sorted({x for m in group for x in s["units"][m].get("status", [])})
    for m in group:
        # removed_from_play keeps the names that guards[].prisoners refers to (new_name skips them)
        remove_from_play(s, m, prot, "captured [8.15]", captured=True)
    _detach_guard(s, w, guard, captive, group, prot)
    if captive["side"] == "Enemy":
        s["prisoners"] = s.get("prisoners", 0) + st
        campaign.book_xp(
            s, st * (campaign.xp_table(s, "prisoner_step") or 2), f"{st} prisoners ({', '.join(group)})", prot
        )
    else:
        s["us_captured"] = s.get("us_captured", 0) + st
    mk = f", remove the counter with its {', '.join(marks)} marker" if marks else ""
    prot.insert(
        0, f"{', '.join(group)} ({captive['side']}) captured, Removed from Play{mk}; one guard step for all [8.15]"
    )
    _capture_casualties(s, captive, prot)
    _cease_fire_after_capture(s, captive, prot)
    m = fire.update_activity(s)
    if m:
        prot.append(m)
    state.save_state(s, "; ".join(prot), "3.5.1 p.16, 8.15 p.69")
    briefing.print_board(prot, s)
