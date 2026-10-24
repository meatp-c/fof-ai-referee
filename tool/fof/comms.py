"""Communication: visual-verbal, radio, telephone, runners, chain of command (4.3)."""

from . import briefing, geometry, rules, state


def radios_of(e, type_=None, net=None):
    """Radios carried by the unit (setup field 'funk': [{typ, netz}]); destroyed ones do not count."""
    return [
        g
        for g in e.get("funk", [])
        if not g.get("zerstoert") and (type_ is None or g["typ"] == type_) and (net is None or g["netz"] == net)
    ]


def radio_los(s, a, b):
    """SCR536 LOS: [RULE 2.5 p.12] within staging and to adjacent cards of row 1; otherwise 5.2.1/5.2.2 [RULE 4.3.5 p.29]."""
    ka, kb = state.card(s, a), state.card(s, b)
    if ka.get("staging") and kb.get("staging"):
        return True, "both in the Staging Area, radio LOS always exists [RULE 2.5 p.12]"
    if ka.get("staging") or kb.get("staging"):
        st, mp = (a, b) if ka.get("staging") else (b, a)
        if state.card(s, mp)["reihe"] == geometry.first_card_row(s) and geometry.adjacent(s, st, mp):
            return True, f"Staging {st} and adjacent card {mp} of row 1 [RULE 2.5 p.12]"
        if state.option(s, "U10_staging_funk_ueber_hill"):
            ok, g = geometry.los(s, a, b, radio=True, staging_frei=True)
            return ok, g + state.open_reading(s, "U10_staging_funk_ueber_hill")
        return (
            False,
            f"from the Staging Area only to adjacent cards of row 1 [RULE 2.5 p.12]{state.open_reading(s, 'U10_staging_funk_ueber_hill')}",
        )
    # radio traffic goes both ways: LOS must exist from both ends (5.4 makes LOS one-sided with Incoming) [open U3]
    ok, g = geometry.los(s, a, b, radio=True)
    if ok:
        ok, g = geometry.los(s, b, a, radio=True)
    return ok, g


def radio_direct(s, a_name, b_name, type_="SCR536", net="CO TAC"):
    """Direct radio link between two units: both carry a device of the net, SCR536 not under a cover marker and only with LOS."""
    a, b = s["einheiten"][a_name], s["einheiten"][b_name]
    if not radios_of(a, type_, net):
        return False, f"{a_name} has no {type_} {net}"
    if not radios_of(b, type_, net):
        return False, f"{b_name} has no {type_} {net}"
    if type_ == "SCR536":
        for n, e in ((a_name, a), (b_name, b)):
            if e.get("bereich", "offen") != "offen":
                return (
                    False,
                    f"{n} is under cover marker {e['bereich']}; SCR536 does not work there [RULE 4.3.5 p.29, FM1 p.50]",
                )
        ok, g = radio_los(s, a["karte"], b["karte"])
        if not ok:
            return False, f"no radio LOS {a['karte']} to {b['karte']}: {g} [RULE 4.3.5 p.29]"
        return True, f"{type_} {net}, LOS {a['karte']} to {b['karte']} ({g})"
    return True, f"{type_} {net} [RULE 4.3.5 p.29]"


def radio_link(s, a_name, b_name):
    """CO TAC Net [RULE 4.3.3 p.27]: the CO HQ is the hub; (None, '') if neither unit has a radio."""
    a, b = s["einheiten"][a_name], s["einheiten"][b_name]
    if not (radios_of(a) or radios_of(b)) or not state.radio_active(s):
        return None, ""
    if s.get("co_tac_mittel") == "telefon":
        return phone_link(s, a_name, b_name)  # [CSR 1 p.13, 4.3.4 p.28]
    for n, e in ((a_name, a), (b_name, b)):
        if not radios_of(e, "SCR536", "CO TAC"):
            return False, f"{n} has no SCR536 CO TAC (FOs may not join the CO TAC Net, [RULE 4.3.3 p.28])" if e[
                "typ"
            ] == "FO" else f"{n} has no SCR536 CO TAC"
    co = s.get("co_hq")
    if co in (a_name, b_name):
        return radio_direct(s, a_name, b_name)
    if co not in s["einheiten"]:
        return False, "CO HQ (hub of the CO TAC Net) not in play [RULE 4.3.3 p.27]"
    if not state.option(s, "U11_plt_mtr_ueber_hub"):
        return False, "only links with the CO HQ itself [RULE 4.3.3 p.27]" + state.open_reading(
            s, "U11_plt_mtr_ueber_hub"
        )
    ok1, g1 = radio_direct(s, a_name, co)
    ok2, g2 = radio_direct(s, co, b_name)
    if ok1 and ok2:
        return True, f"via the hub {co}: {g1}; {g2} [RULE 4.3.5 p.29]" + state.open_reading(s, "U11_plt_mtr_ueber_hub")
    return False, f"via the hub {co}: " + (g1 if not ok1 else g2) + state.open_reading(s, "U11_plt_mtr_ueber_hub")


