"""Map geometry, LOS, range, visibility and illumination (5.2, 9.x)."""

from typing import NamedTuple, Optional

from . import rules, state


def direction(s, from_, to_):
    card_a, card_b = state.card(s, from_), state.card(s, to_)
    dr, dc = card_b["row"] - card_a["row"], card_b["column"] - card_a["column"]
    return ((dr > 0) - (dr < 0), (dc > 0) - (dc < 0))


def edge(c, d):
    """Edge colour of card c on the side facing direction d=(dr,dc); 'edges' as text (all sides) or
    object with top/bottom/links/right/diagonal (Gully: white edges on two sides only, FM1 p.34/p.45)."""
    r = c.get("edges")
    if r is None or isinstance(r, str):
        return r
    return r.get(rules.SIDE_NAME.get(d, "diagonal"), r.get("rest"))


def first_card_row(s):
    return min(c["row"] for c in s["cards"].values() if not c.get("staging"))


def distance(s, a, b):
    card_a, card_b = state.card(s, a), state.card(s, b)
    return max(abs(card_a["row"] - card_b["row"]), abs(card_a["column"] - card_b["column"]))


def adjacent(s, a, b):
    return a != b and distance(s, a, b) == 1


def card_at(s, r, c):
    for k, v in s["cards"].items():
        if v["row"] == r and v["column"] == c:
            return k
    return None


def line_between(s, a, b):
    """Cards between a and b on one of the eight straight lines (excluding a and b); None if not on a straight line."""
    card_a, card_b = state.card(s, a), state.card(s, b)
    dr, dc = card_b["row"] - card_a["row"], card_b["column"] - card_a["column"]
    if a == b or not (dr == 0 or dc == 0 or abs(dr) == abs(dc)):
        return None
    n = max(abs(dr), abs(dc))
    sr, sc = (dr > 0) - (dr < 0), (dc > 0) - (dc < 0)
    out = []
    for i in range(1, n):
        k = card_at(s, card_a["row"] + sr * i, card_a["column"] + sc * i)
        if k is None:
            return None
        out.append(k)
    return out


def blocks_los(c, radio=False, s=None):
    """[RULE 5.4 p.38] Smoke, Incoming!, Air Strike! block LOS out of the card and through it.
    Radio (SCR536): [RULE 4.3.5 p.29] 'as if Daylight, and ignoring smoke'; Incoming per option U3."""
    types_ = ("Incoming", "AirStrike", "Smoke")
    if radio:
        types_ = ("Incoming", "AirStrike") if (s is None or state.option(s, "U3_incoming_blocks_radio")) else ()
    return any(x["type"] in types_ for x in c.get("external", []))


def see_through(c, from_d, to_d):
    """[RULE 5.2.1 p.34] Entry and exit sides of the card crossed must be white. None = not recorded."""
    r = c.get("edges")
    if r is None:
        return None
    if isinstance(r, str):
        return r == "white"
    sides = (edge(c, from_d), edge(c, to_d))
    if any(x is not None and x != "white" for x in sides):
        return False
    # a side missing from the recorded edges is 'not recorded' (note in los), not dark
    return None if None in sides else True


def light_weather(s):
    """[RULE 9.0 p.69] Visibility modifier = Light Level + Weather. Legacy: 'visibility' counts as light."""
    l = s.get("light")
    if l is None:
        l = s.get("visibility", 0) or 0
    return l, s.get("weather", 0) or 0


def update_visibility(s):
    """[RULE 9.0 p.69] +2 or more is Limited Visibility (9.1): 4 Commands per impulse, save limit G2/L4/V6, LOS Close Range."""
    l, w = light_weather(s)
    s["sight"] = "limited" if l + w >= 2 else "day"


def illumination_value(s, card_id):
    """[RULE 9.2 p.70] best (lowest) Illumination modifier on card_id: top value of the marker on card_id,
    bottom value of markers on adjacent cards; not cumulative. None = not illuminated."""
    values_ = []
    for k2, c in s["cards"].items():
        for m in c.get("illum", []):
            if k2 == card_id:
                values_.append(m["top"])
            elif m.get("bottom") is not None and distance(s, k2, card_id) == 1:
                values_.append(m["bottom"])
    return min(values_) if values_ else None


