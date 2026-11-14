"""Pyrotechnics (4.4): smoke, illumination and colour signals with their recipients. Split from commands.py."""

from __future__ import annotations

from . import commands, fire, geometry, options, rules, state


def execute_pyro(s, recipient, name, o, prot):
    """[RULE 4.2.1c p.22, 4.4 p.30] Fire a pyrotechnic asset: Hand Held Illumination, HC/WP smoke or a signal (split into the parts below)."""
    type_, target_card = pyro_target(s, recipient, name, o)
    recipient["assets"].remove(type_)
    if type_ == "Handheld Illumination":
        _pyro_illumination(s, type_, target_card, prot)
    elif type_ in ("HC Smoke", "WP Smoke"):
        _pyro_smoke(s, type_, target_card, o, prot)
    else:
        _pyro_signal(s, type_, target_card, name, o, prot)


def pyro_target(s, recipient, name, o):
    """Legality of a pyro order: the recipient carries the asset and may use it; aerial pyrotechnics on the own or an
    adjacent card, smoke on the own card, no colored smoke at night. Returns (asset type, card)."""
    type_ = o.get("--asset")
    if not type_ or type_ not in recipient.get("assets", []):
        raise rules.Violation(
            f"{name}: specify --asset=<type>; carries {', '.join(recipient.get('assets', [])) or 'no pyro asset'} [4.2.1c p.22]"
        )
    if not (
        state.good_order(recipient)
        or (recipient["type"] in ("Assault Team", "Fire Team") and not state.pinned(recipient))
    ):
        raise rules.Violation("Recipient: Good Order unit or unpinned Assault/Fire Team [4.2.1c p.22]")
    target_card = o.get("--target", recipient["card"])
    state.card(s, target_card)
    if type_ in rules.PYRO_AERIAL:
        if target_card != recipient["card"] and not geometry.adjacent(s, recipient["card"], target_card):
            raise rules.Violation("Aerial pyrotechnics on the own card or an adjacent card [4.4 p.30]")
    elif target_card != recipient["card"]:
        raise rules.Violation("Non-aerial (smoke) only on the own card [4.4 p.30]")
    if type_ in rules.PYRO_COLOR and (s.get("light") or 0) >= 2:
        # [RULE 4.4.1 p.30] "Colored smoke cannot be used for signaling during night missions (Moon +2 or higher)"
        raise rules.Violation(
            f"{type_}: colored smoke cannot be used for signaling at night (light {s.get('light'):+d}, Moon +2 or higher); aerial pyrotechnics only [RULE 4.4.1 p.30]"
        )
    return type_, target_card


def _pyro_illumination(s, type_, target_card, prot):
    """[RULE 4.4, 9.2 p.70, Marker E34] Hand Held Illumination: this card only, immediately."""
    iv = (s.get("illum_values") or {}).get(type_) or {"top": -1, "bottom": None}
    state.card(s, target_card).setdefault("illum", []).append(
        {"top": iv["top"], "bottom": iv.get("bottom"), "source": type_}
    )
    prot.append(
        f"Hand Held Illumination {iv['top']:+d} on {target_card} (this card only), immediately; removed in Clean Up [4.4, 9.2 p.70, Marker E34]"
    )
    fire.open_fire(s, prot)


def _pyro_smoke(s, type_, target_card, o, prot):
    """[RULE 4.4.3 p.31, 5.4 p.38] HC/WP smoke on the own card: cover value from the marker, blocks LOS out of the card."""
    w = options.int_opt(o, "--value", "smoke cover value")
    if w is None:
        raise rules.Violation(
            f"{type_}: read the cover value from the marker (UNVERIFIED) and specify --value=<n> [4.4.3 p.31]"
        )
    state.card(s, target_card).setdefault("external", []).append(
        {"type": "Smoke", "value": w, "source": type_, "side": "US"}
    )
    prot.append(
        f"{type_} on {target_card} (cover +{w} against everything except Incoming/Air Strike/Mines/Grenade; blocks LOS out of and through {target_card}; removed in Clean Up) [4.4.3 p.31, 5.4 p.38]"
    )
    # [RULE 6.1.2 p.40 example 1]: firing units on the card keep firing, VOF on their own card (uses ammo), PDF
    # removed; Clean Up lifts the smoke and they fire along the old PDF again. Before: Cease Fire (no ammo).
    fire.cease_fire_on_los_loss(s, prot)


