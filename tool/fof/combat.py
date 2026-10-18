"""Net combat modifier, hit effects, unit reduction, ammunition, prisoners (6.4, 7.18, 8.15)."""

import copy

from . import briefing, campaign, commands, comms, enemy, fire, geometry, rules, state


def cc_row(s, e):
    """[RULE 5.2.3 p.36] Two C&C values: the higher one if any fire comes across a dark edge; the lower one if all
    fire comes across white edges, as Incoming/indirect mortar fire, or from within the card itself."""
    kid = e["karte"]
    c = state.card(s, kid)
    if c.get("cc2") is None:
        return (f"Terrain {c['terrain']}", c.get("cc", 0))
    dark = []
    for x in fire.vof_entries(s, kid):
        if x[3] not in (None, e["seite"]) or x[4] is None or x[4] == kid:
            continue  # external (Incoming, Indirect), Point Blank, or does not hit this side
        if geometry.edge(c, geometry.direction(s, kid, x[4])) != "weiss":
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
    tr = [x for x in fire.vof_entries(s, e["karte"]) if x[3] in (None, e["seite"]) and x[0] != "Mines"]
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
        mw = min([x["wert"] for x in c.get("extern", []) if x["typ"] == "Mines"] or [-4])
        candidate.append(("Mines! VOF (mine check lost)", mw, "Mines"))  # [RULE 7.9.1 p.54, 6.3.6]
    for sn, sz in s.get("sniper_ziele", {}).items():
        if sz == name and sn in s["einheiten"]:
            candidate.append((f"Sniper VOF from {sn}", -3, "Sniper"))  # [RULE 7.15 p.57]
    if e.get("grenade"):
        candidate.append(("Grenade VOF (cumulative)", sum(e["grenade"]), "G"))
    if not candidate and c.get("grenade_miss"):
        candidate.append(("Grenade Miss als VOF", -1, "G"))
    return candidate


def _rows_for(s, e, c, base):
    """NCM rows for one fire effect as the base VOF [RULE 6.4 p.45, Charts & Tables 1]."""
    type_ = base[2]
    rows = [(base[0], base[1])]
    if c.get("grenade_miss") and base[0] != "Grenade Miss als VOF":
        rows.append(("Grenade Miss", -1))
    if fire.crossfire(s, e["karte"], e["seite"]):
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
        rows.append((f"Cover {cv['id']} {cv['typ']} lost (Critical Hit Grenade) [7.10.3]", 0))
    elif cv and e.get("cf_critical"):
        rows.append((f"Cover {cv['id']} {cv['typ']} lost (Critical Hit Concentrated Fire) [7.11.4]", 0))  # L154
    elif cv:
        rows.append((f"Cover {cv['id']} {cv['typ']}", cv["wert"]))
    if state.pinned(e):
        rows.append(("Pinned", +1))
    if "Exposed" in e["status"]:
        rows.append(("Exposed", -2))
    if type_ in rules.TERRAIN_LIKE_INCOMING and c.get("burst") is not None:
        rows.append(("Burst symbol", c["burst"]))  # [RULE 5.2.3 p.36, Charts 1: only Incoming and indirect mortar fire]
    smoke = [x.get("wert") or 0 for x in c.get("extern", []) if x["typ"] == "Smoke"]
    if smoke and type_ not in ("Incoming", "AirStrike", "Mines", "G") and max(smoke):
        rows.append(("Smoke (best value)", max(smoke)))  # [RULE 5.4 p.38]
    if cv and type_ in ("Incoming", "AirStrike", "G"):
        st = sum(
            state.steps(s["einheiten"][m])
            for m in state.units_on(s, e["karte"], e["seite"])
            if s["einheiten"][m].get("bereich") == cv["id"]
        )
        if st > 3:
            rows.append((f"Stacking {st} steps under cover", -(st - 3)))
    sk = geometry.visibility_on_card(s, e["karte"])
    if sk and type_ not in ("Incoming", "AirStrike", "G", "Mines"):
        il = geometry.illumination_value(s, e["karte"])
        rows.append(
            ("Visibility (ch. 9)" + (f", illumination {il:+d} included" if il is not None else ""), sk)
        )  # [RULE 9.0 p.69]
    return rows


def ncm_rows(s, name):
    """[RULE 6.4 p.45] 'When multiple VOF are affecting a card, take into account their value after modifiers ... Light levels
    (9.0) and cover modifiers (5.3) may modify different weapons in different ways' (Clarification 3): every fire effect is
    evaluated with its own modifiers, the strongest result counts (L61 Incoming, L129 all effects, e.g. Grenade at night)."""
    e = state.unit(s, name)
    c = state.card(s, e["karte"])
    candidate = _fire_effects(s, e, c, name)
    if not candidate:
        raise rules.Violation(f"No VOF against {name} on {e['karte']} [3.7.4]")
    best = None
    for cand in candidate:
        rows = _rows_for(s, e, c, cand)
        if best is None or sum(v for _, v in rows) < sum(v for _, v in best):
            best = rows
    return best


