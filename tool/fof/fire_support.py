"""Call for Fire, Indirect Lay and the fire missions (7.3.2, 7.16, 8.10): observers, target markers, Short, the 4.2.4i/4.2.4j order handlers. Split from commands.py (L556)."""

from __future__ import annotations

from . import commands, comms, fire, geometry, options, rules, state


def cff_precheck(s, z, name, o):
    """L251: unused originator parameter removed (also from indirect_lay, order_bn, order_v4; set_area keeps its
    signature, it has callers outside commands.py).
    7.16.1 p.58: valid target (Spotted), eligible observer with LOS, connection to the firing unit; number of cards per observer."""
    fm = s.get("feuermissionen", 0)
    if not isinstance(fm, dict) and fm != "unbegrenzt" and (fm or 0) <= 0:
        raise rules.Violation("No Fire Mission available any more [7.16.1]")
    observer = s.get("cff_beobachter", {})
    key = cff_observer_key(s, name, z)
    if z["typ"] != "FO" and not z.get("beobachter") and key not in observer:
        raise rules.Violation(
            f"{name} is not an observer according to the mission [7.16.1]"
            + (f"; eligible: {', '.join(observer)}" if observer else "")
        )
    if state.fire_team_side(z):
        raise rules.Violation("Observer on its Fire Team side cannot call for fire [7.16.1]")
    zt = o.get("--ziel")
    if not zt:
        raise rules.Violation("Specify --target=<card with Spotted enemy> [7.16.1]")
    state.card(s, zt)
    wp = "WP" in (commands.text_opt(o, "--agentur") or "")
    illum = "Illum" in (commands.text_opt(o, "--agentur") or "")
    if illum:
        if state.card(s, zt).get("staging"):
            raise rules.Violation("Illumination only on terrain cards [7.16.2E]")
    elif not wp and not commands.spotted_enemies(s, zt):
        raise rules.Violation(
            f"No Spotted enemy on {zt} [7.16.1]"
            + (" (WP missions may hit empty/Unspotted cards, 7.16.2C)" if isinstance(fm, dict) else "")
        )
    if not illum:
        ok, reason = geometry.los(
            s, z["karte"], zt, ha=geometry.height_bonus(s, z), hb=geometry.card_height_bonus(s, zt, "Feind")
        )
        if not ok:
            raise rules.Violation(f"Observer needs LOS to the target: {reason} [7.16.1]")
    agency = None
    if s.get("fm_werte"):
        fw = s["fm_werte"]
        agency = o.get("--agentur") or (next(iter(fw)) if len(fw) == 1 else None)
        if agency not in fw:
            raise rules.Violation(
                f"Specify --agency={'|'.join(fw)} ({', '.join(f'{a} {w:+d}' for a, w in fw.items())}) [FM1 p.36, 7.16.1 p.58]"
            )
        if isinstance(fm, dict) and fm.get(agency, 0) <= 0:
            raise rules.Violation(f"No {agency} Fire Mission left ({fm}) [7.16.1, Normandy M1 p.17]")
        sp = s.get("fm_gesperrt") or {}
        if sp.get("zug") == s["zug"] and s.get("fm_gruppe", {}).get(agency, agency) == sp.get("gruppe"):
            raise rules.Violation(f"Artillery Displacing: {sp['gruppe']} not available this turn [Normandy M1 p.18]")
        # Connection to the firing unit [RULE 7.16.1 p.58]
        if z["typ"] == "FO":
            fd = [g for g in comms.radios_of(z, s=s) if "FD" in g.get("netz", "")]  # L526: jeep radio on the same card
            if not fd and state.radio_active(s) and not state.option(s, "U2_fo_fd_funk"):
                raise rules.Violation(
                    f"{name} has no FD radio, no connection to the firing unit [RULE 7.16.1 p.58]"
                    + state.open_reading(s, "U2_fo_fd_funk")
                )
            if not fd and state.radio_active(s):
                s.setdefault("_hinweise", []).append(
                    f"{name} calls over its FD net (device implicit under option U2){state.open_reading(s, 'U2_fo_fd_funk')}"
                )
        elif key == "PLT HQ":
            # L512 [RULE 7.16.1 p.58 'When PLT HQs are eligible, they use the CO TAC Net ... the CO HQ relays'] the PLT
            # HQ needs communication with the CO HQ
            co = s.get("co_hq")
            if not co or co == name:
                raise rules.Violation(f"{name}: no CO HQ to relay the Call for Fire [RULE 7.16.1 p.58]")
            try:
                comms.communication(s, co, name)
            except rules.Violation as v:
                raise rules.Violation(
                    f"{name} calls over the CO TAC Net, the CO HQ relays; no connection to {co}: {v} [RULE 7.16.1 p.58]"
                ) from None
        elif z.get("ebene") == "CO" and state.radio_active(s) and not s.get("co_immer_in_kommunikation"):
            if not comms.radios_of(z, "SCR300", "BN TAC"):
                raise rules.Violation(f"{name} calls over the BN TAC Net and needs its SCR300 [RULE 7.16.1 p.58]")
    tab = s.get("cff_tabelle") or {}
    if agency in tab:
        if key not in tab[agency]:
            raise rules.Violation(
                f"{name} may not call {agency}; eligible: {', '.join(tab[agency])} [Normandy M2 p.22]"
            )
        base = tab[agency][key]  # [Normandy M2 p.22] number of cards per firing unit and observer
    else:
        base = observer.get(key, s.get("cff_karten", 2))
    extra = (
        1 if agency and s.get("target_marker", {}).get(target_marker_key(s, agency)) == zt else 0
    )  # [RULE 7.16.5 p.59]
    return base, extra, agency


