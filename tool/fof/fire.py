"""Derived fire: VOF, PDF, Crossfire, Activity Level, opening and ceasing fire (6.1 to 6.3).

Import cycle: fire imports geometry, rules and state at module level; vehicles imports fire, so fire imports vehicles
inside the function that needs it (open_fire). state in turn imports fire inside marker_summary."""

import contextlib
from typing import Any

from . import geometry, rules, state


RCL_WEAPONS = ("57mm RCL", "75mm RCL")


def can_fire(e):
    if state.in_deep_bunker(e):
        return False  # units inside a Deep Bunker place no VOF [rules.DEEP_BUNKER_REF]
    if state.is_mortar(e) and not state.fire_team_side(e) and (rules.EXPOSED in e["status"] or e.get("indirect")):
        return False  # [RULE 7.3.1 p.53] no fire with Exposed; [RULE 7.3.2 p.53] Indirect Lay replaces Direct Lay
    if e.get("tripod") and rules.EXPOSED in e["status"] and not state.fire_team_side(e):
        return False  # [RULE 7.2.1 p.51] tripod MG does not fire with an Exposed marker
    if e.get("at_weapon") in RCL_WEAPONS and e.get("vof_rating") == "H" and rules.EXPOSED in e["status"]:
        return (
            False  # [RULE 7.4 p.54] H VOF rocket launchers/RCL 'cannot fire at all when marked with an Exposed marker'
        )
    if e.get("vof_rating") == "G" and not state.fire_team_side(e) and not e.get("out_of_ammo"):
        return False  # [RULE 7.3.2 p.53, 6.3.6 p.45] G! units fire only via Grenade Attack (Mortar Team: own PDF, 'pdf_only')
    # on its Fire Team side a unit fires with ft_vof even if its front has no VOF (enemy Spotter after F/A, 8.10;
    # US HQ/Staff flipped to the Fire Team side)
    rating = (e.get("ft_vof") or e.get("vof_rating")) if state.fire_team_side(e) else e.get("vof_rating")
    return bool(rating) and e["type"] not in ("Litter Team", "Paralyzed Team", "Runner")


def is_firing(e):
    return e.get("target") is not None and (can_fire(e) or bool(e.get("pdf_only")))


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
    e = s["units"][n]
    target_card = e["target"]
    if target_card == e["card"]:
        return target_card
    hi = state.range_limits(s, e)[1]
    last_in_range = None
    for k in geometry.line_between(s, e["card"], target_card) or []:
        if geometry.distance(s, e["card"], k) > hi:
            # [RULE 6.3.2 p.43 example, 7.18.2] out of range (e.g. Out of Ammo: range Close): "The PDF stays the same but
            # its VOF is moved to the adjacent card"; the VOF lies on the last card in range along the PDF
            return last_in_range or e["card"]
        last_in_range = k
        if geometry.blocks_los(state.card(s, k), False, s):
            return k  # [RULE 6.1.2 p.44] Smoke/Incoming/Air Strike along the PDF: move the VOF back to the blocking card (even over own troops, no Overhead)
        occupants = [
            m for m in state.units_on(s, k) if s["units"][m]["side"] == e["side"] or state.is_visible(s["units"][m])
        ]
        if state.is_mortar(e):
            # [RULE 7.3.1 p.53] mortars fire over cards with friendly troops without hitting them
            occupants = [m for m in occupants if s["units"][m]["side"] != e["side"]]
        elif (e.get("vof_rating") == "H" or e.get("tripod")) and overhead_possible(s, e["card"], k, target_card):
            # [RULE 7.2.1 p.51, 7.2.3] Overhead Fire (tripod MG, H VOF): "Do not place a VOF marker on the card being fired over";
            # 8.4.3 example 1: also over opposing units (RCL shifts fire over the CCF squad to the HMG on the hill).
            occupants = []
        if occupants:
            return k
    if geometry.distance(s, e["card"], target_card) > hi:
        return last_in_range or e["card"]
    return target_card


def grazing(e):
    """[RULE 7.2.2 p.51] Grazing Fire: tripod-mounted MG firing at range (not Point Blank) on its Good Order side,
    not Pinned (BGG 3498699: the Pinned VOF has no Grazing Fire) and not Out of Ammo (7.18.2: VOF S)."""
    return bool(
        e.get("tripod")
        and not state.fire_team_side(e)
        and not state.pinned(e)
        and not e.get("out_of_ammo")
        and e.get("target") is not None
        and e["target"] != e.get("card")
        and can_fire(e)
    )


