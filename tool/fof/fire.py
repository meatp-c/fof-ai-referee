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
    hi = state.range_limits(s, e)[1]
    last_in_range = None
    for k in geometry.line_between(s, e["karte"], z) or []:
        if geometry.distance(s, e["karte"], k) > hi:
            # L147 [RULE 6.3.2 p.43 example, 7.18.2] out of range (e.g. Out of Ammo: range Close): "The PDF stays the same but
            # its VOF is moved to the adjacent card"; the VOF lies on the last card in range along the PDF
            return last_in_range or e["karte"]
        last_in_range = k
        if geometry.blocks_los(state.card(s, k), False, s):
            return k  # L96 [RULE 6.1.2 p.44] Smoke/Incoming/Air Strike along the PDF: move the VOF back to the blocking card (even over own troops, no Overhead)
        occupants = [
            m
            for m in state.units_on(s, k)
            if s["einheiten"][m]["seite"] == e["seite"] or state.is_visible(s["einheiten"][m])
        ]
        if state.is_mortar(e):
            # [RULE 7.3.1 p.53] mortars fire over cards with friendly troops without hitting them
            occupants = [m for m in occupants if s["einheiten"][m]["seite"] != e["seite"]]
        elif (e.get("vof_rating") == "H" or e.get("tripod")) and overhead_possible(s, e["karte"], k, z):
            # [RULE 7.2.1 p.51, 7.2.3] Overhead Fire (tripod MG, H VOF): "Do not place a VOF marker on the card being fired over";
            # 8.4.3 example 1: also over opposing units (RCL shifts fire over the CCF squad to the HMG on the hill). L147
            occupants = []
        if occupants:
            return k
    if geometry.distance(s, e["karte"], z) > hi:
        return last_in_range or e["karte"]
    return z


def grazing(s, e):
    """[RULE 7.2.2 p.51] Grazing Fire: tripod-mounted MG firing at range (not Point Blank) on its Good Order side,
    not Pinned (BGG 3498699: the Pinned VOF has no Grazing Fire) and not Out of Ammo (7.18.2: VOF S). L128"""
    return bool(
        e.get("tripod")
        and not state.fire_team_side(e)
        and not state.pinned(e)
        and not e.get("out_of_ammo")
        and e.get("ziel") is not None
        and e["ziel"] != e.get("karte")
        and can_fire(e)
    )


def grazing_cards(s, n):
    """[RULE 7.2.2 p.51] 'it exerts its VOF into every card along its PDF up to its maximum range as long as all the cards
    are at the same elevation, or all uphill/all downhill ... and LOS exists.' Cards beyond the target included; a LOS block
    (Smoke/Incoming, 6.1.2 p.44, example 4 p.41) is the last card; friendly cards on the line are hit too (note 7.2.2).
    No Grazing Fire at all when the elevation pattern breaks before the target (BGG 3535366, 3558804). L128"""
    e = s["einheiten"][n]
    if not grazing(s, e) or e["karte"] not in s["karten"] or e["ziel"] not in s["karten"]:
        return []
    ka, kz = state.card(s, e["karte"]), state.card(s, e["ziel"])
    dr, dc = kz["reihe"] - ka["reihe"], kz["spalte"] - ka["spalte"]
    if not (dr == 0 or dc == 0 or abs(dr) == abs(dc)):
        return []
    sr, sc = (dr > 0) - (dr < 0), (dc > 0) - (dc < 0)
    ray, prev, trend, i = [], ka.get("elevation", 1), None, 1
    while True:  # cards on the line with a valid elevation pattern, up to max range
        k = geometry.card_at(s, ka["reihe"] + sr * i, ka["spalte"] + sc * i)
        if k is None or not geometry.in_range(s, e, k) or state.card(s, k).get("staging"):
            break
        ez = state.card(s, k).get("elevation", 1)
        step = (ez > prev) - (ez < prev)
        if trend is None:
            trend = step
        elif step != trend:
            break  # level and slope must not mix, slope must not reverse
        ray.append(k)
        prev, i = ez, i + 1
    if e["ziel"] not in ray:
        return []  # e.g. 2-1-1: the MG just fires at the nearest card
    out = []
    for k in ray:  # LOS: a blocking card (Smoke/Incoming) is the last one, the cards behind it get no VOF
        ok, _why = geometry.los(
            s,
            e["karte"],
            k,
            ha=geometry.height_bonus(s, e),
            hb=geometry.card_height_bonus(s, k, geometry.opponent_of(e)),
        )
        if not ok:
            break
        out.append(k)
    return out


def vof_entries(s, kid):
    """Fire effects on card kid: (typ, wert, quelle, trifft_seite or None=both, von_karte)."""
    out = []
    for n, e in s["einheiten"].items():
        if not is_firing(e) or e.get("nur_pdf"):
            continue
        if effective_fire_target(s, n) != kid and kid not in grazing_cards(s, n):
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
        and (effective_fire_target(s, n) == kid or kid in grazing_cards(s, n))
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
            own_between = [
                between
                for between in (geometry.line_between(s, e["karte"], kid) or [])
                if state.units_on(s, between, e["seite"])
            ]
            if own_between and not state.is_mortar(e):
                overhead = (e.get("vof_rating") == "H" or e.get("tripod")) and all(
                    overhead_possible(s, e["karte"], b, kid) for b in own_between
                )
                if not overhead:
                    continue  # [RULE 6.1.1 p.40 ex. 2, K16] VOF would land on the friendly intervening card; only Overhead Fire (7.2.3: tripod MG or H VOF with the elevation condition) and mortars fire over it (L147)
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