def is_illuminated(s, card_id):
    """[RULE 9.2.1 p.70] Illuminated only in Limited Visibility; never with Weather Conditions +2 or higher."""
    l, w = light_weather(s)
    return l + w >= 2 and w < 2 and illumination_value(s, card_id) is not None


def visibility_on_card(s, card_id):
    """[RULE 9.0/9.2 p.69/70] Visibility modifier on card_id: Illumination only mitigates light, light plus illum never better than +0."""
    l, w = light_weather(s)
    iw = illumination_value(s, card_id)
    if iw is not None:
        l = max(0, l + iw)
    return l + w


def height_bonus(s, e):
    """[RULE 5.2.2 p.35] Upper Story / Church Tower: +1 elevation level for the unit under it."""
    cv = cover_marker(s, e) if e else None
    return 1 if cv and cv["type"] in ("Upper Story", "Church Tower") else 0


def opponent_of(e):
    return "Enemy" if e.get("side") == "US" else "US"


def card_height_bonus(s, k, side):
    """highest extra level of one side's units on card k (Upper Story seen/seeing, 5.2.2 'Even if only part of a card is in LOS')."""
    return max([height_bonus(s, s["units"][m]) for m in state.units_on(s, k, side)] or [0])


class LosResult(NamedTuple):
    """Machine-readable LOS result (callers matched the reason text by prefix).
    code: same_card, not_straight, too_far, staging, blocked_out (smoke/Incoming on the origin a), blocked_between
    (smoke/Incoming on an intervening card), too_high, slope, dark_edges, ok. card: the blocking card or None."""

    ok: bool
    code: str
    card: Optional[str]
    text: str


def los_detail(s, a, b, radio=False, staging_frei=False, ha=0, hb=0):
    """5.2.1/5.2.2/5.4: geometry, range, edge, Incoming/Smoke, elevation, staging. Returns a LosResult.
    radio=True: LOS for SCR536 [RULE 4.3.5 p.29] 'as if Daylight, and ignoring smoke' (range always up to Very Long)."""
    if a == b:
        return LosResult(True, "same_card", None, "same card")
    between = line_between(s, a, b)
    if between is None:
        return LosResult(False, "not_straight", None, "not on one of the eight straight lines [5.2.1]")
    maxr = 3 if radio else (1 if s["sight"] == "limited" and not is_illuminated(s, b) else 3)  # [RULE 9.1, 9.2.1 p.70]
    if distance(s, a, b) > maxr:
        return LosResult(False, "too_far", None, f"farther than {maxr} cards [5.2.1]")
    card_a, card_b = state.card(s, a), state.card(s, b)
    if (card_b.get("staging") or card_a.get("staging")) and not staging_frei:
        return LosResult(False, "staging", None, "Staging Area: no LOS in or out [2.5]")
    reading = state.open_reading(s, "U3_incoming_blocks_radio") if radio else ""
    if blocks_los(card_a, radio, s):
        return LosResult(False, "blocked_out", a, f"{a} has Incoming/Smoke, no LOS out [5.4]" + reading)
    ea, eb = card_a.get("elevation", 1) + ha, card_b.get("elevation", 1) + hb  # Upper Story +1 [RULE 5.2.2 p.35]
    for mid in between:
        c = state.card(s, mid)
        if blocks_los(c, radio, s):
            return LosResult(False, "blocked_between", mid, f"Incoming/Smoke on {mid} blocks [5.4]" + reading)
        elevation = c.get("elevation", 1)
        if elevation > max(ea, eb) or (elevation == max(ea, eb) and elevation > min(ea, eb)):
            return LosResult(
                False, "too_high", mid, f"{mid} is higher than or as high as the lower point, blocks [5.2.2]"
            )
        ds = see_through(c, direction(s, mid, a), direction(s, mid, b))
        if max(ea, eb) > elevation:
            # [RULE 5.2.2 p.35] higher sees over lower despite dark edges; but 'straight up or downhill'
            # (level 3 to 1 across a level-2 card with dark edges) is blocked
            if elevation > min(ea, eb) and ds is False:
                return LosResult(
                    False,
                    "slope",
                    mid,
                    f"{mid} lies between the elevation levels and has dark edges (straight up/downhill) [5.2.2]",
                )
            continue
        if ds is None:
            s.setdefault("_hints", []).append(
                f"LOS {a} to {b} passes through {mid}: edge colours of {mid} not recorded, check on the board (entry and exit sides white?) [5.2.1]"
            )
        elif ds is False:
            return LosResult(False, "dark_edges", mid, f"{mid} has dark edges [5.2.1]")
    return LosResult(True, "ok", None, "ok")