def cff_observer_key(s, name, z):
    """L512 [RULE 7.16.1 p.58 'Some Missions allow for CO HQs (and even PLT HQs) to Call for Fire'] a 'PLT HQ' column of
    the Fire Support Available Table covers every PLT HQ (also the HMG PLT HQ); otherwise the unit name is the key."""
    observer = s.get("cff_beobachter", {})
    columns = set(observer) | {k for tab in (s.get("cff_tabelle") or {}).values() for k in tab}
    if name not in columns and z.get("typ") == "HQ" and z.get("ebene") == "PLT" and "PLT HQ" in columns:
        return "PLT HQ"
    return name


def target_marker_key(s, agency):
    """Target marker per firing unit; HE and WP of the same battery share it [open U29]."""
    if s.get("fm_gruppe") and state.option(s, "U29_ein_target_marker_he_wp"):
        return s["fm_gruppe"].get(agency, agency)
    return agency


def short_place(s, z, zt, o):
    """[RULE 7.16.4 p.59] Short: one card closer to the observer along the LOS; observer on the target card: random adjacent card."""
    if z["karte"] == zt:
        pl = o.get("--platz")
        if not pl or not geometry.adjacent(s, zt, pl):
            nb = [k for k in s["karten"] if geometry.adjacent(s, zt, k)]
            raise rules.Violation(
                f"Short, observer is on the target card: draw a random adjacent card (R#/{len(nb)} from {', '.join(nb)}) and --place=<card> [RULE 7.16.4 p.59]"
            )
        return pl
    between = geometry.line_between(s, z["karte"], zt) or []
    return between[-1] if between else z["karte"]