def _ncm_total(s, name):
    if s["phase"] == "3.7.4" and name in s.get("kampf_ncm", {}):
        rows = [tuple(z) for z in s["kampf_ncm"][name]]
    else:
        rows = ncm_rows(s, name)
    raw = sum(v for _, v in rows)
    return max(-4, min(6, raw)), raw, rows


def ncm_groups(s):
    """L155 (V18): open Combat Effects card by card, per card one group per NCM value.
    Returns [(card, ncm, [units])] in board order (cards by number, groups by NCM, units in protocol order)."""
    by_card = {}
    for n in s.get("kampf_offen", []):
        if n not in s["einheiten"]:
            continue
        try:
            ncm, _raw, _rows = _ncm_total(s, n)
        except rules.Violation:
            continue
        by_card.setdefault(s["einheiten"][n]["karte"], {}).setdefault(ncm, []).append(n)
    out = []
    for k in sorted(by_card, key=lambda x: (state.card(s, x)["reihe"], state.card(s, x)["spalte"])):
        for ncm in sorted(by_card[k]):
            out.append((k, ncm, by_card[k][ncm]))
    return out


def print_next_group(s):
    """L155: the next NCM group as a numbered list, so the player sees how many cards to draw at once."""
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
        e = s["einheiten"][n]
        print(f"  {i}. {n} ({comms.experience(e)}, {state.steps(e)} step{'s' if state.steps(e) > 1 else ''})")
    print("  NCM rows:")
    for t_, v_ in rows:
        print(f"    {t_} {v_:+d}")  # one per line (L156)
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
    if args and args[0] in ("weiter", "next", "gruppe", "group"):
        if s["phase"] != "3.7.4":
            raise rules.Violation("ncm next only in the Combat Effects Segment 3.7.4")
        if not ncm_groups(s):
            print("No Combat Effects open [3.7.4]")
            return
        print_next_group(s)
        return
    name = args[0]
    if s["phase"] == "3.7.4" and name in s.get("kampf_ncm", {}):
        rows = [tuple(z) for z in s["kampf_ncm"][name]]  # state on entering 3.7.4 [RULE 3.7.4 p.17]
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
        f'Draw an Action card, Combat Resolution at {ncm:+d}: HIT, PIN or MISS. Then fof.py hit "{name}" <HIT|PIN|MISS> [effect letters under {comms.experience(s["einheiten"][name])}]'
    )


LAT_VALUES = {
    "Assault Team": ("A", "P"),
    "Fire Team": ("S", "C"),
    "Litter Team": (None, "C"),
    "Paralyzed Team": (None, "C"),
}  # Normandy Unit Breakdown p.47: Assault TM A/P, Fire Team S/C


def set_lat_values(e, lat):
    e["vof_rating"], e["reichweite"] = LAT_VALUES[lat]


def new_lat(e, lat, origin):
    return {
        "typ": lat,
        "seite": e["seite"],
        "platoon": e.get("platoon"),
        "erfahrung": rules.LAT_EXPERIENCE[lat],
        "karte": e["karte"],
        "bereich": e.get("bereich", "offen"),
        "status": ["Pinned"],
        "steps": 1,
        "herkunft": origin,
        "ziel": None,
        "vof_rating": LAT_VALUES[lat][0],
        "reichweite": LAT_VALUES[lat][1],
        "spotted": e.get("spotted", True),
        "typname": lat,
        **({"deep_bunker": e["deep_bunker"]} if e.get("deep_bunker") else {}),
    }  # [CSR 5 p.14] LATs in a Deep Bunker also have no VOF


def make_casualty(s, e, prot, name):
    c = state.card(s, e["karte"])
    key = "casualties" if e["seite"] == "US" else "casualties_feind"
    c[key] = c.get(key, 0) + 1
    if e["seite"] == "US" and state.is_v4(s):
        s["us_casualties_gesamt"] = (
            s.get("us_casualties_gesamt", 0) + 1
        )  # [RULE 12.4 p.81] all casualties of the mission
    prot.append(f"{name}: one step becomes a Casualty, Casualty marker on {e['karte']} [6.4.3]")


