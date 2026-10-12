"""Map geometry, LOS, range, visibility and illumination (5.2, 9.x)."""

from . import rules, state


def direction(s, from_, to_):
    ka, kb = state.card(s, from_), state.card(s, to_)
    dr, dc = kb["reihe"] - ka["reihe"], kb["spalte"] - ka["spalte"]
    return ((dr > 0) - (dr < 0), (dc > 0) - (dc < 0))


def edge(c, d):
    """Edge colour of card c on the side facing direction d=(dr,dc); 'raender' as text (all sides) or
    object with oben/unten/links/rechts/diagonal (Gully: white edges on two sides only, FM1 p.34/p.45)."""
    r = c.get("raender")
    if r is None or isinstance(r, str):
        return r
    return r.get(rules.SIDE_NAME.get(d, "diagonal"), r.get("rest"))


def first_card_row(s):
    return min(c["reihe"] for c in s["karten"].values() if not c.get("staging"))


def distance(s, a, b):
    ka, kb = state.card(s, a), state.card(s, b)
    return max(abs(ka["reihe"] - kb["reihe"]), abs(ka["spalte"] - kb["spalte"]))


def adjacent(s, a, b):
    return a != b and distance(s, a, b) == 1


def card_at(s, r, c):
    for k, v in s["karten"].items():
        if v["reihe"] == r and v["spalte"] == c:
            return k
    return None


def line_between(s, a, b):
    """Cards between a and b on one of the eight straight lines (excluding a and b); None if not on a straight line."""
    ka, kb = state.card(s, a), state.card(s, b)
    dr, dc = kb["reihe"] - ka["reihe"], kb["spalte"] - ka["spalte"]
    if a == b or not (dr == 0 or dc == 0 or abs(dr) == abs(dc)):
        return None
    n = max(abs(dr), abs(dc))
    sr, sc = (dr > 0) - (dr < 0), (dc > 0) - (dc < 0)
    out = []
    for i in range(1, n):
        k = card_at(s, ka["reihe"] + sr * i, ka["spalte"] + sc * i)
        if k is None:
            return None
        out.append(k)
    return out


def blocks_los(c, radio=False, s=None):
    """[RULE 5.4 p.38] Smoke, Incoming!, Air Strike! block LOS out of the card and through it.
    Radio (SCR536): [RULE 4.3.5 p.29] 'as if Daylight, and ignoring smoke'; Incoming per option U3."""
    types_ = ("Incoming", "AirStrike", "Smoke")
    if radio:
        types_ = ("Incoming", "AirStrike") if (s is None or state.option(s, "U3_incoming_blockiert_funk")) else ()
    return any(x["typ"] in types_ for x in c.get("extern", []))


def see_through(c, from_d, to_d):
    """[RULE 5.2.1 p.34] Entry and exit sides of the card crossed must be white. None = not recorded."""
    r = c.get("raender")
    if r is None:
        return None
    if isinstance(r, str):
        return r == "weiss"
    return edge(c, from_d) == "weiss" and edge(c, to_d) == "weiss"


def light_weather(s):
    """[RULE 9.0 p.69] Visibility modifier = Light Level + Weather. Legacy: 'visibility' counts as light."""
    l = s.get("licht")
    if l is None:
        l = s.get("visibility", 0) or 0
    return l, s.get("wetter", 0) or 0


def update_visibility(s):
    """[RULE 9.0 p.69] +2 or more is Limited Visibility (9.1): 4 Commands per impulse, save limit G2/L4/V6, LOS Close Range."""
    l, w = light_weather(s)
    s["sicht"] = "eingeschraenkt" if l + w >= 2 else "tag"


def illumination_value(s, kid):
    """[RULE 9.2 p.70] best (lowest) Illumination modifier on kid: top value of the marker on kid,
    bottom value of markers on adjacent cards; not cumulative. None = not illuminated."""
    values_ = []
    for k2, c in s["karten"].items():
        for m in c.get("illum", []):
            if k2 == kid:
                values_.append(m["oben"])
            elif m.get("unten") is not None and distance(s, k2, kid) == 1:
                values_.append(m["unten"])
    return min(values_) if values_ else None


def is_illuminated(s, kid):
    """[RULE 9.2.1 p.70] Illuminated only in Limited Visibility; never with Weather Conditions +2 or higher."""
    l, w = light_weather(s)
    return l + w >= 2 and w < 2 and illumination_value(s, kid) is not None


def visibility_on_card(s, kid):
    """[RULE 9.0/9.2 p.69/70] Visibility modifier on kid: Illumination only mitigates light, light plus illum never better than +0."""
    l, w = light_weather(s)
    iw = illumination_value(s, kid)
    if iw is not None:
        l = max(0, l + iw)
    return l + w