def indirect_lay(s, orig_name, orig, mortar_name, m, o, prot, gi):
    """4.2.4j p.25, 7.3.2 p.53: HQ with LOS calls Indirect Lay of the multi-step mortar unit; VOF H without PDF, terrain like Incoming."""
    if not state.is_mortar(m):
        raise rules.Violation(f"{mortar_name} is not an on-map mortar unit [RULE 4.2.4j p.25]")
    laid = [
        kid
        for kid, c in s["karten"].items()
        if any(x.get("typ") == "Indirect" and x.get("quelle") == mortar_name for x in c.get("extern", []))
    ]
    if laid or m.get("indirekt"):
        # L243 (review M17): one Indirect Lay per mortar and turn; the VOF stays until Clean Up [RULE 7.3.2 p.53]
        raise rules.Violation(
            f"{mortar_name} already fires an Indirect Lay this turn (VOF on {', '.join(laid) or '?'}); a second one is not stacked [RULE 7.3.2 p.53]"
        )
    if gi and orig_name == mortar_name:
        raise rules.Violation(
            "Indirect Lay needs an HQ eligible to give orders as observer: --originator=<HQ> [RULE 7.3.2 p.53]"
            + state.open_reading(s, "U12_indirekt_unter_gi")
        )
    if gi and not state.option(s, "U12_indirekt_unter_gi"):
        raise rules.Violation(
            "Indirect Lay under General Initiative not allowed under option U12 (reading a); order it in the impulse of an eligible HQ [RULE 7.3.2 p.53]"
            + state.open_reading(s, "U12_indirekt_unter_gi")
        )
    if not state.is_hq(orig):
        raise rules.Violation("Originator must be an HQ or Staff [RULE 4.2.4j p.25]")
    comms.chain_of_command(
        s, orig_name, mortar_name
    )  # [RULE 7.3.2 p.53] 'someone who is eligible to issue orders to the mortar'
    if state.steps(m) < 2:
        raise rules.Violation(
            f"{mortar_name} has {state.steps(m)} step; Indirect Lay only with at least two steps [RULE 4.2.4j p.25, 7.3.2 p.53]"
        )
    if not state.good_order(m) or rules.EXPOSED in m["status"]:
        raise rules.Violation(f"{mortar_name} must be Good Order and not Exposed [RULE 4.2.4j p.25, 7.3.1 p.53]")
    if state.card(s, m["karte"]).get("staging"):
        raise rules.Violation("No firing from the Staging Area [RULE 2.5 p.12]")
    vb = fire.fire_position_forbidden(s, m)
    if vb:
        raise rules.Violation(vb)
    # Connection: visual-verbal/radio or mortar in the same card area as an HQ with radio/phone (relay) [RULE 7.3.2 p.53]
    try:
        comms.communication(s, orig_name, mortar_name, "4.2.4j")
    except rules.Violation as v:
        relay = [
            n
            for n, e in s["einheiten"].items()
            if state.is_hq(e)
            and e["karte"] == m["karte"]
            and e.get("bereich", "offen") == m.get("bereich", "offen")
            and comms.radios_of(e)
        ]
        if not relay:
            raise rules.Violation(
                f"No connection {orig_name} with {mortar_name}: {v}; also no HQ with radio in the same card area as relay [RULE 7.3.2 p.53]"
            ) from None
        prot.append(f"Order via relay {relay[0]} (HQ with radio in the same area) [7.3.2 p.53]")
    zt = o.get("--ziel")
    if not zt:
        raise rules.Violation("Specify --target=<card with Spotted enemy> [RULE 4.2.4j p.25]")
    state.card(s, zt)
    if not commands.spotted_enemies(s, zt):
        raise rules.Violation(f"No Spotted enemy on {zt} [RULE 4.2.4j p.25]")
    ok, reason = geometry.los(
        s, orig["karte"], zt, ha=geometry.height_bonus(s, orig), hb=geometry.card_height_bonus(s, zt, "Feind")
    )
    if not ok:
        raise rules.Violation(f"Observer {orig_name} has no LOS to {zt}: {reason} [RULE 7.3.2 p.53]")
    lo, hi = state.range_limits(s, m)
    d = geometry.distance(s, m["karte"], zt)
    if not (max(1, lo) <= d <= hi):
        raise rules.Violation(
            f"{zt} is {d} cards away from {mortar_name}; range in cards (diagonals counted, own card excluded) {max(1, lo)} to {hi} [RULE 7.3.2 p.53]"
            + state.open_reading(s, "U12_moerser_reichweite")
        )
    if m.get("ziel"):
        prot.append(
            f"{mortar_name}: remove Direct Lay PDF and VOF to {m['ziel']}, Indirect Lay takes precedence [RULE 7.3.2 p.53]"
        )
    fire.cease_fire(m)  # L549 (review C10): all working fields of the Direct Lay go, not only the target
    m["indirekt"] = True
    state.card(s, zt).setdefault("extern", []).append(
        {"typ": "Indirect", "wert": rules.VOF_VALUE["H"], "quelle": mortar_name, "seite": "US"}
    )
    prot.append(
        f"Heavy Weapons VOF (-3, Indirect Lay) on {zt}, no PDF, no Crossfire; hits all units on the card; lower C&C value and Burst apply; remove in Clean Up"
        + state.open_reading(s, "U12_moerser_reichweite")
        + " [RULE 7.3.2 p.53, 5.2.3 p.36]"
    )