def drop_assets(s, e, name, prot, as_casualty=False, successor=None):
    """Carried casualties and radios: [RULE 6.4.3 p.47] onto the card at the last step (5.1.6E);
    [RULE 4.3.5 p.30] casualty of the last step: radio destroyed on R# 1/2; LAT conversion per option U7."""
    c = state.card(s, e["karte"])
    if e.get("traegt_casualties"):
        c["casualties"] = c.get("casualties", 0) + e["traegt_casualties"]
        prot.append(
            f"{name}: drop carried casualties ({e['traegt_casualties']}) on {e['karte']} [5.1.6E p.33, 6.4.3 p.47]"
        )
        e["traegt_casualties"] = 0
    if e.get("leitungen"):
        c["leitung_assets"] = c.get("leitung_assets", 0) + e["leitungen"]
        prot.append(f"{name}: {e['leitungen']} Phone Line(s) remain as an asset on {e['karte']} (BGG D3)")
        e["leitungen"] = 0
    if e.get("traegt_munition"):
        prot.append(f"{name}: carried ammo is lost (BGG C6)")
        e.pop("traegt_munition")
    if e.get("assets"):  # [RULE 5.1.6E p.33, 6.4.3 p.47] assets drop onto the card
        c.setdefault("assets_boden", []).extend(e["assets"])
        prot.append(f"{name}: Assets {', '.join(e['assets'])} lie on {e['karte']} (Pick Up 4.2.2h) [5.1.6E p.33]")
        e["assets"] = []
    gs = comms.radios_of(e)
    if not gs:
        return
    if successor and not as_casualty and ("optionen" not in s or state.option(s, "U7_lat_behaelt_funk")):
        s["einheiten"][successor]["funk"] = [dict(g) for g in gs]
        prot.append(
            f"{successor} keeps {', '.join(g['typ'] for g in gs)} (cannot give orders as a LAT){state.open_reading(s, 'U7_lat_behaelt_funk')} [5.1.6E p.33]"
        )
    else:
        for g in gs:
            c.setdefault("assets", []).append({"typ": g["typ"], "netz": g["netz"], "schaden_offen": bool(as_casualty)})
        prot.append(
            f"{', '.join(g['typ'] + ' ' + g['netz'] for g in gs)} from {name} on {e['karte']}"
            + (
                ": draw R# 1/2, destroyed on 1 (fof.py radio damage <card> <device> intact|destroyed) [RULE 4.3.5 p.30]"
                if as_casualty
                else f" dropped{state.open_reading(s, 'U7_lat_behaelt_funk')} [5.1.6E p.33]"
            )
        )
    e["funk"] = []


def remove_from_play(s, name, prot, reason, as_casualty=False, successor=None):
    e = s["einheiten"][name]
    if state.is_hq(e) and e["seite"] == "US":
        s.setdefault("rfp_daten", {})[name] = {k: e.get(k) for k in ("ebene", "platoon", "ft_vof")}  # for 6.5.2
    drop_assets(s, e, name, prot, as_casualty, successor)
    if not (
        successor and (s["einheiten"].get(successor) or {}).get("munition")
    ):  # L93: the successor (A fire team) inherits the ammo
        enemy.ammo_lost(e, name, prot)
    elif e.get("munition"):
        prot.append(
            f"ammo marker ({e['munition'].get('punkte')} {e['munition'].get('typ', '')}) stays with {successor} on {e.get('karte')} [Normandy p.48, 7.18.1B]"
        )
    _mk = (["Concentrated Fire marker"] if e.get("cf") else []) + (["Grenade VOF marker"] if e.get("grenade") else [])
    if _mk:  # L70: markers on the removed counter, otherwise only named in Clean Up
        prot.append(f"remove {' and '.join(_mk)} of {name} on {e.get('karte')} (counter off the board) [3.8 p.17]")
    del s["einheiten"][name]
    s.setdefault("removed_from_play", []).append(name)
    if name in s["kommandos"]:
        s["kommandos"][name]["gespart"] = 0
    if e["seite"] == "Feind":
        pk = s.get("pakete", {}).get(str(e.get("paket")))
        if pk:
            pk["im_spiel"] = False
    prot.append(f"{name}: {reason}, Removed from Play [1.2.6, 6.4.3]")


