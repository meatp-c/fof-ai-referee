"""Vehicles and AT Combat (Series Rules 10.0-10.8, 3.6, 4.2.1i, 7.8, 8.12; Normandy CSR 7, MSR 2). L187.

The AT Combat & Vehicle Movement Phase (3.6) runs as a small queue. Every attack against a vehicle waits as one entry
until the player has drawn its card:
- VOF against a vehicle (10.5.3), AT Fire (10.6), Reaction Fire (10.5.4), Quick Shot (10.6.1): fof.py at <AT number>
  (or at :<card number> with the action card archive)
- the Grenade attempt of a G!-rated firer first (10.6.2): fof.py at grenade yes|no
A vehicle action is a plan of steps (VOF on its card, the action, VOF on the new card, Reaction Fire) that advances as
soon as the queue is empty (10.5.1)."""

from . import briefing, combat, commands, comms, contact, enemy, fire, geometry, options, rules, state

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
}
RANGE_LETTER = ("P", "C", "L", "V")
# [Anti-Tank Combat Resolution and Modifiers, VOF against a vehicle 10.5.3] AT modifier by VOF type
VOF_AT_MOD = {"Pinned": 4, "S": 3, "A": 2, "H": 1, "Sniper": 1, "Incoming": -1, "Mines": -2, "G": -2, "AirStrike": -3}
QUICK_SHOT_SUMS = {-4, -2, 0, 2, 4}  # [RULE 10.6.1 p.73]
AMBUSH_WEAPONS = {"M1A1 Bazooka", "M20 Bazooka", "Panzerfaust", "Panzerschreck", "75mm AT Gun", "88mm FLAK"}
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
    return bool(e.get("fahrzeug"))


def vehicle_types():
    """Chart keys that are vehicles (target type V), for messages."""
    return [k for k, v in CHART.items() if v[6] == "V"]


def chart(e):
    """Chart line of a vehicle; an unknown 'fahrzeug' is a Violation naming the valid keys, not a KeyError (review M38)."""
    w = e.get("fahrzeug")
    if w not in CHART:
        raise rules.Violation(f"Unknown vehicle type '{w}'; valid types: {', '.join(vehicle_types())}")
    return CHART[w]


def chart_line(w):
    """Chart line of an AT weapon key (vehicle type or 'at_waffe'); unknown keys are a Violation (review M38)."""
    if w not in CHART:
        raise rules.Violation(f"Unknown AT weapon '{w}'; valid chart keys: {', '.join(CHART)}")
    return CHART[w]


def weapon(e):
    """AT weapon of a unit (chart line) or None."""
    if e.get("fahrzeug"):
        return e["fahrzeug"] if chart(e)[0][0] is not None else None
    if state.is_lat(e) or e["typ"] == "Casualty":
        return None
    if e.get("at_waffe"):
        return e["at_waffe"]
    if e.get("panzerfaust", 0) > 0:
        return "Panzerfaust"  # [Normandy M6 p.40] each FJ squad has one Panzerfaust shot
    if e.get("rifle_grenades", 0) > 0 or (e["seite"] == "US" and "Rifle Grenade" in (e.get("assets") or [])):
        return "Rifle Grenade"
    return None


def shots_left(e):
    w = weapon(e)
    if not w:
        return 0
    if w == "Panzerfaust" and not e.get("at_waffe"):
        return e.get("panzerfaust", 0)
    if w == "Rifle Grenade" and not e.get("at_waffe"):
        return e.get("rifle_grenades", 0) or (e.get("assets") or []).count("Rifle Grenade")
    m = combat.ammo(e)
    return m["punkte"] if m else 1


def at_capable(e):
    """AT-capable now (10.5.4, glossary 1.2.6): an AT weapon with shots left, not a Litter/Paralyzed Team."""
    return bool(weapon(e)) and shots_left(e) > 0 and e["typ"] not in ("Paralyzed Team", "Litter Team")


def use_shot(s, n, e, prot):
    w = weapon(e)
    if w == "Panzerfaust" and not e.get("at_waffe"):
        e["panzerfaust"] -= 1
        prot.append(f"{n}: Panzerfaust fired, {e['panzerfaust']} left [Normandy M6 p.40, CSR 7]")
    elif w == "Rifle Grenade" and not e.get("at_waffe"):
        if e.get("rifle_grenades", 0) > 0:
            e["rifle_grenades"] -= 1
        else:
            e["assets"].remove("Rifle Grenade")
        prot.append(f"{n}: Rifle Grenade used [8.9, 10.6.2]")
    else:
        combat.ammo_use(s, n, e, 1, "AT Fire", prot)  # [Charts: each AT Fire attempt uses 1 ammo]


def at36(s):
    return s.setdefault(
        "at36", {"queue": [], "aktion": None, "angegriffen": [], "naechste": None, "ende": False, "bericht": []}
    )


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
    if geometry.edge(c, geometry.direction(s, target_card, from_card)) != "weiss":
        return c["cc"], f"C&C {c['terrain']} (higher value, across a dark edge)"
    return c["cc2"], f"C&C {c['terrain']} (lower value, across a white edge)"


def ambush(s, target_name, shooter):
    """[RULE 10.8.3 p.76] susceptible vehicle (mission), rocket launcher or AT gun at P/C, no Good Order friendly infantry
    on the vehicle's card."""
    z = s["einheiten"][target_name]
    if not z.get("ambush") or weapon(shooter) not in AMBUSH_WEAPONS:
        return False
    if geometry.distance(s, shooter["karte"], z["karte"]) > 1:
        return False
    infantry = [
        m
        for m in state.units_on(s, z["karte"], z["seite"])
        if not is_vehicle(s["einheiten"][m]) and state.good_order(s["einheiten"][m])
    ]
    return not infantry


def gunnery(w, dist):
    if dist > 3:
        return None
    return chart_line(w)[0][dist]


def line_of_fire(s, shooter, target_card):
    """LOS and range of an AT shot (10.6 A); AT Fire does not need a PDF (10.5.2 A)."""
    w = weapon(shooter)
    d = geometry.distance(s, shooter["karte"], target_card)
    if not w or gunnery(w, d) is None:
        return None
    if d:
        ok, _ = geometry.los(
            s,
            shooter["karte"],
            target_card,
            ha=geometry.height_bonus(s, shooter),
            hb=geometry.card_height_bonus(s, target_card, geometry.opponent_of(shooter)),
        )
        if not ok:
            return None
    return d


