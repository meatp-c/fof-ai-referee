"""Derived fire: VOF, PDF, Crossfire, Activity Level, opening and ceasing fire (6.1 to 6.3)."""

from . import geometry, rules, state


def can_fire(e):
    if e.get("deep_bunker") and e.get("bereich") == e["deep_bunker"]:
        return False  # [CSR 5 p.14] Deep Bunker: units inside place no VOF
    if state.is_mortar(e) and ("Exposed" in e["status"] or e.get("indirekt")):
        return False  # [RULE 7.3.1 p.53] no fire with Exposed; [RULE 7.3.2 p.53] Indirect Lay replaces Direct Lay
    if e.get("tripod") and "Exposed" in e["status"] and not state.fire_team_side(e):
        return False  # [RULE 7.2.1 p.51] tripod MG does not fire with an Exposed marker
    if e.get("vof_rating") == "G" and not state.fire_team_side(e) and not e.get("out_of_ammo"):
        return False  # [RULE 7.3.2 p.53, 6.3.6 p.45] G! units fire only via Grenade Attack (Mortar Team: own PDF, 'nur_pdf')
    return bool(e.get("vof_rating")) and e["typ"] not in ("Litter Team", "Paralyzed Team", "Runner")


def is_firing(e):
    return e.get("ziel") is not None and (can_fire(e) or bool(e.get("nur_pdf")))


def current_vof_rating(e, point_blank):
    r = e.get("ft_vof", "S") if state.fire_team_side(e) else e.get("vof_rating")
    if e.get("out_of_ammo"):
        return "S"  # [RULE 7.18.2 p.61] Out of Ammo: VOF S
    if r == "S!":
        return "S"  # [RULE 7.15 p.57] Sniper: Small Arms on the card, Sniper VOF on one target
    if r == "A/S":
        r = "A" if point_blank else "S"
    return r


def overhead_possible(s, from_, between, target):
    """[RULE 7.2.1 p.51] Elevation conditions for Overhead Fire over an intervening card."""
    lf, li, lt = (state.card(s, k).get("elevation", 1) for k in (from_, between, target))
    return (li == lt and li <= lf - 1) or (li == lf and li <= lt - 1) or (li < lf and li < lt)


def effective_fire_target(s, n):
    """6.1.1/6.1.2: VOF lies on the nearest occupied card along the PDF (unspotted enemies are fired over)."""
    e = s["einheiten"][n]
    z = e["ziel"]
    if z == e["karte"]:
        return z
    for k in geometry.line_between(s, e["karte"], z) or []:
        if geometry.blocks_los(state.card(s, k), False, s):
            return k  # L96 [RULE 6.1.2 p.44] Smoke/Incoming/Air Strike along the PDF: move the VOF back to the blocking card (even over own troops, no Overhead)
        occupants = [
            m
            for m in state.units_on(s, k)
            if s["einheiten"][m]["seite"] == e["seite"] or state.is_visible(s["einheiten"][m])
        ]
        if state.is_mortar(e) or (
            (e.get("vof_rating") == "H" or e.get("tripod")) and overhead_possible(s, e["karte"], k, z)
        ):
            # [RULE 7.3.1 p.53] mortars fire over cards with friendly troops without hitting them
            # [RULE 7.2.1 p.51] Overhead Fire (tripod MG, H VOF): "Do not place a VOF marker on the card being fired over."
            occupants = [m for m in occupants if s["einheiten"][m]["seite"] != e["seite"]]
        if occupants:
            return k
    return z


def vof_entries(s, kid):
    """Fire effects on card kid: (typ, wert, quelle, trifft_seite or None=both, von_karte)."""
    out = []
    for n, e in s["einheiten"].items():
        if not is_firing(e) or effective_fire_target(s, n) != kid or e.get("nur_pdf"):
            continue
        pb = e["karte"] == kid
        type_ = "Pinned" if state.pinned(e) else current_vof_rating(e, pb)
        out.append(
            (type_, rules.VOF_VALUE.get(type_, 0), n, state.opponent_of_side(e["seite"]) if pb else None, e["karte"])
        )
    for x in state.card(s, kid).get("extern", []):
        if x["typ"] not in ("Pending", "Smoke"):  # [RULE 5.4 p.38] smoke is cover, not a VOF (v4 correction)
            out.append((x["typ"], x["wert"], x.get("quelle", x["typ"]), None, None))
    return out


