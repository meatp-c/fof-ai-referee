"""Derived fire: VOF, PDF, Crossfire, Activity Level, opening and ceasing fire (6.1 to 6.3).

Import cycle: fire imports geometry, rules and state at module level; vehicles imports fire, so fire imports vehicles
inside the function that needs it (open_fire). state in turn imports fire inside marker_summary."""

import contextlib

from . import geometry, rules, state


def can_fire(e):
    if e.get("deep_bunker") and e.get("bereich") == e["deep_bunker"]:
        return False  # [CSR 5 p.14] Deep Bunker: units inside place no VOF
    if state.is_mortar(e) and (rules.EXPOSED in e["status"] or e.get("indirekt")):
        return False  # [RULE 7.3.1 p.53] no fire with Exposed; [RULE 7.3.2 p.53] Indirect Lay replaces Direct Lay
    if e.get("tripod") and rules.EXPOSED in e["status"] and not state.fire_team_side(e):
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


def grazing(e):
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
    if not grazing(e) or e["karte"] not in s["karten"] or e["ziel"] not in s["karten"]:
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


_FIRE_MAPS = {}  # id(state) -> fire_map (or None until first use) while a `cached(s)` block is open


@contextlib.contextmanager
def cached(s):
    """Read-only section (review Effizienz): fire_map(s) is built once and reused by vof_entries and pdfs_to instead of
    walking every unit (target along the PDF, Grazing Fire LOS per ray card) for every card. Only for code that changes
    no unit, target, status or marker inside the block (marker summary, activity level, NCM rows and groups).
    Nested blocks share the outer map."""
    key = id(s)
    if key in _FIRE_MAPS:
        yield
        return
    _FIRE_MAPS[key] = None
    try:
        yield
    finally:
        _FIRE_MAPS.pop(key, None)


def fire_map(s):
    """{card: [names of firing units whose fire reaches the card]}, units in board order: the card along the PDF
    (effective_fire_target) plus Grazing Fire cards. Includes nur_pdf units (PDF without VOF)."""
    out = {}
    for n, e in s["einheiten"].items():
        if not is_firing(e):
            continue
        hit = effective_fire_target(s, n)
        out.setdefault(hit, []).append(n)
        for k in grazing_cards(s, n):
            if k != hit:
                out.setdefault(k, []).append(n)
    return out


def firing_at(s, kid, keep=None):
    """(name, unit) of every firing unit whose fire reaches kid, in board order; from the map of an open cached(s)
    block, otherwise computed. keep(e): cheap filter applied first (spares the PDF walk for units not wanted)."""
    key = id(s)
    if key not in _FIRE_MAPS:
        return [
            (n, e)
            for n, e in s["einheiten"].items()
            if is_firing(e)
            and (keep is None or keep(e))
            and (effective_fire_target(s, n) == kid or kid in grazing_cards(s, n))
        ]
    if _FIRE_MAPS[key] is None:
        _FIRE_MAPS[key] = fire_map(s)
    units = ((n, s["einheiten"][n]) for n in _FIRE_MAPS[key].get(kid, []))
    return [(n, e) for n, e in units if keep is None or keep(e)]


def vof_entries(s, kid):
    """Fire effects on card kid: (typ, wert, quelle, trifft_seite or None=both, von_karte)."""
    out = []
    for n, e in firing_at(s, kid, keep=lambda e: not e.get("nur_pdf")):
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
    return next(x for x in tr if x[1] == best)[0], best, [x[2] for x in tr]  # best is the minimum of tr: never empty


def pdfs_to(s, kid, target_side):
    """Cards from which fire of the opposing side affects kid from outside."""
    side = state.opponent_of_side(target_side)
    return {e["karte"] for _n, e in firing_at(s, kid, keep=lambda e: e["karte"] != kid and e["seite"] == side)}


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
    with cached(s):
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
        if cv and cv["typ"] in rules.NO_FIRE_FROM_COVER:  # L203: Light/Strong Building are the CSR 8 names
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
        targets = state.valid_target(s, kid, e["seite"])
        if targets and e.get("vof_rating") in ("A", "H", "A/S"):
            from . import (
                vehicles,
            )  # L187 [RULE 10.3 p.71] A/H-rated AT-capable units do not open fire on vehicle-only cards

            if vehicles.at_capable(e) and all(vehicles.is_vehicle(s["einheiten"][m]) for m in targets):
                continue
        if targets:
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
    out = [m for m in e.get("status", []) if m != rules.EXPOSED]
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