def grazing_note(s, n):
    """Cards besides the target that receive the VOF through Grazing Fire (L128)."""
    e = s["einheiten"][n]
    extra = [k for k in grazing_cards(s, n) if k != e.get("ziel")]
    return f"; Grazing Fire: VOF marker also on {', '.join(extra)} [7.2.2 p.51]" if extra else ""


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
                + grazing_note(s, n)
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
        prot.append(f"{n}: these markers move along: {', '.join(carried)}")  # L109
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
    # L149 [RULE 6.3.4 p.44] "if the last unit under a VOF from an opposing unit on the same card moves away to an adjacent card
    # (in any direction), the opposing unit's fire follows the moving unit to the new card. Move the VOF to the new card and place a PDF marker."
    if state.is_visible(e) and e.get("karte") in s["karten"]:
        for m, f in s["einheiten"].items():
            if (
                f["seite"] != e["seite"]
                and f.get("karte") in s["karten"]
                and f["karte"] != e["karte"]
                and is_firing(f)
                and f["ziel"] == f["karte"]
                and geometry.adjacent(s, f["karte"], e["karte"])
                and not state.valid_target(s, f["karte"], f["seite"])
            ):
                ok, _why = geometry.los(
                    s,
                    f["karte"],
                    e["karte"],
                    ha=geometry.height_bonus(s, f),
                    hb=geometry.card_height_bonus(s, e["karte"], geometry.opponent_of(f)),
                )
                if ok and geometry.in_range(s, f, e["karte"]) and e["karte"] in fire_candidates(s, m):
                    f["ziel"] = e["karte"]
                    f.pop("konzentriert", None)
                    prot.append(
                        f"{m}: fire follows {n} to {e['karte']}, PDF from {f['karte']} to {e['karte']}"
                        + pdf_note(s, f["karte"], e["karte"], m)
                        + " [6.3.4 p.44]"
                    )
                else:
                    f["ziel"] = None
                    f.pop("konzentriert", None)
                    prot.append(
                        f"{m}: last Point Blank target left {f['karte']}, cannot follow: Cease Fire, opens fire anew per 6.1.1 [6.3.4, 6.3.3]"
                    )
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
        if zk and zk == e.get("karte") and e.get("_rauch_ziel") and e["karte"] in s["karten"]:
            # L148: smoke/Incoming on the own card has lifted: back to the former target if still possible
            if not geometry.blocks_los(state.card(s, e["karte"]), False, s):
                old = e.pop("_rauch_ziel")
                ok2, _r = (
                    geometry.los(
                        s,
                        e["karte"],
                        old,
                        ha=geometry.height_bonus(s, e),
                        hb=geometry.card_height_bonus(s, old, geometry.opponent_of(e)),
                    )
                    if old in s["karten"]
                    else (False, "")
                )
                if ok2 and geometry.in_range(s, e, old) and state.valid_target(s, old, e["seite"]):
                    e["ziel"] = old
                    prot.append(f"{n}: smoke on {e['karte']} lifted, fires again at {old} along the PDF [6.1.2]")
                else:
                    e["ziel"] = None
                    prot.append(
                        f"{n}: smoke on {e['karte']} lifted, former target {old} no longer valid: Cease Fire, opens fire anew per 6.1.1 [6.3.3]"
                    )
            continue
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
        if los_ok_ and not geometry.in_range(s, e, zk):
            # L147 [RULE 6.3.2 p.43 example]: out of range (Out of Ammo): the PDF stays, the VOF moves to the last card in range
            fk = effective_fire_target(s, n)
            if fk != e["karte"] and state.units_on(s, fk, e["seite"]) and not state.valid_target(s, fk, e["seite"]):
                # [RULE 6.1.1 p.40 example 2, K16] the VOF would lie on own units: no fire at all
                e["ziel"] = None
                e.pop("konzentriert", None)
                e.pop("_reichweite_vof", None)
                prot.append(f"{n} ceases fire on {zk}: out of range and own units on {fk} along the PDF [6.3.2, 6.1.1]")
                continue
            if e.get("_reichweite_vof") != fk:
                e["_reichweite_vof"] = fk
                prot.append(f"{n}: {zk} out of range, PDF stays, VOF marker moves to {fk} [6.3.2 p.43, 7.18.2]")
            continue
        if e.pop("_reichweite_vof", None) and los_ok_:
            # L164: only when the target is really back in LOS and range (no message before a Cease Fire for lost LOS)
            prot.append(f"{n}: target {zk} in range again, VOF back on {zk} [6.3.2]")
        if not los_ok_ and los_reason.startswith(f"{e['karte']} has Incoming/Smoke"):
            # L148 [RULE 6.1.2 p.40 example 1]: smoke on the firing card: "the PDF is removed and the ... VOF is placed on its
            # card as a reminder that it is still firing and will use ammunition. (This VOF will affect any ... units which enter the card.)"
            e["_rauch_ziel"] = zk
            e["ziel"] = e["karte"]
            e.pop("konzentriert", None)
            prot.append(
                f"{n}: no LOS out of {e['karte']} (smoke/Incoming): remove the PDF to {zk}, its VOF stays on {e['karte']} (hits opposing units entering the card) [6.1.2 p.40 example 1]"
            )
            continue
        if not los_ok_:
            e["ziel"] = None
            e.pop("konzentriert", None)
            prot.append(f"{n} ceases fire on {zk}, remove the VOF marker from {zk}: {los_reason} [6.1.2]")  # L94


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