def _pyro_signal(s, type_, target_card, name, o, prot):
    """[RULE 4.4.1 p.30] Signal per the Mission Log assignment: Cease Fire, move or infiltrate to a card."""
    code = s.get("pyro_codes", {}).get(type_)
    prot.append(
        f"{type_} on {target_card} fired"
        + (f", Mission Log: {code}" if code else ", no assignment (no effect)")
        + " [4.4.1 p.30]"
    )
    if not code:
        return
    state.card(s, target_card).setdefault("pyro", []).append(type_)  # display only; removed in Clean Up (3.8), no VOF
    consequences = signal_recipients(s, type_, target_card, name)
    if code == "CF":
        for n in consequences:
            e = s["units"][n]
            if fire.is_firing(e):
                fire.cease_fire(e)
                prot.append(f"{n} ceases fire [4.2.4k]")
        fire.open_fire(s, prot)
        prot.append(
            "Cease Fire by signal: units with a Spotted enemy in LOS open fire again immediately per 6.1.1 [4.4.1 footnote]"
        )
        return
    targets_of = signal_targets(s, code, target_card, consequences)
    follow_signal(s, code, targets_of, o, prot)


def signal_recipients(s, type_, target_card, name):
    """[RULE 4.4.1 p.30] The US units that see the signal: colored flares everywhere, colored smoke only with normal LOS
    to the card; HQs of higher rank than the firing unit ignore it (unless option U21)."""
    consequences = []
    for n, e in s["units"].items():
        if e["side"] != "US":
            continue
        if type_ in rules.PYRO_COLOR and not (e["card"] == target_card or geometry.los(s, e["card"], target_card)[0]):
            continue
        if (
            not state.option(s, "U21_pyro_all_units")
            and state.is_hq(e)
            and n != name
            and commands.hq_rank(e) < commands.hq_rank(state.unit(s, name))
        ):
            continue
        consequences.append(n)
    return consequences


def signal_targets(s, code, target_card, consequences):
    """The card each recipient moves to for a movement signal (M2S, M2PO/M2SO, M2RP<n>, XPL<n>, InfAP2PO/SO)."""
    zi = s.get("objectives", {})
    targets_of = {}
    for n in consequences:
        e = s["units"][n]
        if code == "M2S" and geometry.adjacent(s, e["card"], target_card):
            targets_of[n] = target_card
        elif code in ("M2PO", "M2SO"):
            obj = zi.get("primary" if code == "M2PO" else "secondary")
            if obj and geometry.adjacent(s, e["card"], obj):
                targets_of[n] = obj
        elif code.startswith("M2RP"):
            rp = zi.get("route", {}).get(code[4:])
            if rp and geometry.adjacent(s, e["card"], rp):
                targets_of[n] = rp
        elif code.startswith("XPL"):
            r = zi.get("phaselines", {}).get(code[3:])
            if r is not None and state.card(s, e["card"])["row"] == r:
                k2 = geometry.card_at(s, r + 1, state.card(s, e["card"])["column"])
                if k2:
                    targets_of[n] = k2
        elif code in ("InfAP2PO", "InfAP2SO"):
            obj = zi.get("primary" if code == "InfAP2PO" else "secondary")
            if obj and e["card"] == zi.get("ap"):
                targets_of[n] = obj
    return targets_of


def follow_signal(s, code, targets_of, o, prot):
    """Every recipient with a target card moves (Exposed) or infiltrates (own draw per unit, Exposed on failure)."""
    result = commands.parse_per_unit(o.get("--success"))
    for n, zk2 in targets_of.items():
        e = s["units"][n]
        action_id = "4.2.2c" if code.startswith("Inf") else "4.2.2a"
        try:
            commands.check_move(s, e, n, zk2, action_id)
        except rules.Violation as v:
            prot.append(f"{n} cannot follow the signal: {v}")
            continue
        if action_id == "4.2.2c" and result.get(n) not in ("yes", "no"):
            raise rules.Violation(
                "infiltration by signal: every unit draws 2 cards (own experience): --success="
                + ",".join(f"{m}:yes|no" for m in targets_of)
                + " [4.4.1 p.30]"
            )
        commands.move_unit(s, n, zk2, None, exposed=(action_id == "4.2.2a" or result.get(n) == "no"), prot=prot)
    if not targets_of:
        prot.append("no unit meets the requirement of the signal")
