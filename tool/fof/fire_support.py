"""Call for Fire, Indirect Lay and the fire missions (7.3.2, 7.16, 8.10): observers, target markers, Short, the 4.2.4i/4.2.4j order handlers. Split from commands.py."""

from __future__ import annotations

from . import commands, comms, fire, geometry, options, rules, state


def _cff_target(s, observer_unit, o, fm):
    """The target card of a Call for Fire: Spotted enemy (not for WP and Illumination) in the observer's LOS."""
    target_card = o.get("--target")
    if not target_card:
        raise rules.Violation("Specify --target=<card with Spotted enemy> [7.16.1]")
    card = state.card(s, target_card)
    agency_text = commands.text_opt(o, "--agency") or ""
    if "Illum" in agency_text:
        if card.get("staging"):
            raise rules.Violation("Illumination only on terrain cards [7.16.2E]")
        return target_card
    if "WP" not in agency_text and not commands.spotted_enemies(s, target_card):
        raise rules.Violation(
            f"No Spotted enemy on {target_card} [7.16.1]"
            + (" (WP missions may hit empty/Unspotted cards, 7.16.2C)" if isinstance(fm, dict) else "")
        )
    ok, reason = geometry.los(
        s,
        observer_unit["card"],
        target_card,
        ha=geometry.height_bonus(s, observer_unit),
        hb=geometry.card_height_bonus(s, target_card, "Enemy"),
    )
    if not ok:
        raise rules.Violation(f"Observer needs LOS to the target: {reason} [7.16.1]")
    return target_card


def _cff_agency(s, o, fm):
    """The firing agency (--agency, or the only one of the mission): it has a Fire Mission left and is not displacing."""
    fm_values = s["fm_values"]
    agency = o.get("--agency") or (next(iter(fm_values)) if len(fm_values) == 1 else None)
    if agency not in fm_values:
        raise rules.Violation(
            f"Specify --agency={'|'.join(fm_values)} ({', '.join(f'{a} {w:+d}' for a, w in fm_values.items())}) [FM1 p.36, 7.16.1 p.58]"
        )
    if isinstance(fm, dict) and fm.get(agency, 0) <= 0:
        raise rules.Violation(f"No {agency} Fire Mission left ({fm}) [7.16.1, Normandy M1 p.17]")
    blocked = s.get("fm_blocked") or {}
    if blocked.get("turn") == s["turn"] and s.get("fm_group", {}).get(agency, agency) == blocked.get("group"):
        raise rules.Violation(f"Artillery Displacing: {blocked['group']} not available this turn [Normandy M1 p.18]")
    return agency


def _cff_connection(s, observer_unit, name, key):
    """Connection of the observer to the firing unit [RULE 7.16.1 p.58]."""
    if observer_unit["type"] == "FO":
        if any("FD" in g.get("net", "") for g in comms.radios_of(observer_unit, s=s)) or not state.radio_active(s):
            return  # its own FD radio, or the jeep radio on the same card
        if not state.option(s, "U2_fo_fd_radio"):
            raise rules.Violation(
                f"{name} has no FD radio, no connection to the firing unit [RULE 7.16.1 p.58]"
                + state.open_reading(s, "U2_fo_fd_radio")
            )
        s.setdefault("_hints", []).append(
            f"{name} calls over its FD net (device implicit under option U2){state.open_reading(s, 'U2_fo_fd_radio')}"
        )
    elif key == "PLT HQ":
        # 'When PLT HQs are eligible, they use the CO TAC Net ... the CO HQ relays': communication with the CO HQ
        co = s.get("co_hq")
        if not co or co == name:
            raise rules.Violation(f"{name}: no CO HQ to relay the Call for Fire [RULE 7.16.1 p.58]")
        try:
            comms.communication(s, co, name)
        except rules.Violation as v:
            raise rules.Violation(
                f"{name} calls over the CO TAC Net, the CO HQ relays; no connection to {co}: {v} [RULE 7.16.1 p.58]"
            ) from None
    elif observer_unit.get("level") == "CO" and state.radio_active(s) and not s.get("co_always_in_comm"):
        if not comms.radios_of(observer_unit, "SCR300", "BN TAC"):
            raise rules.Violation(f"{name} calls over the BN TAC Net and needs its SCR300 [RULE 7.16.1 p.58]")