def cease_fire(e):
    """The one place a unit stops firing: clears the target and every fire-related working field (L225, review H6:
    a stale _rauch_ziel used to hijack a later Point Blank target)."""
    e["ziel"] = None
    for k in ("konzentriert", "_rauch_ziel", "_vof_sperre", "_reichweite_vof", "ziel_offen", "nur_pdf"):
        e.pop(k, None)


def fire_after_move(s, n, prot, origin=None, open_all=True):
    """6.1.2: movement to another card = Cease Fire, then 6.1.1 again; firing opponents on the new card shift to Point Blank.
    origin: the card the unit came from; 6.3.4 'fire follows' only applies to opponents on that card (L226, review M34).
    open_all=False: the caller moves several units together (Platoon Move) and runs the board-wide open_fire once after
    the last one (L450)."""
    e = s["einheiten"][n]
    carried = carried_markers(e)
    if carried:
        prot.append(f"{n}: these markers move along: {', '.join(carried)}")  # L109
    if e.get("ziel") is not None:
        prot.append(f"{n} ceases fire due to the movement (adjust PDF/VOF) [6.1.2]")
        cease_fire(e)
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
                and (origin is None or f["karte"] == origin)
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
                    cease_fire(f)
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
    if open_all:
        open_fire(s, prot)


def cover_of(s, e):
    """Old name kept for callers; review Struktur 9: one cover lookup, geometry.cover_marker (with the unknown-card
    guard). A wrapper, not an alias: geometry may still be half-imported here (circular imports)."""
    return geometry.cover_marker(s, e)


def _los_from(s, e, target):
    return geometry.los_detail(
        s,
        e["karte"],
        target,
        ha=geometry.height_bonus(s, e),
        hb=geometry.card_height_bonus(s, target, geometry.opponent_of(e)),
    )


def classify_los_loss(s, n, e):
    """What cease_fire_on_los_loss has to do for one unit (review Struktur): (kind, data) or None.
    kinds: smoke_lifted (data: former target, still valid?), blocked_between (VOF card), out_of_range (VOF card,
    own units there?), smoke_on_own_card, lost (LosResult), in_view (LosResult: LOS and range fine)."""
    zk = e.get("ziel")
    if zk and zk == e.get("karte") and e.get("_rauch_ziel") and e["karte"] in s["karten"]:
        # L148: smoke/Incoming on the own card has lifted: back to the former target if still possible
        if geometry.blocks_los(state.card(s, e["karte"]), False, s):
            return None
        old = e["_rauch_ziel"]
        valid = (
            old in s["karten"]
            and _los_from(s, e, old).ok
            and geometry.in_range(s, e, old)
            and bool(state.valid_target(s, old, e["seite"]))
        )
        return "smoke_lifted", (old, valid)
    if not zk or zk == e.get("karte") or zk not in s["karten"] or e.get("karte") not in s["karten"]:
        return None
    r = _los_from(s, e, zk)
    if r.code == "blocked_between":
        # L96 [RULE 6.1.2 p.44]: a block on an intervening card is no Cease Fire; the VOF sits on the blocking card
        return "blocked_between", effective_fire_target(s, n)
    if r.ok and not geometry.in_range(s, e, zk):
        # L147 [RULE 6.3.2 p.43 example]: out of range (Out of Ammo): the PDF stays, the VOF moves to the last card in range
        fk = effective_fire_target(s, n)
        own = fk != e["karte"] and bool(state.units_on(s, fk, e["seite"])) and not state.valid_target(s, fk, e["seite"])
        return "out_of_range", (fk, own)
    if r.code == "blocked_out":
        return "smoke_on_own_card", r
    if not r.ok:
        return "lost", r
    return "in_view", r