def bn_link(s):
    """[RULE 4.1.1 p.18] BN HQ off-map activates the CO HQ if it is in communication via BN TAC."""
    co = s.get("co_hq")
    if co not in s["einheiten"]:
        return False, "CO HQ not in play"
    if s.get("co_immer_in_kommunikation") or not state.radio_active(s):
        return True, "always in communication per the mission"
    if not radios_of(s["einheiten"][co], "SCR300", "BN TAC"):
        return False, f"{co} carries no working SCR300 BN TAC [RULE 4.3.3 p.28, FM1 p.50]"
    return True, "SCR300 BN TAC, works everywhere [RULE 4.3.5 p.29]"


def visual_verbal(s, hq_name, target_name, akt=None):
    hq, z = state.unit(s, hq_name), state.unit(s, target_name)
    if hq["karte"] != z["karte"]:
        raise rules.Violation(
            f"{hq_name} ({hq['karte']}) and {target_name} ({z['karte']}) not on the same card, no Visual-Verbal communication [RULE 4.3.1 p.27]"
        )
    if hq.get("bereich", "offen") != z.get("bereich", "offen"):
        raise rules.Violation(
            f"{hq_name} and {target_name} in different areas of {hq['karte']} (cover marker/open) [RULE 4.3.1 p.27]"
        )
    if state.pinned(hq):
        raise rules.Violation(f"{hq_name} is Pinned and cannot give Visual-Verbal orders [RULE 4.3.1 p.27]")
    if state.pinned(z) and akt not in ("4.2.3a", "4.2.1b"):
        raise rules.Violation(
            f"{target_name} is Pinned; via Visual-Verbal only 'Attempt to Remove a Pinned marker' (4.2.3a) and a subsequent Exhort [RULE 4.3.1 p.27]"
        )
    return True


def communication(s, hq_name, target_name, akt=None):
    """4.3.1 Visual-Verbal: same card, same area, both Unpinned. Exception: Rally/Exhort to Pinned.
    Radio: field 'netz' (v2) or radios 'funk' (v3: SCR536 CO TAC with LOS, not under cover, CO HQ as hub)."""
    hq, z = state.unit(s, hq_name), state.unit(s, target_name)
    if hq_name == target_name:
        return True
    from . import vehicles  # L187 [RULE 10.1.1/10.1.2 p.70/71] vehicle nets and vehicle orders

    if (vehicles.is_vehicle(z) or vehicles.is_vehicle(hq)) and vehicles.order_check(s, hq_name, target_name, akt):
        return True
    if hq.get("netz") and z.get("netz") and hq["netz"] == z["netz"]:
        return True
    # FM1 CAC Run 1 p.36: 'assume that the CO HQ is always in communication with the PLT HQs and with the mortar section'
    if (
        s.get("co_immer_in_kommunikation")
        and hq_name == s.get("co_hq")
        and target_name in s.get("co_immer_in_kommunikation_mit", [])
    ):
        return True
    try:
        return visual_verbal(s, hq_name, target_name, akt)
    except rules.Violation as vv:
        ok, reason = radio_link(s, hq_name, target_name)
        if ok:
            s.setdefault("_hinweise", []).append(
                f"Communication {hq_name} with {target_name} by {'phone' if s.get('co_tac_mittel') == 'telefon' else 'radio'}: {reason}"
            )
            return True
        if ok is None:
            raise
        raise rules.Violation(f"{vv}; radio: {reason}") from None