def vof_against(s, kid, side, ignore_mines=False):
    """Best (lowest) VOF that hits units of the side on kid: (typ, wert, [quellen]) or None.
    ohne_minen: Mines! markers count as VOF markers (Pinned Recovery, Rally, Infiltration, activity; BGG E35), but only hit
    the units that failed the mine check [RULE 6.3.6 p.45, 7.9.1 p.54]."""
    tr = [x for x in vof_entries(s, kid) if x[3] in (None, side) and not (ignore_mines and x[0] == "Mines")]
    if not tr:
        return None
    best = min(x[1] for x in tr)
    return [x for x in tr if x[1] == best][0][0], best, [x[2] for x in tr]


def pdfs_to(s, kid, target_side):
    """Cards from which fire of the opposing side affects kid from outside."""
    return {
        e["karte"]
        for n, e in s["einheiten"].items()
        if is_firing(e)
        and e["karte"] != kid
        and effective_fire_target(s, n) == kid
        and e["seite"] == state.opponent_of_side(target_side)
    }


def crossfire(s, kid, target_side):
    """6.2.4: two or more PDFs from different directions from outside."""
    kz = state.card(s, kid)
    dir_name = set()
    for k in pdfs_to(s, kid, target_side):
        kk = state.card(s, k)
        dr, dc = kk["reihe"] - kz["reihe"], kk["spalte"] - kz["spalte"]
        dir_name.add(((dr > 0) - (dr < 0), (dc > 0) - (dc < 0)))
    return len(dir_name) >= 2


def expected_activity(s):
    """8.1 / Charts 1: No Contact only without any VOF/PDF marker and without a spotted enemy."""
    vk = [k for k in s["karten"] if vof_entries(s, k)]
    occupants = [k for k in vk if state.units_on(s, k)]
    spotted = any(e["seite"] == "Feind" and e.get("spotted") for e in s["einheiten"].values())
    pdf = any(is_firing(e) and e["ziel"] != e["karte"] for e in s["einheiten"].values())
    pending = any(x["typ"] == "Pending" for c in s["karten"].values() for x in c.get("extern", []))
    if len(occupants) >= 2 and any(state.units_on(s, k, "US") and state.units_on(s, k, "Feind") for k in occupants):
        return "Heavily Engaged"
    if len(occupants) >= 2:
        return "Engaged"
    if vk or spotted or pdf or pending:
        return "Contact"
    return "No Contact"


def update_activity(s):
    if s.get("aktivitaet") is None or s["phase"] == "3.7.4":
        return None
    old, new = s["aktivitaet"], expected_activity(s)
    s["aktivitaet"] = new
    return None if old == new else f"Activity level {old} becomes {new}: move the Activity marker [8.1]"


def fire_position_forbidden(s, e):
    """Reason why a unit may not fire at all from its card, otherwise None."""
    if state.is_mortar(e):
        c = state.card(s, e["karte"])
        if "Woods" in c.get("terrain", "") or c.get("moerser_verbot"):
            return "Mortars do not fire from Woods [RULE 7.3.1 p.53, FM1 p.36]"
        cv = geometry.cover_marker(s, e)
        if cv and cv["typ"] in rules.STRUCTURES + ("Building", "Cave"):
            return "Mortars do not fire from Building/Bunker/Cave/Pillbox [RULE 7.3.1 p.52]"
    return None


def fire_candidates(s, n):
    e = s["einheiten"][n]
    candidate = []
    if fire_position_forbidden(s, e):
        return candidate
    arc = geometry.arc_direction(s, e)
    for kid in s["karten"]:
        if kid == e["karte"]:
            if geometry.no_point_blank(s, e):
                continue
            if not geometry.in_range(s, e, kid):
                continue
        else:
            if (
                not geometry.in_range(s, e, kid)
                or not geometry.los(
                    s,
                    e["karte"],
                    kid,
                    ha=geometry.height_bonus(s, e),
                    hb=geometry.card_height_bonus(s, kid, geometry.opponent_of(e)),
                )[0]
            ):
                continue
            if e["seite"] == "US" and state.units_on(s, kid, "US"):
                continue  # 8.4.3: friendly units do not open fire on jointly occupied cards
            if (
                not state.is_mortar(e)
                and e.get("vof_rating") != "H"
                and any(
                    state.units_on(s, between, e["seite"])
                    for between in (geometry.line_between(s, e["karte"], kid) or [])
                )
            ):
                continue  # [RULE 6.1.1 p.40 ex. 2, K16] VOF would land on the friendly intervening card; only H (Overhead) and mortars fire over it
            if not state.is_mortar(e) and any(
                [m for m in state.units_on(s, between, geometry.opponent_of(e)) if state.is_visible(s["einheiten"][m])]
                for between in (geometry.line_between(s, e["karte"], kid) or [])
            ):
                continue  # L122 [RULE 6.1.2 p.39] the VOF would be exerted into the closer occupied card, which is the real target
            if (
                e.get("bunker_richtung")
                and kid != e["bunker_richtung"]
                and e["bunker_richtung"] not in ((geometry.line_between(s, e["karte"], kid) or []) + [kid])
            ):
                continue
            if arc and geometry.direction(s, e["karte"], kid) != arc:
                continue  # [RULE 5.3.2 p.37] only in the arrow direction
        if state.valid_target(s, kid, e["seite"]):
            candidate.append(kid)
    return candidate


