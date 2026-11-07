"""Pyrotechnics (4.4): smoke, illumination and colour signals with their recipients. Split from commands.py (L556)."""

from __future__ import annotations

from . import commands, fire, geometry, options, rules, state


def execute_pyro(s, z, name, o, prot):
    """[RULE 4.2.1c p.22, 4.4 p.30] Fire a pyrotechnic asset: Hand Held Illumination, HC/WP smoke or a signal (L256:
    split into the parts below)."""
    type_, zk = pyro_target(s, z, name, o)
    z["assets"].remove(type_)
    if type_ == "Handheld Illumination":
        _pyro_illumination(s, type_, zk, prot)
    elif type_ in ("HC Smoke", "WP Smoke"):
        _pyro_smoke(s, type_, zk, o, prot)
    else:
        _pyro_signal(s, type_, zk, name, o, prot)


def pyro_target(s, z, name, o):
    """Legality of a pyro order: the recipient carries the asset and may use it; aerial pyrotechnics on the own or an
    adjacent card, smoke on the own card, no colored smoke at night. Returns (asset type, card)."""
    type_ = o.get("--asset")
    if not type_ or type_ not in z.get("assets", []):
        raise rules.Violation(
            f"{name}: specify --asset=<type>; carries {', '.join(z.get('assets', [])) or 'no pyro asset'} [4.2.1c p.22]"
        )
    if not (state.good_order(z) or (z["typ"] in ("Assault Team", "Fire Team") and not state.pinned(z))):
        raise rules.Violation("Recipient: Good Order unit or unpinned Assault/Fire Team [4.2.1c p.22]")
    zk = o.get("--ziel", z["karte"])
    state.card(s, zk)
    if type_ in rules.PYRO_AERIAL:
        if zk != z["karte"] and not geometry.adjacent(s, z["karte"], zk):
            raise rules.Violation("Aerial pyrotechnics on the own card or an adjacent card [4.4 p.30]")
    elif zk != z["karte"]:
        raise rules.Violation("Non-aerial (smoke) only on the own card [4.4 p.30]")
    if type_ in rules.PYRO_COLOR and (s.get("licht") or 0) >= 2:
        # L138 [RULE 4.4.1 p.30] "Colored smoke cannot be used for signaling during night missions (Moon +2 or higher)"
        raise rules.Violation(
            f"{type_}: colored smoke cannot be used for signaling at night (light {s.get('licht'):+d}, Moon +2 or higher); aerial pyrotechnics only [RULE 4.4.1 p.30]"
        )
    return type_, zk


def _pyro_illumination(s, type_, zk, prot):
    """[RULE 4.4, 9.2 p.70, Marker E34] Hand Held Illumination: this card only, immediately."""
    iv = (s.get("illum_werte") or {}).get(type_) or {"oben": -1, "unten": None}
    state.card(s, zk).setdefault("illum", []).append({"oben": iv["oben"], "unten": iv.get("unten"), "quelle": type_})
    prot.append(
        f"Hand Held Illumination {iv['oben']:+d} on {zk} (this card only), immediately; removed in Clean Up [4.4, 9.2 p.70, Marker E34]"
    )
    fire.open_fire(s, prot)


def _pyro_smoke(s, type_, zk, o, prot):
    """[RULE 4.4.3 p.31, 5.4 p.38] HC/WP smoke on the own card: cover value from the marker, blocks LOS out of the card."""
    w = options.int_opt(o, "--wert", "smoke cover value")
    if w is None:
        raise rules.Violation(
            f"{type_}: read the cover value from the marker (UNVERIFIED) and specify --value=<n> [4.4.3 p.31]"
        )
    state.card(s, zk).setdefault("extern", []).append({"typ": "Smoke", "wert": w, "quelle": type_, "seite": "US"})
    prot.append(
        f"{type_} on {zk} (cover +{w} against everything except Incoming/Air Strike/Mines/Grenade; blocks LOS out of and through {zk}; removed in Clean Up) [4.4.3 p.31, 5.4 p.38]"
    )
    # L462 [RULE 6.1.2 p.40 example 1]: firing units on the card keep firing, VOF on their own card (uses ammo), PDF
    # removed; Clean Up lifts the smoke and they fire along the old PDF again (L148). Before: Cease Fire (no ammo).
    fire.cease_fire_on_los_loss(s, prot)