def chain_of_command(s, hq_name, target_name):
    """4.0 p.18 Command Reference Table: PLT HQ orders its own platoon units and any LAT; CO HQ/Staff everything except higher HQs."""
    hq, z = state.unit(s, hq_name), state.unit(s, target_name)
    if hq_name == target_name or state.is_lat(z):
        return True
    if hq["typ"] == "Staff" or hq.get("ebene") in ("CO", "BN"):
        if hq["typ"] == "Staff" and z.get("ebene") in ("CO", "BN"):
            raise rules.Violation("Staff may not order a higher HQ [RULE 4.0 p.18]")
        if hq["typ"] == "Staff" and z["typ"] == "Staff" and z.get("rang", 9) < hq.get("rang", 9):
            raise rules.Violation(
                f"{hq_name} may not order {target_name} (Command Reference Table: 1st Sgt not to CO XO) [RULE 4.0 p.18]"
            )
        return True
    if z.get("platoon") != hq.get("platoon") and hq_name not in z.get("attached_an", []):
        raise rules.Violation(
            f"{target_name} is not in the chain of command of {hq_name} (Platoon {hq.get('platoon')}) [RULE 4.0 p.18]"
        )
    return True


def action_allowed(z, target_name, akt):
    """4.2.5: Pinned takes precedence, then LAT lists, Fire Team side like Fire Team."""
    name = rules.ACTIONS[akt][0]
    cc = akt.startswith("4.2.1")
    if (
        z.get("fahrzeug")
        and akt not in {"4.2.2h", "4.2.3a", "4.2.4k", "4.2.4l", "4.2.1i"}
        and not (cc and state.is_hq(z))
    ):
        raise rules.Violation(
            f"{target_name} is a vehicle: in the Command Phase only Load/Unload/Embark, Rally, Cease/Shift Fire and Activate for AT Combat & Vehicle Movement [10.1.2 p.71]"
        )  # L187
    if akt == "4.2.1i":
        return  # L187 [RULE 4.2.1i p.22] recipient check in vehicles.order_4_2_1i
    if z.get("stationaer") and akt.startswith("4.2.2"):
        raise rules.Violation(
            f"{target_name} is not part of the patrol: orders and fire yes, but no movement (except automatic retreat) [Normandy M3 MSR 1]"
        )
    if state.pinned(z) and akt not in rules.PINNED_ALLOWED and not cc:
        raise rules.Violation(
            f"{target_name} is Pinned: only Move to Adjacent (staging/friendly card without VOF), Seek Cover, Move within a Card, Rally 4.2.3a are allowed; no Combat Actions [RULE 4.2.5 p.26]"
        )
    if state.pinned(z) and akt in rules.PINNED_ALLOWED:
        return  # Pinned takes precedence over the LAT lists (4.2.5)
    if z["typ"] in rules.LAT_ALLOWED and akt not in rules.LAT_ALLOWED[z["typ"]] and not cc:
        raise rules.Violation(f"{z['typ']} may not perform '{name}' [RULE 4.2.5 p.26]")
    if state.fire_team_side(z) and akt not in rules.LAT_ALLOWED["Fire Team"] | {"4.2.3f"} and not cc:
        raise rules.Violation(
            f"{target_name} is on its Fire Team side and acts like a Fire Team [RULE 4.2.5 p.26, 6.4.3 p.47]"
        )


def experience(e):
    if state.is_lat(e):
        return rules.LAT_EXPERIENCE[e["typ"]]
    if state.fire_team_side(e):
        return "Green"
    return e.get("erfahrung", "Line")


def enemy_rally_cards(e):
    """[RULE 6.5.1 p.48] Rally under VOF: 2 cards, modified by the experience of the commander; for the enemy the unit itself (L fix 08.10.2026)."""
    ez = e.get("erfahrung")
    return max(1, 2 + {"Green": -1, "Veteran": 1}.get(ez, 0)), ez


