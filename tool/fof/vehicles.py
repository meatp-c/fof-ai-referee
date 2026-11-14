"""Vehicles and AT Combat (Series Rules 10.0-10.8, 3.6, 4.2.1i, 7.8, 8.12; Normandy CSR 7, MSR 2)..

The AT Combat & Vehicle Movement Phase (3.6) runs as a small queue. Every attack against a vehicle waits as one entry
until the player has drawn its card:
- VOF against a vehicle (10.5.3), AT Fire (10.6), Reaction Fire (10.5.4), Quick Shot (10.6.1): fof.py at <AT number>
  (or at :<card number> with the action card archive)
- the Grenade attempt of a G!-rated firer first (10.6.2): fof.py at grenade yes|no
A vehicle action is a plan of steps (VOF on its card, the action, VOF on the new card, Reaction Fire) that advances as
soon as the queue is empty (10.5.1)."""

from . import (
    briefing,
    campaign,
    combat,
    commands,
    comms,
    contact,
    enemy,
    fire,
    geometry,
    migrate,
    options,
    rules,
    state,
)

# [Vehicle and Anti-Tank Weapons Chart, WWII] gunnery P, C, L, V (None: no fire at that range), defensive value, crew steps,
# mobile, Move & Fire modifier (None: no Move then Fire), Quick Shot, target type, G! procedure (10.6.2), transport capacity
CHART = {
    "M5 Light Tank 37mm": ((-1, 0, 1, 3), -1, 1, True, 2, True, "V", True, None),
    "M4 Sherman 75mm": ((-3, 0, 1, 2), 0, 2, True, 2, True, "V", False, 4),
    "M4 Sherman 76mm": ((-5, -3, -1, 0), 0, 2, True, 2, True, "V", False, 4),
    "M10 TD 76mm": ((-5, -3, -1, 0), -1, 2, True, 2, True, "V", False, 4),
    "M1A1 Bazooka": ((-2, -1, None, None), None, None, True, None, False, "I", True, None),
    "M20 Bazooka": ((-3, -2, None, None), None, None, True, None, False, "I", True, None),
    "Rifle Grenade": ((0, 1, None, None), None, None, True, None, False, "I", True, None),
    "75mm Infantry Gun": ((-3, -1, 1, 3), None, None, False, None, False, "I", True, None),
    "75mm AT Gun": ((-4, -3, -1, 0), None, None, False, None, True, "I", False, None),
    "88mm FLAK": ((-6, -5, -3, -2), None, None, False, None, True, "I", False, None),
    "Panzerfaust": ((-3, None, None, None), None, None, True, None, False, "I", True, None),
    "Panzerschreck": ((-4, -2, None, None), None, None, True, None, False, "I", True, None),
    "Jeep": ((None, None, None, None), -2, 0, True, None, False, "V", False, 2),
    "Truck": ((None, None, None, None), -2, 1, True, None, False, "V", False, 10),
    ".50 Cal HMG": ((0, 0, 1, 2), None, None, False, None, False, "I", False, None),
    # [Vehicle and Anti-Tank Weapons Chart, Korea / Korea & Vietnam]
    "M26 Pershing 90mm": ((-6, -5, -3, -2), 2, 2, True, 3, True, "V", False, 4),
    "T-34/85": ((-5, -3, -1, 0), 1, 2, True, 3, True, "V", False, 4),
    "SU-76M": ((-4, -3, -1, 0), 0, 2, True, None, True, "V", False, 4),
    "Quad .50": ((0, 0, 1, 2), -1, 2, True, 1, True, "V", False, None),
    "57mm RCL": ((-3, -3, -2, 0), None, None, True, None, False, "I", True, None),
    "75mm RCL": ((-4, -3, -2, 0), None, None, True, None, False, "I", False, None),
}
RANGE_LETTER = ("P", "C", "L", "V")
# [Anti-Tank Combat Resolution and Modifiers, VOF against a vehicle 10.5.3] AT modifier by VOF type
VOF_AT_MOD = {"Pinned": 4, "S": 3, "A": 2, "H": 1, "Sniper": 1, "Incoming": -1, "Mines": -2, "G": -2, "AirStrike": -3}
QUICK_SHOT_SUMS = {-4, -2, 0, 2, 4}  # [RULE 10.6.1 p.73]
# [RULE 10.8.3 p.76] "anti-tank guns or rocket launchers"; recoilless rifles count with the rocket launchers (7.4, open U37)
AMBUSH_WEAPONS = {
    "M1A1 Bazooka",
    "M20 Bazooka",
    "Panzerfaust",
    "Panzerschreck",
    "75mm AT Gun",
    "88mm FLAK",
    "57mm RCL",
    "75mm RCL",
}
# [Normandy CSR 7 p.15] automatically Activated every turn; the others only on a card with a US vehicle
CSR7_ALWAYS = {"75mm AT Gun", "88mm FLAK", "Panzerschreck"}
CSR7_SAME_CARD = {"Panzerfaust", "75mm Infantry Gun"}
TRAFFIC = {"normal": True, "slow": "SLOW", "no": False}
AT_USAGE = "at <AT number>|:<card no>|grenade yes|no|again|stop"


def result_v(final):
    """[RULE 10.7 p.74, Combat Effects V] final sum against a ground vehicle."""
    if final <= -1:
        return "Brewed Up"
    if final <= 1:
        return "Knocked Out"
    if final <= 3:
        return "Retreat"
    if final <= 5:
        return "Pinned"
    return "Missed"


def is_vehicle(e):
    return bool(e.get("vehicle"))


# [Normandy CSR 1 p.13] Arty Jeep: the Arty FD Net SCR610 mounted in a jeep that carries only the Arty FO
ARTY_JEEP = "Arty Jeep"


def passengers(s, name):
    """Units embarked on vehicle `name` (field on_board, 10.8.1)."""
    return [n for n, e in s["units"].items() if e.get("on_board") == name]


_EXP_ORDER = {"Green": 0, "Line": 1, "Veteran": 2}


def crewless_jeep(e):
    """Arty Jeep or company Jeep: no crew (10.8.8), whatever unit is embarked drives it (10.8.1)."""
    return bool(e.get("arty_jeep") or e.get("company_jeep"))


def company_jeep_unit(card=None):
    """company Jeep asset: no crew (10.8.8), capacity per the chart, Exp as per driver/passenger (Naktong p.12)."""
    return {
        "side": "US",
        "type": "Vehicle",
        "vehicle": "Jeep",
        "company_jeep": True,
        "card": card,
        "area": "open",
        "status": [],
        "steps": 0,
        "target": None,
        "vof_rating": None,
        "range": None,
        "experience": None,
        "platoon": None,
        "attached_to": [],
        "note": "Company Jeep asset (no crew, 10.8.8): carries 2 steps of infantry; embarked HQ/Staff activate it themselves, "
        "other passengers through an HQ in Visual-Verbal communication or GI; passengers Exposed when it moves (10.8.1)",
    }


def update_jeep_experience(s, name):
    """[RULE 10.8.8 p.77] a crewless vehicle uses the highest Experience Level of the units on board."""
    j = s["units"].get(name)
    if j is None or not j.get("company_jeep"):
        return
    exp = [comms.experience(s["units"][m]) for m in passengers(s, name)]
    j["experience"] = max(exp, key=_EXP_ORDER.get) if exp else None


def refresh_jeeps(s):
    """the company jeep's experience follows its passengers (10.8.8) also when a passenger changes
    without embarking (Fire Team side, HQ hit): recomputed whenever the state is loaded or saved."""
    for n, e in s.get("units", {}).items():
        if e.get("company_jeep"):
            update_jeep_experience(s, n)


def arty_jeep_unit(fo):
    """The ARTY FD Net Jeep counter (E79): no crew (10.8.8), Jeep chart line, embarked units drive it (10.8.1)."""
    return {
        "side": "US",
        "type": "Vehicle",
        "vehicle": "Jeep",
        "arty_jeep": True,
        "card": fo.get("card"),
        "area": "open",
        "status": [],
        "steps": 0,
        "target": None,
        "vof_rating": None,
        "range": None,
        "experience": fo.get("experience"),
        "platoon": None,
        "attached_to": [],
        "note": "ARTY FD Net Jeep with SCR610 (E79); no crew (10.8.8); carries only the Arty FO; automatically Activated for "
        "Vehicle Movement while he is on board (Normandy CSR 1 p.13)",
    }


def vehicle_types():
    """Chart keys that are vehicles (target type V), for messages."""
    return [k for k, v in CHART.items() if v[6] == "V"]


def chart(e):
    """Chart line of a vehicle; an unknown 'vehicle' is a Violation naming the valid keys, not a KeyError."""
    w = e.get("vehicle")
    if w not in CHART:
        raise rules.Violation(f"Unknown vehicle type '{w}'; valid types: {', '.join(vehicle_types())}")
    return CHART[w]


def chart_line(w):
    """Chart line of an AT weapon key (vehicle type or 'at_weapon'); unknown keys are a Violation."""
    if w not in CHART:
        raise rules.Violation(f"Unknown AT weapon '{w}'; valid chart keys: {', '.join(CHART)}")
    return CHART[w]


def weapon(e):
    """AT weapon of a unit (chart line) or None."""
    if e.get("vehicle"):
        return e["vehicle"] if chart(e)[0][0] is not None else None
    if state.is_lat(e) or e["type"] == "Casualty":
        return None
    if e.get("at_weapon"):
        return e["at_weapon"]
    if e.get("panzerfaust", 0) > 0:
        return "Panzerfaust"  # [Normandy M6 p.40] each FJ squad has one Panzerfaust shot
    if e.get("rifle_grenades", 0) > 0 or (e["side"] == "US" and "Rifle Grenade" in (e.get("assets") or [])):
        return "Rifle Grenade"
    return None


def shots_left(e):
    w = weapon(e)
    if not w:
        return 0
    if w == "Panzerfaust" and not e.get("at_weapon"):
        return e.get("panzerfaust", 0)
    if w == "Rifle Grenade" and not e.get("at_weapon"):
        return e.get("rifle_grenades", 0) or (e.get("assets") or []).count("Rifle Grenade")
    m = combat.ammo(e)
    return m["points"] if m else 1