def order_call_for_fire(s, ctx):
    """Order handler for: akt == '4.2.4i' (L256: split into Illumination, Pending marker with agency, legacy Pending)."""
    zt = ctx.o["--ziel"]
    if ctx.success != "ja":
        ctx.prot.append("Call for Fire failed, no Fire Mission used")
        s["letzter_versuch"] = [ctx.target_name, ctx.akt, s["phase"]]
        return
    place = ctx.o.get("--platz", zt)
    if ctx.o.get("--short") == "ja":
        place = short_place(s, ctx.z, zt, ctx.o)
    if s.get("fm_werte") and "Illum" in ctx.agency:
        _cff_illumination(s, ctx, zt, place)
    elif s.get("fm_werte"):
        _cff_pending(s, ctx, zt, place)
    else:
        _cff_pending_legacy(s, ctx, place)


def use_fire_mission(s, agency=None):
    """One Fire Mission crossed off: per agency (dict), as a count, or unlimited in legacy games (L247)."""
    fm = s.get("feuermissionen")
    if isinstance(fm, dict):
        fm[agency] -= 1
    elif fm != "unbegrenzt":
        s["feuermissionen"] = fm - 1


def move_target_marker(s, ctx, place, note):
    """[RULE 7.16.5 p.59] after a successful Fire Mission the Target marker of the firing unit goes to the target card
    (unless --move-target-marker=no)."""
    if ctx.o.get("--target_marker") == "nein":
        return
    key = target_marker_key(s, ctx.agency)
    old = s.setdefault("target_marker", {}).get(key)
    s["target_marker"][key] = place
    ctx.prot.append(
        f"Target marker ({ctx.agency} Concentration) on {place}"
        + (f", moved from {old}" if old and old != place else "")
        + note
    )


def _cff_illumination(s, ctx, zt, place):
    """[RULE 7.16.2E p.58, 9.2 p.70] Illumination: on any terrain card, without LOS, immediately, no Pending marker."""
    iv = (s.get("illum_werte") or {}).get(ctx.agency)
    if ctx.o.get("--illum"):
        top_value, _, un = str(ctx.o["--illum"]).partition("/")
        iv = {
            "oben": rules.int_value(top_value, "Illumination top value"),
            "unten": rules.int_value(un, "Illumination bottom value") if un else None,
        }
    if not iv:
        raise rules.Violation(
            f"Illumination values for {ctx.agency} not recorded: read them off the marker, --illum=<top>/<bottom> [9.2]"
        )
    state.card(s, place).setdefault("illum", []).append(
        {"oben": iv["oben"], "unten": iv.get("unten"), "quelle": ctx.agency}
    )
    if isinstance(s.get("feuermissionen"), dict):  # Illumination is only counted per agency
        s["feuermissionen"][ctx.agency] -= 1
    ctx.prot.append(
        f"Illumination marker {iv['oben']:+d}"
        + (f"/{iv['unten']:+d}" if iv.get("unten") is not None else "")
        + f" ({ctx.agency}) immediately on {place}"
        + (f" (Short instead of {zt})" if place != zt else "")
        + f"; Fire Missions: {s['feuermissionen']}; removed in Clean Up [RULE 7.16.2E p.58, 9.2 p.70]"
    )
    if place == zt:
        # [RULE 7.16.5 p.59 "after a successful Fire Mission"; BGG Shonai_Dweller 3520262: Illumination also moves the Target marker]
        move_target_marker(s, ctx, place, " [RULE 7.16.5 p.59, BGG 3520262]")
    fire.open_fire(s, ctx.prot)