def at_rows(s, shooter_name, target_name):
    """[RULE 10.6 A-E p.73] net AT modifier of an AT Fire attack as rows (label, value)."""
    a, z = s["einheiten"][shooter_name], s["einheiten"][target_name]
    w = weapon(a)
    d = line_of_fire(s, a, z["karte"])
    if d is None:  # review M29: no TypeError on RANGE_LETTER[None]
        raise rules.Violation(f"{target_name} not in LOS/range of {shooter_name} [10.6 A]")
    rows = [(f"Gunnery {w} at range {RANGE_LETTER[d]}", gunnery(w, d))]
    rows.append((f"Defensive value {z['fahrzeug']}", chart(z)[1]))
    v, label = card_cc(s, z["karte"], a["karte"])
    rows.append((label, v))
    if a.get("in_bewegung") and chart_line(w)[4] is not None and is_vehicle(a):
        rows.append(("Move & Fire", chart_line(w)[4]))
    if state.pinned(z):
        rows.append(("Target is Pinned", -1))
    if z.get("in_bewegung"):
        rows.append(("Target is moving", 1))
    if state.pinned(a):
        rows.append(("Firer is Pinned", 1))
    if ambush(s, target_name, a):
        rows.append(("Tank Ambush [10.8.3]", -4 if state.pinned(z) else -3))
    return rows


def grenade_cards(s, shooter_name, target_name):
    """[RULE 10.6.2 p.73] G!-rated firer: first a Grenade attempt, two cards adjusted for Experience; Ambush +1 (+1 more on a
    Pinned target, 10.8.3)."""
    a, z = s["einheiten"][shooter_name], s["einheiten"][target_name]
    n = 2 + {"Green": -1, "Veteran": 1}.get(comms.experience(a), 0)
    if ambush(s, target_name, a):
        n += 2 if state.pinned(z) else 1
    return max(1, n)


def vof_on_vehicle(s, n):
    """[RULE 10.5.3 p.72] strongest VOF on the vehicle's card from non-AT-capable units and S-rated AT-capable units
    (VOF of A/H-rated AT-capable units is ignored); external VOF (Incoming, Mines on a mine hit) counts as well."""
    e = s["einheiten"][n]
    best = None
    for typ, wert, src, side, from_card in fire.vof_entries(s, e["karte"]):
        if side not in (None, e["seite"]):
            continue
        if typ == "Mines" and not e.get("mine_hit"):
            continue
        su = s["einheiten"].get(src)
        # L214 [RULE 10.5.3 p.72, 6.2] no exception for friendly VOF: own Incoming or own small arms on the card hit the
        # vehicle too (friendly fire); Point Blank VOF only hits the opposing side (side filter above, 6.2.1b)
        if su is not None and at_capable(su) and su.get("vof_rating") in ("A", "H", "A/S"):
            continue  # ignored: A/H-rated AT-capable units only fire AT Fire / Reaction Fire at vehicles
        if typ not in VOF_AT_MOD:
            continue  # review M37: the AT chart has no Indirect Lay line, so an "Indirect" VOF is ignored (open reading)
        if best is None or wert < best[1]:
            best = (typ, wert, src, from_card)
    if e.get("grenade") and (best is None or VOF_AT_MOD["G"] < VOF_AT_MOD[best[0]]):
        # L205 [RULE 10.5.3 p.72, AT chart 'Grenade -2']: a Grenade VOF placed on the vehicle (e.g. G! mortar) counts too;
        # 'Hand Grenade VOF does not stack': only the strongest VOF (by AT modifier) is applied
        best = ("G", min(e["grenade"]), "Grenade Attack", None)
    return best


def queue_vof(s, n, prot, label):
    b = vof_on_vehicle(s, n)
    if not b:
        return
    e = s["einheiten"][n]
    typ, _wert, src, from_card = b
    rows = [("Gunnery (VOF) 0", 0), (f"Defensive value {e['fahrzeug']}", chart(e)[1])]
    v, lab = card_cc(s, e["karte"], from_card)
    rows.append((lab, v))
    if typ == "Incoming" and state.card(s, e["karte"]).get("burst") is not None:
        rows.append(("Burst symbol", state.card(s, e["karte"])["burst"]))
    if e.get("in_bewegung"):
        rows.append(("Target is moving", 1))
    if state.pinned(e):
        rows.append(("Target is Pinned", -1))
    rows.append((f"VOF {rules.VOF_NAME.get(typ, typ)} ({src})", VOF_AT_MOD[typ]))
    at36(s)["queue"].append(make_item("vof", ziel=n, zeilen=rows, label=label))
    prot.append(f"{label}: VOF {rules.VOF_NAME.get(typ, typ)} from {src} against {n} [10.5.3 p.72]")


def make_item(art, **fields):
    """Queue entry of 3.6 (art: vof, at, wahl). 'reaction' marks the Reaction Fire chain (10.5.4 Exception, 10.6.1) and
    is set once here from the kind or the flag passed along (review M36)."""
    item = {"art": art, "ziel": None, "zeilen": [], "reaction": False}
    item.update(fields)
    item["reaction"] = bool(item["reaction"] or item.get("typ") == "reaction")
    return item


def make_step(kind, **fields):
    """Plan step of a vehicle action (kind: vof, move, react, fire, cf, spot, ende)."""
    step = {"art": kind}
    step.update(fields)
    return step


def _legacy_step(step):
    """Plan steps saved before the review as tuples/lists: ("vof", label), ("move", card, area), ("fire", target), ..."""
    if isinstance(step, dict):
        return step
    kind = step[0]
    if kind == "vof":
        return make_step("vof", label=step[1])
    if kind == "move":
        return make_step("move", karte=step[1], bereich=step[2])
    if kind == "fire":
        return make_step("fire", ziel=step[1])
    return make_step(kind)


def queue_at(s, shooter, target, prot, kind, reaction=False):
    """One AT Fire attack (kind: action, reaction, quick); reaction=True keeps the Reaction Fire chain through Quick Shots."""
    a = s["einheiten"][shooter]
    w = weapon(a)
    item = make_item(
        "at", schuetze=shooter, ziel=target, typ=kind, zeilen=at_rows(s, shooter, target), reaction=reaction
    )
    if chart_line(w)[7]:
        item["g_karten"] = grenade_cards(s, shooter, target)
    at36(s)["queue"].append(item)
    prot.append(
        f"{'Reaction Fire' if kind == 'reaction' else 'Quick Shot' if kind == 'quick' else 'AT Fire'}: {shooter} ({w}) at {target}"
        + (f"; first the Grenade attempt, {item['g_karten']} cards [10.6.2]" if item.get("g_karten") else "")
    )


def reaction_shooters(s, target):
    """[RULE 10.5.4 p.73] opposing AT-capable units not marked Moved/Fired with LOS and range; enemies always fire.
    Unspotted enemies react too (10.5.4 names no Spotted condition; the review's dead 'and False' branch is gone)."""
    z = s["einheiten"][target]
    out = []
    for n, e in s["einheiten"].items():
        if e["seite"] == z["seite"] or not at_capable(e) or moved_fired(e):
            continue
        if e.get("karte") not in s["karten"] or line_of_fire(s, e, z["karte"]) is None:
            continue
        out.append(n)
    return out


def queue_reactions(s, target, prot):
    for n in reaction_shooters(s, target):
        if s["einheiten"][n]["seite"] == "Feind":
            queue_at(s, n, target, prot, "reaction")
        else:
            prot.append(f"{n} may Reaction Fire at {target}: fof.py vehicle react {n} {target} [10.5.4]")