def at_capable(e):
    """AT-capable now (10.5.4, glossary 1.2.6): an AT weapon with shots left, not a Litter/Paralyzed Team."""
    return bool(weapon(e)) and shots_left(e) > 0 and e["type"] not in ("Paralyzed Team", "Litter Team")


def use_shot(s, n, e, prot):
    w = weapon(e)
    if w == "Panzerfaust" and not e.get("at_weapon"):
        e["panzerfaust"] -= 1
        prot.append(f"{n}: Panzerfaust fired, {e['panzerfaust']} left [Normandy M6 p.40, CSR 7]")
    elif w == "Rifle Grenade" and not e.get("at_weapon"):
        if e.get("rifle_grenades", 0) > 0:
            e["rifle_grenades"] -= 1
        else:
            e["assets"].remove("Rifle Grenade")
        prot.append(f"{n}: Rifle Grenade used [8.9, 10.6.2]")
    else:
        combat.ammo_use(s, n, e, 1, "AT Fire", prot)  # [Charts: each AT Fire attempt uses 1 ammo]


def at36(s):
    return s.setdefault("at36", {"queue": [], "action": None, "attacked": [], "next": None, "end": False, "report": []})


def activated(e):
    return rules.ACTIVATED in e["status"]


def moved_fired(e):
    return rules.MOVED_FIRED in e["status"]


def card_cc(s, target_card, from_card):
    """[RULE 5.2.3 p.36] two C&C values: higher one across a dark edge, lower one across white edges or from the card itself."""
    c = state.card(s, target_card)
    if c.get("cc2") is None:
        return c.get("cc", 0), f"C&C {c['terrain']}"
    if from_card is None or from_card == target_card:
        return c["cc2"], f"C&C {c['terrain']} (lower value, from within the card)"
    if geometry.edge(c, geometry.direction(s, target_card, from_card)) != "white":
        return c["cc"], f"C&C {c['terrain']} (higher value, across a dark edge)"
    return c["cc2"], f"C&C {c['terrain']} (lower value, across a white edge)"


def ambush(s, target_name, shooter):
    """[RULE 10.8.3 p.76] susceptible vehicle (mission), rocket launcher or AT gun at P/C, no Good Order friendly infantry
    on the vehicle's card."""
    target_unit = s["units"][target_name]
    if not target_unit.get("ambush") or weapon(shooter) not in AMBUSH_WEAPONS:
        return False
    if geometry.distance(s, shooter["card"], target_unit["card"]) > 1:
        return False
    infantry = [
        m
        for m in state.units_on(s, target_unit["card"], target_unit["side"])
        if not is_vehicle(s["units"][m]) and state.good_order(s["units"][m])
    ]
    return not infantry


def gunnery(w, dist):
    if dist > 3:
        return None
    return chart_line(w)[0][dist]


def line_of_fire(s, shooter, target_card):
    """LOS and range of an AT shot (10.6 A); AT Fire does not need a PDF (10.5.2 A)."""
    w = weapon(shooter)
    d = geometry.distance(s, shooter["card"], target_card)
    if not w or gunnery(w, d) is None:
        return None
    if d:
        ok, _ = geometry.los(
            s,
            shooter["card"],
            target_card,
            ha=geometry.height_bonus(s, shooter),
            hb=geometry.card_height_bonus(s, target_card, geometry.opponent_of(shooter)),
        )
        if not ok:
            return None
    return d


def at_rows(s, shooter_name, target_name):
    """[RULE 10.6 A-E p.73] net AT modifier of an AT Fire attack as rows (label, value)."""
    a, target_unit = s["units"][shooter_name], s["units"][target_name]
    w = weapon(a)
    d = line_of_fire(s, a, target_unit["card"])
    if d is None:  # no TypeError on RANGE_LETTER[None]
        raise rules.Violation(f"{target_name} not in LOS/range of {shooter_name} [10.6 A]")
    rows = [(f"Gunnery {w} at range {RANGE_LETTER[d]}", gunnery(w, d))]
    rows.append((f"Defensive value {target_unit['vehicle']}", chart(target_unit)[1]))
    v, label = card_cc(s, target_unit["card"], a["card"])
    rows.append((label, v))
    if a.get("in_motion") and chart_line(w)[4] is not None and is_vehicle(a):
        rows.append(("Move & Fire", chart_line(w)[4]))
    if state.pinned(target_unit):
        rows.append(("Target is Pinned", -1))
    if target_unit.get("in_motion"):
        rows.append(("Target is moving", 1))
    if state.pinned(a):
        rows.append(("Firer is Pinned", 1))
    if ambush(s, target_name, a):
        rows.append(("Tank Ambush [10.8.3]", -4 if state.pinned(target_unit) else -3))
    return rows


def grenade_cards(s, shooter_name, target_name):
    """[RULE 10.6.2 p.73] G!-rated firer: first a Grenade attempt, two cards adjusted for Experience; Ambush +1 (+1 more on a
    Pinned target, 10.8.3)."""
    a, target_unit = s["units"][shooter_name], s["units"][target_name]
    n = 2 + {"Green": -1, "Veteran": 1}.get(comms.experience(a), 0)
    if ambush(s, target_name, a):
        n += 2 if state.pinned(target_unit) else 1
    return max(1, n)


def vof_on_vehicle(s, n):
    """[RULE 10.5.3 p.72] strongest VOF on the vehicle's card from non-AT-capable units and S-rated AT-capable units
    (VOF of A/H-rated AT-capable units is ignored); external VOF (Incoming, Mines on a mine hit) counts as well."""
    e = s["units"][n]
    best = None
    for type_, value, src, side, from_card in fire.vof_entries(s, e["card"]):
        if side not in (None, e["side"]):
            continue
        if type_ == "Mines" and not e.get("mine_hit"):
            continue
        su = s["units"].get(src)
        # [RULE 10.5.3 p.72, 6.2] no exception for friendly VOF: own Incoming or own small arms on the card hit the
        # vehicle too (friendly fire); Point Blank VOF only hits the opposing side (side filter above, 6.2.1b)
        if su is not None and at_capable(su) and su.get("vof_rating") in ("A", "H", "A/S"):
            continue  # ignored: A/H-rated AT-capable units only fire AT Fire / Reaction Fire at vehicles
        if type_ not in VOF_AT_MOD:
            continue  # the AT chart has no Indirect Lay line, so an "Indirect" VOF is ignored (open reading)
        if best is None or value < best[1]:
            best = (type_, value, src, from_card)
    if e.get("grenade") and (best is None or VOF_AT_MOD["G"] < VOF_AT_MOD[best[0]]):
        # [RULE 10.5.3 p.72, AT chart 'Grenade -2']: a Grenade VOF placed on the vehicle (e.g. G! mortar) counts too;
        # 'Hand Grenade VOF does not stack': only the strongest VOF (by AT modifier) is applied
        best = ("G", min(e["grenade"]), "Grenade Attack", None)
    return best


def queue_vof(s, n, prot, label):
    b = vof_on_vehicle(s, n)
    if not b:
        return
    e = s["units"][n]
    type_, _wert, src, from_card = b
    rows = [("Gunnery (VOF) 0", 0), (f"Defensive value {e['vehicle']}", chart(e)[1])]
    v, lab = card_cc(s, e["card"], from_card)
    rows.append((lab, v))
    if type_ == "Incoming" and state.card(s, e["card"]).get("burst") is not None:
        rows.append(("Burst symbol", state.card(s, e["card"])["burst"]))
    if e.get("in_motion"):
        rows.append(("Target is moving", 1))
    if state.pinned(e):
        rows.append(("Target is Pinned", -1))
    rows.append((f"VOF {rules.VOF_NAME.get(type_, type_)} ({src})", VOF_AT_MOD[type_]))
    at36(s)["queue"].append(make_item("vof", target=n, modifiers=rows, label=label))
    prot.append(f"{label}: VOF {rules.VOF_NAME.get(type_, type_)} from {src} against {n} [10.5.3 p.72]")


def make_item(kind, **fields):
    """Queue entry of 3.6 (kind: vof, at, choice). 'reaction' marks the Reaction Fire chain (10.5.4 Exception, 10.6.1) and
    is set once here from the kind or the flag passed along."""
    item = {"kind": kind, "target": None, "modifiers": [], "reaction": False}
    item.update(fields)
    item["reaction"] = bool(item["reaction"] or item.get("type") == "reaction")
    return item


def make_step(kind, **fields):
    """Plan step of a vehicle action (kind: vof, move, react, fire, cf, spot, end)."""
    step = {"kind": kind}
    step.update(fields)
    return step


def _legacy_step(step):
    """Plan steps of older saved games are tuples/lists: ("vof", label), ("move", card, area), ("fire", target), ..."""
    if isinstance(step, dict):
        return step
    kind = step[0]
    if kind == "vof":
        return make_step("vof", label=step[1])
    if kind == "move":
        return make_step("move", card=step[1], area=step[2])
    if kind == "fire":
        return make_step("fire", target=step[1])
    return make_step(kind)


def queue_at(s, shooter, target, prot, kind, reaction=False):
    """One AT Fire attack (kind: action, reaction, quick); reaction=True keeps the Reaction Fire chain through Quick Shots."""
    a = s["units"][shooter]
    w = weapon(a)
    item = make_item(
        "at", shooter=shooter, target=target, type=kind, modifiers=at_rows(s, shooter, target), reaction=reaction
    )
    if chart_line(w)[7]:
        item["g_cards"] = grenade_cards(s, shooter, target)
    at36(s)["queue"].append(item)
    prot.append(
        f"{'Reaction Fire' if kind == 'reaction' else 'Quick Shot' if kind == 'quick' else 'AT Fire'}: {shooter} ({w}) at {target}"
        + (f"; first the Grenade attempt, {item['g_cards']} cards [10.6.2]" if item.get("g_cards") else "")
    )