def apply_los_loss(s, n, e, outcome, prot):
    """Carry out one classify_los_loss outcome (markers and messages unchanged, L94-L96, L147, L148, L164)."""
    kind, data = outcome
    zk = e.get("ziel")
    if kind == "smoke_lifted":
        old, valid = data
        e.pop("_rauch_ziel")
        if valid:
            e["ziel"] = old
            prot.append(f"{n}: smoke on {e['karte']} lifted, fires again at {old} along the PDF [6.1.2]")
        else:
            cease_fire(e)
            prot.append(
                f"{n}: smoke on {e['karte']} lifted, former target {old} no longer valid: Cease Fire, opens fire anew per 6.1.1 [6.3.3]"
            )
        return
    if kind == "blocked_between":
        if e.get("_vof_sperre") != data:
            e["_vof_sperre"] = data
            prot.append(
                f"{n}: move the VOF from {zk} back along the PDF to the blocking card {data} (PDF stays) [6.1.2 p.44, 5.4]"
            )
        return
    if e.pop("_vof_sperre", None):
        prot.append(f"{n}: block lifted, VOF back on {effective_fire_target(s, n)} [6.1.2]")
    if kind == "out_of_range":
        fk, own = data
        if own:
            # [RULE 6.1.1 p.40 example 2, K16] the VOF would lie on own units: no fire at all
            cease_fire(e)
            prot.append(f"{n} ceases fire on {zk}: out of range and own units on {fk} along the PDF [6.3.2, 6.1.1]")
        elif e.get("_reichweite_vof") != fk:
            e["_reichweite_vof"] = fk
            prot.append(f"{n}: {zk} out of range, PDF stays, VOF marker moves to {fk} [6.3.2 p.43, 7.18.2]")
        return
    if e.pop("_reichweite_vof", None) and data.ok:
        # L164: only when the target is really back in LOS and range (no message before a Cease Fire for lost LOS)
        prot.append(f"{n}: target {zk} in range again, VOF back on {zk} [6.3.2]")
    if kind == "smoke_on_own_card":
        # L148 [RULE 6.1.2 p.40 example 1]: smoke on the firing card: "the PDF is removed and the ... VOF is placed on its
        # card as a reminder that it is still firing and will use ammunition. (This VOF will affect any ... units which enter the card.)"
        e["_rauch_ziel"] = zk
        e["ziel"] = e["karte"]
        e.pop("konzentriert", None)
        prot.append(
            f"{n}: no LOS out of {e['karte']} (smoke/Incoming): remove the PDF to {zk}, its VOF stays on {e['karte']} (hits opposing units entering the card) [6.1.2 p.40 example 1]"
        )
    elif kind == "lost":
        cease_fire(e)
        prot.append(f"{n} ceases fire on {zk}, remove the VOF marker from {zk}: {data.text} [6.1.2]")  # L94


def cease_fire_on_los_loss(s, prot):
    """[RULE 6.1.2, 9.1, 9.2.1] Target no longer in LOS/range (e.g. Illumination removed in Clean Up): cease fire.
    Unit by unit: classify, then apply (a unit's outcome is decided on the board as left by the units before it)."""
    for n, e in s["einheiten"].items():
        outcome = classify_los_loss(s, n, e)
        if outcome is not None:
            apply_los_loss(s, n, e, outcome, prot)


def enemy_cease_fire(s, prot):
    """8.6.4 / 3.4.2 / 3.8: enemies without a valid target cease fire and open fire anew per 6.1.1."""
    for n, e in s["einheiten"].items():
        if e["seite"] == "Feind" and is_firing(e):
            zk = effective_fire_target(s, n)
            # L227 (review M33): while the VOF sits on a blocking card (_vof_sperre), the last card in range
            # (_reichweite_vof) or the own card under smoke (_rauch_ziel), the PDF target decides, not the VOF card
            check = e.get("_rauch_ziel") or (e["ziel"] if e.get("_vof_sperre") or e.get("_reichweite_vof") else zk)
            if check not in s["karten"] or not state.valid_target(s, check, "Feind"):
                cease_fire(e)
                prot.append(f"{n}: Cease Fire, no valid target left on {check} [8.6.4]")
    open_fire(s, prot, only=[n for n, e in s["einheiten"].items() if e["seite"] == "Feind"])