def require_phase(s):
    if s["phase"] != "3.6":
        raise rules.Violation(
            f"Vehicle actions only in the AT Combat & Vehicle Movement Phase 3.6, currently {s['phase']}"
        )


def choice_live(s, w):
    """A pending Quick Shot target choice (review M29) is live while its shooter and at least one listed target can
    still be attacked; a stale one lapses in purge()."""
    return (
        bool(w) and w["schuetze"] in s["einheiten"] and any(t in vehicle_targets(s, w["schuetze"]) for t in w["ziele"])
    )


def lock(s):
    contact.mine_lock(s)
    st = at36(s)
    q = st["queue"]
    if q:
        raise rules.Violation("First resolve the open AT draw: " + describe(s, q[0]))
    if choice_live(s, st.get("wahl")):
        raise rules.Violation("First resolve the open target choice: " + describe(s, st["wahl"]))
    crew = [n for n, e in s["einheiten"].items() if e.get("crew_hit_offen")]
    if crew:
        raise rules.Violation(
            "Crew teams still need their HIT: "
            + ", ".join(f'fof.py hit "{n}" HIT <letters>' for n in crew)
            + " [10.7 Knocked Out]"
        )


def net(item):
    return sum(v for _, v in item.get("zeilen", []))


def describe(s, item):
    rows = "; ".join(f"{t} {v:+d}" for t, v in item.get("zeilen", []))
    if item.get("art") == "wahl" or "ziele" in item:  # a choice saved before the review has no 'art'
        return (
            f"{item['schuetze']} Quick Shot: choose the target randomly, R# column {len(item['ziele'])}: "
            + ", ".join(f"{i}={t}" for i, t in enumerate(item["ziele"], 1))
            + "; then fof.py vehicle target <R#> [CSR 7]"
        )
    if item.get("typ") == "quick_offer":
        return f"{item['schuetze']} may take a Quick Shot at {item['ziel']}: fof.py at again | at stop [10.6.1 p.73]"
    if item.get("g_karten"):
        return (
            f"{item['schuetze']}: Grenade attempt first, draw {item['g_karten']} Action cards, success on the Grenade icon; "
            "then fof.py at grenade yes|no [10.6.2 p.73]"
        )
    head = (
        f"VOF against {item['ziel']}"
        if item["art"] == "vof"
        else f"{item['schuetze']} at {item['ziel']} ({item['typ']})"
    )
    return f"{head}: net AT modifier {net(item):+d} ({rows}); draw an Action card, fof.py at <AT number> [10.6 p.73]"


def add_wreck_cover(s, c, val):
    """[RULE 10.7 p.74] a Wreck cover marker (+val) on card c with the next free id C<i>; returns the id."""
    ids = [cv["id"] for cv in c.get("cover", [])]
    i = 1
    while f"C{i}" in ids:
        i += 1
    c.setdefault("cover", []).append({"id": f"C{i}", "typ": "Wreck", "wert": val, "feld": False, "wrack": True})
    return f"C{i}"


def apply_result(s, target, res, prot):
    """[RULE 10.7 p.74] Brewed Up, Knocked Out, Retreat, Pinned, Missed."""
    z = s["einheiten"][target]
    kid = z["karte"]
    c = state.card(s, kid)
    at36(s)["angegriffen"].append(target)
    crew = chart(z)[2] or 0
    if res == "Brewed Up":
        # review M35: crew steps become Casualties of their own side (keys as in combat.make_casualty)
        key = "casualties" if z["seite"] == "US" else "casualties_feind"
        c[key] = c.get(key, 0) + crew
        if z["seite"] == "US":
            s["us_casualties_gesamt"] = s.get("us_casualties_gesamt", 0) + crew
        smoke = (s.get("fahrzeug_werte") or {}).get("burning_wreck_smoke", 1)
        c.setdefault("extern", []).append({"typ": "Smoke", "wert": smoke, "quelle": "Burning Wreck", "wrack": True})
        combat.remove_from_play(
            s, target, prot, f"Brewed Up: Burning Wreck marker on {kid}, {crew} crew step(s) become Casualties"
        )
        prot.append(f"{kid}: Burning Wreck (smoke +{smoke}, blocks LOS, no cover marker) [10.7 p.74, 5.4]")
    elif res == "Knocked Out":
        val = (s.get("fahrzeug_werte") or {}).get("wreck_cover", 1)
        cid = add_wreck_cover(s, c, val)
        crew_names = []
        for _ in range(crew):
            fn = commands.new_name(s, "Fire Team")
            ft = combat.new_lat(z, "Fire Team", target)
            ft.update(bereich=cid, status=[rules.EXPOSED], crew_hit_offen=True)
            s["einheiten"][fn] = ft
            crew_names.append(fn)
        combat.remove_from_play(s, target, prot, f"Knocked Out: Wreck marker {cid} (cover +{val}) on {kid}")
        if crew_names:
            prot.append(
                f"Crew: {', '.join(crew_names)} under the Wreck {cid}, Exposed; each takes a HIT now: draw a second card per team and "
                + ", ".join(f'fof.py hit "{x}" HIT <letters>' for x in crew_names)
                + " [10.7 p.74]"
            )
    elif res == "Retreat":
        combat.remove_from_play(s, target, prot, "Retreat: the vehicle leaves the map for the rest of the mission")
    elif res == "Pinned":
        if not state.pinned(z):
            z["status"].append(rules.PINNED)
        prot.append(
            f"{target} Pinned (buttoned up): -1 as target, +1 when firing, no Spot or Concentrate Fire [10.7 p.74]"
        )
    else:
        prot.append(f"{target}: Missed")
    if target in s["kommandos"] and target not in s["einheiten"]:
        prot.append(f"{target} was a vehicle PLT HQ: its Command marker leaves the track")


def finish_shooter(s, shooter, prot, keep_open=False):
    a = s["einheiten"].get(shooter)
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
    if not st["queue"]:
        raise rules.Violation("No AT draw open")
    crew = [n for n, e in s["einheiten"].items() if e.get("crew_hit_offen")]
    if crew:
        raise rules.Violation(
            "First the crew HITs: " + ", ".join(f'fof.py hit "{n}" HIT <letters>' for n in crew) + " [10.7]"
        )
    rules.need(args, 1, AT_USAGE)
    item = st["queue"][0]
    prot = []
    handler = AT_SUBCOMMANDS.get(args[0])
    if handler is None:
        handler = at_quick_offer if item.get("typ") == "quick_offer" else at_draw
    handler(s, st, item, args, prot)
    return finish(s, prot)


def at_grenade(s, st, item, args, prot):
    """at grenade yes|no: the Grenade attempt of a G!-rated firer before its AT draw (10.6.2)."""
    if not item.get("g_karten"):
        raise rules.Violation("This attack needs no Grenade attempt")
    a = s["einheiten"][item["schuetze"]]
    if len(args) < 2 or args[1] not in ("ja", "nein"):
        raise rules.Violation("at grenade yes|no")
    if args[1] == "nein":
        use_shot(s, item["schuetze"], a, prot)
        st["queue"].pop(0)
        prot.append(f"{item['schuetze']}: Grenade attempt failed, no AT draw, no Grenade Miss marker [10.6.2 p.73]")
        finish_shooter(s, item["schuetze"], prot)
    else:
        item.pop("g_karten")
        prot.append(f"{item['schuetze']}: Grenade attempt successful, now the AT draw [10.6.2 p.73]")