def reaction_shooters(s, target):
    """[RULE 10.5.4 p.73] opposing AT-capable units not marked Moved/Fired with LOS and range; enemies always fire.
    Unspotted enemies react too (10.5.4 names no Spotted condition)."""
    target_unit = s["units"][target]
    out = []
    for n, e in s["units"].items():
        if e["side"] == target_unit["side"] or not at_capable(e) or moved_fired(e):
            continue
        if e.get("card") not in s["cards"] or line_of_fire(s, e, target_unit["card"]) is None:
            continue
        out.append(n)
    return out


def queue_reactions(s, target, prot):
    """[RULE 10.5.4 p.73] enemy shooters always react (queued); eligible US shooters get a Reaction Fire window that
    holds the plan until each has reacted or the player passes: the moving vehicle is still on the
    card of its move and still 'moving'."""
    us = []
    for n in reaction_shooters(s, target):
        if s["units"][n]["side"] == "Enemy":
            queue_at(s, n, target, prot, "reaction")
        else:
            us.append(n)
    if us:
        at36(s)["reaction_open"] = {"target": target, "shooters": us}  # resume() names it as the next step


def window_live(s):
    """The open Reaction Fire window, with shooters that are still eligible; a stale window is dropped."""
    st = at36(s)
    w = st.get("reaction_open")
    if not w:
        return None
    if w["target"] not in s["units"]:
        st.pop("reaction_open")
        return None
    w["shooters"] = [n for n in w["shooters"] if n in s["units"] and n in reaction_shooters(s, w["target"])]
    if not w["shooters"]:
        st.pop("reaction_open")
        return None
    return w


def window_text(s):
    w = at36(s).get("reaction_open")
    return (
        f"Reaction Fire at {w['target']} possible for {', '.join(w['shooters'])}: fof.py vehicle react <unit> {w['target']} "
        "for each one that fires, or vehicle react pass [10.5.4]"
    )


def require_phase(s):
    if s["phase"] != "3.6":
        raise rules.Violation(
            f"Vehicle actions only in the AT Combat & Vehicle Movement Phase 3.6, currently {s['phase']}"
        )


def choice_live(s, w):
    """A pending Quick Shot target choice is live while its shooter and at least one listed target can
    still be attacked; a stale one lapses in purge()."""
    return (
        bool(w) and w["shooter"] in s["units"] and any(t in vehicle_targets(s, w["shooter"]) for t in w["objectives"])
    )


def lock(s):
    contact.mine_lock(s)
    st = at36(s)
    q = st["queue"]
    if q:
        raise rules.Violation("First resolve the open AT draw: " + describe(s, q[0]))
    if choice_live(s, st.get("choice")):
        raise rules.Violation("First resolve the open target choice: " + describe(s, st["choice"]))
    if window_live(s):
        raise rules.Violation("First decide on Reaction Fire: " + window_text(s))
    crew = [n for n, e in s["units"].items() if e.get("crew_hit_open")]
    if crew:
        raise rules.Violation(
            "Crew teams still need their HIT: "
            + ", ".join(f'fof.py hit "{n}" HIT <letters>' for n in crew)
            + " [10.7 Knocked Out]"
        )


def net(item):
    return sum(v for _, v in item.get("modifiers", []))


def describe(s, item):
    rows = "; ".join(f"{t} {v:+d}" for t, v in item.get("modifiers", []))
    if item.get("kind") == "choice" or "objectives" in item:  # a choice of an older saved game has no 'kind'
        return (
            f"{item['shooter']} Quick Shot: choose the target randomly, R# column {len(item['objectives'])}: "
            + ", ".join(f"{i}={t}" for i, t in enumerate(item["objectives"], 1))
            + "; then fof.py vehicle target <R#> [CSR 7]"
        )
    if item.get("type") == "quick_offer":
        return f"{item['shooter']} may take a Quick Shot at {item['target']}: fof.py at again | at stop [10.6.1 p.73]"
    if item.get("g_cards"):
        return (
            f"{item['shooter']}: Grenade attempt first, draw {item['g_cards']} Action cards, success on the Grenade icon; "
            "then fof.py at grenade yes|no [10.6.2 p.73]"
        )
    head = (
        f"VOF against {item['target']}"
        if item["kind"] == "vof"
        else f"{item['shooter']} at {item['target']} ({item['type']})"
    )
    return f"{head}: net AT modifier {net(item):+d} ({rows}); draw an Action card, fof.py at <AT number> [10.6 p.73]"


def add_wreck_cover(s, c, val):
    """[RULE 10.7 p.74] a Wreck cover marker (+val) on card c with the next free id C<i>; returns the id."""
    ids = [cv["id"] for cv in c.get("cover", [])]
    i = 1
    while f"C{i}" in ids:
        i += 1
    c.setdefault("cover", []).append({"id": f"C{i}", "type": "Wreck", "value": val, "field": False, "wreck": True})
    return f"C{i}"


def apply_result(s, target, res, prot):
    """[RULE 10.7 p.74] Brewed Up, Knocked Out, Retreat, Pinned, Missed."""
    target_unit = s["units"][target]
    card_id = target_unit["card"]
    c = state.card(s, card_id)
    at36(s)["attacked"].append(target)
    if target_unit["side"] == "Enemy" and res in ("Brewed Up", "Knocked Out"):
        # [Naktong p.12 Experience] 'Knock out or Brew Up enemy tank or assault gun 4 per vehicle', truck 2
        key = "enemy_truck" if "Truck" in (target_unit.get("vehicle") or "") else "enemy_tank"
        campaign.book_xp(s, campaign.xp_table(s, key), f"{target} {res}", prot)
    crew = chart(target_unit)[2] or 0
    if res == "Brewed Up":
        # crew steps become Casualties of their own side; through combat.make_casualty,
        # the one casualty path (mission total only in campaign, as for infantry)
        for _ in range(crew):
            combat.make_casualty(s, target_unit, prot, target)
        smoke = (s.get("vehicle_values") or {}).get("burning_wreck_smoke", 1)
        c.setdefault("external", []).append({"type": "Smoke", "value": smoke, "source": "Burning Wreck", "wreck": True})
        combat.remove_from_play(
            s, target, prot, f"Brewed Up: Burning Wreck marker on {card_id}, {crew} crew step(s) become Casualties"
        )
        prot.append(f"{card_id}: Burning Wreck (smoke +{smoke}, blocks LOS, no cover marker) [10.7 p.74, 5.4]")
    elif res == "Knocked Out":
        val = (s.get("vehicle_values") or {}).get("wreck_cover", 1)
        cid = add_wreck_cover(s, c, val)
        crew_names = []
        for _ in range(crew):
            fn = commands.new_name(s, "Fire Team", side=target_unit["side"], card=target_unit["card"])
            ft = combat.new_lat(target_unit, "Fire Team", target)
            ft.update(area=cid, status=[rules.EXPOSED], crew_hit_open=True)
            s["units"][fn] = ft
            crew_names.append(fn)
        combat.remove_from_play(s, target, prot, f"Knocked Out: Wreck marker {cid} (cover +{val}) on {card_id}")
        if crew_names:
            prot.append(
                f"Crew: {', '.join(crew_names)} under the Wreck {cid}, Exposed; each takes a HIT now: draw a second card per team and "
                + ", ".join(f'fof.py hit "{x}" HIT <letters>' for x in crew_names)
                + " [10.7 p.74]"
            )
    elif res == "Retreat":
        combat.remove_from_play(s, target, prot, "Retreat: the vehicle leaves the map for the rest of the mission")
    elif res == "Pinned":
        if not state.pinned(target_unit):
            target_unit["status"].append(rules.PINNED)
        prot.append(
            f"{target} Pinned (buttoned up): -1 as target, +1 when firing, no Spot or Concentrate Fire [10.7 p.74]"
        )
    else:
        prot.append(f"{target}: Missed")
    if target in s["commands"] and target not in s["units"]:
        prot.append(f"{target} was a vehicle PLT HQ: its Command marker leaves the track")


def finish_shooter(s, shooter, prot, keep_open=False):
    a = s["units"].get(shooter)
    if not a:
        return
    if not keep_open and not moved_fired(a):
        a["status"] = [m for m in a["status"] if m != rules.ACTIVATED] + [rules.MOVED_FIRED]
        prot.append(f"{shooter}: flip to Moved/Fired [10.4]")


def cmd_at(s, args):
    """at <AT number>|:<card no>|grenade yes|no|again|stop: resolve the next open AT draw."""
    require_phase(s)
    contact.mine_lock(s)
    st = at36(s)
    prot = []
    purge(s, prot)  # a draw against a unit removed by another command lapses instead of a KeyError
    if prot and not st["queue"]:
        return finish(s, prot)
    if not st["queue"]:
        raise rules.Violation("No AT draw open")
    crew = [n for n, e in s["units"].items() if e.get("crew_hit_open")]
    if crew:
        raise rules.Violation(
            "First the crew HITs: " + ", ".join(f'fof.py hit "{n}" HIT <letters>' for n in crew) + " [10.7]"
        )
    rules.need(args, 1, AT_USAGE)
    item = st["queue"][0]
    handler = AT_SUBCOMMANDS.get(args[0])
    if handler is None:
        handler = at_quick_offer if item.get("type") == "quick_offer" else at_draw
    handler(s, st, item, args, prot)
    return finish(s, prot)


def at_grenade(s, st, item, args, prot):
    """at grenade yes|no: the Grenade attempt of a G!-rated firer before its AT draw (10.6.2)."""
    if not item.get("g_cards"):
        raise rules.Violation("This attack needs no Grenade attempt")
    a = s["units"][item["shooter"]]
    if len(args) < 2 or args[1] not in ("yes", "no"):
        raise rules.Violation("at grenade yes|no")
    if args[1] == "no":
        use_shot(s, item["shooter"], a, prot)
        st["queue"].pop(0)
        prot.append(f"{item['shooter']}: Grenade attempt failed, no AT draw, no Grenade Miss marker [10.6.2 p.73]")
        finish_shooter(s, item["shooter"], prot)
    else:
        item.pop("g_cards")
        prot.append(f"{item['shooter']}: Grenade attempt successful, now the AT draw [10.6.2 p.73]")