def grazing_cards(s, n):
    """[RULE 7.2.2 p.51] 'it exerts its VOF into every card along its PDF up to its maximum range as long as all the cards
    are at the same elevation, or all uphill/all downhill ... and LOS exists.' Cards beyond the target included; a LOS block
    (Smoke/Incoming, 6.1.2 p.44, example 4 p.41) is the last card; friendly cards on the line are hit too (note 7.2.2).
    No Grazing Fire at all when the elevation pattern breaks before the target (BGG 3535366, 3558804)."""
    e = s["units"][n]
    if not grazing(e) or e["card"] not in s["cards"] or e["target"] not in s["cards"]:
        return []
    origin, destination = state.card(s, e["card"]), state.card(s, e["target"])
    dr, dc = destination["row"] - origin["row"], destination["column"] - origin["column"]
    if not (dr == 0 or dc == 0 or abs(dr) == abs(dc)):
        return []
    sr, sc = (dr > 0) - (dr < 0), (dc > 0) - (dc < 0)
    ray, prev, trend, i = [], origin.get("elevation", 1), None, 1
    while True:  # cards on the line with a valid elevation pattern, up to max range
        k = geometry.card_at(s, origin["row"] + sr * i, origin["column"] + sc * i)
        if k is None or not geometry.in_range(s, e, k) or state.card(s, k).get("staging"):
            break
        elevation = state.card(s, k).get("elevation", 1)
        step = (elevation > prev) - (elevation < prev)
        if trend is None:
            trend = step
        elif step != trend:
            break  # level and slope must not mix, slope must not reverse
        ray.append(k)
        prev, i = elevation, i + 1
    if e["target"] not in ray:
        return []  # e.g. 2-1-1: the MG just fires at the nearest card
    out = []
    for k in ray:  # LOS: a blocking card (Smoke/Incoming) is the last one, the cards behind it get no VOF
        ok, _why = geometry.los(
            s,
            e["card"],
            k,
            ha=geometry.height_bonus(s, e),
            hb=geometry.card_height_bonus(s, k, geometry.opponent_of(e)),
        )
        if not ok:
            break
        out.append(k)
    return out


_FIRE_MAPS: dict[int, Any] = {}  # id(state) -> fire_map (or None until first use) while a `cached(s)` block is open


@contextlib.contextmanager
def cached(s):
    """Read-only section: fire_map(s) is built once and reused by vof_entries and pdfs_to instead of
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
    (effective_fire_target) plus Grazing Fire cards. Includes pdf_only units (PDF without VOF)."""
    out = {}
    for n, e in s["units"].items():
        if not is_firing(e):
            continue
        hit = effective_fire_target(s, n)
        out.setdefault(hit, []).append(n)
        for k in grazing_cards(s, n):
            if k != hit:
                out.setdefault(k, []).append(n)
    return out


def firing_at(s, card_id, keep=None):
    """(name, unit) of every firing unit whose fire reaches card_id, in board order; from the map of an open cached(s)
    block, otherwise computed. keep(e): cheap filter applied first (spares the PDF walk for units not wanted)."""
    key = id(s)
    if key not in _FIRE_MAPS:
        return [
            (n, e)
            for n, e in s["units"].items()
            if is_firing(e)
            and (keep is None or keep(e))
            and (effective_fire_target(s, n) == card_id or card_id in grazing_cards(s, n))
        ]
    if _FIRE_MAPS[key] is None:
        _FIRE_MAPS[key] = fire_map(s)
    units = ((n, s["units"][n]) for n in _FIRE_MAPS[key].get(card_id, []))
    return [(n, e) for n, e in units if keep is None or keep(e)]


def vof_entries(s, card_id):
    """Fire effects on card card_id: (type, value, source, trifft_seite or None=both, von_karte)."""
    out = []
    for n, e in firing_at(s, card_id, keep=lambda e: not e.get("pdf_only")):
        pb = e["card"] == card_id
        type_ = "Pinned" if state.pinned(e) else current_vof_rating(e, pb)
        out.append(
            (type_, rules.VOF_VALUE.get(type_, 0), n, state.opponent_of_side(e["side"]) if pb else None, e["card"])
        )
    for x in state.card(s, card_id).get("external", []):
        if x["type"] not in ("Pending", "Smoke"):  # [RULE 5.4 p.38] smoke is cover, not a VOF (campaign correction)
            out.append((x["type"], x["value"], x.get("source", x["type"]), None, None))
    return out


def vof_against(s, card_id, side, ignore_mines=False):
    """Best (lowest) VOF that hits units of the side on card_id: (type, value, [sources]) or None.
    ohne_minen: Mines! markers count as VOF markers (Pinned Recovery, Rally, Infiltration, activity; BGG E35), but only hit
    the units that failed the mine check [RULE 6.3.6 p.45, 7.9.1 p.54]."""
    tr = [x for x in vof_entries(s, card_id) if x[3] in (None, side) and not (ignore_mines and x[0] == "Mines")]
    if not tr:
        return None
    best = min(x[1] for x in tr)
    return next(x for x in tr if x[1] == best)[0], best, [x[2] for x in tr]  # best is the minimum of tr: never empty