def pdf_note(s, from_, to_, n):
    """V20 (the player): with every new PDF, state whether the source card has further PDFs."""
    others = sorted(
        {
            x["ziel"]
            for m, x in s["einheiten"].items()
            if m != n and x.get("karte") == from_ and x.get("ziel") and x["ziel"] not in (from_, to_) and is_firing(x)
        }
    )
    same = [
        m
        for m, x in s["einheiten"].items()
        if m != n and x.get("karte") == from_ and x.get("ziel") == to_ and is_firing(x)
    ]
    head = f" (PDF marker {from_} to {to_} already lies there from {', '.join(same)}, no new marker" if same else " ("
    tail = f"further PDF from {from_}: to {', '.join(others)})" if others else f"no other PDF from {from_})"
    return head + ("; " if same else "") + tail  # L121


def open_fire(s, prot, only=None):
    """6.1.1: unengaged units with a VOF rating open fire automatically. Tie: random choice by the player."""
    for n, e in s["einheiten"].items():
        if only is not None and n not in only:
            continue
        if (
            e.get("ziel") is not None
            or not can_fire(e)
            or e.get("karte") not in s["karten"]
            or state.card(s, e["karte"]).get("staging")
        ):
            continue
        if e.get("kein_feuer_bis_clean_up"):
            continue  # [RULE 8.3 p.63] Place PDF/VOF No: opens fire only in Clean Up
        candidate = fire_candidates(s, n)
        if not candidate:
            e.pop("ziel_offen", None)
            continue
        # L122 [RULE 6.1.1 p.39] "If a unit enters a card where there is firing already going on ... the entering unit joins in the existing fire"
        existing = sorted(
            {
                x["ziel"]
                for m, x in s["einheiten"].items()
                if m != n
                and x["seite"] == e["seite"]
                and x.get("karte") == e["karte"]
                and is_firing(x)
                and x["ziel"] in candidate
            }
        )
        if existing:
            candidate = existing
        if e["seite"] == "US":
            d = min(geometry.distance(s, e["karte"], k) for k in candidate)
            candidate = [k for k in candidate if geometry.distance(s, e["karte"], k) == d]
            if len(candidate) > 1:

                def vof_from(k):
                    w = [x[1] for x in vof_entries(s, e["karte"]) if x[4] == k]
                    return min(w) if w else 99

                b = min(vof_from(k) for k in candidate)
                candidate = [k for k in candidate if vof_from(k) == b]
        else:

            def us_steps(k):
                return sum(state.steps(s["einheiten"][m]) for m in state.valid_target(s, k, "Feind"))

            m = max(us_steps(k) for k in candidate)
            candidate = [k for k in candidate if us_steps(k) == m]
        if len(candidate) == 1:
            cf_vorher = crossfire(s, candidate[0], state.opponent_of_side(e["seite"]))
            e["ziel"] = candidate[0]
            e.pop("ziel_offen", None)
            prot.append(
                f"{n} opens fire on {candidate[0]}"
                + (
                    " (Point Blank)"
                    if candidate[0] == e["karte"]
                    else f", PDF from {e['karte']} to {candidate[0]}" + pdf_note(s, e["karte"], candidate[0], n)
                )
                + (" with Pinned VOF" if state.pinned(e) else "")
                + " [6.1.1]"
            )
            if not cf_vorher and crossfire(s, candidate[0], state.opponent_of_side(e["seite"])):
                prot.append(f"Crossfire marker on {candidate[0]} (PDFs from two directions) [6.2.4]")
        else:
            e["ziel_offen"] = candidate
            prot.append(
                f'{n}: determine fire target by R# from {", ".join(candidate)}, then fof.py fire "{n}" <card> [6.1.1]'
            )


def carried_markers(e):
    """Markers that travel with a moving counter: Pinned, ammo, Out of Ammo, assets, radios (L109)."""
    out = [m for m in e.get("status", []) if m != "Exposed"]
    m = e.get("munition")
    if m:
        out.append(f"{m.get('typ', '')} ammo marker {m.get('punkte')}")
    if e.get("out_of_ammo"):
        out.append("Out of Ammo")
    out += list(e.get("assets") or [])
    out += [f"radio {r.get('typ')}" for r in e.get("funk") or []]
    if e.get("traegt_casualties"):
        out.append(f"{e['traegt_casualties']} Casualty")
    return out