def cff_precheck(s, observer_unit, name, o):
    """[RULE 7.16.1 p.58] valid target (Spotted), eligible observer with LOS, connection to the firing unit. Returns
    (cards per observer, extra card for a Target marker, agency)."""
    fm = s.get("fire_missions", 0)
    if not isinstance(fm, dict) and fm != "unlimited" and (fm or 0) <= 0:
        raise rules.Violation("No Fire Mission available any more [7.16.1]")
    observer = s.get("cff_observers", {})
    key = cff_observer_key(s, name, observer_unit)
    if observer_unit["type"] != "FO" and not observer_unit.get("observer") and key not in observer:
        raise rules.Violation(
            f"{name} is not an observer according to the mission [7.16.1]"
            + (f"; eligible: {', '.join(observer)}" if observer else "")
        )
    if state.fire_team_side(observer_unit):
        raise rules.Violation("Observer on its Fire Team side cannot call for fire [7.16.1]")
    target_card = _cff_target(s, observer_unit, o, fm)
    agency = None
    if s.get("fm_values"):
        agency = _cff_agency(s, o, fm)
        _cff_connection(s, observer_unit, name, key)
    tab = s.get("cff_table") or {}
    if agency in tab:
        if key not in tab[agency]:
            raise rules.Violation(
                f"{name} may not call {agency}; eligible: {', '.join(tab[agency])} [Normandy M2 p.22]"
            )
        base = tab[agency][key]  # [Normandy M2 p.22] number of cards per firing unit and observer
    else:
        base = observer.get(key, s.get("cff_cards", 2))
    marked = agency and s.get("target_marker", {}).get(target_marker_key(s, agency)) == target_card
    return base, 1 if marked else 0, agency  # [RULE 7.16.5 p.59] +1 card on the Target marker


def cff_observer_key(s, name, observer_unit):
    """[RULE 7.16.1 p.58 'Some Missions allow for CO HQs (and even PLT HQs) to Call for Fire'] a 'PLT HQ' column of
    the Fire Support Available Table covers every PLT HQ (also the HMG PLT HQ); otherwise the unit name is the key."""
    observer = s.get("cff_observers", {})
    columns = set(observer) | {k for tab in (s.get("cff_table") or {}).values() for k in tab}
    if (
        name not in columns
        and observer_unit.get("type") == "HQ"
        and observer_unit.get("level") == "PLT"
        and "PLT HQ" in columns
    ):
        return "PLT HQ"
    return name


def target_marker_key(s, agency):
    """Target marker per firing unit; HE and WP of the same battery share it [open U29]."""
    if s.get("fm_group") and state.option(s, "U29_one_target_marker_he_wp"):
        return s["fm_group"].get(agency, agency)
    return agency


def short_place(s, observer_unit, target_card, o):
    """[RULE 7.16.4 p.59] Short: one card closer to the observer along the LOS; observer on the target card: random adjacent card."""
    if observer_unit["card"] == target_card:
        pl = o.get("--place")
        if not pl or not geometry.adjacent(s, target_card, pl):
            nb = [k for k in s["cards"] if geometry.adjacent(s, target_card, k)]
            raise rules.Violation(
                f"Short, observer is on the target card: draw a random adjacent card (R#/{len(nb)} from {', '.join(nb)}) and --place=<card> [RULE 7.16.4 p.59]"
            )
        return pl
    between = geometry.line_between(s, observer_unit["card"], target_card) or []
    return between[-1] if between else observer_unit["card"]


def cff_friendly_fire(s, observer_unit, target_card):
    """Draw prompt of a Call for Fire: own units on the target card, and the card a Short would hit [7.16.4 p.59]."""
    notes = []
    own = state.units_on(s, target_card, "US")
    if own:
        notes.append(f"WATCH friendly fire: own units on {target_card} ({', '.join(own)}) are hit as well [7.16.3]")
    if observer_unit["card"] == target_card:
        notes.append("a Short lands on a random adjacent card [7.16.4]")
    else:
        short = (geometry.line_between(s, observer_unit["card"], target_card) or [observer_unit["card"]])[-1]
        own = state.units_on(s, short, "US")
        notes.append(f"a Short lands on {short}" + (f", on own units ({', '.join(own)})" if own else "") + " [7.16.4]")
    return "; ".join(notes)