def pdfs_to(s, card_id, target_side):
    """Cards from which fire of the opposing side affects card_id from outside."""
    side = state.opponent_of_side(target_side)
    return {e["card"] for _n, e in firing_at(s, card_id, keep=lambda e: e["card"] != card_id and e["side"] == side)}


def crossfire(s, card_id, target_side):
    """6.2.4: two or more PDFs from different directions from outside."""
    own_card = state.card(s, card_id)
    dir_name = set()
    for k in pdfs_to(s, card_id, target_side):
        source_card = state.card(s, k)
        dr, dc = source_card["row"] - own_card["row"], source_card["column"] - own_card["column"]
        dir_name.add(((dr > 0) - (dr < 0), (dc > 0) - (dc < 0)))
    return len(dir_name) >= 2


def expected_activity(s):
    """8.1 / Charts 1: No Contact only without any VOF/PDF marker and without a spotted enemy."""
    with cached(s):
        vk = [k for k in s["cards"] if vof_entries(s, k)]
    occupants = [k for k in vk if state.units_on(s, k)]
    spotted = any(e["side"] == "Enemy" and e.get("spotted") for e in s["units"].values())
    pdf = any(is_firing(e) and e["target"] != e["card"] for e in s["units"].values())
    pending = any(x["type"] == "Pending" for c in s["cards"].values() for x in c.get("external", []))
    if len(occupants) >= 2 and any(state.units_on(s, k, "US") and state.units_on(s, k, "Enemy") for k in occupants):
        return "Heavily Engaged"
    if len(occupants) >= 2:
        return "Engaged"
    if vk or spotted or pdf or pending:
        return "Contact"
    return "No Contact"


def update_activity(s):
    if s.get("activity") is None or s["phase"] == "3.7.4":
        return None
    old, new = s["activity"], expected_activity(s)
    s["activity"] = new
    return None if old == new else f"Activity level {old} becomes {new}: move the Activity marker [8.1]"


def fire_position_forbidden(s, e):
    """Reason why a unit may not fire at all from its card, otherwise None."""
    if e.get("at_weapon") in RCL_WEAPONS:
        cv = geometry.cover_marker(s, e)
        if cv and cv["type"] in rules.NO_FIRE_FROM_COVER:
            # [RULE 7.4 p.54] 'No rocket launcher or recoilless rifle may fire from Building, Bunker, Cave or Pillbox cover'
            return "Rocket launchers/RCL do not fire from Building/Bunker/Cave/Pillbox [RULE 7.4 p.54]"
    if state.is_mortar(e) and not state.fire_team_side(e):
        c = state.card(s, e["card"])
        if "Woods" in c.get("terrain", "") or c.get("mortar_banned"):
            return "Mortars do not fire from Woods [RULE 7.3.1 p.53, FM1 p.36]"
        cv = geometry.cover_marker(s, e)
        if cv and cv["type"] in rules.NO_FIRE_FROM_COVER:  # Light/Strong Building are the CSR 8 names
            return "Mortars do not fire from Building/Bunker/Cave/Pillbox [RULE 7.3.1 p.52]"
    return None


def _reaches(s, e, card_id, arc):
    """Unit e can exert its VOF onto another card: range, LOS, nothing occupied in between, fixed fire arcs."""
    if (
        not geometry.in_range(s, e, card_id)
        or not geometry.los(
            s,
            e["card"],
            card_id,
            ha=geometry.height_bonus(s, e),
            hb=geometry.card_height_bonus(s, card_id, geometry.opponent_of(e)),
        )[0]
    ):
        return False
    if e["side"] == "US" and state.units_on(s, card_id, "US"):
        return False  # 8.4.3: friendly units do not open fire on jointly occupied cards
    between = geometry.line_between(s, e["card"], card_id) or []
    if not state.is_mortar(e):
        own_between = [k for k in between if state.units_on(s, k, e["side"])]
        overhead = (e.get("vof_rating") == "H" or e.get("tripod")) and all(
            overhead_possible(s, e["card"], k, card_id) for k in own_between
        )
        if own_between and not overhead:
            # [RULE 6.1.1 p.40 ex. 2, K16] the VOF would land on the friendly intervening card; only Overhead Fire
            # (7.2.3: tripod MG or H VOF with the elevation condition) and mortars fire over it
            return False
        opponent = geometry.opponent_of(e)
        if any(state.is_visible(s["units"][m]) for k in between for m in state.units_on(s, k, opponent)):
            return False  # [RULE 6.1.2 p.39] the VOF would be exerted into the closer occupied card, the real target
    bunker = e.get("bunker_direction")
    if bunker and card_id != bunker and bunker not in between:
        return False
    return not arc or geometry.direction(s, e["card"], card_id) == arc  # [RULE 5.3.2 p.37] only in the arrow direction