def fire_after_move(s, n, prot):
    """6.1.2: movement to another card = Cease Fire, then 6.1.1 again; firing opponents on the new card shift to Point Blank."""
    e = s["einheiten"][n]
    carried = carried_markers(e)
    if carried:
        prot.append(f"{n}: these markers move along: {', '.join(carried)}")  # L109 (Manuel)
    if e.get("ziel") is not None:
        prot.append(f"{n} ceases fire due to the movement (adjust PDF/VOF) [6.1.2]")
        e["ziel"] = None
        e.pop("konzentriert", None)
    # [RULE 8.5 p.65] "A card can never contain both Spotted and Unspotted enemy units" (L108)
    if e["seite"] == "Feind":
        group = state.units_on(s, e["karte"], "Feind")
        if any(s["einheiten"][m].get("spotted") for m in group) and not all(
            s["einheiten"][m].get("spotted") for m in group
        ):
            for m in group:
                s["einheiten"][m]["spotted"] = True
            prot.append(f"Enemies on {e['karte']} now all Spotted: remove Unspotted markers [8.5 p.65]")
    open_fire(s, prot, only=[n])
    for m, f in s["einheiten"].items():
        if (
            f["seite"] != e["seite"]
            and f["karte"] == e["karte"]
            and is_firing(f)
            and f["ziel"] != f["karte"]
            and state.is_visible(e)
            and not geometry.no_point_blank(s, f)
        ):
            f["ziel"] = f["karte"]
            prot.append(f"{m} shifts fire to its own card (Point Blank) [6.1.2]")
    # [RULE 3.0 p.15, 6.1.1 p.39] after every board change all unengaged units with a valid target open fire
    open_fire(s, prot)


def cover_of(s, e):
    if e.get("bereich", "offen") == "offen":
        return None
    for c in state.card(s, e["karte"]).get("cover", []):
        if c["id"] == e["bereich"]:
            return c
    return None


def cease_fire_on_los_loss(s, prot):
    """[RULE 6.1.2, 9.1, 9.2.1] Target no longer in LOS/range (e.g. Illumination removed in Clean Up): cease fire."""
    for n, e in s["einheiten"].items():
        zk = e.get("ziel")
        if not zk or zk == e.get("karte") or zk not in s["karten"] or e.get("karte") not in s["karten"]:
            continue
        los_ok_, los_reason = geometry.los(
            s,
            e["karte"],
            zk,
            ha=geometry.height_bonus(s, e),
            hb=geometry.card_height_bonus(s, zk, geometry.opponent_of(e)),
        )
        if not los_ok_ and los_reason.startswith("Incoming/Smoke on "):
            # L96 [RULE 6.1.2 p.44]: a block on an intervening card is no Cease Fire; the VOF sits on the blocking card (feuerziel_effektiv)
            fk = effective_fire_target(s, n)
            if e.get("_vof_sperre") != fk:
                e["_vof_sperre"] = fk
                prot.append(
                    f"{n}: move the VOF from {zk} back along the PDF to the blocking card {fk} (PDF stays) [6.1.2 p.44, 5.4]"
                )
            continue
        if e.pop("_vof_sperre", None):
            prot.append(f"{n}: block lifted, VOF back on {effective_fire_target(s, n)} [6.1.2]")
        if not los_ok_ or not geometry.in_range(s, e, zk):
            e["ziel"] = None
            e.pop("konzentriert", None)
            reason = (
                los_reason if not los_ok_ else "out of range"
            )  # L94: name the real reason instead of a blanket night 9.1
            prot.append(f"{n} ceases fire on {zk}, remove the VOF marker from {zk}: {reason} [6.1.2]")


def enemy_cease_fire(s, prot):
    """8.6.4 / 3.4.2 / 3.8: enemies without a valid target cease fire and open fire anew per 6.1.1."""
    for n, e in s["einheiten"].items():
        if e["seite"] == "Feind" and is_firing(e):
            zk = effective_fire_target(s, n)
            if not state.valid_target(s, zk, "Feind"):
                e["ziel"] = None
                e.pop("konzentriert", None)
                prot.append(f"{n}: Cease Fire, no valid target left on {zk} [8.6.4]")
    open_fire(s, prot, only=[n for n, e in s["einheiten"].items() if e["seite"] == "Feind"])