def at_stop(s, st, item, args, prot):
    """at stop: decline the offered Quick Shot (10.6.1)."""
    if item.get("typ") != "quick_offer":
        raise rules.Violation("Nothing to stop")
    st["queue"].pop(0)
    # review M36 [RULE 10.6.1 p.73]: a Quick Shot draw obtained as Reaction Fire leaves the unit without Moved/Fired
    # "even if the player chooses not to continue firing"; the flag travels through the whole chain, so the first
    # and every later offer behave alike. A chain that ends with a non-Quick-Shot draw flips to Moved/Fired (10.5.4).
    finish_shooter(s, item["schuetze"], prot, keep_open=item.get("reaction", False))
    prot.append(f"{item['schuetze']}: no further Quick Shot")


def at_quick_offer(s, st, item, args, prot):
    """at again: take the offered Quick Shot (10.6.1)."""
    if args[0] not in ("again", "nochmal"):
        raise rules.Violation(f"{item['schuetze']} may take a Quick Shot: fof.py at again | at stop [10.6.1]")
    st["queue"].pop(0)
    if item["ziel"] in s["einheiten"]:
        queue_at(s, item["schuetze"], item["ziel"], prot, "quick", reaction=item.get("reaction", False))


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
    if item.get("g_karten"):
        raise rules.Violation(describe(s, item))
    number = at_number(args)
    total = net(item) + number
    res = result_v(total)
    st["queue"].pop(0)
    target = item["ziel"]
    if item["art"] == "vof":
        prot.append(f"VOF against {target}: {net(item):+d} + AT {number} = {total}: {res} [10.5.3, 10.7]")
        apply_result(s, target, res, prot)
        return
    shooter = item["schuetze"]
    a = s["einheiten"].get(shooter)
    if a:
        use_shot(s, shooter, a, prot)
    prot.append(f"{shooter} at {target}: {net(item):+d} + AT {number} = {total}: {res} [10.6, 10.7]")
    apply_result(s, target, res, prot)
    w = weapon(a) if a else None
    quick = a is not None and w and chart_line(w)[5] and total in QUICK_SHOT_SUMS and shots_left(a) > 0
    reaction = bool(item["typ"] == "reaction" or item.get("reaction"))
    if quick and quick_shot(s, st, shooter, a, target, total, reaction, prot):
        return
    finish_shooter(s, shooter, prot)


def quick_shot(s, st, shooter, a, target, total, reaction, prot):
    """Quick Shot result (10.6.1): enemies fire again at once (new random target, CSR 7), the player is offered one.
    Returns True when the shooter stays open (next shot queued, offer pending or Reaction Fire exception)."""
    targets = vehicle_targets(s, shooter)
    if a["seite"] == "Feind" and targets:
        # [Normandy CSR 7 p.15] draw a new target for each Quick Shot; [10.6.1] enemies always take it
        if len(targets) == 1:
            queue_at(s, shooter, targets[0], prot, "quick", reaction=reaction)
        else:
            st["wahl"] = make_item("wahl", schuetze=shooter, ziele=targets, reaction=reaction)
        prot.append(f"{shooter}: Quick Shot result ({total}), fires again [10.6.1 p.73]")
        return True
    if a["seite"] == "US" and target in s["einheiten"]:
        st["queue"].insert(0, make_item("at", typ="quick_offer", schuetze=shooter, ziel=target, reaction=reaction))
        prot.append(f"{shooter}: Quick Shot result ({total}); fof.py at again | at stop [10.6.1 p.73]")
        return True
    if reaction:
        prot.append(f"{shooter}: Quick Shot draw on Reaction Fire, not marked Moved/Fired [10.5.4 Exception]")
        return True
    return False


AT_SUBCOMMANDS = {"granate": at_grenade, "grenade": at_grenade, "stop": at_stop}