def fire_candidates(s, n):
    """Cards with a valid target that unit n could open fire on from where it stands [6.1.1]."""
    e = s["units"][n]
    candidate = []
    if fire_position_forbidden(s, e):
        return candidate
    arc = geometry.arc_direction(s, e)
    for card_id in s["cards"]:
        if card_id == e["card"]:
            if geometry.no_point_blank(s, e) or not geometry.in_range(s, e, card_id):
                continue
        elif not _reaches(s, e, card_id, arc):
            continue
        targets = state.valid_target(s, card_id, e["side"])
        if targets and e.get("vof_rating") in ("A", "H", "A/S"):
            from . import vehicles

            # [RULE 10.3 p.71] A/H-rated AT-capable units do not open fire on vehicle-only cards
            if vehicles.at_capable(e) and all(vehicles.is_vehicle(s["units"][m]) for m in targets):
                continue
        if targets:
            candidate.append(card_id)
    return candidate


def pdf_note(s, from_, to_, n):
    """V20 (the player): with every new PDF, state whether the source card has further PDFs."""
    others = sorted(
        {
            x["target"]
            for m, x in s["units"].items()
            if m != n
            and x.get("card") == from_
            and x.get("target")
            and x["target"] not in (from_, to_)
            and is_firing(x)
        }
    )
    same = [
        m
        for m, x in s["units"].items()
        if m != n and x.get("card") == from_ and x.get("target") == to_ and is_firing(x)
    ]
    head = f" (PDF marker {from_} to {to_} already lies there from {', '.join(same)}, no new marker" if same else " ("
    tail = f"further PDF from {from_}: to {', '.join(others)})" if others else f"no other PDF from {from_})"
    return head + ("; " if same else "") + tail


def grazing_note(s, n):
    """Cards besides the target that receive the VOF through Grazing Fire."""
    e = s["units"][n]
    extra = [k for k in grazing_cards(s, n) if k != e.get("target")]
    return f"; Grazing Fire: VOF marker also on {', '.join(extra)} [7.2.2 p.51]" if extra else ""


def _sniper_targets(s, e, candidate):
    """[RULE 6.1.1 p.39 target priorities, Sniper (friendly or enemy)] '1. Card with HQ, Staff or Leader present
    (closest, then random) 2. Card projecting the strongest (lowest) VOF (most steps if equal, then random)'."""
    side = state.opponent_of_side(e["side"])
    on = {k: [s["units"][m] for m in state.valid_target(s, k, e["side"])] for k in candidate}
    led = [k for k in candidate if any(state.is_hq(x) or x["type"] == "Staff" or x.get("leader") for x in on[k])]
    if led:
        nearest = min(geometry.distance(s, e["card"], k) for k in led)
        return [k for k in led if geometry.distance(s, e["card"], k) == nearest]

    def strength(k):  # lowest VOF value any unit of the card projects, then most steps
        vof = [
            rules.VOF_VALUE.get("Pinned" if state.pinned(x) else current_vof_rating(x, False), 99)
            for x in on[k]
            if x["side"] == side and can_fire(x)
        ]
        return (min(vof, default=99), -sum(state.steps(x) for x in on[k]))

    best = min(strength(k) for k in candidate)
    return [k for k in candidate if strength(k) == best]


def _narrow_targets(s, n, e, candidate):
    """The fire target among the candidates [6.1.1]: Point Blank first, then the card units of this card already fire
    at; US units the closest card (tie: the one with the strongest fire at them), enemies the card with most steps."""
    if e["card"] in candidate:
        # [RULE 6.2.1b p.42] "If units from both sides occupy a card, they fire at each other"
        candidate = [e["card"]]
    if e.get("vof_rating") == "S!" and not state.fire_team_side(e) and not state.is_lat(e) and len(candidate) > 1:
        return _sniper_targets(s, e, candidate)
    # [RULE 6.1.1 p.39] "If a unit enters a card where there is firing already going on ... the entering unit joins in the existing fire"
    existing = sorted(
        {
            x["target"]
            for m, x in s["units"].items()
            if m != n
            and x["side"] == e["side"]
            and x.get("card") == e["card"]
            and is_firing(x)
            and x["target"] in candidate
        }
    )
    if existing:
        candidate = existing
    if e["side"] != "US":
        us_steps = {k: sum(state.steps(s["units"][m]) for m in state.valid_target(s, k, "Enemy")) for k in candidate}
        return [k for k in candidate if us_steps[k] == max(us_steps.values())]
    nearest = min(geometry.distance(s, e["card"], k) for k in candidate)
    candidate = [k for k in candidate if geometry.distance(s, e["card"], k) == nearest]
    if len(candidate) > 1:
        vof_from = {k: min([x[1] for x in vof_entries(s, e["card"]) if x[4] == k], default=99) for k in candidate}
        candidate = [k for k in candidate if vof_from[k] == min(vof_from.values())]
    return candidate