def _indirect_lay_mortar(s, orig_name, orig, mortar_name, m, gi):
    """The mortar may fire an Indirect Lay now and the originator may order it [RULE 4.2.4j p.25, 7.3.2 p.53]."""
    if not state.is_mortar(m):
        raise rules.Violation(f"{mortar_name} is not an on-map mortar unit [RULE 4.2.4j p.25]")
    laid = [
        card_id
        for card_id, c in s["cards"].items()
        if any(x.get("type") == "Indirect" and x.get("source") == mortar_name for x in c.get("external", []))
    ]
    if laid or m.get("indirect"):
        # one Indirect Lay per mortar and turn; the VOF stays until Clean Up [RULE 7.3.2 p.53]
        raise rules.Violation(
            f"{mortar_name} already fires an Indirect Lay this turn (VOF on {', '.join(laid) or '?'}); a second one is not stacked [RULE 7.3.2 p.53]"
        )
    if gi and orig_name == mortar_name:
        raise rules.Violation(
            "Indirect Lay needs an HQ eligible to give orders as observer: --originator=<HQ> [RULE 7.3.2 p.53]"
            + state.open_reading(s, "U12_indirect_under_gi")
        )
    if gi and not state.option(s, "U12_indirect_under_gi"):
        raise rules.Violation(
            "Indirect Lay under General Initiative not allowed under option U12 (reading a); order it in the impulse of an eligible HQ [RULE 7.3.2 p.53]"
            + state.open_reading(s, "U12_indirect_under_gi")
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
    if state.card(s, m["card"]).get("staging"):
        raise rules.Violation("No firing from the Staging Area [RULE 2.5 p.12]")
    forbidden = fire.fire_position_forbidden(s, m)
    if forbidden:
        raise rules.Violation(forbidden)


def _indirect_lay_connection(s, orig_name, mortar_name, m, prot):
    """Visual-verbal or radio, or an HQ with a radio in the mortar's card area as relay [RULE 7.3.2 p.53]."""
    try:
        comms.communication(s, orig_name, mortar_name, "4.2.4j")
    except rules.Violation as v:
        relay = [
            n
            for n, e in s["units"].items()
            if state.is_hq(e)
            and e["card"] == m["card"]
            and e.get("area", "open") == m.get("area", "open")
            and comms.radios_of(e)
        ]
        if not relay:
            raise rules.Violation(
                f"No connection {orig_name} with {mortar_name}: {v}; also no HQ with radio in the same card area as relay [RULE 7.3.2 p.53]"
            ) from None
        prot.append(f"Order via relay {relay[0]} (HQ with radio in the same area) [7.3.2 p.53]")


def _indirect_lay_target(s, orig_name, orig, mortar_name, m, o):
    """The target card: Spotted enemy, in the observer's LOS and in the mortar's range [RULE 7.3.2 p.53]."""
    target_card = o.get("--target")
    if not target_card:
        raise rules.Violation("Specify --target=<card with Spotted enemy> [RULE 4.2.4j p.25]")
    state.card(s, target_card)
    if not commands.spotted_enemies(s, target_card):
        raise rules.Violation(f"No Spotted enemy on {target_card} [RULE 4.2.4j p.25]")
    ok, reason = geometry.los(
        s,
        orig["card"],
        target_card,
        ha=geometry.height_bonus(s, orig),
        hb=geometry.card_height_bonus(s, target_card, "Enemy"),
    )
    if not ok:
        raise rules.Violation(f"Observer {orig_name} has no LOS to {target_card}: {reason} [RULE 7.3.2 p.53]")
    lo, hi = state.range_limits(s, m)
    d = geometry.distance(s, m["card"], target_card)
    if not (max(1, lo) <= d <= hi):
        raise rules.Violation(
            f"{target_card} is {d} cards away from {mortar_name}; range in cards (diagonals counted, own card excluded) {max(1, lo)} to {hi} [RULE 7.3.2 p.53]"
            + state.open_reading(s, "U12_mortar_range")
        )
    return target_card


def indirect_lay(s, orig_name, orig, mortar_name, m, o, prot, gi):
    """4.2.4j p.25, 7.3.2 p.53: HQ with LOS calls Indirect Lay of the multi-step mortar unit; VOF H without PDF, terrain like Incoming."""
    _indirect_lay_mortar(s, orig_name, orig, mortar_name, m, gi)
    _indirect_lay_connection(s, orig_name, mortar_name, m, prot)
    target_card = _indirect_lay_target(s, orig_name, orig, mortar_name, m, o)
    if m.get("target"):
        prot.append(
            f"{mortar_name}: remove Direct Lay PDF and VOF to {m['target']}, Indirect Lay takes precedence [RULE 7.3.2 p.53]"
        )
    fire.cease_fire(m)  # all working fields of the Direct Lay go, not only the target
    m["indirect"] = True
    state.card(s, target_card).setdefault("external", []).append(
        {"type": "Indirect", "value": rules.VOF_VALUE["H"], "source": mortar_name, "side": "US"}
    )
    prot.append(
        f"Heavy Weapons VOF (-3, Indirect Lay) on {target_card}, no PDF, no Crossfire; hits all units on the card; lower C&C value and Burst apply; remove in Clean Up"
        + state.open_reading(s, "U12_mortar_range")
        + " [RULE 7.3.2 p.53, 5.2.3 p.36]"
    )


def order_call_for_fire(s, ctx):
    """Order handler for: action_id == '4.2.4i' (split into Illumination, Pending marker with agency, legacy Pending)."""
    target_card = ctx.o["--target"]
    if ctx.success != "yes":
        ctx.prot.append("Call for Fire failed, no Fire Mission used")
        s["last_attempt"] = [ctx.target_name, ctx.action_id, s["phase"]]
        return
    place = ctx.o.get("--place", target_card)
    if ctx.o.get("--short") == "yes":
        place = short_place(s, ctx.recipient, target_card, ctx.o)
    if s.get("fm_values") and "Illum" in ctx.agency:
        _cff_illumination(s, ctx, target_card, place)
    elif s.get("fm_values"):
        _cff_pending(s, ctx, target_card, place)
    else:
        _cff_pending_legacy(s, ctx, place)


def use_fire_mission(s, agency=None):
    """One Fire Mission crossed off: per agency (dict), as a count, or unlimited in legacy games."""
    fm = s.get("fire_missions")
    if isinstance(fm, dict):
        fm[agency] -= 1
    elif fm != "unlimited":
        s["fire_missions"] = fm - 1


def move_target_marker(s, ctx, place, note):
    """[RULE 7.16.5 p.59] after a successful Fire Mission the Target marker of the firing unit goes to the target card
    (unless --move-target-marker=no)."""
    if ctx.o.get("--move-target-marker") == "no":
        return
    key = target_marker_key(s, ctx.agency)
    old = s.setdefault("target_marker", {}).get(key)
    s["target_marker"][key] = place
    ctx.prot.append(
        f"Target marker ({ctx.agency} Concentration) on {place}"
        + (f", moved from {old}" if old and old != place else "")
        + note
    )


def _cff_illumination(s, ctx, target_card, place):
    """[RULE 7.16.2E p.58, 9.2 p.70] Illumination: on any terrain card, without LOS, immediately, no Pending marker."""
    iv = (s.get("illum_values") or {}).get(ctx.agency)
    if ctx.o.get("--illum"):
        top_value, _, un = str(ctx.o["--illum"]).partition("/")
        iv = {
            "top": rules.int_value(top_value, "Illumination top value"),
            "bottom": rules.int_value(un, "Illumination bottom value") if un else None,
        }
    if not iv:
        raise rules.Violation(
            f"Illumination values for {ctx.agency} not recorded: read them off the marker, --illum=<top>/<bottom> [9.2]"
        )
    state.card(s, place).setdefault("illum", []).append(
        {"top": iv["top"], "bottom": iv.get("bottom"), "source": ctx.agency}
    )
    if isinstance(s.get("fire_missions"), dict):  # Illumination is only counted per agency
        s["fire_missions"][ctx.agency] -= 1
    ctx.prot.append(
        f"Illumination marker {iv['top']:+d}"
        + (f"/{iv['bottom']:+d}" if iv.get("bottom") is not None else "")
        + f" ({ctx.agency}) immediately on {place}"
        + (f" (Short instead of {target_card})" if place != target_card else "")
        + f"; Fire Missions: {s['fire_missions']}; removed in Clean Up [RULE 7.16.2E p.58, 9.2 p.70]"
    )
    if place == target_card:
        # [RULE 7.16.5 p.59 "after a successful Fire Mission"; BGG Shonai_Dweller 3520262: Illumination also moves the Target marker]
        move_target_marker(s, ctx, place, " [RULE 7.16.5 p.59, BGG 3520262]")
    fire.open_fire(s, ctx.prot)


def _cff_pending(s, ctx, target_card, place):
    """[RULE 7.16.3 p.59] Pending Fire Mission marker of an agency with a value table; Battalion Fire Mission 7.16.2B."""
    value = options.int_opt(ctx.o, "--value", "Fire Mission value", s["fm_values"][ctx.agency])
    pending = {"type": "Pending", "value": value, "source": ctx.target_name, "agency": ctx.agency, "side": "US"}
    state.card(s, place).setdefault("external", []).append(pending)
    use_fire_mission(s, ctx.agency)
    bat = options.list_option(ctx.o, "--battalion")
    if bat:
        gr = s.get("fm_group", {}).get(ctx.agency, ctx.agency)
        if gr not in s.get("battalion_fm", []):
            raise rules.Violation(f"Battalion Fire Mission for {gr} not available per mission [RULE 7.16.2B p.58]")
        if ctx.o.get("--short") == "yes" or len(bat) != 2 or len(set(bat)) != 2:
            raise rules.Violation(
                "Battalion Fire Mission: 3 Bursts symbol, two different cards adjacent to the target card: --battalion=K1,K2 [RULE 7.16.2B p.58]"
            )
        for bk in bat:
            if geometry.distance(s, target_card, bk) != 1 or state.card(s, bk).get("staging"):
                raise rules.Violation(
                    f"{bk} is not adjacent to {target_card} (terrain card required) [RULE 7.16.2B p.58]"
                )
            state.card(s, bk).setdefault("external", []).append(dict(pending))
        ctx.prot.append(
            f"Battalion Fire Mission: additional Pending markers {ctx.agency} ({value:+d}) on {', '.join(bat)}, without observer LOS [RULE 7.16.2B p.58]"
        )
    ctx.prot.append(
        f"Pending Fire Mission Marker {ctx.agency} (value {value:+d}) on {place}"
        + (f" (Short, one card closer to the observer instead of {target_card})" if place != target_card else "")
        + f"; Fire Missions: {s['fire_missions']}; becomes active in 3.7.1 (Incoming!), takes effect in 3.7.4, is removed in 3.7.1 of the following turn [RULE 7.16.3 p.59, 3.7.1 p.17]"
    )
    own = state.units_on(s, place, "US")
    if own:
        ctx.prot.append(f"WATCH friendly fire: own units on {place} ({', '.join(own)}) are under this Fire Mission")
    if place == target_card or state.option(s, "U13_target_marker_on_short"):
        move_target_marker(
            s, ctx, place, "; later calls of this firing unit on this card +1 card [RULE 7.16.5 p.59, FM1 p.42]"
        )
    else:
        ctx.prot.append(
            "Short: Target marker not moved automatically (7.16.5 does not cover this case)"
            + state.open_reading(s, "U13_target_marker_on_short")
        )


def _cff_pending_legacy(s, ctx, place):
    """Games before the agency tables (no fm_values): one Pending marker with the mission's value."""
    value = options.int_opt(ctx.o, "--value", "Fire Mission value", s.get("fm_value", -3))
    state.card(s, place).setdefault("external", []).append(
        {"type": "Pending", "value": value, "source": ctx.target_name}
    )
    use_fire_mission(s)  # legacy games without a Fire Mission count
    ctx.prot.append(
        f"Pending Fire Mission Marker on {place} (value {value}), Fire Mission crossed off ({s['fire_missions']} left); active from 3.7.1 of this turn [RULE 3.7.1 p.17, FM1 p.44]. On 'Short!': one card closer to the observer (--place) [7.16.3, 7.16.4]"
    )


def order_indirect_lay(s, ctx):
    """Order handler for: action_id == '4.2.4j'"""
    indirect_lay(s, ctx.orig_name, ctx.orig, ctx.target_name, ctx.recipient, ctx.o, ctx.prot, ctx.gi)