def reduce_unit(s, name, code, prot):
    """6.4.3: one letter applied to one step."""
    e = s["einheiten"][name]
    lat = rules.LAT_TYPES[code]
    if state.is_lat(e):
        if e["typ"] == lat:
            commands.mark(e, "Pinned")
            prot.append(f"{name} is already {lat}: Pinned only [6.4.3]")
        elif code == "C":
            make_casualty(s, e, prot, name)
            drop_assets(s, e, name, prot, as_casualty=True)
            del s["einheiten"][name]
            prot.append(f"{name} ({e['typ']}) becomes a Casualty, remove counter")
        else:
            e["typ"], e["erfahrung"] = lat, rules.LAT_EXPERIENCE[lat]
            # L163 [Normandy Unit Breakdown p.47, K12, E72 counter photo]: generic LAT counter values, Assault Team A • P, Fire Team S • C
            e["vof_rating"], e["reichweite"] = LAT_VALUES[lat]
            if e["vof_rating"] is None:
                e["ziel"] = None
            commands.mark(e, "Pinned")
            prot.append(f"{name} becomes {lat} (swap counter), Pinned [6.4.3]")
        return
    if state.fire_team_side(e):
        if code in ("F", "A"):
            commands.mark(e, "Pinned")
            prot.append(f"{name} (named Fire Team): no further effect, Pinned [6.4.3]")
        elif code == "C":
            make_casualty(s, e, prot, name)
            remove_from_play(s, name, prot, "Casualty", as_casualty=True)
        else:
            new = commands.new_name(s, lat)
            s["einheiten"][new] = new_lat(e, lat, name)
            prot.append(f"{name} becomes {lat} ({new})")
            remove_from_play(s, name, prot, "Fire Team side converted", successor=new)
        return
    if state.steps(e) == 1:
        if code in ("F", "A") and e.get("fire_team_seite"):
            commands.mark(e, "Fire Team side")
            commands.mark(e, "Pinned")
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
            new = commands.new_name(s, lat)
            s["einheiten"][new] = new_lat(e, lat, name)
            prot.append(f"{name}: step becomes {lat} ({new}) on {e['karte']}, Pinned")
        remove_from_play(s, name, prot, "last step converted", as_casualty=(code == "C"), successor=new)
        return
    if code in ("F", "A") and e.get("breakdown") == "mtr_sec" and state.is_v4(s):
        # [CSR 2 p.13, Normandy p.47] F/A hit on the Mortar Section: the step becomes a named 1-step Mortar Team (Fire Team side)
        tn = mortar_team_name(s, ("1/Mtr", "2/Mtr", "3/Mtr"))
        te = mortar_team(s, e, tn)
        te["status"] = ["Fire Team side", "Pinned"]
        s["einheiten"][tn] = te
        prot.append(
            f"{name}: one step becomes {tn} on the Fire Team side (S • C), Pinned, with the same ammo ({(e.get('munition') or {}).get('punkte')}) [CSR 2 p.13, 7.18.1B p.60]"
        )
    elif code in ("F", "A") and e.get("breakdown") == "mtr_sec_de" and state.steps(e) == 2:
        # [CSR 4 p.14, Normandy p.48] last two steps: 1/81mm Mtr (Fire Team side) and 2/81mm Mtr, full ammo
        te = mortar_team_de(s, e, "1/81mm Mtr")
        te["status"] = ["Fire Team side", "Pinned"]
        s["einheiten"][commands.new_name(s, "1/81mm Mtr")] = te
        prot.append(
            f"{name}: one step becomes 1/81mm Mtr on the Fire Team side (S • C), Pinned, ammo {(e.get('munition') or {}).get('punkte')} [CSR 4 p.14, Normandy p.48]"
        )
    elif code == "C":
        make_casualty(s, e, prot, name)
    else:
        new = commands.new_name(s, lat)
        s["einheiten"][new] = new_lat(e, lat, name)
        if code == "F" and e.get("fj_breakdown") and state.steps(e) == 2 and e.get("vof_rating") == "A":
            fj = s.get("_fj_r")
            if fj not in ("1", "2"):
                raise rules.Violation(
                    f"{name}: F hit on the second step of an A-rated Fallschirmjaeger squad: draw an Action card, R# column 2: --fj=1 (two A Fire Teams) or --fj=2 (S and A) [CSR 3 p.14, Normandy p.48]"
                )
            if fj == "1":
                s["einheiten"][new].update(vof_rating="A", reichweite="C")
                if e.get("munition"):
                    m = e["munition"]
                    half = m.get("punkte", 0) // 2
                    s["einheiten"][new]["munition"] = dict(m, punkte=half)
                    m["punkte"] = m.get("punkte", 0) - half
                    prot.append(
                        f"{new}: A • C with {half} MG ammo, remaining {m['punkte']} with the last team (rounded up for the second team, 7.18.1B)"
                    )
                prot.append("FJ R#1/2: two A-rated Fire Teams [CSR 3 p.14]")
            else:
                prot.append("FJ R#2/2: one S-rated and one A-rated Fire Team [CSR 3 p.14]")
        prot.append(
            f"{name}: one step becomes {lat} ({new}) on {e['karte']}, Pinned"
            + (state.open_reading(s, "U27_mtr_sec_nicht_fa") if e.get("breakdown") == "mtr_sec" else "")
        )
    e["steps"] = state.steps(e) - 1
    prot.append(f"{name}: flip to {e['steps']} steps")


def mortar_team_name(s, order_of):
    for tn in order_of:
        if tn not in s["einheiten"] and tn not in s.get("removed_from_play", []):
            return tn
    return commands.new_name(s, "Mtr Team")


def mortar_team(s, section, tn):
    """1-step Mortar Team from the Section: values from the setup data (CSR 2), ammo as the Section (7.18.1B)."""
    te = copy.deepcopy(s.get("aufbau_einheiten", {}).get(tn) or s.get("reserve_einheiten", {}).get("1/Mtr", {}))
    te.update(
        karte=section["karte"],
        bereich=section.get("bereich", "offen"),
        platoon=section.get("platoon"),
        attached_an=list(section.get("attached_an", [])),
        ziel=None,
        steps=1,
        seite="US",
        erfahrung=section.get("erfahrung", "Line"),
    )
    te.setdefault("typ", "Weapons Team")
    te["funk"] = []
    if section.get("munition"):
        te["munition"] = copy.deepcopy(section["munition"])
    return te


def mortar_team_de(s, section, tn):
    """[CSR 4 p.14, Normandy p.48] German 81mm Mortar Team from the Section, full ammo of the Section."""
    te = copy.deepcopy(s.get("mtr_team_de", {}).get(tn, {}))
    te.update(
        karte=section["karte"],
        bereich=section.get("bereich", "offen"),
        ziel=None,
        steps=1,
        seite="Feind",
        erfahrung=section.get("erfahrung", "Line"),
        spotted=section.get("spotted", True),
        typname=tn,
        paket=section.get("paket"),
        pc_herkunft=section.get("pc_herkunft"),
    )
    te.setdefault("typ", "Weapons Team")
    te.setdefault("status", [])
    if section.get("munition"):
        te["munition"] = copy.deepcopy(section["munition"])
    return te