def card_count(s, akt, orig, z, extra=0, base_cff=None):
    """4.2 p.21: base 2 (Seek Cover: card; Call for Fire: mission); experience of the recipient (movement/combat) or of the originator (Rally).
    Clarification 1: 0 cards = not possible (except Spotting: minimum 1)."""
    if akt == "4.2.2e":
        base = state.card(s, z["karte"]).get("cover_draw")
        if base is None:
            raise rules.Violation(
                f"Cover draw number of card {z['karte']} not recorded (bottom centre of the terrain card)"
            )
    elif akt == "4.2.4i":
        base = (
            base_cff if base_cff is not None else s.get("cff_karten", 2)
        )  # [RULE 7.16.1 p.58] number according to the actual observer
    else:
        base = 2
    who = orig if akt.startswith("4.2.3") else z
    if akt == "4.2.4a":
        # [RULE 8.5 Spotting Chart] the spotter's experience is already in spot_modifikatoren ("Spotting Recipient is Green -1 / Veteran +1"), do not count it twice (L41)
        return max(1, base + extra), who, base
    n = base + {"Green": -1, "Veteran": 1}.get(experience(who), 0) + extra
    if akt in ("4.2.4b", "4.2.4c") and z.get("tripod") and not state.fire_team_side(z):
        n += 1  # L137 [RULE 7.11.2 p.56] 'plus one additional card if firing a tripod-mounted machine gun'
    if n <= 0:
        raise rules.Violation(f"Number of cards {n}: attempt not possible [Clarification 1 to 4.2, May 2025]")
    return n, who, base


def spot_modifiers(s, sp, target_card_):
    """8.5 Spotting Attempt Draw Modifiers Chart (Charts & Tables 1)."""
    mods = []
    ez = experience(sp)
    if ez == "Green":
        mods.append(("Spotter Green", -1))
    if ez == "Veteran":
        mods.append(("Spotter Veteran", +1))
    ks, kz = state.card(s, sp["karte"]), state.card(s, target_card_)
    if ks.get("elevation", 1) + geometry.height_bonus(s, sp) > kz.get("elevation", 1) + geometry.card_height_bonus(
        s, target_card_, "Feind"
    ):  # L85: Upper Story counts (5.2.2)
        mods.append(("Spotter higher", +1))
    enemies = [s["einheiten"][n] for n in state.units_on(s, target_card_, "Feind")]
    if any(f.get("bereich", "offen") != "offen" for f in enemies):
        mods.append(("Target under cover", -1))
    if any(f.get("typname") in ("Sniper", "Spotter") for f in enemies):
        mods.append(("Target Sniper/FO", -1))
    if any(experience(f) == "Veteran" for f in enemies):
        mods.append(("Target Veteran", -1))
    if any(experience(f) == "Green" for f in enemies):
        mods.append(("Target Green", +1))
    cc = kz.get("cc", 0)
    if (
        kz.get("cc2") is not None
        and target_card_ != sp["karte"]
        and geometry.edge(kz, geometry.direction(s, target_card_, sp["karte"])) == "weiss"
    ):
        cc = kz[
            "cc2"
        ]  # [PLAYER AID Charts & Tables 1, Spotting Chart *] lower value when spotting across a white edge (5.2.3)
    if cc >= 3:
        mods.append(("Target card C&C +3 or more", -1))
    if cc == 0:
        mods.append(("Target card C&C +0", +1))
    if target_card_ == sp["karte"]:
        mods.append(("same card", +1))
    if any(rules.EXPOSED in f["status"] for f in enemies):
        mods.append(("Target Exposed", +2))
    if any(f.get("vof_rating") == "A" for f in enemies):
        mods.append(("Target with VOF A", +1))  # A/S does not count [FM1 p.43 Note]
    if any(f.get("vof_rating") in ("H", "G") for f in enemies):
        mods.append(("Target with VOF H or G!", +2))
    return mods


def phone_nodes(s):
    """Cards that are part of the phone line network: intact line, phone in use (implicit line, BGG E28), Staging (integrated)."""
    kn = set()
    for k, c in s["karten"].items():
        if c.get("staging") or any(not l.get("cut") for l in c.get("leitungen", [])):
            kn.add(k)
    for e in s["einheiten"].values():
        if e["seite"] == "US" and e.get("karte") in s["karten"] and radios_of(e, "EE8"):
            kn.add(e["karte"])
    return kn