def _cff_pending(s, ctx, zt, place):
    """[RULE 7.16.3 p.59] Pending Fire Mission marker of an agency with a value table; Battalion Fire Mission 7.16.2B."""
    value = options.int_opt(ctx.o, "--wert", "Fire Mission value", s["fm_werte"][ctx.agency])
    pending = {"typ": "Pending", "wert": value, "quelle": ctx.target_name, "agentur": ctx.agency, "seite": "US"}
    state.card(s, place).setdefault("extern", []).append(pending)
    use_fire_mission(s, ctx.agency)
    bat = options.list_option(ctx.o, "--bataillon")
    if bat:
        gr = s.get("fm_gruppe", {}).get(ctx.agency, ctx.agency)
        if gr not in s.get("bataillon_fm", []):
            raise rules.Violation(f"Battalion Fire Mission for {gr} not available per mission [RULE 7.16.2B p.58]")
        if ctx.o.get("--short") == "ja" or len(bat) != 2 or len(set(bat)) != 2:
            raise rules.Violation(
                "Battalion Fire Mission: 3 Bursts symbol, two different cards adjacent to the target card: --battalion=K1,K2 [RULE 7.16.2B p.58]"
            )
        for bk in bat:
            if geometry.distance(s, zt, bk) != 1 or state.card(s, bk).get("staging"):
                raise rules.Violation(f"{bk} is not adjacent to {zt} (terrain card required) [RULE 7.16.2B p.58]")
            state.card(s, bk).setdefault("extern", []).append(dict(pending))
        ctx.prot.append(
            f"Battalion Fire Mission: additional Pending markers {ctx.agency} ({value:+d}) on {', '.join(bat)}, without observer LOS [RULE 7.16.2B p.58]"
        )
    ctx.prot.append(
        f"Pending Fire Mission Marker {ctx.agency} (value {value:+d}) on {place}"
        + (f" (Short, one card closer to the observer instead of {zt})" if place != zt else "")
        + f"; Fire Missions: {s['feuermissionen']}; becomes active in 3.7.1 (Incoming!), takes effect in 3.7.4, is removed in 3.7.1 of the following turn [RULE 7.16.3 p.59, 3.7.1 p.17]"
    )
    if place == zt or state.option(s, "U13_target_marker_bei_short"):
        move_target_marker(
            s, ctx, place, "; later calls of this firing unit on this card +1 card [RULE 7.16.5 p.59, FM1 p.42]"
        )
    else:
        ctx.prot.append(
            "Short: Target marker not moved automatically (7.16.5 does not cover this case)"
            + state.open_reading(s, "U13_target_marker_bei_short")
        )


def _cff_pending_legacy(s, ctx, place):
    """Games before the agency tables (no fm_werte): one Pending marker with the mission's value."""
    value = options.int_opt(ctx.o, "--wert", "Fire Mission value", s.get("fm_wert", -3))
    state.card(s, place).setdefault("extern", []).append({"typ": "Pending", "wert": value, "quelle": ctx.target_name})
    use_fire_mission(s)  # L247: legacy games without a Fire Mission count
    ctx.prot.append(
        f"Pending Fire Mission Marker on {place} (value {value}), Fire Mission crossed off ({s['feuermissionen']} left); active from 3.7.1 of this turn [RULE 3.7.1 p.17, FM1 p.44]. On 'Short!': one card closer to the observer (--place) [7.16.3, 7.16.4]"
    )


def order_indirect_lay(s, ctx):
    """Order handler for: akt == '4.2.4j'"""
    indirect_lay(s, ctx.orig_name, ctx.orig, ctx.target_name, ctx.z, ctx.o, ctx.prot, ctx.gi)