def cmd_hit(s, args):
    fjo = [a for a in args if a.startswith("--fj=")]
    args = [a for a in args if not a.startswith("--fj=")]
    s["_fj_r"] = fjo[0].split("=", 1)[1] if fjo else None
    if len(args) < 2:
        raise rules.Violation("hit <unit> <HIT|PIN|MISS> [letters] (L118)")
    name, result = args[0], args[1].upper()
    effect = args[2].upper() if len(args) > 2 else ""
    e = state.unit(s, name)
    prot = []
    if result == "MISS":
        if state.pinned(e):
            e["status"].remove("Pinned")
            prot.append(f"{name}: MISS, remove Pinned marker [6.4.2A]")
        else:
            prot.append(f"{name}: no effect")
    elif result == "PIN":
        commands.mark(e, "Pinned")
        prot.append(
            f"{name} Pinned" + (" (its VOF becomes 'All Pinned' +2, adjust marker in 3.8)" if fire.is_firing(e) else "")
        )
    elif result == "HIT":
        if not effect:
            raise rules.Violation(
                f"HIT: draw a second Action card, read Hit Effects under {comms.experience(e)} and give the letters [RULE 6.4.3 p.47]"
            )
        codes = list(effect[:1]) if state.steps(e) == 1 else list(effect[:2])
        if e.get("breakdown_hinweis") and any(c in "FA" for c in codes):
            prot.append(f"{name}: {e['breakdown_hinweis']} [6.4.3 p.47]")
        for code in codes:
            if code not in rules.LAT_TYPES:
                raise rules.Violation(f"Unknown effect {code} (C P L F A)")
            if name in s["einheiten"]:
                reduce_unit(s, name, code, prot)
        if name in s["einheiten"]:
            e = s["einheiten"][name]
            if state.steps(e) == 1 and e.get("breakdown") == "mtr_sec_de":
                te = mortar_team_de(s, e, "2/81mm Mtr")
                te["status"] = ["Pinned"]
                tn = commands.new_name(s, "2/81mm Mtr")
                s["einheiten"][tn] = te
                remove_from_play(
                    s,
                    name,
                    prot,
                    f"last step becomes {tn} (G! • C-V, ammo {(te.get('munition') or {}).get('punkte')}) [CSR 4 p.14, Normandy p.48]",
                    successor=tn,
                )
            elif state.steps(e) == 1 and e.get("breakdown") == "mtr_sec" and state.is_v4(s):
                # [CSR 2 p.13] 'If only one step remains, place a 1-step mortar team'
                tn = mortar_team_name(s, ("3/Mtr", "2/Mtr", "1/Mtr"))
                te = mortar_team(s, e, tn)
                te["status"] = ["Pinned"]
                te["funk"] = [dict(g) for g in comms.radios_of(e)]
                e["funk"] = []
                s["einheiten"][tn] = te
                remove_from_play(
                    s,
                    name,
                    prot,
                    f"last step becomes 1-step Mortar Team {tn} (G! • C-L, ammo {(te.get('munition') or {}).get('punkte')}) [CSR 2 p.13]",
                )
            elif state.steps(e) == 1 and e.get("letzter_step") and not state.is_lat(e):
                lat2 = e["letzter_step"]
                new2 = commands.new_name(s, lat2)
                s["einheiten"][new2] = new_lat(e, lat2, name)
                if e.get("letzter_step_werte"):
                    s["einheiten"][new2].update(
                        e["letzter_step_werte"]
                    )  # Normandy p.48: A squad ends as an A-rated Fire Team
                    if e.get("munition"):
                        s["einheiten"][new2]["munition"] = copy.deepcopy(e["munition"])
                    prot.append(
                        f"{new2}: {' • '.join(str(v) for v in e['letzter_step_werte'].values()) if isinstance(e['letzter_step_werte'], dict) else e['letzter_step_werte']} with the remaining ammo [Normandy p.48, 7.18.1B]"
                    )
                remove_from_play(
                    s,
                    name,
                    prot,
                    f"no 1-step side, last step becomes a generic {lat2} ({new2}); can be reconstituted from 2-3 teams [6.4.3 p.47, FM1 p.31]",
                    successor=new2,
                )
            else:
                commands.mark(e, "Pinned")
                prot.append(f"{name} Pinned (every HIT pins) [6.4.3]")
    else:
        raise rules.Violation("Result must be HIT, PIN or MISS")
    if s.get("kampf_offen") and name in s["kampf_offen"]:
        s["kampf_offen"].remove(name)
    s.pop("_fj_r", None)
    state.save_state(s, f"Combat Effects {name}: {result} {effect}; " + "; ".join(prot), "6.4.2 p.47, 6.4.3 p.47")
    briefing.print_board(prot, s)
    if s.get("kampf_offen"):
        print("Still open: " + ", ".join(s["kampf_offen"]))
        if s["phase"] == "3.7.4":
            print_next_group(s)  # L155


def ammo(e):
    return e.get("munition")