def phone_net_connected(s, a, b, diag=None):
    """[RULE 4.3.4 p.28] 'unbroken string of phone line markers or other phones'; Staging with integrated lines.
    Returns: False, True (without diagonal) or 'diagonal' (only via diagonal adjacency, open U14)."""
    if diag is None:
        if phone_net_connected(s, a, b, False):
            return True
        return "diagonal" if state.option(s, "U14_telefon_diagonal") and phone_net_connected(s, a, b, True) else False
    kn = phone_nodes(s)
    if a not in kn or b not in kn:
        return False
    seen, stack = {a}, [a]
    while stack:
        k = stack.pop()
        if k == b:
            return True
        ck = state.card(s, k)
        for m in kn:
            if m in seen:
                continue
            cm_ = state.card(s, m)
            dr, dc = abs(ck["reihe"] - cm_["reihe"]), abs(ck["spalte"] - cm_["spalte"])
            nb = (dr + dc == 1) or (diag and dr == 1 and dc == 1) or (ck.get("staging") and cm_.get("staging"))
            if nb:
                seen.add(m)
                stack.append(m)
    return False


def phone_link(s, a_name, b_name):
    """CO TAC by telephone: both with EE8 CO TAC, the CO HQ is the hub; cover, Pinned, areas do not matter (4.3.4 p.28)."""
    a, b = s["einheiten"][a_name], s["einheiten"][b_name]
    for n, e in ((a_name, a), (b_name, b)):
        if not radios_of(e, "EE8", "CO TAC"):
            return False, f"{n} has no EE8 CO TAC"
    co = s.get("co_hq")
    if co not in (a_name, b_name):
        if co not in s["einheiten"]:
            return False, "CO HQ (hub of the CO TAC Net) not in play [4.3.3 p.27]"
        ok1, g1 = phone_link(s, a_name, co)
        ok2, g2 = phone_link(s, co, b_name)
        return (ok1 and ok2), f"via the hub {co}: " + (
            "; ".join((g1, g2)) if ok1 and ok2 else (g1 if not ok1 else g2)
        ) + state.open_reading(s, "U11_plt_mtr_ueber_hub")
    if a["karte"] == b["karte"]:
        return True, f"EE8 on the same card {a['karte']} [4.3.4 p.28]"
    vb = phone_net_connected(s, a["karte"], b["karte"])
    if vb:
        return True, f"EE8 CO TAC, line chain {a['karte']} to {b['karte']}" + (
            " (via diagonally adjacent cards)" + state.open_reading(s, "U14_telefon_diagonal")
            if vb == "diagonal"
            else ""
        ) + " [4.3.4 p.28]"
    return False, f"no unbroken line chain {a['karte']} to {b['karte']} (line cut or missing) [4.3.4 p.28]"


def lay_line(s, n, e, from_, prot, o=None):
    """[RULE 4.3.4 p.28] 'lay down one phone line marker per card ... automatically when a laying unit leaves a card' [open U15]."""
    if not e.get("leitungen") or state.card(s, from_).get("staging"):
        return
    if (o or {}).get("--leitung") == "nein" or not state.option(s, "U15_leitung_automatisch"):
        return
    c = state.card(s, from_)
    if any(not l.get("cut") for l in c.get("leitungen", [])):
        return
    c.setdefault("leitungen", []).append({"cut": False})
    e["leitungen"] -= 1
    prot.append(
        f"{n} lays a Phone Line on {from_} ({e['leitungen']} left)"
        + state.open_reading(s, "U15_leitung_automatisch")
        + " [4.3.4 p.28]"
    )