def open_fire(s, prot, only=None):
    """6.1.1: unengaged units with a VOF rating open fire automatically. Tie: random choice by the player."""
    for n, e in s["units"].items():
        if only is not None and n not in only:
            continue
        if (
            e.get("target") is not None
            or not can_fire(e)
            or e.get("card") not in s["cards"]
            or state.card(s, e["card"]).get("staging")
            or e.get("no_fire_until_clean_up")  # [RULE 8.3 p.63] Place PDF/VOF No: opens fire only in Clean Up
        ):
            continue
        candidate = fire_candidates(s, n)
        if not candidate:
            e.pop("target_open", None)
            continue
        candidate = _narrow_targets(s, n, e, candidate)
        if len(candidate) > 1:
            e["target_open"] = candidate
            prot.append(
                f'{n}: determine fire target by R# from {", ".join(candidate)}, then fof.py fire "{n}" <card> [6.1.1]'
            )
            continue
        target, opponent = candidate[0], state.opponent_of_side(e["side"])
        crossfire_before = crossfire(s, target, opponent)
        e["target"] = target
        e.pop("target_open", None)
        prot.append(
            f"{n} opens fire on {target}"
            + (
                " (Point Blank)"
                if target == e["card"]
                else f", PDF from {e['card']} to {target}" + pdf_note(s, e["card"], target, n)
            )
            + (" with Pinned VOF" if state.pinned(e) else "")
            + " [6.1.1]"
            + grazing_note(s, n)
        )
        if not crossfire_before and crossfire(s, target, opponent):
            prot.append(f"Crossfire marker on {target} (PDFs from two directions) [6.2.4]")


def carried_markers(e):
    """Markers that travel with a moving counter: Pinned, ammo, Out of Ammo, assets, radios."""
    out = [m for m in e.get("status", []) if m != rules.EXPOSED]
    m = e.get("ammo")
    if m:
        out.append(f"{m.get('type', '')} ammo marker {m.get('points')}")
    if e.get("out_of_ammo"):
        out.append("Out of Ammo")
    out += list(e.get("assets") or [])
    out += [f"radio {r.get('type')}" for r in e.get("radio") or []]
    if e.get("carries_casualties"):
        out.append(f"{e['carries_casualties']} Casualty")
    return out


def cease_fire(e):
    """The one place a unit stops firing: clears the target and every fire-related working field (a stale _smoke_target would hijack a later Point Blank target)."""
    e["target"] = None
    for k in ("concentrated", "_smoke_target", "_vof_blocked", "_range_vof", "target_open", "pdf_only"):
        e.pop(k, None)


def cf_counts(s, card_id):
    return {n: e.get("cf", 0) for n, e in s["units"].items() if e.get("card") == card_id}


def track_concentrated(s, shooter, before):
    """Remember the Concentrated Fire markers this unit just placed, one entry [target, card, area] per marker
    (before = cf_counts of the target card ahead of the hit), so that 7.11.5 can take them off again."""
    for n, was in before.items():
        e = s["units"].get(n) or {}
        for _ in range(e.get("cf", 0) - was):
            shooter.setdefault("cf_on", []).append([n, e["card"], e.get("area", "open")])


def drop_concentrated(s, shooter, why, lines):
    """[RULE 7.11.5 p.56] the markers of this unit's Concentrated Fire come off its targets."""
    for t, _card, _area in shooter.pop("cf_on", []):
        f = s["units"].get(t)
        if f and f.get("cf"):
            f["cf"] -= 1
            if not f["cf"]:
                f.pop("cf_critical", None)
            lines.append(f"{t}: remove a Concentrated Fire marker ({why}) [7.11.5 p.56]")