def ammo_capacity(e):
    m = ammo(e)
    if not m or e.get("munition_traeger_abstrakt"):
        return None
    k = rules.AMMO_CAPACITY.get(m["typ"])
    return None if k is None else k * state.steps(e)


def ammo_use(s, n, e, points, reason, prot):
    m = ammo(e)
    if not m:
        return
    old = m["punkte"]
    m["punkte"] = max(0, old - points)
    prot.append(f"{n}: {points} {m['typ']} ammo ({reason}), {old} to {m['punkte']} [7.18 p.59]")
    if m["punkte"] == 0 and not e.get("out_of_ammo"):
        if state.option(s, "U22_munition_leer_im_clean_up") and s["phase"] == "3.7.4":
            e["munition_leer"] = True
            prot.append(
                f"{n}: last ammo fired; Out of Ammo effects in Clean Up{state.open_reading(s, 'U22_munition_leer_im_clean_up')} [7.18.2 p.61]"
            )
        else:
            out_of_ammo(s, n, e, prot)


def out_of_ammo(s, n, e, prot):
    """[RULE 7.18.2 p.61, 8.11 p.68] 1-step weapons team with S or A/S reverse: flip to the Fire Team side; otherwise Out of Ammo marker
    (VOF S, range Close). [RULE 7.18.1D p.60] SG! unit with rockets only loses the Close Range Grenade Attacks."""
    e.pop("munition_leer", None)
    m = ammo(e)
    if m and m["typ"] == "RKT" and e.get("grenade_ranged") and e.get("vof_rating") == "S":
        e["grenade_ranged"] = False
        e["rkt_leer"] = True
        prot.append(f"{n}: no rockets left, no Grenade Attacks at range; Basic VOF S remains [7.18.1D p.60]")
        return
    if state.steps(e) == 1 and e.get("fire_team_seite") and e.get("ft_vof") in ("S", "A/S") and e["typ"] != "Squad":
        commands.mark(e, "Fire Team side")
        e["ziel"] = None
        prot.append(
            f"{n}: Out of Ammo, flip to the Fire Team side [7.18.2 p.61]"
            + (
                " (enemy: Spotted attempts Fall Back instead of the hierarchy in the Activity Check, 8.11)"
                if e["seite"] == "Feind"
                else ""
            )
        )
        if e["seite"] == "Feind":
            e["ooa_fallback"] = True
        return
    e["out_of_ammo"] = True
    prot.append(f"{n}: Out of Ammo marker: VOF S, range Close until resupply [7.18.2 p.61, 8.11 p.68]")
    los_now = (
        geometry.los(
            s,
            e["karte"],
            e["ziel"],
            ha=geometry.height_bonus(s, e),
            hb=geometry.card_height_bonus(s, e["ziel"], geometry.opponent_of(e)),
        )[0]
        if e.get("ziel") and e["ziel"] in s["karten"] and e["ziel"] != e["karte"]
        else False
    )
    if e.get("ziel") and e["ziel"] != e["karte"] and los_now and not geometry.in_range(s, e, e["ziel"]):
        # L164: without LOS (e.g. Illumination removed) the Cease Fire of cease_fire_on_los_loss follows; no VOF shift message
        # L147 [RULE 6.3.2 p.43 example]: "The PDF stays the same ... but its VOF is moved to the adjacent card" (replaces L40)
        fk = fire.effective_fire_target(s, n)
        if fk != e["karte"] and state.units_on(s, fk, e["seite"]) and not state.valid_target(s, fk, e["seite"]):
            prot.append(
                f"{n}: target {e['ziel']} now out of range and own units on {fk} along the PDF: Cease Fire, reopens per 6.1.1 [6.3.2, 6.1.1]"
            )
            e["ziel"] = None
        else:
            e["_reichweite_vof"] = fk
            prot.append(
                f"{n}: target {e['ziel']} now out of range (Close): PDF stays, VOF marker S moves to {fk} [6.3.2 p.43, 7.18.2]"
            )


def ammo_surplus(s, n, e, from_, prot):
    """[RULE 7.18 Note p.60, 8.11 p.68] A unit carrying more than its capacity leaves the rest behind when moving."""
    k = ammo_capacity(e)
    m = ammo(e)
    if k is None or not m or m["punkte"] <= k:
        return
    remainder = m["punkte"] - k
    m["punkte"] = k
    depot = state.card(s, from_).setdefault("munition", {})
    depot[m["typ"]] = depot.get(m["typ"], 0) + remainder
    prot.append(f"{n} can only carry {k} {m['typ']} ammo: {remainder} stay behind on {from_} [5.1.6A p.33, 7.18 p.60]")