def cmd_line(s, args):
    """Phone lines: result of the damage check in 3.7.4 (ok|cut) or manual laying."""
    from . import cli  # lazy: one usage text, from the command table (review H10)

    usage = cli.usage("line")
    rules.need(args, 1, usage)
    prot = []
    if args[0] == "legen":
        rules.need(args, 3, usage)  # L330: 'line lay <card>' without the unit was an IndexError
        kid, n = args[1], args[2]
        e = state.unit(s, n)
        if e["karte"] != kid or not e.get("leitungen"):
            raise rules.Violation(f"{n} is not on {kid} or carries no phone line")
        state.card(s, kid).setdefault("leitungen", []).append({"cut": False})
        e["leitungen"] -= 1
        prot.append(f"{n} lays a Phone Line on {kid} (4.3.4: 'may lay down one phone line marker per card')")
    else:
        rules.need(args, 2, usage)  # L330: 'line <card>' without ok|cut
        kid, result = args[0], args[1]
        open_ = s.get("leitung_checks", {})
        if kid not in open_:
            raise rules.Violation(f"No phone line check is pending for {kid}")
        reason = open_.pop(kid)
        if result == "cut":
            for l in state.card(s, kid).get("leitungen", []):
                l["cut"] = True
            prot.append(f"Phone Line on {kid} cut ({reason}): marker to the Cut side; repair with 4.2.1k [4.3.4 p.29]")
        elif result == "ok":
            prot.append(f"Phone Line on {kid} stays intact ({reason})")
        else:
            raise rules.Violation(f"Usage: {usage}")
    state.save_state(s, "; ".join(prot), "4.3.4 p.29")
    briefing.print_board(prot, s)


def line_checks_3_7_4(s, prot):
    """[RULE 4.3.4 p.29] Incoming/Air Strike: R#1/2 cut; Good Order enemy without Good Order friendly: R#1-2/3 cut."""
    ch = {}
    for kid, c in s["karten"].items():
        if not any(not l.get("cut") for l in c.get("leitungen", [])):
            continue
        if any(x["typ"] in ("Incoming", "AirStrike") for x in c.get("extern", [])):
            ch[kid] = "Incoming/Air Strike, R# 1/2 = cut"
        elif any(state.good_order(s["einheiten"][m]) for m in state.units_on(s, kid, "Feind")) and not any(
            state.good_order(s["einheiten"][m]) for m in state.units_on(s, kid, "US")
        ):
            ch[kid] = "Good Order enemy without Good Order friendly, R# 1-2/3 = cut"
    if ch:
        s["leitung_checks"] = ch
        prot.append(
            "Check phone lines: "
            + "; ".join(f"{k} ({g})" for k, g in ch.items())
            + "; then fof.py line <card> ok|cut [4.3.4 p.29]"
        )


def runner_box(s):
    return s.setdefault("runner_box", [])


def runner_count(s):
    return len(runner_box(s)) + len([n for n, e in s["einheiten"].items() if e["typ"] == "Runner"])


def deliver_runner(s, prot):
    """[RULE 4.3.2 p.27] In the CO HQ impulse of the following turn: Runner not Pinned, HQ still on the card and not on its Fire Team side:
    HQ activated, Runner back to the Assets box. Otherwise it returns at the start of the first CO HQ impulse in Good Order."""
    for n, e in list(s["einheiten"].items()):
        if e["typ"] != "Runner" or e["seite"] != "US":
            continue
        if e.get("unterwegs_seit") == s["zug"]:
            continue
        hq = e.get("runner_ziel")
        h = s["einheiten"].get(hq)
        if state.pinned(e) or not state.good_order(e):
            prot.append(
                f"{n}: Pinned/not Good Order, no delivery; returns in the first CO HQ impulse in Good Order [4.3.2 p.27]"
            )
            continue
        if h and h["karte"] == e["karte"] and not state.fire_team_side(h) and hq in s["kommandos"]:
            s["kommandos"][hq]["aktiviert"] = True
            prot.append(
                f"{n} delivers: {hq} activated (Command marker on Commands Available); Runner back to the CO HQ Assets box [4.3.2 p.27]"
            )
        else:
            prot.append(
                f"{n}: {hq} no longer on {e['karte']} or on its Fire Team side; Runner returns to the Assets box [4.3.2 p.27]"
            )
        del s["einheiten"][n]  # back to the CO HQ Assets box (reusable), not a removal from play
        runner_box(s).append(n)


def cmd_runner(s, args):
    box = runner_box(s)
    on_board = [
        f"{n} on {e['karte']} for {e.get('runner_ziel')}" for n, e in s["einheiten"].items() if e["typ"] == "Runner"
    ]
    print(
        f"Runners in the CO HQ Assets box: {', '.join(box) or 'none'}; en route: {', '.join(on_board) or 'none'}; at most two in play [4.3.2 p.27]"
    )