def reconcile_concentrated(s):
    """[RULE 7.11.5 p.56] 'The Concentrated Fire marker is removed if LOS is subsequently lost due to Smoke or
    Incoming!, if the unit Shifts or Ceases Fire, if the target moves away (to another card, into, out of, or between
    cover markers ...) or if the unit otherwise loses its VOF'. Checked at every save outside the Combat Effects
    Segment (3.7.4: VOF and PDF are frozen); returns the board lines."""
    lines = []
    if s.get("phase") == "3.7.4":
        return lines
    for n, e in s["units"].items():
        if not e.get("cf_on"):
            continue
        fires = is_firing(e)
        keep = []
        for entry in e["cf_on"]:
            t, card_id, area = entry
            f = s["units"].get(t)
            if f is None or (f.get("card"), f.get("area", "open")) != (card_id, area):
                why = "the target moved away"
            elif not fires or effective_fire_target(s, n) != card_id:
                why = f"{n} no longer fires at it"
            else:
                keep.append(entry)
                continue
            if f and f.get("cf"):
                f["cf"] -= 1
                if not f["cf"]:
                    f.pop("cf_critical", None)
                lines.append(f"{t}: remove a Concentrated Fire marker ({why}) [7.11.5 p.56]")
        e["cf_on"] = keep
        if not keep:
            del e["cf_on"]
    return lines


def set_target(e, card_id):
    """a firing unit changes its target by itself (fire follows 6.3.4, Point Blank shift 6.1.2): the
    working fields that belong to the old target go, as in cease_fire, then the new target is set."""
    for k in ("concentrated", "_smoke_target", "_vof_blocked", "_range_vof", "target_open"):
        e.pop(k, None)
    e["target"] = card_id


def pdf_left_behind(s, n, e, origin):
    """what happens to the PDF marker the mover leaves on its origin card: it stays while another unit there still
    fires at the same target, otherwise it is removed (or turned back to the single arrow if the fire was mutual)."""
    target = e.get("target")
    if origin is None or target is None or target == origin:
        return " (adjust PDF/VOF)"
    others = [
        m
        for m, x in s["units"].items()
        if m != n and x["card"] == origin and x["side"] == e["side"] and x.get("target") == target and is_firing(x)
    ]
    if others:
        return f"; PDF marker {origin} to {target} stays ({', '.join(others)} still fire{'s' if len(others) == 1 else ''} there)"
    back = [
        m
        for m, x in s["units"].items()
        if x["card"] == target and x["side"] != e["side"] and x.get("target") == origin and is_firing(x)
    ]
    if back:
        return f"; PDF {origin} to {target}: turn the marker to the single arrow from {target} ({', '.join(back)} still fire{'s' if len(back) == 1 else ''} at {origin})"
    return f"; remove PDF marker {origin} to {target} (nobody else on {origin} fires there)"


def _spot_whole_card(s, e, prot):
    """A moved enemy joins the Spotted status of its new card."""
    # [RULE 8.5 p.65] "A card can never contain both Spotted and Unspotted enemy units"
    if e["side"] == "Enemy":
        group = state.units_on(s, e["card"], "Enemy")
        if any(s["units"][m].get("spotted") for m in group) and not all(s["units"][m].get("spotted") for m in group):
            for m in group:
                s["units"][m]["spotted"] = True
            prot.append(f"Enemies on {e['card']} now all Spotted: remove Unspotted markers [8.5 p.65]")


def _fire_follows_from_same_card(s, n, e, origin, prot):
    """Opponents who fired Point Blank at the mover follow it to the adjacent card, or cease fire."""
    # [RULE 6.3.4 p.44] "if the last unit under a VOF from an opposing unit on the same card moves away to an adjacent card
    # (in any direction), the opposing unit's fire follows the moving unit to the new card. Move the VOF to the new card and place a PDF marker."
    if state.is_visible(e) and e.get("card") in s["cards"]:
        for m, f in s["units"].items():
            if (
                f["side"] != e["side"]
                and f.get("card") in s["cards"]
                and f["card"] != e["card"]
                and (origin is None or f["card"] == origin)
                and is_firing(f)
                and f["target"] == f["card"]
                and geometry.adjacent(s, f["card"], e["card"])
                and not state.valid_target(s, f["card"], f["side"])
            ):
                ok, _why = geometry.los(
                    s,
                    f["card"],
                    e["card"],
                    ha=geometry.height_bonus(s, f),
                    hb=geometry.card_height_bonus(s, e["card"], geometry.opponent_of(f)),
                )
                if ok and geometry.in_range(s, f, e["card"]) and e["card"] in fire_candidates(s, m):
                    set_target(f, e["card"])
                    prot.append(
                        f"{m}: fire follows {n} to {e['card']}, PDF from {f['card']} to {e['card']}"
                        + pdf_note(s, f["card"], e["card"], m)
                        + " [6.3.4 p.44]"
                    )
                else:
                    cease_fire(f)
                    prot.append(
                        f"{m}: last Point Blank target left {f['card']}, cannot follow: Cease Fire, opens fire anew per 6.1.1 [6.3.4, 6.3.3]"
                    )