def _cards():
    import json

    try:
        return json.loads((state.DATA / "karten.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def vehicle_targets(s, shooter):
    a = s["einheiten"][shooter]
    return [
        n
        for n, e in s["einheiten"].items()
        if is_vehicle(e) and e["seite"] != a["seite"] and line_of_fire(s, a, e["karte"]) is not None
    ]


def run_fire(s, n, step, prot):
    """AT Fire step of a vehicle action (10.5.2 D); after a Move the LOS/range is checked again."""
    t = step["ziel"]
    if t not in s["einheiten"]:
        return
    if line_of_fire(s, s["einheiten"][n], s["einheiten"][t]["karte"]) is None:
        prot.append(f"{n}: {t} no longer in LOS/range after the move, no AT Fire [10.6 A]")
        return
    queue_at(s, n, t, prot, "action")


def run_cf(s, n, step, prot):
    """Concentrate Fire step (10.5.2 B, 7.11): effects only now, after the VOF before the action (review M30)."""
    if not step["erfolg"]:
        prot.append(f"{n}: Concentrate Fire failed")
        return
    ze = step["ziel"]
    if ze not in s["einheiten"]:
        prot.append(f"{n}: Concentrate Fire target {ze} is gone, no marker")
        return
    for m in enemy.cf_stack(s, ze):
        s["einheiten"][m]["cf"] = s["einheiten"][m].get("cf", 0) + 1
    prot.append(f"Concentrated Fire marker on {ze} (stack: {', '.join(enemy.cf_stack(s, ze))}) [10.5.2 B, 7.11]")
    commands.cf_critical(s, ze, {"--kritisch": "ja" if step.get("kritisch") else "nein"}, prot)


def run_spot(s, n, step, prot):
    """Spot step (10.5.2 E, 8.5): the counters flip only now, after the VOF before the action (review M30)."""
    kid = step["karte"]
    if not step["erfolg"]:
        prot.append(f"{n}: Spot failed")
        return
    hidden = commands.unspotted_enemies(s, kid)
    if not hidden:
        prot.append(f"{kid}: no Unspotted enemy left to Spot")
        return
    for m in hidden:
        s["einheiten"][m]["spotted"] = True
    prot.append(f"{kid}: {', '.join(hidden)} Spotted, flip the counters [8.5]")
    fire.open_fire(s, prot)


def advance(s, prot):
    """Run the plan of the current vehicle action until a draw (or a Quick Shot target choice) is needed (10.5.1)."""
    st = at36(s)
    while not st["queue"] and not st.get("wahl") and not s.get("minen_checks"):
        ak = st.get("aktion")
        if not ak:
            return
        n = ak["einheit"]
        if n not in s["einheiten"]:
            prot.append(f"{n} is gone: its action ends")
            st["aktion"] = None
            switch_side(s, prot)
            return
        if not ak["plan"]:
            if ak.get("ende"):
                end_action(s, prot)
            return
        step = _legacy_step(ak["plan"].pop(0))
        kind = step["art"]
        if kind == "vof":
            queue_vof(s, n, prot, step["label"])
        elif kind == "move":
            do_move(s, n, step["karte"], step["bereich"], prot)
        elif kind == "react":
            queue_reactions(s, n, prot)
        elif kind == "fire":
            run_fire(s, n, step, prot)
        elif kind == "cf":
            run_cf(s, n, step, prot)
        elif kind == "spot":
            run_spot(s, n, step, prot)
        elif kind == "ende":
            ak["ende"] = True


def purge(s, prot):
    """Open draws against a vehicle that is gone (Brewed Up, Knocked Out, Retreat) lapse; so does a Quick Shot target
    choice whose shooter or targets are gone (review M29)."""
    st = at36(s)
    keep = []
    for q in st["queue"]:
        if q["ziel"] in s["einheiten"] and (q.get("schuetze") is None or q["schuetze"] in s["einheiten"]):
            keep.append(q)
        else:
            prot.append(f"{q.get('schuetze') or 'VOF'} at {q['ziel']}: lapses, the target is gone")
    st["queue"] = keep
    w = st.get("wahl")
    if not w:
        return
    if w["schuetze"] in s["einheiten"]:
        valid = vehicle_targets(s, w["schuetze"])
        gone = [t for t in w["ziele"] if t not in valid]
        if gone:
            w["ziele"] = [t for t in w["ziele"] if t in valid]
            prot.append(f"{w['schuetze']} Quick Shot: {', '.join(gone)} no longer a target (gone or out of LOS/range)")
    if not choice_live(s, w):
        st.pop("wahl")
        prot.append(f"{w['schuetze']}: Quick Shot target choice lapses, no target left")


def resume(s, prot):
    """Continue the phase after an interruption (mine check, resolved draw): lapsed draws go, the plan runs on, the next
    step is named. contact.py uses this after a mine check (review LOW, L187)."""
    purge(s, prot)
    advance(s, prot)
    st = at36(s)
    if st["queue"]:
        prot.append("Next draw: " + describe(s, st["queue"][0]))
    elif st.get("wahl"):
        prot.append("Next: " + describe(s, st["wahl"]))
    elif st.get("aktion") and not st["aktion"].get("ende"):
        n = st["aktion"]["einheit"]
        if st["aktion"].get("slow"):  # L196: after a SLOW card only Move then AT Fire or done remain
            prot.append(f"{n} may continue: fof.py vehicle fire {n} <target> (Move then AT Fire) | vehicle done {n}")
        else:
            prot.append(
                f"{n} may continue: fof.py vehicle move {n} <card> | vehicle fire {n} <target> (Move then AT Fire) | vehicle done {n}"
            )
    else:
        prot.append(next_hint(s))


def finish(s, prot):
    resume(s, prot)
    ak = fire.update_activity(s)
    if ak:
        prot.append(ak)
    state.save_state(s, "; ".join(prot), "10.5 p.72, 10.6 p.73")
    briefing.print_board(prot, s)


def end_action(s, prot):
    st = at36(s)
    ak = st.get("aktion")
    if not ak:
        return
    n = ak["einheit"]
    e = s["einheiten"].get(n)
    if e:
        e.pop("in_bewegung", None)
        finish_shooter(s, n, prot)
        e["hat_gehandelt"] = True
    st["aktion"] = None
    switch_side(s, prot)


def action_group(e):
    """L201 [Normandy M6 MSR 2 p.41]: 1 Tanks, 2 Jeeps (and Trucks), 3 AT Guns & AT-capable infantry."""
    if is_vehicle(e):
        w = e.get("fahrzeug") or ""
        return 2 if ("Jeep" in w or "Truck" in w) else 1
    return 3


def _enemy_base(s):
    return [
        n
        for n, e in s["einheiten"].items()
        if e["seite"] == "Feind" and activated(e) and not moved_fired(e) and at_capable(e) and vehicle_targets(s, n)
    ]


def _us_base(s):
    return [n for n, e in s["einheiten"].items() if e["seite"] == "US" and activated(e) and not moved_fired(e)]


def _group_of(s, enemy_base, us_base):
    if not (s.get("sonderregeln") or {}).get("fahrzeug_reihenfolge"):
        return None
    groups = [action_group(s["einheiten"][n]) for n in enemy_base + us_base]
    return min(groups) if groups else None


def current_group(s):
    """L201: with a mission group order (sonderregeln.fahrzeug_reihenfolge) only the lowest group still to act may act
    (both sides); Reaction Fire is not affected. None without such a rule."""
    return _group_of(s, _enemy_base(s), _us_base(s))


def actors(s):
    """(US actors, enemy actors) of the current group in one pass: the LOS scan of _enemy_base runs once (review LOW)."""
    en, us = _enemy_base(s), _us_base(s)
    g = _group_of(s, en, us)

    def in_group(names):
        return [n for n in names if g is None or action_group(s["einheiten"][n]) == g]

    return in_group(us), in_group(en)


def enemy_actors(s):
    """Activated enemy AT units, not Moved/Fired, with a US vehicle in LOS and range (AT Guns without target are redrawn,
    10.5.1 note); with MSR 2 only those of the current group."""
    return actors(s)[1]


def us_actors(s):
    return actors(s)[0]


def switch_side(s, prot):
    st = at36(s)
    side = st.get("naechste") or "US"
    other = "Feind" if side == "US" else "US"
    if enemy_actors(s) if other == "Feind" else us_actors(s):
        st["naechste"] = other


def next_hint(s):
    st = at36(s)
    us, en = actors(s)
    if not us and not en:
        return "No Activated unit left to act: phase next resolves the VOF against vehicles that did not act [10.5.1]"
    side = st.get("naechste") or ("US" if us else "Feind")
    if side == "Feind" and en:
        return "Next: enemy AT action, fof.py vehicle enemy [10.5.1, 8.12]"
    if us:
        return "Next: a US action (vehicle move|fire|cf|spot|done <unit> ...): " + ", ".join(us)
    return "Next: enemy AT action, fof.py vehicle enemy [10.5.1, 8.12]"


def base_type(terrain):
    """'Cemetery auf 1 Hill' / 'Woods on 1 Hill' -> terrain type of the card itself (L191: card without terrain -> '')."""
    terrain = terrain or ""
    return terrain.split(" auf ")[0].split(" on ")[0]


def traffic(s, kid):
    c = state.card(s, kid)
    if c.get("staging"):
        return True  # L194: Staging Area cards carry no terrain; vehicles start and move there normally (reading)
    t = c.get("fahrzeuge")
    if t is None:
        cat = s.get("terrain_katalog", {}).get(base_type(c["terrain"]), {})
        t = cat.get("fahrzeuge")
    return t


def do_move(s, n, kid, area, prot):
    e = s["einheiten"][n]
    from_ = e["karte"]
    commands.move_unit(s, n, kid, area, exposed=False, prot=prot)
    e["in_bewegung"] = True
    ak = at36(s)["aktion"]
    ak["bewegt"] = True
    ak["plan"] = [make_step("vof", label=f"VOF on {kid} after the move"), make_step("react")] + ak["plan"]
    if traffic(s, kid) == "SLOW":
        ak["slow"] = True
        prot.append(f"{kid} is SLOW: {n} must stop moving here [10.5.2 C, 5.2.4]")
    prot.append(f"{n} moves {from_} to {kid} (+1 moving target on {kid}) [10.5.2 C]")


def check_move_vehicle(s, n, kid):
    e = s["einheiten"][n]
    state.card(s, kid)
    if not geometry.adjacent(s, e["karte"], kid):
        raise rules.Violation(f"{kid} is not adjacent to {e['karte']} [10.5.2 C]")
    if not chart(e)[3]:
        raise rules.Violation(f"{n} is not mobile [10.8.4]")
    c = state.card(s, kid)
    if c.get("ausserhalb"):
        raise rules.Violation(f"{kid} is outside the mission boundaries [2.4.1]")
    t = traffic(s, kid)
    if t is None:
        raise rules.Violation(
            f"Trafficability of {base_type(c['terrain'])} not recorded (vehicle symbol on the card: normal, SLOW or NO); "
            f'fof.py vehicle traffic "{base_type(c["terrain"])}" normal|slow|no [5.2.4, E76]'
        )
    if t is False:
        raise rules.Violation(f"{kid} ({c['terrain']}) has trafficability NO: vehicles may not enter [10.5.2 C, 5.2.4]")
    vehicles = [m for m in state.units_on(s, kid, e["seite"]) if is_vehicle(s["einheiten"][m])]
    if len(vehicles) >= 4:
        raise rules.Violation(f"{kid} already has 4 vehicles of this side [5.1.5 p.32]")


def require_open(s):
    """review M31: after leave_3_6 queued the end-of-phase VOF (ende) no further action of either side may start."""
    if at36(s).get("ende"):
        raise rules.Violation(
            "The phase is ending (VOF against vehicles that did not act): no further action, phase next [10.5.1]"
        )


def start_action(s, n, kind):
    require_phase(s)
    lock(s)
    require_open(s)
    st = at36(s)
    e = state.unit(s, n)
    if e["seite"] != "US":
        raise rules.Violation("Only friendly units; enemy actions with fof.py vehicle enemy")
    if st.get("aktion") and st["aktion"]["einheit"] != n:
        raise rules.Violation(f"{st['aktion']['einheit']} is still acting: finish it first (vehicle done)")
    if not activated(e) or moved_fired(e):
        raise rules.Violation(
            f"{n} is not Activated for AT Combat & Vehicle Movement (4.2.1i) or already Moved/Fired [10.4]"
        )
    g = current_group(s)
    if g is not None and action_group(e) > g and not st.get("aktion"):
        raise rules.Violation(
            f"{n} belongs to group {action_group(e)}; first all units of group {g} act (1 Tanks, 2 Jeeps, 3 AT Guns/AT infantry) [MSR 2]"
        )
    if not st.get("aktion"):
        if (st.get("naechste") == "Feind") and enemy_actors(s):
            raise rules.Violation("It is the enemy's turn to act: fof.py vehicle enemy [10.5.1]")
        st["aktion"] = {"einheit": n, "plan": [], "bewegt": False}
        if is_vehicle(e):
            st["aktion"]["plan"].append(make_step("vof", label=f"VOF on {e['karte']} before the action"))
        st["naechste"] = "US"
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
    """Option that needs a value: a bare --flag (stored as True) is a Violation, not a name lookup (review H12)."""
    v = o.get(key)
    if v is True:
        raise rules.Violation(f"{key} needs a value: {usage}")
    return v


def vehicle_status(s):
    st = at36(s)
    lines = [f"AT Combat & Vehicle Movement (3.6), phase {s['phase']}"]
    for n, e in s["einheiten"].items():
        if is_vehicle(e) or (activated(e) or moved_fired(e)):
            lines.append(
                f"- {n} ({e.get('fahrzeug') or weapon(e)}) on {e['karte']}: "
                + ", ".join(x for x in e["status"])
                + (f", ammo {shots_left(e)}" if weapon(e) else "")
            )
    if st["queue"]:
        lines.append("Open draw: " + describe(s, st["queue"][0]))
    elif st.get("wahl"):
        lines.append("Open target choice: " + describe(s, st["wahl"]))
    lines.append(next_hint(s))
    print("\n".join(lines))


def vehicle_traffic(s, rest, o):
    """vehicle traffic <terrain type> normal|slow|no: record the vehicle symbol of a terrain type (5.2.4, E76)."""
    rules.need(rest, 2, "vehicle traffic <terrain type> normal|slow|no")
    typ, val = rest[0], rest[1].lower()
    if val not in TRAFFIC:
        raise rules.Violation("normal | slow | no")
    s.setdefault("terrain_katalog", {}).setdefault(typ, {})["fahrzeuge"] = TRAFFIC[val]
    for c in s["karten"].values():
        if base_type(c.get("terrain", "")) == typ:
            c["fahrzeuge"] = TRAFFIC[val]
    state.save_state(s, f"Trafficability {typ}: {val} (vehicle symbol on the card) [5.2.4, E76]", "5.2.4 p.36")
    print(f"Trafficability {typ}: {val}")


def vehicle_move(s, rest, o):
    """vehicle move <vehicle> <card>: Move action to an adjacent card (10.5.2 C)."""
    rules.need(rest, 2, "vehicle move <vehicle> <card>")
    n, kid = rest[0], rest[1]
    prot = []
    st, e = start_action(s, n, "move")
    if not is_vehicle(e):
        raise rules.Violation("Activated AT-capable infantry and AT guns can only AT Fire [10.5.2]")
    ak = st["aktion"]
    if ak.get("slow"):
        raise rules.Violation(f"{n} entered a SLOW card and must stop [10.5.2 C]")
    if ak.get("gefeuert"):
        raise rules.Violation(f"{n} has fired and may not move any more [10.5.2 D]")
    check_move_vehicle(s, n, kid)
    if o.get("--bereich") not in (None, "offen"):
        raise rules.Violation("Vehicles do not go under Cover markers; AT Combat uses the card's C&C value [10.6 C]")
    ak["plan"].append(make_step("move", karte=kid, bereich=None))
    prot.append(f"{n}: Move action to {kid} [10.5.2 C]")
    return prot


def vehicle_fire(s, rest, o):
    """vehicle fire <unit> <target vehicle>: AT Fire action, also Move then Fire (10.5.2 D)."""
    rules.need(rest, 2, "vehicle fire <unit> <target vehicle>")
    n, target = rest[0], rest[1]
    st, e = start_action(s, n, "fire")
    z = state.unit(s, target)
    if not is_vehicle(z) or z["seite"] == e["seite"]:
        raise rules.Violation(f"{target} is not an opposing vehicle")
    if not at_capable(e):
        raise rules.Violation(f"{n} has no AT weapon with shots left")
    ak = st["aktion"]
    if ak.get("bewegt") and chart_line(weapon(e))[4] is None:
        raise rules.Violation(f"{n} has no Move & Fire capability: no AT Fire after moving [10.5.2 D]")
    if line_of_fire(s, e, z["karte"]) is None:
        raise rules.Violation(f"{target} not in LOS/range of {n} [10.6 A]")
    ak["plan"] += [make_step("fire", ziel=target), make_step("react"), make_step("ende")]
    ak["gefeuert"] = True
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
    if st.get("aktion") and st["aktion"]["einheit"] == n:
        end_action(s, prot)
    elif activated(e) and not moved_fired(e):
        if (st.get("naechste") == "Feind") and enemy_actors(s):  # L200: passing is an action in the alternation too
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
    st, e = start_action(s, n, "cf")
    if not is_vehicle(e) or state.pinned(e):
        raise rules.Violation("Concentrate Fire: an Activated vehicle not under a Pinned marker [10.5.2 B]")
    if not fire.is_firing(e):
        raise rules.Violation(f"{n} exerts no VOF [10.5.2 B]")
    if o.get("--erfolg") not in ("ja", "nein"):
        k = 2 + {"Green": -1, "Veteran": 1}.get(comms.experience(e), 0)
        raise rules.Violation(
            f"Concentrate Fire by {n}: draw {k} Action cards, success on Crosshairs (2+: Critical Hit, --critical=yes; Jam no effect); "
            "then --success=yes|no --unit=<target> [10.5.2 B, 7.11]"
        )
    ze = None
    if o["--erfolg"] == "ja":
        ze = text_opt(o, "--einheit", "--unit=<target enemy>")
        if not ze:
            raise rules.Violation("Specify --unit=<target enemy>")
        zt = fire.effective_fire_target(s, n)
        commands.cf_target_check(s, zt, ze, e)
    # review M30: the effect is a plan step after the VOF before the action (10.5.1 step 1); a vehicle Brewed Up by
    # that VOF leaves no Concentrated Fire marker behind
    st["aktion"]["plan"] += [
        make_step("cf", erfolg=o["--erfolg"] == "ja", ziel=ze, kritisch=o.get("--kritisch") == "ja"),
        make_step("react"),
        make_step("ende"),
    ]
    return [f"{n}: Concentrate Fire action [10.5.2 B]"]


def vehicle_spot(s, rest, o):
    """vehicle spot <vehicle> --target=<card> --success=yes|no: Spot action (10.5.2 E, 8.5)."""
    rules.need(rest, 1, "vehicle spot <vehicle> --target=<card> --success=yes|no")
    n = rest[0]
    st, e = start_action(s, n, "spot")
    if not is_vehicle(e) or state.pinned(e):
        raise rules.Violation("Spot: an Activated vehicle not under a Pinned marker [10.5.2 E]")
    kid = text_opt(o, "--ziel", "--target=<card>")
    if not kid:
        raise rules.Violation("--target=<card with Unspotted enemies>")
    hidden = commands.unspotted_enemies(s, kid)
    if not hidden:
        raise rules.Violation(f"No Unspotted enemy on {kid}")
    if o.get("--erfolg") not in ("ja", "nein"):
        mods = comms.spot_modifiers(s, e, kid)
        k = max(1, 2 + sum(m for _, m in mods))
        raise rules.Violation(
            f"Spot by {n}: draw {k} Action cards ({', '.join(f'{t} {m:+d}' for t, m in mods)}), success on Crosshairs; then --success=yes|no [10.5.2 E, 8.5]"
        )
    # review M30: the Spot result is a plan step after the VOF before the action (10.5.1 step 1)
    st["aktion"]["plan"] += [
        make_step("spot", erfolg=o["--erfolg"] == "ja", karte=kid),
        make_step("react"),
        make_step("ende"),
    ]
    return [f"{n}: Spot action on {kid} [10.5.2 E]"]


def vehicle_enemy(s, rest, o):
    """vehicle enemy [--unit=] [--target=]: AT Fire of an Activated enemy AT unit (10.5.1, 8.12, CSR 7)."""
    require_phase(s)
    lock(s)
    require_open(s)
    st = at36(s)
    if st.get("aktion"):
        raise rules.Violation(f"{st['aktion']['einheit']} is still acting")
    actors = enemy_actors(s)
    if not actors:
        raise rules.Violation("No Activated enemy AT unit with a US vehicle in LOS and range")
    if st.get("naechste") == "US" and us_actors(s):  # review M32: the sides alternate (10.5.1), as in start_action
        raise rules.Violation("It is the US side's turn to act (vehicle move|fire|cf|spot|done <unit>) [10.5.1]")
    n = text_opt(o, "--einheit", "--unit=<enemy unit>")
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
    targets = vehicle_targets(s, n)
    t = text_opt(o, "--ziel", "--target=<vehicle>")
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
    st["naechste"] = "US"
    return prot


def vehicle_target(s, rest, o):
    """vehicle target <R#>: the randomly drawn target of an enemy Quick Shot (CSR 7, review M29)."""
    require_phase(s)
    contact.mine_lock(s)
    rules.need(rest, 1, "vehicle target <R#>")
    st = at36(s)
    if st["queue"]:
        raise rules.Violation("First resolve the open AT draw: " + describe(s, st["queue"][0]))
    prot = []
    purge(s, prot)  # a choice whose targets are gone lapses (saved below) instead of blocking the phase
    w = st.get("wahl")
    if not w:
        if prot:
            return prot
        raise rules.Violation("No target choice open")
    i = rules.int_value(rest[0], "vehicle target <R#>")
    if not 1 <= i <= len(w["ziele"]):
        raise rules.Violation(f"R# {i} is not in the choice list (1-{len(w['ziele'])}): " + describe(s, w))
    t = w["ziele"][i - 1]
    if t not in vehicle_targets(s, w["schuetze"]):
        raise rules.Violation(f"{t} is no longer a target of {w['schuetze']} (gone or out of LOS/range) [10.6 A]")
    st.pop("wahl")
    queue_at(s, w["schuetze"], t, prot, "quick", reaction=w.get("reaction", False))
    return prot


def vehicle_react(s, rest, o):
    """vehicle react <unit> <target vehicle>: Reaction Fire of a US AT-capable unit (10.5.4)."""
    rules.need(rest, 2, "vehicle react <unit> <target vehicle>")
    n, t = rest[0], rest[1]
    require_phase(s)
    require_open(s)
    state.unit(s, n)
    state.unit(s, t)
    if n not in reaction_shooters(s, t):
        raise rules.Violation(f"{n} cannot Reaction Fire at {t} [10.5.4]")
    prot = []
    queue_at(s, n, t, prot, "reaction")
    return prot


VEHICLE_SUBCOMMANDS = {
    "verkehr": vehicle_traffic,
    "traffic": vehicle_traffic,
    "move": vehicle_move,
    "bewegen": vehicle_move,
    "fire": vehicle_fire,
    "feuer": vehicle_fire,
    "done": vehicle_done,
    "fertig": vehicle_done,
    "cf": vehicle_cf,
    "spot": vehicle_spot,
    "spotten": vehicle_spot,
    "enemy": vehicle_enemy,
    "feind": vehicle_enemy,
    "target": vehicle_target,
    "ziel": vehicle_target,
    "react": vehicle_react,
    "reaktion": vehicle_react,
}


# ---- hooks into the sequence of play


def enter_3_6(s, prot):
    """[Normandy CSR 7] German AT activation; list of Activated units; side to act first (10.5.1)."""
    st = at36(s)
    st.update(queue=[], aktion=None, angegriffen=[], ende=False)
    us_vehicles = {e["karte"] for e in s["einheiten"].values() if is_vehicle(e) and e["seite"] == "US"}
    for n, e in s["einheiten"].items():
        if e["seite"] != "Feind" or not at_capable(e):
            continue
        w = weapon(e)
        if w in CSR7_ALWAYS or (w in CSR7_SAME_CARD and e["karte"] in us_vehicles):
            if not activated(e):
                e["status"].append(rules.ACTIVATED)
                prot.append(f"{n} ({w}) automatically Activated for AT Combat [CSR 7 p.15]")
    st["naechste"] = "US" if s.get("typ") != "defensiv" else "Feind"
    if us_actors(s) or enemy_actors(s):
        prot.append(next_hint(s))
    elif any(is_vehicle(e) for e in s["einheiten"].values()):
        prot.append("No Activated unit; phase next resolves the VOF against vehicles [10.5.1]")


def leave_3_6(s, prot):
    """Before leaving 3.6: no open draw or action; enemies acted; VOF against vehicles that did not act (10.5.1 end);
    Pinned vehicles not attacked lose the marker (10.7 Pinned)."""
    st = at36(s)
    lock(s)
    if st.get("aktion"):
        raise rules.Violation(f"{st['aktion']['einheit']} is still acting (vehicle done)")
    if enemy_actors(s):
        raise rules.Violation("Activated enemy AT units still have a target: fof.py vehicle enemy [10.5.1]")
    # review H5: under MSR 2 an enemy of a later group must not be skipped because a US unit of an earlier group simply
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
    if not st.get("ende"):
        st["ende"] = True
        for n, e in s["einheiten"].items():
            if is_vehicle(e) and not e.get("hat_gehandelt"):
                queue_vof(s, n, prot, "End of phase")
        if st["queue"]:
            state.save_state(
                s, "; ".join(prot + ["End of 3.6: VOF against vehicles that did not act [10.5.1]"]), "10.5.1 p.72"
            )
            raise rules.Violation("VOF against vehicles still to resolve: " + describe(s, st["queue"][0]))
    for n, e in s["einheiten"].items():
        if is_vehicle(e) and state.pinned(e) and n not in st["angegriffen"]:
            e["status"].remove(rules.PINNED)
            prot.append(f"{n}: remove Pinned (not attacked in this phase) [10.7 Pinned]")


def clean_up(s, prot):
    """3.8: remove Activated and Moved/Fired markers (10.4); Burning Wrecks become Wrecks (3.8 step 9)."""
    for n, e in s["einheiten"].items():
        for m in (rules.ACTIVATED, rules.MOVED_FIRED):
            if m in e["status"]:
                e["status"].remove(m)
                prot.append(f"{n}: remove {m} marker [10.4]")
        e.pop("hat_gehandelt", None)
        e.pop("in_bewegung", None)
    for kid, c in s["karten"].items():
        for x in list(c.get("extern", [])):
            if x.get("wrack"):
                val = (s.get("fahrzeug_werte") or {}).get("wreck_cover", 1)
                cid = add_wreck_cover(s, c, val)
                prot.append(
                    f"{kid}: flip the Burning Wreck to its Wreck side (cover marker {cid} +{val}) [3.8 step 9, 10.7]"
                )
    s.pop("at36", None)


def order_4_2_1i(s, ctx):
    """[RULE 4.2.1i p.22, 10.4 p.72] Activate a vehicle or an unpinned AT-capable infantry unit."""
    z = ctx.z
    if not (is_vehicle(z) or (at_capable(z) and not state.pinned(z))):
        raise rules.Violation(
            f"{ctx.target_name}: only a vehicle or an unpinned AT-capable infantry unit [RULE 4.2.1i p.22]"
        )
    if activated(z):
        raise rules.Violation(f"{ctx.target_name} is already Activated")
    z["status"].append(rules.ACTIVATED)
    ctx.prot.append(f"{ctx.target_name}: place the Activated marker [4.2.1i, 10.4]")


VEHICLE_ORDERS = {"4.2.2h", "4.2.3a", "4.2.4k", "4.2.4l", "4.2.1i"}


def order_check(s, hq_name, target_name, akt):
    """[RULE 10.1.1/10.1.2 p.70/71] vehicle orders and vehicle chains of command. Returns True if communication is settled."""
    hq, z = state.unit(s, hq_name), state.unit(s, target_name)
    if is_vehicle(hq) and state.is_hq(hq) and not is_vehicle(z):
        raise rules.Violation(
            f"{hq_name} is a vehicle PLT HQ: it only orders the vehicles of its platoon [10.1.1 p.70]"
        )
    if not is_vehicle(z):
        return False
    akt = akt or "4.2.1a"
    if (
        akt not in VEHICLE_ORDERS
        and not (akt == "4.2.1a" and state.is_hq(z))
        and not (akt.startswith("4.2.1") and hq_name == target_name)
    ):
        raise rules.Violation(
            "Vehicles only take Load/Unload/Embark, Rally, Cease/Shift Fire and Activate for AT Combat & Vehicle Movement in the Command Phase [10.1.2 p.71]"
        )
    if hq_name == target_name or hq_name == "GI":
        return True
    plt = z.get("platoon")
    plt_hq = [m for m, x in s["einheiten"].items() if x.get("platoon") == plt and is_vehicle(x) and state.is_hq(x)]
    if plt and plt_hq:
        if hq_name in plt_hq:
            return True  # [10.1.1] the vehicle PLT HQ is always in communication with its platoon
        if hq.get("ebene") == "CO" and hq["typ"] == "HQ":
            ok = comms.radios_of(hq, "SCR300", "BN TAC") or not state.radio_active(s)
            if not ok:
                raise rules.Violation(
                    f"{hq_name} carries no SCR300 BN TAC: no contact with the tank platoon [10.1.1 p.70]"
                )
            return True
        raise rules.Violation(f"{target_name} takes orders only from its vehicle PLT HQ and the CO HQ [10.1.2 p.71]")
    return False


def tank_hq_activation(s, hq_name, target_name):
    """[RULE 10.1.1 p.70] the CO HQ activates a vehicle PLT HQ over the BN TAC Net (WWII)."""
    z = s["einheiten"].get(target_name, {})
    hq = s["einheiten"].get(hq_name, {})
    if is_vehicle(z) and state.is_hq(z) and hq.get("ebene") == "CO":
        return bool(comms.radios_of(hq, "SCR300", "BN TAC") or not state.radio_active(s))
    return False