def _pyro_signal(s, type_, zk, name, o, prot):
    """[RULE 4.4.1 p.30] Signal per the Mission Log assignment: Cease Fire, move or infiltrate to a card."""
    code = s.get("pyro_belegung", {}).get(type_)
    prot.append(
        f"{type_} on {zk} fired"
        + (f", Mission Log: {code}" if code else ", no assignment (no effect)")
        + " [4.4.1 p.30]"
    )
    if not code:
        return
    state.card(s, zk).setdefault("pyro", []).append(type_)  # display only; removed in Clean Up (3.8), no VOF
    consequences = signal_recipients(s, type_, zk, name)
    if code == "CF":
        for n in consequences:
            e = s["einheiten"][n]
            if fire.is_firing(e):
                fire.cease_fire(e)
                prot.append(f"{n} ceases fire [4.2.4k]")
        fire.open_fire(s, prot)
        prot.append(
            "Cease Fire by signal: units with a Spotted enemy in LOS open fire again immediately per 6.1.1 [4.4.1 footnote]"
        )
        return
    targets_of = signal_targets(s, code, zk, consequences)
    follow_signal(s, code, targets_of, o, prot)


def signal_recipients(s, type_, zk, name):
    """[RULE 4.4.1 p.30] The US units that see the signal: colored flares everywhere, colored smoke only with normal LOS
    to the card; HQs of higher rank than the firing unit ignore it (unless option U21)."""
    consequences = []
    for n, e in s["einheiten"].items():
        if e["seite"] != "US":
            continue
        if type_ in rules.PYRO_COLOR and not (e["karte"] == zk or geometry.los(s, e["karte"], zk)[0]):
            continue
        if (
            not state.option(s, "U21_pyro_alle_einheiten")
            and state.is_hq(e)
            and n != name
            and commands.hq_rank(e) < commands.hq_rank(state.unit(s, name))
        ):
            continue
        consequences.append(n)
    return consequences


def signal_targets(s, code, zk, consequences):
    """The card each recipient moves to for a movement signal (M2S, M2PO/M2SO, M2RP<n>, XPL<n>, InfAP2PO/SO)."""
    zi = s.get("ziele", {})
    targets_of = {}
    for n in consequences:
        e = s["einheiten"][n]
        if code == "M2S" and geometry.adjacent(s, e["karte"], zk):
            targets_of[n] = zk
        elif code in ("M2PO", "M2SO"):
            obj = zi.get("primaer" if code == "M2PO" else "sekundaer")
            if obj and geometry.adjacent(s, e["karte"], obj):
                targets_of[n] = obj
        elif code.startswith("M2RP"):
            rp = zi.get("route", {}).get(code[4:])
            if rp and geometry.adjacent(s, e["karte"], rp):
                targets_of[n] = rp
        elif code.startswith("XPL"):
            r = zi.get("phaselines", {}).get(code[3:])
            if r is not None and state.card(s, e["karte"])["reihe"] == r:
                k2 = geometry.card_at(s, r + 1, state.card(s, e["karte"])["spalte"])
                if k2:
                    targets_of[n] = k2
        elif code in ("InfAP2PO", "InfAP2SO"):
            obj = zi.get("primaer" if code == "InfAP2PO" else "sekundaer")
            if obj and e["karte"] == zi.get("ap"):
                targets_of[n] = obj
    return targets_of


def follow_signal(s, code, targets_of, o, prot):
    """Every recipient with a target card moves (Exposed) or infiltrates (own draw per unit, Exposed on failure)."""
    result = commands.parse_per_unit(o.get("--erfolg"))  # L230 (review H8)
    for n, zk2 in targets_of.items():
        e = s["einheiten"][n]
        akt = "4.2.2c" if code.startswith("Inf") else "4.2.2a"
        try:
            commands.check_move(s, e, n, zk2, akt)
        except rules.Violation as v:
            prot.append(f"{n} cannot follow the signal: {v}")
            continue
        if akt == "4.2.2c" and result.get(n) not in ("ja", "nein"):
            raise rules.Violation(
                "infiltration by signal: every unit draws 2 cards (own experience): --success="
                + ",".join(f"{m}:yes|no" for m in targets_of)
                + " [4.4.1 p.30]"
            )
        commands.move_unit(s, n, zk2, None, exposed=(akt == "4.2.2a" or result.get(n) == "nein"), prot=prot)
    if not targets_of:
        prot.append("no unit meets the requirement of the signal")