def _fire_follows_along_pdf(s, n, e, origin, prot):
    """Opponents firing at the origin card follow the mover one card further along the same PDF."""
    # [RULE 6.3.4 p.44] "if the last unit with an opposing unit's VOF on its card moves to a further away card in
    # LOS, within Range, and along the same PDF ... the VOF will move with the unit to the new card"
    if origin and state.is_visible(e) and e.get("card") in s["cards"] and origin in s["cards"]:
        for m, f in s["units"].items():
            if (
                f["side"] != e["side"]
                and f.get("card") in s["cards"]
                and is_firing(f)
                and f["target"] == origin
                and f["card"] != origin
                and not state.valid_target(s, origin, f["side"])
                and geometry.direction(s, f["card"], origin) == geometry.direction(s, f["card"], e["card"])
                and geometry.distance(s, f["card"], e["card"]) == geometry.distance(s, f["card"], origin) + 1
                and origin in (geometry.line_between(s, f["card"], e["card"]) or [])
                and e["card"] in fire_candidates(s, m)
            ):
                set_target(f, e["card"])
                prot.append(f"{m}: fire follows {n} along the same PDF to {e['card']} [6.3.4 p.44]")


def _shift_to_point_blank(s, e, prot):
    """Opponents on the mover's new card who fire elsewhere shift their fire to their own card."""
    for m, f in s["units"].items():
        if (
            f["side"] != e["side"]
            and f["card"] == e["card"]
            and is_firing(f)
            and f["target"] != f["card"]
            and state.is_visible(e)
            and not geometry.no_point_blank(s, f)
        ):
            set_target(f, f["card"])
            prot.append(f"{m} shifts fire to its own card (Point Blank) [6.1.2]")


def fire_after_move(s, n, prot, origin=None, open_all=True):
    """6.1.2: movement to another card = Cease Fire, then 6.1.1 again; firing opponents on the new card shift to Point Blank.
    origin: the card the unit came from; 6.3.4 'fire follows' only applies to opponents on that card.
    open_all=False: the caller moves several units together (Platoon Move) and runs the board-wide open_fire once after
    the last one."""
    e = s["units"][n]
    carried = carried_markers(e)
    if carried:
        prot.append(f"{n}: these markers move along: {', '.join(carried)}")
    if e.get("target") is not None:
        prot.append(f"{n} ceases fire due to the movement{pdf_left_behind(s, n, e, origin)} [6.1.2]")
        cease_fire(e)
    _spot_whole_card(s, e, prot)
    open_fire(s, prot, only=[n])
    _fire_follows_from_same_card(s, n, e, origin, prot)
    _fire_follows_along_pdf(s, n, e, origin, prot)
    _shift_to_point_blank(s, e, prot)
    # [RULE 3.0 p.15, 6.1.1 p.39] after every board change all unengaged units with a valid target open fire
    if open_all:
        open_fire(s, prot)


def cover_of(s, e):
    """One cover lookup, geometry.cover_marker (with the unknown-card
    guard). A wrapper, not an alias: geometry may still be half-imported here (circular imports)."""
    return geometry.cover_marker(s, e)


def _los_from(s, e, target):
    return geometry.los_detail(
        s,
        e["card"],
        target,
        ha=geometry.height_bonus(s, e),
        hb=geometry.card_height_bonus(s, target, geometry.opponent_of(e)),
    )


def classify_los_loss(s, n, e):
    """What cease_fire_on_los_loss has to do for one unit: (kind, data) or None.
    kinds: smoke_lifted (data: former target, still valid?), blocked_between (VOF card), out_of_range (VOF card,
    own units there?), smoke_on_own_card, lost (LosResult), in_view (LosResult: LOS and range fine)."""
    target_card = e.get("target")
    if target_card and target_card == e.get("card") and e.get("_smoke_target") and e["card"] in s["cards"]:
        # smoke/Incoming on the own card has lifted: back to the former target if still possible
        if geometry.blocks_los(state.card(s, e["card"]), False, s):
            return None
        old = e["_smoke_target"]
        valid = (
            old in s["cards"]
            and _los_from(s, e, old).ok
            and geometry.in_range(s, e, old)
            and bool(state.valid_target(s, old, e["side"]))
        )
        return "smoke_lifted", (old, valid)
    if (
        not target_card
        or target_card == e.get("card")
        or target_card not in s["cards"]
        or e.get("card") not in s["cards"]
    ):
        return None
    r = _los_from(s, e, target_card)
    if r.code == "blocked_between":
        # [RULE 6.1.2 p.44]: a block on an intervening card is no Cease Fire; the VOF sits on the blocking card
        return "blocked_between", effective_fire_target(s, n)
    if r.ok and not geometry.in_range(s, e, target_card):
        # [RULE 6.3.2 p.43 example]: out of range (Out of Ammo): the PDF stays, the VOF moves to the last card in range
        fire_card = effective_fire_target(s, n)
        own = (
            fire_card != e["card"]
            and bool(state.units_on(s, fire_card, e["side"]))
            and not state.valid_target(s, fire_card, e["side"])
        )
        return "out_of_range", (fire_card, own)
    if r.code == "blocked_out":
        return "smoke_on_own_card", r
    if not r.ok:
        return "lost", r
    return "in_view", r