def at_stop(s, st, item, args, prot):
    """at stop: decline the offered Quick Shot (10.6.1)."""
    if item.get("type") != "quick_offer":
        raise rules.Violation("Nothing to stop")
    st["queue"].pop(0)
    # [RULE 10.6.1 p.73]: a Quick Shot draw obtained as Reaction Fire leaves the unit without Moved/Fired
    # "even if the player chooses not to continue firing"; the flag travels through the whole chain, so the first
    # and every later offer behave alike. A chain that ends with a non-Quick-Shot draw flips to Moved/Fired (10.5.4).
    finish_shooter(s, item["shooter"], prot, keep_open=item.get("reaction", False))
    prot.append(f"{item['shooter']}: no further Quick Shot")


def at_quick_offer(s, st, item, args, prot):
    """at again: take the offered Quick Shot (10.6.1)."""
    if args[0] != "again":
        raise rules.Violation(f"{item['shooter']} may take a Quick Shot: fof.py at again | at stop [10.6.1]")
    st["queue"].pop(0)
    if item["target"] in s["units"]:
        queue_at(s, item["shooter"], item["target"], prot, "quick", reaction=item.get("reaction", False))


def at_number(args):
    """AT modifier of the drawn card: a number or :<card no> from the action card archive."""
    val = args[0]
    if val.startswith(":"):
        card = _cards().get(val[1:])
        if not card or card.get("at") is None:
            raise rules.Violation(f"Action card {val[1:]} without AT value in the archive; give the AT number")
        val = card["at"]
    return rules.int_value(val, "at <AT number> (the AT value printed on the Action card)")


def at_draw(s, st, item, args, prot):
    """at <AT number>: resolve the open VOF or AT Fire draw (10.6 F, 10.7), then Quick Shot (10.6.1)."""
    if item.get("g_cards"):
        raise rules.Violation(describe(s, item))
    number = at_number(args)
    total = net(item) + number
    res = result_v(total)
    st["queue"].pop(0)
    target = item["target"]
    if item["kind"] == "vof":
        prot.append(f"VOF against {target}: {net(item):+d} + AT {number} = {total}: {res} [10.5.3, 10.7]")
        apply_result(s, target, res, prot)
        return
    shooter = item["shooter"]
    a = s["units"].get(shooter)
    if a:
        use_shot(s, shooter, a, prot)
    prot.append(f"{shooter} at {target}: {net(item):+d} + AT {number} = {total}: {res} [10.6, 10.7]")
    apply_result(s, target, res, prot)
    w = weapon(a) if a else None
    quick = a is not None and w and chart_line(w)[5] and total in QUICK_SHOT_SUMS and shots_left(a) > 0
    reaction = bool(item["type"] == "reaction" or item.get("reaction"))
    if quick and quick_shot(s, st, shooter, a, target, total, reaction, prot):
        return
    finish_shooter(s, shooter, prot)


def quick_shot(s, st, shooter, a, target, total, reaction, prot):
    """Quick Shot result (10.6.1): enemies fire again at once (new random target, CSR 7), the player is offered one.
    Returns True when the shooter stays open (next shot queued, offer pending or Reaction Fire exception)."""
    targets = vehicle_targets(s, shooter)
    if a["side"] == "Enemy" and targets:
        # [Normandy CSR 7 p.15] draw a new target for each Quick Shot; [10.6.1] enemies always take it
        if len(targets) == 1:
            queue_at(s, shooter, targets[0], prot, "quick", reaction=reaction)
        else:
            st["choice"] = make_item("choice", shooter=shooter, objectives=targets, reaction=reaction)
        prot.append(f"{shooter}: Quick Shot result ({total}), fires again [10.6.1 p.73]")
        return True
    if a["side"] == "US" and target in s["units"]:
        st["queue"].insert(0, make_item("at", type="quick_offer", shooter=shooter, target=target, reaction=reaction))
        prot.append(f"{shooter}: Quick Shot result ({total}); fof.py at again | at stop [10.6.1 p.73]")
        return True
    if reaction:
        prot.append(f"{shooter}: Quick Shot draw on Reaction Fire, not marked Moved/Fired [10.5.4 Exception]")
        return True
    return False


AT_SUBCOMMANDS = {"grenade": at_grenade, "stop": at_stop}