def los(s, a, b, radio=False, staging_frei=False, ha=0, hb=0):
    """(bool, reason text) as before; see los_detail for the reason code."""
    r = los_detail(s, a, b, radio=radio, staging_frei=staging_frei, ha=ha, hb=hb)
    return r.ok, r.text


def face_down(c):
    """[RULE 2.2.1 p.9, 5.2 p.34] a card laid face down (mission instructions, e.g. Naktong M1) and not yet revealed."""
    return bool(c.get("face_down"))


def reveal_candidates(s):
    """[RULE 5.2 p.34] 'reveal a hidden card when a friendly non-aircraft unit has LOS to it'; before turn 1 also the
    cards in LOS of the Staging Area (mission setup, e.g. Naktong M1 p.15). Face-down cards count as elevation 1 with dark
    borders (BGG 3503051, 3550060). Returns {card: [seen from, ..]} for the cards to flip now."""
    hidden = [k for k, c in s["cards"].items() if face_down(c)]
    if not hidden:
        return {}
    sources = {}
    for e in s["units"].values():
        if e.get("side") == "US" and e.get("card") in s["cards"] and e.get("type") != "Aircraft":
            sources.setdefault(e["card"], height_bonus(s, e))
    if state.in_setup(s) or s.get("reveal_staging"):
        for k, c in s["cards"].items():
            if c.get("staging"):
                sources.setdefault(k, 0)
    out = {}
    for b in hidden:
        for a, ha in sorted(sources.items()):
            if a != b and los(s, a, b, staging_frei=True, ha=ha)[0]:
                out.setdefault(b, []).append(a)
    return out


def reveal_dependencies(s, candidates=None):
    """[RULE 5.2.2 p.35]: a face-down card seen only over another face-down card (a higher unit looks over the
    hidden card, which counts as elevation 1) depends on that card: once it is revealed, a Hill there can close the
    line. Returns {card: [face-down cards it waits for]} for the candidates that have no LOS free of hidden cards."""
    cand = reveal_candidates(s) if candidates is None else candidates
    out = {}
    for b, sources in cand.items():
        waits, free = set(), False
        for a in sources:
            hidden = [mid for mid in (line_between(s, a, b) or []) if face_down(state.card(s, mid))]
            if hidden:
                waits.update(hidden)
            else:
                free = True
        if not free and waits:
            out[b] = sorted(waits)
    return out


def in_range(s, e, target):
    lo, hi = state.range_limits(s, e)
    return lo <= distance(s, e["card"], target) <= hi


def cover_marker(s, e):
    """Cover marker the unit is under (or None)."""
    if e.get("area", "open") == "open" or e["card"] not in s["cards"]:
        return None
    for c in s["cards"][e["card"]].get("cover", []):
        if c["id"] == e["area"]:
            return c
    return None


def no_point_blank(s, e):
    """No Point Blank fire: [RULE 5.3.2 p.37] units in Bunker/Pillbox; [RULE 7.3.1 p.52] mortars (the tube, not the
    crew fighting as a Fire Team on the counter's Fire Team side)."""
    cv = cover_marker(s, e)
    mortar = state.is_mortar(e) and not state.fire_team_side(e)
    return bool(e.get("no_point_blank")) or mortar or bool(cv and cv["type"] in rules.STRUCTURES)


def arc_direction(s, e):
    """Fire direction from Bunker/Pillbox [RULE 5.3.2 p.37]: marker field 'direction' [dr,dc] or unit field 'bunker_direction' (card, basic game)."""
    cv = cover_marker(s, e)
    if cv and cv["type"] in rules.STRUCTURES and cv.get("direction"):
        return tuple(cv["direction"])
    return None