def apply_los_loss(s, n, e, outcome, prot):
    """Carry out one classify_los_loss outcome (markers and messages unchanged, - )."""
    kind, data = outcome
    target_card = e.get("target")
    if kind == "smoke_lifted":
        old, valid = data
        e.pop("_smoke_target")
        if valid:
            e["target"] = old
            prot.append(f"{n}: smoke on {e['card']} lifted, fires again at {old} along the PDF [6.1.2]")
        else:
            cease_fire(e)
            prot.append(
                f"{n}: smoke on {e['card']} lifted, former target {old} no longer valid: Cease Fire, opens fire anew per 6.1.1 [6.3.3]"
            )
        return
    if kind == "blocked_between":
        if e.get("_vof_blocked") != data:
            e["_vof_blocked"] = data
            prot.append(
                f"{n}: move the VOF from {target_card} back along the PDF to the blocking card {data} (PDF stays) [6.1.2 p.44, 5.4]"
            )
        return
    if e.pop("_vof_blocked", None):
        prot.append(f"{n}: block lifted, VOF back on {effective_fire_target(s, n)} [6.1.2]")
    if kind == "out_of_range":
        fire_card, own = data
        if own:
            # [RULE 6.1.1 p.40 example 2, K16] the VOF would lie on own units: no fire at all
            cease_fire(e)
            prot.append(
                f"{n} ceases fire on {target_card}: out of range and own units on {fire_card} along the PDF [6.3.2, 6.1.1]"
            )
        elif e.get("_range_vof") != fire_card:
            e["_range_vof"] = fire_card
            prot.append(
                f"{n}: {target_card} out of range, PDF stays, VOF marker moves to {fire_card} [6.3.2 p.43, 7.18.2]"
            )
        return
    if e.pop("_range_vof", None) and data.ok:
        # only when the target is really back in LOS and range (no message before a Cease Fire for lost LOS)
        prot.append(f"{n}: target {target_card} in range again, VOF back on {target_card} [6.3.2]")
    if kind == "smoke_on_own_card":
        # [RULE 6.1.2 p.40 example 1]: smoke on the firing card: "the PDF is removed and the ... VOF is placed on its
        # card as a reminder that it is still firing and will use ammunition. (This VOF will affect any ... units which enter the card.)"
        e["_smoke_target"] = target_card
        e["target"] = e["card"]
        e.pop("concentrated", None)
        prot.append(
            f"{n}: no LOS out of {e['card']} (smoke/Incoming): remove the PDF to {target_card}, its VOF stays on {e['card']} (hits opposing units entering the card) [6.1.2 p.40 example 1]"
        )
    elif kind == "lost":
        cease_fire(e)
        prot.append(f"{n} ceases fire on {target_card}, remove the VOF marker from {target_card}: {data.text} [6.1.2]")


def cease_fire_on_los_loss(s, prot):
    """[RULE 6.1.2, 9.1, 9.2.1] Target no longer in LOS/range (e.g. Illumination removed in Clean Up): cease fire.
    Unit by unit: classify, then apply (a unit's outcome is decided on the board as left by the units before it)."""
    for n, e in s["units"].items():
        outcome = classify_los_loss(s, n, e)
        if outcome is not None:
            apply_los_loss(s, n, e, outcome, prot)


def enemy_cease_fire(s, prot):
    """8.6.4 / 3.4.2 / 3.8: enemies without a valid target cease fire and open fire anew per 6.1.1."""
    for n, e in s["units"].items():
        if e["side"] == "Enemy" and is_firing(e):
            target_card = effective_fire_target(s, n)
            # while the VOF sits on a blocking card (_vof_blocked), the last card in range
            # (_range_vof) or the own card under smoke (_smoke_target), the PDF target decides, not the VOF card
            check = e.get("_smoke_target") or (
                e["target"] if e.get("_vof_blocked") or e.get("_range_vof") else target_card
            )
            if check not in s["cards"] or not state.valid_target(s, check, "Enemy"):
                cease_fire(e)
                prot.append(f"{n}: Cease Fire, no valid target left on {check} [8.6.4]")
    open_fire(s, prot, only=[n for n, e in s["units"].items() if e["side"] == "Enemy"])