def _cards():
    import json

    try:
        return migrate.data(json.loads(state.data_file("action_cards.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {}


def vehicle_targets(s, shooter):
    a = s["units"][shooter]
    return [
        n
        for n, e in s["units"].items()
        if is_vehicle(e) and e["side"] != a["side"] and line_of_fire(s, a, e["card"]) is not None
    ]


def run_fire(s, n, step, prot):
    """AT Fire step of a vehicle action (10.5.2 D); after a Move the LOS/range is checked again."""
    t = step["target"]
    if t not in s["units"]:
        return
    if line_of_fire(s, s["units"][n], s["units"][t]["card"]) is None:
        prot.append(f"{n}: {t} no longer in LOS/range after the move, no AT Fire [10.6 A]")
        return
    queue_at(s, n, t, prot, "action")


def run_choose(s, n, step, prot):
    """Move & Fire with several targets: the still valid ones go to a random choice (vehicle target <R#>)."""
    targets = [t for t in step["objectives"] if t in vehicle_targets(s, n)]
    if len(targets) == 1:
        queue_at(s, n, targets[0], prot, "action")
    elif targets:
        at36(s)["choice"] = make_item("choice", shooter=n, objectives=targets, type_after="action")
    else:
        prot.append(f"{n}: no target left in LOS/range after the move, no AT Fire [10.6 A]")


def run_cf(s, n, step, prot):
    """Concentrate Fire step (10.5.2 B, 7.11): effects only now, after the VOF before the action."""
    if not step["success"]:
        prot.append(f"{n}: Concentrate Fire failed")
        return
    target_unit_name = step["target"]
    if target_unit_name not in s["units"]:
        prot.append(f"{n}: Concentrate Fire target {target_unit_name} is gone, no marker")
        return
    for m in enemy.cf_stack(s, target_unit_name):
        s["units"][m]["cf"] = s["units"][m].get("cf", 0) + 1
    prot.append(
        f"Concentrated Fire marker on {target_unit_name} (stack: {', '.join(enemy.cf_stack(s, target_unit_name))}) [10.5.2 B, 7.11]"
    )
    commands.cf_critical(s, target_unit_name, {"--critical": "yes" if step.get("critical") else "no"}, prot)


def run_spot(s, n, step, prot):
    """Spot step (10.5.2 E, 8.5): the counters flip only now, after the VOF before the action."""
    card_id = step["card"]
    if not step["success"]:
        prot.append(f"{n}: Spot failed")
        return
    hidden = commands.unspotted_enemies(s, card_id)
    if not hidden:
        prot.append(f"{card_id}: no Unspotted enemy left to Spot")
        return
    for m in hidden:
        s["units"][m]["spotted"] = True
    prot.append(f"{card_id}: {', '.join(hidden)} Spotted, flip the counters [8.5]")
    fire.open_fire(s, prot)


def advance(s, prot):
    """Run the plan of the current vehicle action until a draw (or a Quick Shot target choice) is needed (10.5.1)."""
    st = at36(s)
    while not st["queue"] and not st.get("choice") and not window_live(s) and not s.get("mine_checks"):
        action = st.get("action")
        if not action:
            return
        n = action["unit"]
        if n not in s["units"]:
            prot.append(f"{n} is gone: its action ends")
            st["action"] = None
            switch_side(s, prot)
            return
        if not action["plan"]:
            if action.get("end"):
                end_action(s, prot)
            return
        step = _legacy_step(action["plan"].pop(0))
        kind = step["kind"]
        if kind == "vof":
            queue_vof(s, n, prot, step["label"])
        elif kind == "move":
            do_move(s, n, step["card"], step["area"], prot)
        elif kind == "tankmove":
            tank_move_step(s, n, step, action, prot)
        elif kind == "react":
            queue_reactions(s, n, prot)
        elif kind == "fire":
            run_fire(s, n, step, prot)
        elif kind == "choose":
            run_choose(s, n, step, prot)
        elif kind == "cf":
            run_cf(s, n, step, prot)
        elif kind == "spot":
            run_spot(s, n, step, prot)
        elif kind == "end":
            action["end"] = True


def purge(s, prot):
    """Open draws against a vehicle that is gone (Brewed Up, Knocked Out, Retreat) lapse; so does a Quick Shot target
    choice whose shooter or targets are gone."""
    st = at36(s)
    keep = []
    for q in st["queue"]:
        if q["target"] in s["units"] and (q.get("shooter") is None or q["shooter"] in s["units"]):
            keep.append(q)
        else:
            prot.append(f"{q.get('shooter') or 'VOF'} at {q['target']}: lapses, the target is gone")
    st["queue"] = keep
    w = st.get("choice")
    if not w:
        return
    if w["shooter"] in s["units"]:
        valid = vehicle_targets(s, w["shooter"])
        gone = [t for t in w["objectives"] if t not in valid]
        if gone:
            w["objectives"] = [t for t in w["objectives"] if t in valid]
            prot.append(f"{w['shooter']} Quick Shot: {', '.join(gone)} no longer a target (gone or out of LOS/range)")
    if not choice_live(s, w):
        st.pop("choice")
        prot.append(f"{w['shooter']}: Quick Shot target choice lapses, no target left")


def resume(s, prot):
    """Continue the phase after an interruption (mine check, resolved draw): lapsed draws go, the plan runs on, the next
    step is named. contact.py uses this after a mine check."""
    purge(s, prot)
    advance(s, prot)
    st = at36(s)
    if st["queue"]:
        prot.append("Next draw: " + describe(s, st["queue"][0]))
    elif st.get("choice"):
        prot.append("Next: " + describe(s, st["choice"]))
    elif window_live(s):
        prot.append("Next: " + window_text(s))
    elif st.get("action") and not st["action"].get("end"):
        n = st["action"]["unit"]
        # the Arty Jeep has no gun; AT Fire only against an opposing vehicle in LOS and range (10.6)
        armed = n in s["units"] and at_capable(s["units"][n]) and bool(vehicle_targets(s, n))
        fire_txt = f" | vehicle fire {n} <target> (Move then AT Fire)" if armed else ""
        if st["action"].get("slow"):  # after a SLOW card only Move then AT Fire or done remain
            prot.append(
                f"{n} may continue: fof.py vehicle {'fire ' + n + ' <target> (Move then AT Fire) | vehicle ' if armed else ''}done {n}"
            )
        else:
            prot.append(f"{n} may continue: fof.py vehicle move {n} <card>{fire_txt} | vehicle done {n}")
    else:
        prot.append(next_hint(s))


def finish(s, prot):
    resume(s, prot)
    activity_note = fire.update_activity(s)
    if activity_note:
        prot.append(activity_note)
    state.save_state(s, "; ".join(prot), "10.5 p.72, 10.6 p.73")
    briefing.print_board(prot, s)


def end_action(s, prot):
    st = at36(s)
    action = st.get("action")
    if not action:
        return
    n = action["unit"]
    e = s["units"].get(n)
    if e:
        e.pop("in_motion", None)
        finish_shooter(s, n, prot)
        e["has_acted"] = True
        # the side that just acted hands over (10.5.1); a unit gone during its action keeps next
        st["next"] = e["side"]
    st["action"] = None
    switch_side(s, prot)


def action_group(e):
    """[Normandy M6 MSR 2 p.41]: 1 Tanks, 2 Jeeps (and Trucks), 3 AT Guns & AT-capable infantry."""
    if is_vehicle(e):
        w = e.get("vehicle") or ""
        return 2 if ("Jeep" in w or "Truck" in w) else 1
    return 3


def _enemy_base(s):
    return [
        n
        for n, e in s["units"].items()
        if e["side"] == "Enemy"
        and activated(e)
        and not moved_fired(e)
        and at_capable(e)
        and (vehicle_targets(s, n) or (is_vehicle(e) and tank_priorities(s)))  # tanks act on their priority list
    ]


def _us_base(s):
    return [n for n, e in s["units"].items() if e["side"] == "US" and activated(e) and not moved_fired(e)]


def _group_of(s, enemy_base, us_base):
    if not (s.get("special_rules") or {}).get("vehicle_order"):
        return None
    groups = [action_group(s["units"][n]) for n in enemy_base + us_base]
    return min(groups) if groups else None


def current_group(s):
    """with a mission group order (special_rules.vehicle_order) only the lowest group still to act may act
    (both sides); Reaction Fire is not affected. None without such a rule."""
    return _group_of(s, _enemy_base(s), _us_base(s))


def actors(s):
    """(US actors, enemy actors) of the current group in one pass: the LOS scan of _enemy_base runs once."""
    en, us = _enemy_base(s), _us_base(s)
    g = _group_of(s, en, us)

    def in_group(names):
        return [n for n in names if g is None or action_group(s["units"][n]) == g]

    return in_group(us), in_group(en)


def enemy_actors(s):
    """Activated enemy AT units, not Moved/Fired, with a US vehicle in LOS and range (AT Guns without target are redrawn,
    10.5.1 note); with MSR 2 only those of the current group."""
    return actors(s)[1]


def us_actors(s):
    return actors(s)[0]


def switch_side(s, prot):
    st = at36(s)
    side = st.get("next") or "US"
    other = "Enemy" if side == "US" else "US"
    if enemy_actors(s) if other == "Enemy" else us_actors(s):
        st["next"] = other


def next_hint(s):
    st = at36(s)
    us, en = actors(s)
    if not us and not en:
        return "No Activated unit left to act: phase next resolves the VOF against vehicles that did not act [10.5.1]"
    side = st.get("next") or ("US" if us else "Enemy")
    if side == "Enemy" and en:
        return "Next: enemy AT action, fof.py vehicle enemy [10.5.1, 8.12]"
    if us:
        return "Next: a US action (vehicle move|fire|cf|spot|done <unit> ...): " + ", ".join(us)
    return "Next: enemy AT action, fof.py vehicle enemy [10.5.1, 8.12]"


def base_type(terrain):
    """'Woods on 1 Hill' -> terrain type of the card itself (card without terrain -> '')."""
    terrain = terrain or ""
    return terrain.split(" on ")[0]


def traffic(s, card_id):
    c = state.card(s, card_id)
    if c.get("staging"):
        return True  # Staging Area cards carry no terrain; vehicles start and move there normally (reading)
    t = c.get("vehicles")
    if t is None:
        cat = s.get("terrain_catalog", {}).get(base_type(c["terrain"]), {})
        t = cat.get("vehicles")
    return t


def do_move(s, n, card_id, area, prot):
    e = s["units"][n]
    from_ = e["card"]
    # vehicle and passengers move together; the board-wide open_fire runs once after the last of them
    commands.move_unit(s, n, card_id, area, exposed=False, prot=prot, open_all=False)
    for p in passengers(s, n):
        prot.append(
            f"{p} rides along on {n} to {card_id} [10.8.1]"
        )  # Exposed follows from move_unit (not within staging, 5.1.3)
        commands.move_unit(s, p, card_id, "open", exposed=True, prot=prot, open_all=False)
    fire.open_fire(s, prot)
    e["in_motion"] = True
    action = at36(s)["action"]
    action["moved"] = True
    action["plan"] = [make_step("vof", label=f"VOF on {card_id} after the move"), make_step("react")] + action["plan"]
    if traffic(s, card_id) == "SLOW":
        action["slow"] = True
        prot.append(f"{card_id} is SLOW: {n} must stop moving here [10.5.2 C, 5.2.4]")
    prot.append(f"{n} moves {from_} to {card_id} (+1 moving target on {card_id}) [10.5.2 C]")


def check_move_vehicle(s, n, card_id):
    e = s["units"][n]
    state.card(s, card_id)
    if not geometry.adjacent(s, e["card"], card_id):
        raise rules.Violation(f"{card_id} is not adjacent to {e['card']} [10.5.2 C]")
    if not chart(e)[3]:
        raise rules.Violation(f"{n} is not mobile [10.8.4]")
    c = state.card(s, card_id)
    if c.get("outside"):
        raise rules.Violation(f"{card_id} is outside the mission boundaries [2.4.1]")
    t = traffic(s, card_id)
    if t is None:
        raise rules.Violation(
            f"Trafficability of {base_type(c['terrain'])} not recorded (vehicle symbol on the card: normal, SLOW or NO); "
            f'fof.py vehicle traffic "{base_type(c["terrain"])}" normal|slow|no [5.2.4, E76]'
        )
    if t is False:
        raise rules.Violation(
            f"{card_id} ({c['terrain']}) has trafficability NO: vehicles may not enter [10.5.2 C, 5.2.4]"
        )
    vehicles = [m for m in state.units_on(s, card_id, e["side"]) if is_vehicle(s["units"][m])]
    if len(vehicles) >= 4:
        raise rules.Violation(f"{card_id} already has 4 vehicles of this side [5.1.5 p.32]")


def require_open(s):
    """after leave_3_6 queued the end-of-phase VOF (end) no further action of either side may start."""
    if at36(s).get("end"):
        raise rules.Violation(
            "The phase is ending (VOF against vehicles that did not act): no further action, phase next [10.5.1]"
        )


def start_action(s, n):
    require_phase(s)
    lock(s)
    require_open(s)
    st = at36(s)
    e = state.unit(s, n)
    if e["side"] != "US":
        raise rules.Violation("Only friendly units; enemy actions with fof.py vehicle enemy")
    if st.get("action") and st["action"]["unit"] != n:
        raise rules.Violation(f"{st['action']['unit']} is still acting: finish it first (vehicle done)")
    if not activated(e) or moved_fired(e):
        raise rules.Violation(
            f"{n} is not Activated for AT Combat & Vehicle Movement (4.2.1i) or already Moved/Fired [10.4]"
        )
    g = current_group(s)
    if g is not None and action_group(e) > g and not st.get("action"):
        raise rules.Violation(
            f"{n} belongs to group {action_group(e)}; first all units of group {g} act (1 Tanks, 2 Jeeps, 3 AT Guns/AT infantry) [MSR 2]"
        )
    if not st.get("action"):
        if (st.get("next") == "Enemy") and enemy_actors(s):
            raise rules.Violation("It is the enemy's turn to act: fof.py vehicle enemy [10.5.1]")
        st["action"] = {"unit": n, "plan": [], "moved": False}
        if is_vehicle(e):
            st["action"]["plan"].append(make_step("vof", label=f"VOF on {e['card']} before the action"))
        st["next"] = "US"
    return st, e


def cmd_vehicle(s, args):
    """vehicle [status] | move <v> <card> [--area=] | fire <unit> <target> | cf <v> --unit=<target> --success=yes|no
    [--critical=yes] | spot <v> --target=<card> --success=yes|no | done <unit> | enemy [--unit=] [--target=] | target <R#> |
    react <unit> <target> | traffic <terrain type> normal|slow|no"""
    if not args or args[0] == "status":
        return vehicle_status(s)
    sub, rest = args[0], args[1:]
    o = options.parse_opts(rest)
    rest = [x for x in rest if not x.startswith("--")]
    handler = VEHICLE_SUBCOMMANDS.get(sub)
    if handler is None:
        raise rules.Violation(cmd_vehicle.__doc__)
    prot = handler(s, rest, o)
    if prot is not None:  # status and traffic save or print on their own
        return finish(s, prot)


def text_opt(o, key, usage):
    """Option that needs a value: a bare --flag (stored as True) is a Violation, not a name lookup."""
    v = o.get(key)
    if v is True:
        raise rules.Violation(f"{key} needs a value: {usage}")
    return v


def vehicle_status(s):
    st = at36(s)
    lines = [f"AT Combat & Vehicle Movement (3.6), phase {s['phase']}"]
    for n, e in s["units"].items():
        if is_vehicle(e) or (activated(e) or moved_fired(e)):
            lines.append(
                f"- {n} ({e.get('vehicle') or weapon(e)}) on {e['card']}: "
                + ", ".join(x for x in e["status"])
                + (f", ammo {shots_left(e)}" if weapon(e) else "")
            )
    if st["queue"]:
        lines.append("Open draw: " + describe(s, st["queue"][0]))
    elif st.get("choice"):
        lines.append("Open target choice: " + describe(s, st["choice"]))
    elif window_live(s):
        lines.append("Open: " + window_text(s))
    lines.append(next_hint(s))
    print("\n".join(lines))


def vehicle_traffic(s, rest, o):
    """vehicle traffic <terrain type> normal|slow|no: record the vehicle symbol of a terrain type (5.2.4, E76)."""
    rules.need(rest, 2, "vehicle traffic <terrain type> normal|slow|no")
    type_, val = rest[0], rest[1].lower()
    if val not in TRAFFIC:
        raise rules.Violation("normal | slow | no")
    s.setdefault("terrain_catalog", {}).setdefault(type_, {})["vehicles"] = TRAFFIC[val]
    for c in s["cards"].values():
        if base_type(c.get("terrain", "")) == type_:
            c["vehicles"] = TRAFFIC[val]
    state.save_state(s, f"Trafficability {type_}: {val} (vehicle symbol on the card) [5.2.4, E76]", "5.2.4 p.36")
    print(f"Trafficability {type_}: {val}")


def vehicle_move(s, rest, o):
    """vehicle move <vehicle> <card>: Move action to an adjacent card (10.5.2 C)."""
    rules.need(rest, 2, "vehicle move <vehicle> <card>")
    n, card_id = rest[0], rest[1]
    prot = []
    st, e = start_action(s, n)
    if not is_vehicle(e):
        raise rules.Violation("Activated AT-capable infantry and AT guns can only AT Fire [10.5.2]")
    action = st["action"]
    if action.get("slow"):
        raise rules.Violation(f"{n} entered a SLOW card and must stop [10.5.2 C]")
    if action.get("fired"):
        raise rules.Violation(f"{n} has fired and may not move any more [10.5.2 D]")
    check_move_vehicle(s, n, card_id)
    if o.get("--area") not in (None, "open"):
        raise rules.Violation("Vehicles do not go under Cover markers; AT Combat uses the card's C&C value [10.6 C]")
    action["plan"].append(make_step("move", card=card_id, area=None))
    prot.append(f"{n}: Move action to {card_id} [10.5.2 C]")
    return prot


def vehicle_fire(s, rest, o):
    """vehicle fire <unit> <target vehicle>: AT Fire action, also Move then Fire (10.5.2 D)."""
    rules.need(rest, 2, "vehicle fire <unit> <target vehicle>")
    n, target = rest[0], rest[1]
    st, e = start_action(s, n)
    target_unit = state.unit(s, target)
    if not is_vehicle(target_unit) or target_unit["side"] == e["side"]:
        raise rules.Violation(f"{target} is not an opposing vehicle")
    if not at_capable(e):
        raise rules.Violation(f"{n} has no AT weapon with shots left")
    action = st["action"]
    if action.get("moved") and chart_line(weapon(e))[4] is None:
        raise rules.Violation(f"{n} has no Move & Fire capability: no AT Fire after moving [10.5.2 D]")
    if line_of_fire(s, e, target_unit["card"]) is None:
        raise rules.Violation(f"{target} not in LOS/range of {n} [10.6 A]")
    action["plan"] += [make_step("fire", target=target), make_step("react"), make_step("end")]
    action["fired"] = True
    return []


def vehicle_done(s, rest, o):
    """vehicle done <unit>: end the open action, or pass without an action (10.5.1)."""
    rules.need(rest, 1, "vehicle done <unit>")
    n = rest[0]
    require_phase(s)
    lock(s)
    st = at36(s)
    e = state.unit(s, n)
    prot = []
    if st.get("action") and st["action"]["unit"] == n:
        end_action(s, prot)
    elif activated(e) and not moved_fired(e):
        if (st.get("next") == "Enemy") and enemy_actors(s):  # passing is an action in the alternation too
            raise rules.Violation("It is the enemy's turn to act: fof.py vehicle enemy [10.5.1]")
        finish_shooter(s, n, prot)
        prot.append(f"{n} takes no action (VOF against it is resolved at the end of the phase) [10.5.1]")
        switch_side(s, prot)
    else:
        raise rules.Violation(f"{n} has no open action")
    return prot


def vehicle_cf(s, rest, o):
    """vehicle cf <vehicle> --unit=<target> --success=yes|no [--critical=yes]: Concentrate Fire action (10.5.2 B)."""
    rules.need(rest, 1, "vehicle cf <vehicle> --unit=<target> --success=yes|no [--critical=yes]")
    n = rest[0]
    st, e = start_action(s, n)
    if not is_vehicle(e) or state.pinned(e):
        raise rules.Violation("Concentrate Fire: an Activated vehicle not under a Pinned marker [10.5.2 B]")
    if not fire.is_firing(e):
        raise rules.Violation(f"{n} exerts no VOF [10.5.2 B]")
    if o.get("--success") not in ("yes", "no"):
        k = 2 + {"Green": -1, "Veteran": 1}.get(comms.experience(e), 0)
        raise rules.Violation(
            f"Concentrate Fire by {n}: draw {k} Action cards, success on Crosshairs (2+: Critical Hit, --critical=yes; Jam no effect); "
            "then --success=yes|no --unit=<target> [10.5.2 B, 7.11]"
        )
    target_unit_name = None
    if o["--success"] == "yes":
        target_unit_name = text_opt(o, "--unit", "--unit=<target enemy>")
        if not target_unit_name:
            raise rules.Violation("Specify --unit=<target enemy>")
        target_card = fire.effective_fire_target(s, n)
        commands.cf_target_check(s, target_card, target_unit_name, e)
    # the effect is a plan step after the VOF before the action (10.5.1 step 1); a vehicle Brewed Up by
    # that VOF leaves no Concentrated Fire marker behind
    st["action"]["plan"] += [
        make_step(
            "cf", success=o["--success"] == "yes", target=target_unit_name, critical=o.get("--critical") == "yes"
        ),
        make_step("react"),
        make_step("end"),
    ]
    return [f"{n}: Concentrate Fire action [10.5.2 B]"]


def vehicle_spot(s, rest, o):
    """vehicle spot <vehicle> --target=<card> --success=yes|no: Spot action (10.5.2 E, 8.5)."""
    rules.need(rest, 1, "vehicle spot <vehicle> --target=<card> --success=yes|no")
    n = rest[0]
    st, e = start_action(s, n)
    if not is_vehicle(e) or state.pinned(e):
        raise rules.Violation("Spot: an Activated vehicle not under a Pinned marker [10.5.2 E]")
    card_id = text_opt(o, "--target", "--target=<card>")
    if not card_id:
        raise rules.Violation("--target=<card with Unspotted enemies>")
    hidden = commands.unspotted_enemies(s, card_id)
    if not hidden:
        raise rules.Violation(f"No Unspotted enemy on {card_id}")
    # [RULE 8.5, 5.4 p.38]: the same LOS test as the infantry Spot (4.2.4a); smoke/Incoming on the vehicle's card
    # blocks LOS out of it
    if state.card(s, e["card"]).get("staging"):
        raise rules.Violation("No spotting from the Staging Area [8.5 Note]")
    ok, reason = geometry.los(
        s, e["card"], card_id, ha=geometry.height_bonus(s, e), hb=geometry.card_height_bonus(s, card_id, "Enemy")
    )
    if not ok:
        raise rules.Violation(f"No LOS from {e['card']} to {card_id}: {reason} [8.5, 5.4]")
    if o.get("--success") not in ("yes", "no"):
        mods = comms.spot_modifiers(s, e, card_id)
        k = max(1, 2 + sum(m for _, m in mods))
        raise rules.Violation(
            f"Spot by {n}: draw {k} Action cards ({', '.join(f'{t} {m:+d}' for t, m in mods)}), success on Crosshairs; then --success=yes|no [10.5.2 E, 8.5]"
        )
    # the Spot result is a plan step after the VOF before the action (10.5.1 step 1)
    st["action"]["plan"] += [
        make_step("spot", success=o["--success"] == "yes", card=card_id),
        make_step("react"),
        make_step("end"),
    ]
    return [f"{n}: Spot action on {card_id} [10.5.2 E]"]


def vehicle_enemy(s, rest, o):
    """vehicle enemy [--unit=] [--target=]: AT Fire of an Activated enemy AT unit (10.5.1, 8.12, CSR 7)."""
    require_phase(s)
    lock(s)
    require_open(s)
    st = at36(s)
    if st.get("action"):
        raise rules.Violation(f"{st['action']['unit']} is still acting")
    actors = enemy_actors(s)
    if not actors:
        raise rules.Violation("No Activated enemy AT unit with a US vehicle in LOS and range")
    if st.get("next") == "US" and us_actors(s):  # the sides alternate (10.5.1), as in start_action
        raise rules.Violation("It is the US side's turn to act (vehicle move|fire|cf|spot|done <unit>) [10.5.1]")
    n = text_opt(o, "--unit", "--unit=<enemy unit>")
    if n and n not in actors and s["units"].get(n, {}).get("side") == "US":
        # --unit=<US unit> is the target of a tank's Concentrate Fire, not the acting enemy
        o = {**o, "--target": o.get("--target") or n}
        n = None
    if not n:
        if len(actors) > 1:
            raise rules.Violation(
                f"Which enemy acts: R# column {len(actors)}: "
                + ", ".join(f"{i}={a}" for i, a in enumerate(actors, 1))
                + "; then --unit=<name> [10.5.1 note]"
            )
        n = actors[0]
    if n not in actors:
        raise rules.Violation(f"{n} cannot act now; eligible: {', '.join(actors)}")
    if is_vehicle(s["units"][n]) and tank_priorities(s):
        return enemy_tank_action(s, st, n, o)
    targets = vehicle_targets(s, n)
    t = text_opt(o, "--target", "--target=<vehicle>")
    if not t:
        if len(targets) > 1:
            raise rules.Violation(
                f"Target of {n} randomly, R# column {len(targets)}: "
                + ", ".join(f"{i}={x}" for i, x in enumerate(targets, 1))
                + "; then --target=<vehicle> [CSR 7]"
            )
        t = targets[0]
    if t not in targets:
        raise rules.Violation(f"{t} not in LOS/range of {n}")
    prot = []
    queue_at(s, n, t, prot, "action")
    st["next"] = "Enemy"  # the enemy acted; hand over like end_action
    switch_side(s, prot)
    return prot


def vehicle_target(s, rest, o):
    """vehicle target <R#>: the randomly drawn target of an enemy Quick Shot (CSR 7)."""
    require_phase(s)
    contact.mine_lock(s)
    rules.need(rest, 1, "vehicle target <R#>")
    st = at36(s)
    if st["queue"]:
        raise rules.Violation("First resolve the open AT draw: " + describe(s, st["queue"][0]))
    prot = []
    purge(s, prot)  # a choice whose targets are gone lapses (saved below) instead of blocking the phase
    w = st.get("choice")
    if not w:
        if prot:
            return prot
        raise rules.Violation("No target choice open")
    i = rules.int_value(rest[0], "vehicle target <R#>")
    if not 1 <= i <= len(w["objectives"]):
        raise rules.Violation(f"R# {i} is not in the choice list (1-{len(w['objectives'])}): " + describe(s, w))
    t = w["objectives"][i - 1]
    if t not in vehicle_targets(s, w["shooter"]):
        raise rules.Violation(f"{t} is no longer a target of {w['shooter']} (gone or out of LOS/range) [10.6 A]")
    st.pop("choice")
    queue_at(s, w["shooter"], t, prot, w.get("type_after", "quick"), reaction=w.get("reaction", False))
    return prot


def vehicle_react(s, rest, o):
    """vehicle react <unit> <target vehicle> | vehicle react pass: Reaction Fire of a US AT-capable unit (10.5.4), only
    while the Reaction Fire window of a vehicle action is open (V7)."""
    usage = "vehicle react <unit> <target vehicle> | vehicle react pass"
    require_phase(s)
    rules.need(rest, 1, usage)
    require_open(s)
    contact.mine_lock(s)
    st = at36(s)
    if st["queue"]:
        raise rules.Violation("First resolve the open AT draw: " + describe(s, st["queue"][0]))
    if rest[0].lower() not in ("pass", "none"):
        rules.need(rest, 2, usage)
    w = window_live(s)
    if not w:
        raise rules.Violation(
            "No Reaction Fire window is open: US units react only when an opposing vehicle acts in their LOS and range [10.5.4]"
        )
    prot = []
    if rest and rest[0].lower() in ("pass", "none"):
        prot.append(f"No (further) Reaction Fire at {w['target']} by {', '.join(w['shooters'])} [10.5.4]")
        st.pop("reaction_open")
        return prot
    n, t = rest[0], rest[1]
    state.unit(s, n)
    state.unit(s, t)
    if t != w["target"] or n not in w["shooters"]:
        raise rules.Violation(f"{n} cannot Reaction Fire at {t} now; " + window_text(s))
    w["shooters"].remove(n)
    if not w["shooters"]:
        st.pop("reaction_open")
    queue_at(s, n, t, prot, "reaction")
    return prot


# ---- enemy tanks with a priority list (Naktong CSR 9 p.14, M1 MSR 3 p.19)
AT_TEAM_WEAPONS = ("M1A1 Bazooka", "M20 Bazooka", "57mm RCL", "75mm RCL")


def tank_priorities(s):
    """the mission's enemy tank priority list (special_rules.tank_priorities), or None."""
    return (s.get("special_rules") or {}).get("tank_priorities")


def _cc_low(c):
    """C&C value used to compare cards for a tank (the lower value of a two-value card, open reading U38)."""
    return c["cc2"] if c.get("cc2") is not None else c.get("cc", 0)


def tank_cf_targets(s, n, pred):
    """US units satisfying pred on the card the tank's VOF lies on (priority 2/4 'under VOF')."""
    e = s["units"][n]
    if state.pinned(e) or not fire.is_firing(e):
        return []
    target_card = fire.effective_fire_target(s, n)
    return [m for m in state.units_on(s, target_card, "US") if pred(s["units"][m])]


def tank_better_cards(s, n):
    """Priority 3: the closest cards (vehicle moves, SLOW cards stop) with a better C&C value than the tank's card;
    face-down cards count as unknown. Returns (distance, {card: path})."""
    e = s["units"][n]
    start = e["card"]
    here = _cc_low(state.card(s, start))
    frontier, seen, best = [(start, [])], {start}, {}
    unknown = set()
    dist = 0
    while frontier and not best:
        dist += 1
        nxt = []
        for k, path in frontier:
            if path and traffic(s, k) == "SLOW":
                continue  # a SLOW card ends the move [10.5.2 C, 5.2.4]
            for k2, c2 in s["cards"].items():
                if k2 in seen or not geometry.adjacent(s, k, k2) or c2.get("staging") or geometry.face_down(c2):
                    continue
                if c2.get("outside"):
                    continue  # outside the mission boundaries, as for US vehicles
                t = traffic(s, k2)
                if t is None:
                    unknown.add(base_type(c2.get("terrain")) or k2)
                    continue
                if t is False:
                    continue
                if len([m for m in state.units_on(s, k2, "Enemy") if is_vehicle(s["units"][m])]) >= 4:
                    continue
                seen.add(k2)
                nxt.append((k2, path + [k2]))
                if _cc_low(c2) > here:
                    best[k2] = path + [k2]
        frontier = nxt
    if unknown:  # no silent detour around a card whose vehicle symbol is not recorded
        raise rules.Violation(
            f"Trafficability not recorded for {', '.join(sorted(unknown))}: fof.py vehicle traffic <terrain type> "
            "normal|slow|no, then repeat [5.2.4, E76]"
        )
    return dist, best


def enemy_tank_action(s, st, n, o):
    """[Naktong M1 MSR 3 p.19, BGG 3529491]: the first priority that applies. 1 AT Fire at a visible US vehicle;
    2 Concentrate Fire on a US Bazooka/RCL team under its VOF; 3 move to the closest card with a better C&C value (stop
    and Move & Fire as soon as priority 1 applies); 4 Concentrate Fire on a US LMG/HMG under its VOF; else no action."""
    e = s["units"][n]
    prot = []
    targets = vehicle_targets(s, n)
    if targets:
        t = text_opt(o, "--target", "--target=<vehicle>")
        if not t:
            if len(targets) > 1:
                raise rules.Violation(
                    f"{n} priority 1, AT Fire: target randomly, R# column {len(targets)}: "
                    + ", ".join(f"{i}={x}" for i, x in enumerate(targets, 1))
                    + "; then --target=<vehicle> [MSR 3, CSR 9]"
                )
            t = targets[0]
        if t not in targets:
            raise rules.Violation(f"{t} not in LOS/range of {n}")
        st["action"] = {
            "unit": n,
            "plan": [make_step("vof", label=f"VOF on {e['card']} before the action")],
            "moved": False,
        }
        st["action"]["plan"] += [make_step("fire", target=t), make_step("react"), make_step("end")]
        st["next"] = "Enemy"  # acting side; end_action hands over to the US side
        return [f"{n}: priority 1, AT Fire at {t} [MSR 3]"]
    for prio, pred, what in (
        (2, lambda x: x.get("at_weapon") in AT_TEAM_WEAPONS, "Bazooka/RCL team"),
        (4, lambda x: (combat.ammo(x) or {}).get("type") == "MG", "LMG/HMG"),
    ):
        if prio == 4 and tank_better_cards(s, n)[1]:
            break  # priority 3 comes first
        cands = tank_cf_targets(s, n, pred)
        if not cands:
            continue
        if o.get("--success") not in ("yes", "no"):
            k = 2 + {"Green": -1, "Veteran": 1}.get(comms.experience(e), 0)
            raise rules.Violation(
                f"{n} priority {prio}: Concentrate Fire on a {what} under its VOF ({', '.join(cands)}): draw {k} Action cards, "
                "Crosshairs = success (2+: Critical Hit); target randomly if several; then --success=yes|no [--target=<unit>] "
                "[--critical=yes] [MSR 3, 10.5.2 B]"
            )
        target_unit_name = text_opt(o, "--target", "--target=<unit>") or (cands[0] if len(cands) == 1 else None)
        if o["--success"] == "yes" and target_unit_name not in cands:
            raise rules.Violation(f"--target=<one of {', '.join(cands)}>")
        st["action"] = {
            "unit": n,
            "plan": [make_step("vof", label=f"VOF on {e['card']} before the action")],
            "moved": False,
        }
        st["action"]["plan"] += [
            make_step(
                "cf", success=o["--success"] == "yes", target=target_unit_name, critical=o.get("--critical") == "yes"
            ),
            make_step("react"),
            make_step("end"),
        ]
        st["next"] = "Enemy"  # acting side; end_action hands over to the US side
        return [f"{n}: priority {prio}, Concentrate Fire action [MSR 3, 10.5.2 B]"]
    dist, best = tank_better_cards(s, n)
    if best:
        k = text_opt(o, "--target", "--target=<card>")
        if not k:
            if len(best) > 1:
                cards = sorted(best)
                raise rules.Violation(
                    f"{n} priority 3: closest cards with a better C&C value ({dist} card(s) away), choose randomly, R# column "
                    f"{len(cards)}: "
                    + ", ".join(f"{i}={x}" for i, x in enumerate(cards, 1))
                    + "; then --target=<card> [MSR 3]"
                )
            k = next(iter(best))
        if k not in best:
            raise rules.Violation(f"{k} is not one of the closest better cards: {', '.join(sorted(best))}")
        path = best[k]
        st["action"] = {
            "unit": n,
            "plan": [make_step("vof", label=f"VOF on {e['card']} before the action")],
            "moved": False,
        }
        st["action"]["plan"] += [make_step("tankmove", card=x) for x in path] + [make_step("end")]
        st["next"] = "Enemy"  # acting side; end_action hands over to the US side
        return [
            f"{n}: priority 3, moves toward {k} (route {', '.join(path)}; stops for AT Fire as soon as a US vehicle is in LOS) [MSR 3]"
        ]
    finish_shooter(s, n, prot)
    e["has_acted"] = True
    prot.append(f"{n}: no priority applies, stays where it is (BGG 3553563) [MSR 3]")
    st["next"] = "Enemy"  # the enemy acted (no action); hand over like end_action
    switch_side(s, prot)
    return prot


def tank_move_step(s, n, step, action, prot):
    """one card of a priority-3 move; afterwards the VOF on the new card and Reaction Fire (via do_move), then
    Move & Fire if a US vehicle came into LOS (MSR 3 note)."""
    if action.get("slow"):
        action["plan"] = [x for x in action["plan"] if _legacy_step(x)["kind"] != "tankmove"]
        return
    do_move(s, n, step["card"], None, prot)
    if n not in s["units"]:
        return
    targets = vehicle_targets(s, n)
    if targets and chart_line(weapon(s["units"][n]))[4] is None:
        # no Move & Fire on the chart (SU-76M): no AT Fire after moving, as for US vehicles (10.5.2 D)
        prot.append(
            f"{n}: US vehicle in LOS, but no Move & Fire capability: no AT Fire after moving, it moves on [10.5.2 D]"
        )
        return
    if targets:
        rest = [x for x in action["plan"] if _legacy_step(x)["kind"] not in ("tankmove", "end")]
        if len(targets) == 1:
            action["plan"] = rest + [make_step("fire", target=targets[0]), make_step("react"), make_step("end")]
        else:
            # the target choice is a plan step after the VOF on the new card and the Reaction Fire,
            # like the single-target fire step; it queues an AT Fire action, not a Quick Shot
            action["plan"] = rest + [make_step("choose", objectives=targets), make_step("react"), make_step("end")]
        prot.append(f"{n} stops: US vehicle in LOS, Move & Fire [MSR 3 note]")


VEHICLE_SUBCOMMANDS = {
    "traffic": vehicle_traffic,
    "move": vehicle_move,
    "fire": vehicle_fire,
    "done": vehicle_done,
    "cf": vehicle_cf,
    "spot": vehicle_spot,
    "enemy": vehicle_enemy,
    "target": vehicle_target,
    "react": vehicle_react,
}


# ---- hooks into the sequence of play


def enter_3_6(s, prot):
    """[Normandy CSR 7] German AT activation; list of Activated units; side to act first (10.5.1)."""
    st = at36(s)
    st.update(queue=[], action=None, attacked=[], end=False)
    us_vehicles = {e["card"] for e in s["units"].values() if is_vehicle(e) and e["side"] == "US"}
    for n, e in s["units"].items():
        if e["side"] != "Enemy" or not at_capable(e):
            continue
        w = weapon(e)
        if w in CSR7_ALWAYS or (w in CSR7_SAME_CARD and e["card"] in us_vehicles):
            if not activated(e):
                e["status"].append(rules.ACTIVATED)
                prot.append(f"{n} ({w}) automatically Activated for AT Combat [CSR 7 p.15]")
    if tank_priorities(s):
        for n, e in s["units"].items():
            if e["side"] == "Enemy" and is_vehicle(e) and not activated(e) and not moved_fired(e):
                e["status"].append(rules.ACTIVATED)
                prot.append(f"{n} automatically Activated for Vehicle Movement & AT Combat [Naktong CSR 9 p.14]")
    for n, e in s["units"].items():
        if e.get("arty_jeep") and passengers(s, n) and not activated(e) and not moved_fired(e):
            e["status"].append(rules.ACTIVATED)
            prot.append(
                f"{n}: {', '.join(passengers(s, n))} on board, automatically Activated for Vehicle Movement "
                "(exception to 10.8.1) [Normandy CSR 1 p.13]"
            )
    st["next"] = "US" if s.get("type") != "defensive" else "Enemy"
    if us_actors(s) or enemy_actors(s):
        prot.append(next_hint(s))
    elif any(is_vehicle(e) for e in s["units"].values()):
        prot.append("No Activated unit; phase next resolves the VOF against vehicles [10.5.1]")


def leave_3_6(s, prot):
    """Before leaving 3.6: no open draw or action; enemies acted; VOF against vehicles that did not act (10.5.1 end);
    Pinned vehicles not attacked lose the marker (10.7 Pinned)."""
    st = at36(s)
    lock(s)
    if st.get("action"):
        raise rules.Violation(f"{st['action']['unit']} is still acting (vehicle done)")
    if enemy_actors(s):
        raise rules.Violation("Activated enemy AT units still have a target: fof.py vehicle enemy [10.5.1]")
    # under MSR 2 an enemy of a later group must not be skipped because a US unit of an earlier group simply
    # never acts: such a US unit acts or passes (vehicle done) first; the ungrouped list is the safety net
    us = us_actors(s)
    if us:
        raise rules.Violation(
            "Activated US units still to act or pass (vehicle move|fire|cf|spot|done <unit>): "
            + ", ".join(us)
            + " [10.5.1]"
        )
    if _enemy_base(s):
        raise rules.Violation("Activated enemy AT units still have a target: fof.py vehicle enemy [10.5.1]")
    if not st.get("end"):
        st["end"] = True
        for n, e in s["units"].items():
            if is_vehicle(e) and not e.get("has_acted"):
                queue_vof(s, n, prot, "End of phase")
        if st["queue"]:
            state.save_state(
                s, "; ".join(prot + ["End of 3.6: VOF against vehicles that did not act [10.5.1]"]), "10.5.1 p.72"
            )
            raise rules.Pending("VOF against vehicles still to resolve: " + describe(s, st["queue"][0]))
    for n, e in s["units"].items():
        if is_vehicle(e) and state.pinned(e) and n not in st["attacked"]:
            e["status"].remove(rules.PINNED)
            prot.append(f"{n}: remove Pinned (not attacked in this phase) [10.7 Pinned]")


def clean_up(s, prot):
    """3.8: remove Activated and Moved/Fired markers (10.4); Burning Wrecks become Wrecks (3.8 step 9)."""
    for n, e in s["units"].items():
        for m in (rules.ACTIVATED, rules.MOVED_FIRED):
            if m in e["status"]:
                e["status"].remove(m)
                prot.append(f"{n}: remove {m} marker [10.4]")
        e.pop("has_acted", None)
        e.pop("in_motion", None)
    for card_id, c in s["cards"].items():
        for x in list(c.get("external", [])):
            if x.get("wreck"):
                val = (s.get("vehicle_values") or {}).get("wreck_cover", 1)
                cid = add_wreck_cover(s, c, val)
                prot.append(
                    f"{card_id}: flip the Burning Wreck to its Wreck side (cover marker {cid} +{val}) [3.8 step 9, 10.7]"
                )
    s.pop("at36", None)


def order_4_2_1i(s, ctx):
    """[RULE 4.2.1i p.22, 10.4 p.72] Activate a vehicle or an unpinned AT-capable infantry unit."""
    recipient = ctx.recipient
    if not (is_vehicle(recipient) or (at_capable(recipient) and not state.pinned(recipient))):
        raise rules.Violation(
            f"{ctx.target_name}: only a vehicle or an unpinned AT-capable infantry unit [RULE 4.2.1i p.22]"
        )
    if activated(recipient):
        raise rules.Violation(f"{ctx.target_name} is already Activated")
    if crewless_jeep(recipient) and not passengers(s, ctx.target_name):
        raise rules.Violation(f"{ctx.target_name} has no crew and nobody on board to drive it [10.8.1, 10.8.8]")
    recipient["status"].append(rules.ACTIVATED)
    ctx.prot.append(f"{ctx.target_name}: place the Activated marker [4.2.1i, 10.4]")


VEHICLE_ORDERS = {"4.2.2h", "4.2.3a", "4.2.4k", "4.2.4l", "4.2.1i"}


def order_check(s, hq_name, target_name, action_id):
    """[RULE 10.1.1/10.1.2 p.70/71] vehicle orders and vehicle chains of command. Returns True if communication is settled."""
    hq, recipient = state.unit(s, hq_name), state.unit(s, target_name)
    if is_vehicle(hq) and state.is_hq(hq) and not is_vehicle(recipient):
        raise rules.Violation(
            f"{hq_name} is a vehicle PLT HQ: it only orders the vehicles of its platoon [10.1.1 p.70]"
        )
    if not is_vehicle(recipient):
        return False
    if crewless_jeep(recipient) and not recipient.get("platoon") and hq_name not in ("GI", target_name):
        # [RULE 10.8.1 p.76] embarked HQ/Staff activate themselves; anyone else only in Visual-Verbal communication
        if hq_name in passengers(s, target_name) and state.is_hq(hq):
            return True
        comms.visual_verbal(s, hq_name, target_name, action_id)
        return True
    action_id = action_id or "4.2.1a"
    if (
        action_id not in VEHICLE_ORDERS
        and not (action_id == "4.2.1a" and state.is_hq(recipient))
        and not (action_id.startswith("4.2.1") and hq_name == target_name)
    ):
        raise rules.Violation(
            "Vehicles only take Load/Unload/Embark, Rally, Cease/Shift Fire and Activate for AT Combat & Vehicle Movement in the Command Phase [10.1.2 p.71]"
        )
    if hq_name in (target_name, "GI"):
        return True
    plt = recipient.get("platoon")
    plt_hq = [m for m, x in s["units"].items() if x.get("platoon") == plt and is_vehicle(x) and state.is_hq(x)]
    if plt and plt_hq:
        if hq_name in plt_hq:
            return True  # [10.1.1] the vehicle PLT HQ is always in communication with its platoon
        if hq.get("level") == "CO" and hq["type"] == "HQ":
            ok = comms.radios_of(hq, "SCR300", "BN TAC") or not state.radio_active(s)
            if not ok:
                raise rules.Violation(
                    f"{hq_name} carries no SCR300 BN TAC: no contact with the tank platoon [10.1.1 p.70]"
                )
            return True
        raise rules.Violation(f"{target_name} takes orders only from its vehicle PLT HQ and the CO HQ [10.1.2 p.71]")
    return False