def cmd_ammo(s, args):
    if args and args[0] == "lager":
        kid, type_, number = args[1], args[2], int(args[3])
        ev = s.get("ereignis_munition")
        if not ev:
            raise rules.Violation("Ammo on cards only via event (Ammo Resupply) or dropping (drop <unit> <type>:<n>)")
        if state.card(s, kid)["reihe"] != geometry.first_card_row(s) or state.card(s, kid).get("staging"):
            raise rules.Violation(
                f"Ammo Resupply: a card of mission row 1 (tool row {geometry.first_card_row(s)}) [Normandy M1 p.18]"
            )
        if number != 4 or type_ not in rules.AMMO_CAPACITY:
            raise rules.Violation("Ammo Resupply: 'four of any one type of ammo' (MG, MTR, RKT) [Normandy M1 p.18]")
        depot = state.card(s, kid).setdefault("munition", {})
        depot[type_] = depot.get(type_, 0) + 4
        s.pop("ereignis_munition", None)
        prot = [f"4 {type_} ammo on {kid}; pick up with 4.2.2h --what={type_}:<n> [Normandy M1 p.18, 7.18.3 p.61]"]
        state.save_state(s, "; ".join(prot), "Normandy M1 p.18")
        briefing.print_board(prot, s)
        return
    for n, e in s["einheiten"].items():
        m = ammo(e)
        if m:
            print(
                f"- {n} ({e['seite']}): {m['typ']} {m['punkte']}"
                + (f" of {m.get('start')}" if m.get("start") else "")
                + (" OUT OF AMMO" if e.get("out_of_ammo") else "")
                + (f", carries {ammo_capacity(e)}" if ammo_capacity(e) is not None else "")
            )
        if e.get("traegt_munition"):
            print(f"- {n} additionally carries {e['traegt_munition']['punkte']} {e['traegt_munition']['typ']}")
    for k, c in s["karten"].items():
        if c.get("munition"):
            print(f"- on {k}: " + ", ".join(f"{t} {v}" for t, v in c["munition"].items() if v))


def ammo_pick_up(s, z, name, what, prot):
    """[RULE 5.1.6 p.32, 7.18.3 p.61] Pick up ammo from the card; an Out of Ammo unit is resupplied."""
    type_, number = what.split(":")
    number = int(number)
    depot = state.card(s, z["karte"]).setdefault("munition", {})
    if depot.get(type_, 0) < number:
        raise rules.Violation(f"On {z['karte']} there are only {depot.get(type_, 0)} {type_}")
    m = ammo(z)
    if m and m["typ"] == type_:
        k = ammo_capacity(z)
        new = m["punkte"] + number if k is None else min(k, m["punkte"] + number)
        taken = new - m["punkte"]
        m["punkte"] = new
        depot[type_] -= taken
        prot.append(f"{name} picks up {taken} {type_} (now {new}) [7.18.3 p.61]")
        if z.get("out_of_ammo") or (state.fire_team_side(z) and z.get("fire_team_seite") and z["typ"] != "HQ"):
            z.pop("out_of_ammo", None)
            if state.fire_team_side(z):
                z["status"].remove("Fire Team side")
            prot.append(
                f"{name}: resupplied, Out of Ammo marker removed or back to the Good Order side, fires again with original VOF [7.18.3 p.61]"
            )
        if z.get("rkt_leer"):
            z["grenade_ranged"] = True
            z.pop("rkt_leer")
        return
    capacity = state.steps(z) * rules.AMMO_CAPACITY.get(type_, 1)
    tm = z.get("traegt_munition")
    if tm and tm["typ"] != type_:
        raise rules.Violation(f"{name} already carries {tm['typ']}; only one ammo type per unit [5.1.6A p.33]")
    if z.get("traegt_casualties"):
        raise rules.Violation(f"{name} carries Casualties; Casualties or one ammo type [5.1.6A p.33]")
    have = tm["punkte"] if tm else 0
    if have + number > capacity:
        raise rules.Violation(f"{name} can carry at most {capacity} {type_} ({state.steps(z)} step(s)) [5.1.6A p.33]")
    z["traegt_munition"] = {"typ": type_, "punkte": have + number}
    depot[type_] -= number
    prot.append(f"{name} picks up {number} {type_} for transport [5.1.6 p.32]")


def ammo_drop(s, e, n, what, prot):
    type_, number = what.split(":")
    number = int(number)
    tm = e.get("traegt_munition")
    if not tm or tm["typ"] != type_ or tm["punkte"] < number:
        raise rules.Violation(f"{n} does not carry {number} {type_}")
    tm["punkte"] -= number
    if not tm["punkte"]:
        e.pop("traegt_munition")
    depot = state.card(s, e["karte"]).setdefault("munition", {})
    depot[type_] = depot.get(type_, 0) + number
    prot.append(f"{n} drops {number} {type_} on {e['karte']} (no Command) [5.1.6B p.33, 7.18.3 p.61]")


def ammo_3_7_4(s, prot):
    """[RULE 3.7.4 p.17, 7.18.4 p.61, 8.1 p.61] Every ammo-dependent unit that exercises a VOF (even Pinned, even Indirect Lay)
    uses one point."""
    for n, e in list(s["einheiten"].items()):
        if (
            ammo(e)
            and not e.get("out_of_ammo")
            and (fire.is_firing(e) or e.get("indirekt"))
            and not e.get("nur_pdf")
            and ammo(e)["punkte"] > 0
        ):
            if e.get("rkt_leer"):
                continue
            if ammo(e)["typ"] == "RKT":
                continue  # rockets only for Grenade Attacks (7.18.1D), S fire without ammo
            if e.get("typ") == "AT Gun" and e.get("vof_rating") == "S":
                continue  # L87 [Normandy CSR 7 p.15] PAK40/75mm IG: Small Arms VOF 'for which ammo is not tracked'
            ammo_use(s, n, e, 1, "VOF this turn", prot)