def height_bonus(s, e):
    """L79 [RULE 5.2.2 p.35] Upper Story / Church Tower: +1 elevation level for the unit under it."""
    cv = cover_marker(s, e) if e else None
    return 1 if cv and cv["typ"] in ("Upper Story", "Church Tower") else 0


def opponent_of(e):
    return "Feind" if e.get("seite") == "US" else "US"


def card_height_bonus(s, k, side):
    """L79: highest extra level of one side's units on card k (Upper Story seen/seeing, 5.2.2 'Even if only part of a card is in LOS')."""
    return max([height_bonus(s, s["einheiten"][m]) for m in state.units_on(s, k, side)] or [0])


def los(s, a, b, radio=False, staging_frei=False, ha=0, hb=0):
    """5.2.1/5.2.2/5.4: geometry, range, edge, Incoming/Smoke, elevation, staging. Returns (bool, reason).
    funk=True: LOS for SCR536 [RULE 4.3.5 p.29] 'as if Daylight, and ignoring smoke' (range always up to Very Long)."""
    if a == b:
        return True, "same card"
    between = line_between(s, a, b)
    if between is None:
        return False, "not on one of the eight straight lines [5.2.1]"
    maxr = (
        3 if radio else (1 if s["sicht"] == "eingeschraenkt" and not is_illuminated(s, b) else 3)
    )  # [RULE 9.1, 9.2.1 p.70]
    if distance(s, a, b) > maxr:
        return False, f"farther than {maxr} cards [5.2.1]"
    ka, kb = state.card(s, a), state.card(s, b)
    if (kb.get("staging") or ka.get("staging")) and not staging_frei:
        return False, "Staging Area: no LOS in or out [2.5]"
    if blocks_los(ka, radio, s):
        return False, f"{a} has Incoming/Smoke, no LOS out [5.4]" + (
            state.open_reading(s, "U3_incoming_blockiert_funk") if radio else ""
        )
    ea, eb = ka.get("elevation", 1) + ha, kb.get("elevation", 1) + hb  # L79 Upper Story +1 [RULE 5.2.2 p.35]
    for z in between:
        c = state.card(s, z)
        if blocks_los(c, radio, s):
            return False, f"Incoming/Smoke on {z} blocks [5.4]" + (
                state.open_reading(s, "U3_incoming_blockiert_funk") if radio else ""
            )
        ez = c.get("elevation", 1)
        if ez > max(ea, eb) or (ez == max(ea, eb) and ez > min(ea, eb)):
            return False, f"{z} is higher than or as high as the lower point, blocks [5.2.2]"
        ds = see_through(c, direction(s, z, a), direction(s, z, b))
        if max(ea, eb) > ez:
            # [RULE 5.2.2 p.35] higher sees over lower despite dark edges; but 'straight up or downhill'
            # (level 3 to 1 across a level-2 card with dark edges) is blocked
            if ez > min(ea, eb) and ds is False:
                return False, f"{z} lies between the elevation levels and has dark edges (straight up/downhill) [5.2.2]"
            continue
        if ds is None:
            s.setdefault("_hinweise", []).append(
                f"LOS {a} to {b} passes through {z}: edge colours of {z} not recorded, check on the board (entry and exit sides white?) [5.2.1]"
            )
        elif ds is False:
            return False, f"{z} has dark edges [5.2.1]"
    return True, "ok"


def in_range(s, e, target):
    lo, hi = state.range_limits(s, e)
    return lo <= distance(s, e["karte"], target) <= hi


def cover_marker(s, e):
    """Cover marker the unit is under (or None)."""
    if e.get("bereich", "offen") == "offen" or e["karte"] not in s["karten"]:
        return None
    for c in s["karten"][e["karte"]].get("cover", []):
        if c["id"] == e["bereich"]:
            return c
    return None


def no_point_blank(s, e):
    """No Point Blank fire: [RULE 5.3.2 p.37] units in Bunker/Pillbox; [RULE 7.3.1 p.52] mortars."""
    cv = cover_marker(s, e)
    return bool(e.get("kein_point_blank")) or state.is_mortar(e) or bool(cv and cv["typ"] in rules.STRUCTURES)


def arc_direction(s, e):
    """Fire direction from Bunker/Pillbox [RULE 5.3.2 p.37]: marker field 'richtung' [dr,dc] or unit field 'bunker_richtung' (card, v2)."""
    cv = cover_marker(s, e)
    if cv and cv["typ"] in rules.STRUCTURES and cv.get("richtung"):
        return tuple(cv["richtung"])
    return None