def cmd_capture(s, args):
    """[RULE 3.5.1 p.16, 8.15 p.69, Normandy p.13 'Both sides take prisoners'] Paralyzed/Litter Team alone with unpinned infantry with VOF:
    one guard step and the prisoners are Removed from Play."""
    if s["phase"] != "3.5.1":
        raise rules.Violation("Taking prisoners only in the Capture Segment 3.5.1")
    g, w = args[0], args[1]
    ge, we = state.unit(s, g), state.unit(s, w)
    if ge["typ"] not in ("Paralyzed Team", "Litter Team"):
        raise rules.Violation(f"{g} is not a Paralyzed/Litter Team [3.5.1]")
    # K33: all same-side units on the card are Paralyzed/Litter Teams; one guard step takes them all [8.15 p.69] (L117)
    group = state.units_on(s, ge["karte"], ge["seite"])
    if [m for m in group if s["einheiten"][m]["typ"] not in ("Paralyzed Team", "Litter Team")]:
        raise rules.Violation(
            f"{g} is not alone on {ge['karte']} (other same-side units besides P/L teams) [3.5.1, K33]"
        )
    LATS = ("Fire Team", "Assault Team", "Paralyzed Team", "Litter Team")
    captor = [
        m
        for m in state.units_on(s, ge["karte"], state.opponent_of_side(ge["seite"]))
        if (s["einheiten"][m]["typ"] not in LATS)
        or (s["einheiten"][m]["typ"] in ("Fire Team", "Assault Team") and not state.pinned(s["einheiten"][m]))
    ]
    if not captor:
        raise rules.Violation(
            f"On {ge['karte']} there is no Good Order unit and no unpinned Assault/Fire Team of the opposing side [RULE 8.15 p.69]"
        )
    if we["karte"] != ge["karte"] or we["seite"] == ge["seite"] or not we.get("vof_rating"):
        raise rules.Violation(
            f"Guard {w}: one step of an opposing unit with a printed VOF on the same card [RULE 8.15 p.69]"
        )
    if ge["seite"] == "Feind" and not state.is_v4(s):
        pass
    prot = []
    st = sum(state.steps(s["einheiten"][m]) for m in group)
    for m in group:
        del s["einheiten"][m]
    if we["seite"] == "US":
        # [RULE 8.15 p.69] 'return between missions and retain their original Experience Level (it is not considered
        # an LAT). Make a note of the guard step and its Experience Level on your mission log.' (K35, L126)
        s.setdefault("wachen", []).append(
            {
                "einheit": w,
                "erfahrung": we.get("erfahrung"),
                "karte": ge["karte"],
                "zug": s["zug"],
                "gefangene": list(group),
            }
        )
        prot.append(
            f"{w}: guard step {we.get('erfahrung')} noted on the mission log, returns between missions with this "
            f"Experience Level, not an LAT [8.15 p.69]"
        )
    if state.steps(we) > 1:
        we["steps"] -= 1
        prot.append(f"{w} details one step as guard (now {we['steps']} steps), guard Removed from Play [8.15]")
        if state.steps(we) == 1 and we.get("letzter_step"):
            new = commands.new_name(s, we["letzter_step"])
            s["einheiten"][new] = new_lat(we, we["letzter_step"], w)
            s["einheiten"][new]["status"] = []
            remove_from_play(s, w, prot, f"last step becomes {we['letzter_step']} ({new})", successor=new)
    else:
        remove_from_play(s, w, prot, "detached as guard [8.15]")
    if ge["seite"] == "Feind":
        s["gefangene"] = s.get("gefangene", 0) + st
        campaign.book_xp(
            s, st * (campaign.xp_table(s, "gefangene_step") or 2), f"{st} prisoners ({', '.join(group)})", prot
        )
    else:
        s["us_gefangen"] = s.get("us_gefangen", 0) + st
    prot.insert(0, f"{', '.join(group)} ({ge['seite']}) captured, Removed from Play; one guard step for all [8.15]")
    c = state.card(s, ge["karte"])
    if ge["seite"] == "Feind" and c.get("casualties_feind") and not state.units_on(s, ge["karte"], "Feind"):
        # [RULE 3.5.1 p.16] enemy casualties on a friendly-occupied card are captured automatically (L117)
        n_cas = c["casualties_feind"]
        s["gefangene"] = s.get("gefangene", 0) + n_cas
        c["casualties_feind"] = 0
        prot.append(f"{ge['karte']}: {n_cas} enemy Casualties captured, remove marker [3.5.1, 8.15.1]")
        campaign.book_xp(
            s,
            n_cas * (campaign.xp_table(s, "feind_casualty_step") or 1),
            f"{n_cas} enemy Casualties captured ({ge['karte']})",
            prot,
        )
    m = fire.update_activity(s)
    if m:
        prot.append(m)
    state.save_state(s, "; ".join(prot), "3.5.1 p.16, 8.15 p.69")
    briefing.print_board(prot, s)
