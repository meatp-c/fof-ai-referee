"""Mission setup: terrain, map extension, objectives, unit setup, assets, radios, notes."""

import copy
import re

from . import briefing, campaign, combat, commands, comms, fire, geometry, messages, options, rules, state


def cmd_setup(s, args):
    """[RULE 2.3.5 p.10] Offensive mission: setup in the Staging Area; [RULE 2.3.3 p.10] attachments before the game starts, fixed afterwards."""
    if not state.in_setup(s):
        raise rules.Violation(
            "Setup and attachments only before turn 1 starts (phase 3.1); no regrouping afterwards [RULE 2.3.3 p.10]"
        )
    n = args[0]
    e = state.unit(s, n)
    if e["seite"] != "US":
        raise rules.Violation("Friendly units only")
    o = options.parse_opts(args[1:])
    prot = []
    if "--platoon" in o:
        p = o["--platoon"]
        if (state.is_hq(e) or e["typ"] == "Squad") and not e.get(
            "attachment"
        ):  # L75: Engineers are a squad attachment (2.3.2)
            raise rules.Violation(
                f"{n} belongs permanently to its platoon; attachments and company units can be assigned [RULE 2.3.2 p.10]"
            )
        hqs = {x.get("platoon"): m for m, x in s["einheiten"].items() if x.get("ebene") == "PLT"}
        if p == "keiner":
            e["platoon"], e["attached_an"] = None, []
            prot.append(
                f"{n} assigned to no platoon; orders from the CO HQ and CO Staff (XO, 1st Sgt) [RULE 2.3.3 p.10, 4.0 p.18]"
            )
        else:
            if p not in hqs:
                raise rules.Violation(f"Platoon {p} unknown; available: {', '.join(sorted(k for k in hqs if k))}")
            e["platoon"], e["attached_an"] = p, [hqs[p]]
            prot.append(f"{n} assigned to {hqs[p]} for the whole mission [RULE 2.3.3 p.10]")
    if state.is_v4(s):
        setup_v4(s, n, e, o, prot)
        e = s["einheiten"].get(n, e)
    kz = [a for a in args[1:] if not a.startswith("--")]
    if kz:
        k = kz[0]
        if (
            n not in s["einheiten"]
            and n == "Mtr Sec"
            and s.get("moerser_wahl") == "teams"
            and state.card(s, k).get("staging")
        ):
            for tn in s.get("reserve_einheiten", {}):
                if tn in s["einheiten"]:
                    s["einheiten"][tn]["karte"] = k
            prot.append(f"Mortar Teams into the Staging Area {k}")
            state.save_state(s, "Setup: " + "; ".join(prot), "2.3.3 p.10, 2.3.5 p.10")
            briefing.print_board(prot, s)
            return
        if n not in s["einheiten"]:
            raise rules.Violation(f"{n} is no longer in play")
        if s.get("patrouille_mission"):
            kc = state.card(s, k)
            cop = s.get("ziele", {}).get("cop")
            if e.get("stationaer"):
                if kc["reihe"] != 1 and k != cop:
                    raise rules.Violation(
                        f"{n} is not on patrol: only into the fortifications of row 1 or into the Combat Outpost [MSR 1]"
                    )
                if k == cop:
                    platoons = {
                        x.get("platoon")
                        for m, x in s["einheiten"].items()
                        if x["seite"] == "US" and x.get("karte") == cop and m != n
                    }
                    if e.get("platoon") and platoons - {None, e.get("platoon")}:
                        raise rules.Violation("Units of at most one platoon in the Combat Outpost [MSR 1]")
                if kc.get("cover") and not o.get("--bereich"):  # L55: "Place any others in the fortifications on Row 1"
                    raise rules.Violation(
                        f"{n} is not on patrol: set it up in the fortifications, --area="
                        + "|".join(c["id"] for c in kc["cover"])
                        + " [Normandy M3 p.26 MSR 1: 'Place any others in the fortifications on Row 1']"
                    )
            elif kc["reihe"] != 1:
                raise rules.Violation("The patrol sets up on Row 1 [2.6.1, MSR 4]")
        elif s.get("aufstellung_feld") and not s.get("reattempt_setup"):
            # L75 [Normandy M4 p.28]: "Place 2 Foxholes per card in Row 1 ... any one card in Row 2; some units from one
            # platoon of your choice may be placed on this card. All other units start on Row 1."
            af = s["aufstellung_feld"]
            kc = state.card(s, k)
            if k == af.get("zusatzkarte"):
                if not e.get("platoon"):
                    raise rules.Violation(
                        f"Only units of one platoon on {k}; {n} belongs to no platoon (first setup <unit> --platoon=..) [{af.get('regel', 'Normandy M4 p.28')}]"
                    )
                platoons = {
                    x.get("platoon")
                    for m, x in s["einheiten"].items()
                    if x["seite"] == "US" and x.get("karte") == k and m != n
                }
                if platoons - {e.get("platoon")}:
                    raise rules.Violation(
                        f"Units of platoon {', '.join(sorted(str(p) for p in platoons))} already stand on {k}; one platoon only [{af.get('regel', 'Normandy M4 p.28')}]"
                    )
            elif kc.get("reihe") not in af.get("reihen", [1]):
                raise rules.Violation(
                    f"Setup only on row {', '.join(str(r) for r in af.get('reihen', [1]))}"
                    + (f" or on {af['zusatzkarte']} (units of one platoon)" if af.get("zusatzkarte") else "")
                    + f" [{af.get('regel', 'Normandy M4 p.28')}]"
                )
            _st = sum(
                state.steps(x)
                for m, x in s["einheiten"].items()
                if x["seite"] == "US" and x.get("karte") == k and m != n
            ) + state.steps(e)
            if _st > 16:
                raise rules.Violation(
                    f"Stacking: {k} would hold {_st} US steps, at most 16 per card [RULE 5.1.5 p.32]"
                )  # L76
            if kc.get("cover") and not o.get("--bereich"):
                raise rules.Violation(
                    f"{k} has cover ({', '.join(c['id'] + ' ' + c['typ'] for c in kc['cover'])}): give --area=open|"
                    + "|".join(c["id"] for c in kc["cover"])
                )
        elif not state.card(s, k).get("staging") and not (s.get("reattempt_setup") and campaign.is_secured(s, k)):
            raise rules.Violation(
                f"{k} is not a staging card; offensive mission: setup in the Staging Area [RULE 2.3.5 p.10]"
                + ("; in a reattempt also secured cards (3.9 step 5)" if s.get("reattempt_setup") else "")
            )
        e["karte"], e["bereich"] = k, "offen"
        if o.get("--bereich") and (
            s.get("reattempt_setup") or s.get("patrouille_mission") or s.get("aufstellung_feld")
        ):
            commands.set_area(s, e, n, o["--bereich"])
        prot.append(
            f"{n} {'into the Staging Area' if state.card(s, k).get('staging') else 'on card' if (s.get('patrouille_mission') or s.get('aufstellung_feld')) else 'on the secured card'} {k}"
            + (f" under {e['bereich']}" if e["bereich"] != "offen" else "")
        )
    if not prot:
        raise rules.Violation(
            "setup <unit> <staging card> and/or --platoon=<no>|none"
            + (" | --net= --mortar= --asset= --lines= --pyro= --device=" if state.is_v4(s) else "")
        )
    state.save_state(s, "Setup: " + "; ".join(prot), "2.3.3 p.10, 2.3.5 p.10")
    briefing.print_board(prot, s)


def cmd_radio(s, args):
    """Radio overview, single check, R# 1/2 on radio damage."""
    if not args:
        if not state.company(s):
            print("No CO HQ on the board; communication as specified by the mission.")
            return
        for t in briefing.radio_overview(s):
            print("- " + t)
        return
    if args[0] == "pruefen" and len(args) == 2:
        # L98: every unit <HQ> can reach
        a = args[1]
        state.unit(s, a)
        ok, no_ = [], []
        for n, e in s["einheiten"].items():
            if n == a or e["seite"] != "US":
                continue
            try:
                comms.communication(s, a, n)
                ok.append(n)
            except rules.Violation:
                no_.append(n)
        s.pop("_hinweise", None)
        print(f"{a} reaches: " + (", ".join(ok) if ok else "nobody") + " [RULE 4.3 p.27]")
        print(f"{a} does not reach: " + (", ".join(no_) if no_ else "-"))
        return
    if args[0] == "pruefen":
        a, b = args[1], args[2]
        state.unit(s, a), state.unit(s, b)
        try:
            comms.communication(s, a, b)
            print(f"{messages.ALLOWED}: {a} and {b} in communication {messages.rule('4.3 p.27')}")
        except rules.Violation as v:
            print(f"{messages.VIOLATION}: {v}")
        for h in dict.fromkeys(s.pop("_hinweise", [])):
            print(f"{messages.NOTE}: " + h)
        return
    if args[0] == "schaden":
        kid, type_, result = args[1], args[2], args[3]
        c = state.card(s, kid)
        g = [x for x in c.get("assets", []) if x["typ"] == type_ and x.get("schaden_offen")]
        if not g:
            raise rules.Violation(f"On {kid} there is no {type_} with a pending damage draw")
        if result == "zerstoert":
            c["assets"].remove(g[0])
            s.setdefault("funk_zerstoert", []).append(f"{g[0]['typ']} {g[0]['netz']}")
            prot = [f"{type_} {g[0]['netz']} on {kid} destroyed, removed from play [RULE 4.3.5 p.30]"]
        elif result == "heil":
            g[0]["schaden_offen"] = False
            prot = [
                f"{type_} {g[0]['netz']} lies on {kid}, can be picked up with 4.2.2h (--what={type_}) [RULE 4.3.5 p.30]"
            ]
        else:
            raise rules.Violation("heil (intact) | zerstoert (destroyed)")
        state.save_state(s, "; ".join(prot), "4.3.5 p.30")
        briefing.print_board(prot, s)
        return
    raise rules.Violation("radio | radio check <hq> <unit> | radio damage <card> <device> intact|destroyed")


def cmd_drop(s, args):
    """[RULE 5.1.6B p.33] Drop without spending a command, at any time."""
    if len(args) < 2:
        raise rules.Violation("drop <unit> <Casualty|asset name|radio|Leitung[:n]|AMMO:n>")
    n, what = args[0], args[1]
    e = state.unit(s, n)
    c = state.card(s, e["karte"])
    if what.lower() == "casualty":
        if not e.get("traegt_casualties"):
            raise rules.Violation(f"{n} is not carrying a casualty")
        e["traegt_casualties"] -= 1
        c["casualties"] = c.get("casualties", 0) + 1
        prot = [
            f"{n} drops a casualty on {e['karte']}"
            + (" (CCP: evacuation in Clean Up)" if s.get("ccp") == e["karte"] else "")
        ]
    elif ":" in what and what.split(":")[0] in rules.AMMO_CAPACITY:
        prot = []
        combat.ammo_drop(s, e, n, what, prot)
    elif what in (e.get("assets") or []):
        # L99 [RULE 5.1.6B p.33]: put an asset counter (smoke, rifle grenade, pyro ...) on the card (assets_boden, Pick Up 4.2.2h)
        e["assets"].remove(what)
        c.setdefault("assets_boden", []).append(what)
        prot = [f"{n} drops asset {what} on {e['karte']} (Pick Up 4.2.2h) [5.1.6B p.33]"]
    elif what.startswith("Leitung"):
        nz = int(what.split(":")[1]) if ":" in what else 1
        if e.get("leitungen", 0) < nz:
            raise rules.Violation(f"{n} is not carrying {nz} Phone Line(s)")
        e["leitungen"] -= nz
        c["leitung_assets"] = c.get("leitung_assets", 0) + nz
        prot = [f"{n} drops {nz} Phone Line(s) as an asset on {e['karte']} (no phone line marker) [5.1.6B, BGG D3]"]
    else:
        g = [x for x in comms.radios_of(e) if x["typ"] == what or f"{x['typ']} {x['netz']}" == what]
        if not g:
            raise rules.Violation(f"{n} is not carrying '{what}'")
        e["funk"].remove(g[0])
        c.setdefault("assets", []).append({"typ": g[0]["typ"], "netz": g[0]["netz"], "schaden_offen": False})
        prot = [f"{n} drops {g[0]['typ']} {g[0]['netz']} on {e['karte']}"]
    state.save_state(s, "; ".join(prot), "5.1.6B p.33")
    briefing.print_board(prot, s)


def cmd_options(s, args):
    if "optionen" not in s:
        print("This mission has no open rules questions (no field 'optionen' in the setup).")
        return
    for k, (std, txt) in rules.DEFAULT_OPTIONS.items():
        if not state.is_v4(s) and int(re.match(r"U(\d+)", k).group(1)) > 13:
            continue
        value = state.option(s, k)
        print(
            f"- {k.split('_')[0]} {k}: {value}"
            + (" (default)" if value == std else f" (default {std})")
            + f"; default reading: {txt}"
        )
    print(
        "Change only by the player's decision (E entry in data/klarstellungen.md) and by adjusting 'optionen' in the setup or game state."
    )


def cmd_multistory(s, args):
    """L73 [RULE 5.3.3 p.38, 5.2.2B p.36] card carries the Multi-Story symbol: set the flag; if a building cover without
    Upper Story already lies there, add the Upper Story marker with the same value."""
    kid = args[0]
    c = state.card(s, kid)
    c["mehrstoeckig"] = True
    prot = [f"card {kid}: Multi-Story symbol recorded [5.3.3 p.38]"]
    has_upper_story = any(x["typ"] == "Upper Story" for x in c.get("cover", []))
    building = [x for x in c.get("cover", []) if x["typ"] in ("Light Building", "Strong Building")]
    if building and not has_upper_story:
        uid = commands.new_cover_marker(s, kid, "Upper Story", building[0]["wert"])
        [x for x in c["cover"] if x["id"] == uid][0]["feld"] = True
        prot.append(
            f"Upper Story marker {uid} (+{building[0]['wert']}) on {kid} with the {building[0]['typ']} {building[0]['id']}; does not count towards the Cover Potential [5.3.3 p.38]"
        )
    state.save_state(s, "; ".join(prot), "5.3.3 p.38")
    briefing.print_board(prot, s)


def cmd_note(s, args):
    """Free text into the log (corrections, card numbers supplied later)."""
    text = " ".join(args)
    state.save_state(s, "NOTE: " + text, None)
    briefing.print_board([text], s)


def cmd_visibility(s, args):
    """visibility <light> [<weather>] [--this-turn-only=yes]: [RULE 9.0 p.69] set Light Level and Weather."""
    if not args:
        l, w = geometry.light_weather(s)
        print(
            f"Light {l:+d}, weather {w:+d}, total {l + w:+d}: {'Limited Visibility (9.1)' if l + w >= 2 else 'normal visibility'}"
        )
        return
    s["licht"] = int(args[0])
    s.pop("visibility", None)
    o = options.parse_opts(args[1:])
    if len(args) > 1 and not args[1].startswith("--"):
        s["wetter"] = int(args[1])
        if o.get("--nur_zug") == "ja":
            s["wetter_nur_zug"] = True
    geometry.update_visibility(s)
    l, w = geometry.light_weather(s)
    txt = f"Visibility: light {l:+d}, weather {w:+d}, total {l + w:+d}" + (
        ": Limited Visibility, 4 Commands per impulse, saving G2/L4/V6, LOS Close Range [9.1]" if l + w >= 2 else ""
    )
    fire.open_fire(s, [])
    state.save_state(s, txt, "9.0 p.69")
    print(txt)
    print(briefing.check_stamp(s))


def cmd_illum(s, args):
    """illum <card> <top> [<bottom>] [--origin=..] | illum <card> remove: [RULE 9.2 p.70] immediately, no Pending, removed in Clean Up."""
    kid = args[0]
    c = state.card(s, kid)
    if len(args) > 1 and args[1] == "weg":
        c["illum"] = []
        txt = f"Illumination on {kid} removed"
    else:
        o = options.parse_opts(args[1:])
        remainder = [a for a in args[1:] if not a.startswith("--")]
        m = {
            "oben": int(remainder[0]),
            "unten": int(remainder[1]) if len(remainder) > 1 else None,
            "quelle": o.get("--quelle", "?"),
        }
        c.setdefault("illum", []).append(m)
        txt = (
            f"Illumination marker {m['oben']:+d}"
            + (f"/{m['unten']:+d}" if m["unten"] is not None else "")
            + f" ({m['quelle']}) on {kid}: "
            f"top value for {kid}"
            + (", bottom value for the adjacent cards" if m["unten"] is not None else "")
            + "; not cumulative, light plus illum never better than +0 [9.2]"
        )
        if geometry.light_weather(s)[1] >= 2:
            txt += "; weather +2 or more: cards do not count as illuminated (9.2.1)"
    fire.open_fire(s, [])
    state.save_state(s, txt, "9.2 p.70")
    print(txt)
    print(briefing.check_stamp(s))


def parse_edges(txt):
    if not txt:
        return None
    if txt in ("weiss", "gruen"):
        return txt
    r = {}
    for part in txt.split(","):
        k, v = part.split(":")
        if k not in ("oben", "unten", "links", "rechts", "diagonal") or v not in ("weiss", "gruen"):
            raise rules.Violation(
                "--edges=oben:weiss|gruen,unten:..,links:..,rechts:..,diagonal:.. (oben = toward the enemy)"
            )
        r[k] = v
    for k in ("oben", "unten", "links", "rechts", "diagonal"):
        r.setdefault(k, "gruen")
    return r


def set_terrain(s, kid, type_, o):
    catalog = s.get("terrain_katalog", {})
    if type_ not in catalog:
        raise rules.Violation(
            f"Terrain type '{type_}' not in the catalog: {', '.join(k for k in catalog if k != 'Hill')}; unknown types with all values: --typ-neu=ja --cc=.. --cover_max=.. --cover_draw=.. --edges=.."
        )
    c = state.card(s, kid)
    w = {k: v for k, v in catalog[type_].items() if k not in ("quelle",)}
    c["terrain"] = type_
    for k in (
        "cc",
        "cc2",
        "burst",
        "cover_max",
        "cover_draw",
        "raender",
        "fahrzeuge",
        "moerser_verbot",
        "urban",
        "gebaeude_tabelle",
        "op",
    ):
        if k in w:
            c[k] = w[k]
    for k in ("cc", "cc2", "burst", "cover_max", "cover_draw"):
        if o.get("--" + k) is not None:
            c[k] = int(o["--" + k])
    if o.get("--raender"):
        c["raender"] = parse_edges(o["--raender"])
    if o.get("--nr"):
        c["kartennummer"] = o["--nr"]
    hills = int(o.get("--hill", 0))
    c["elevation"] = 1 + hills  # [RULE 2.2.1 p.9, 5.2.2A p.35] each Hill card +1
    if hills:
        c["terrain"] = f"{type_} on {hills} Hill"
        if isinstance(c.get("raender"), str) or c.get("raender") is None:
            c["raender"] = "gruen"  # E9: Hill cards have dark edges
    missing = [k for k in ("cc", "cover_max", "cover_draw", "raender") if c.get(k) is None]
    if missing:
        raise rules.Violation(
            f"{type_}: values not recorded ({', '.join(missing)}); read them from the board and give them with --{' --'.join(missing)} (UNVERIFIED in the catalog)"
        )
    if "UNVERIFIZIERT" in catalog[type_].get("quelle", ""):
        s.setdefault("_hinweise", []).append(
            f"{type_}: catalog values partly UNVERIFIED ({catalog[type_]['quelle']}); check on the board"
        )
    c.pop("hinweis", None)


def cmd_terrain(s, args):
    """[RULE 2.2.1 p.9] Enter a randomly drawn terrain card: before turn 1 for all cards, later only for cards without terrain."""
    if len(args) < 2:
        raise rules.Violation("terrain <card> <type> [--no=<card number>] [--hill=n] [--edges=..] [--cc=..]")
    kid, type_ = args[0], args[1]
    o = options.parse_opts(args[2:])
    c = state.card(s, kid)
    if c.get("staging"):
        raise rules.Violation("Staging cards stay face down (2.2.1)")
    if c.get("terrain") and not state.in_setup(s):
        raise rules.Violation(f"{kid} already has terrain ({c['terrain']}); change only before turn 1")
    set_terrain(s, kid, type_, o)
    rt = c["raender"] if isinstance(c["raender"], str) else ", ".join(f"{a} {b}" for a, b in c["raender"].items())
    prot = [
        f"{kid}: {c['terrain']} (C&C +{c['cc']}"
        + (f"/+{c['cc2']}" if c.get("cc2") is not None else "")
        + f", Cover {c['cover_max']}/{c['cover_draw']}, edges {rt}"
        + (f", Elevation {c['elevation']}" if c.get("elevation", 1) > 1 else "")
        + ")"
    ]
    state.save_state(s, "Terrain: " + prot[0], "2.2.1 p.9")
    briefing.print_board(prot, s)


def cmd_extend(s, args):
    """[RULE 8.4.5 p.65] Create a card for placing an enemy package; outside the mission boundaries it is off-limits to US (2.4.1)."""
    if len(args) < 3:
        raise rules.Violation("extend <row> <column> <type> [--hill=n] [--edges=..] [--no=..]")
    r, c, type_ = int(args[0]), int(args[1]), args[2]
    o = options.parse_opts(args[3:])
    kid = state.card_id(r, c)
    if kid in s["karten"] or geometry.card_at(s, r, c):
        raise rules.Violation(f"Card at row {r} column {c} already exists")
    if r <= 1:
        raise rules.Violation("No extension behind the Staging Area")
    if not any(abs(v["reihe"] - r) <= 1 and abs(v["spalte"] - c) <= 1 for v in s["karten"].values()):
        raise rules.Violation("Extension only adjacent to existing cards")
    columns = [v["spalte"] for v in s["karten"].values() if not v.get("ausserhalb")]
    outside = r > state.top_row(s) or c < min(columns) or c > max(columns)
    s["karten"][kid] = {"terrain": None, "reihe": r, "spalte": c, "cover": [], "extern": [], "ausserhalb": outside}
    try:
        set_terrain(s, kid, type_, o)
    except rules.Violation:
        del s["karten"][kid]
        raise
    prot = [
        f"Card {kid} (row {r}, column {c}) created: {s['karten'][kid]['terrain']}"
        + (", outside the mission boundaries: off-limits to friendly units [2.4.1, 8.4.5]" if outside else "")
    ]
    state.save_state(s, "; ".join(prot), "8.4.5 p.65")
    briefing.print_board(prot, s)


def cmd_objective(s, args):
    """[RULE 2.4.1 p.10, Normandy M1 p.16] Primary/Secondary on row 3 (tool 4), Attack Position on row 2 (tool 3) next to an
    Objective; CCP anywhere before the mission starts (Normandy p.13, 5.1.7); Phase Lines between rows."""
    if not state.is_v4(s):
        raise rules.Violation("Tactical Controls only in campaign missions")
    if not state.in_setup(s):
        raise rules.Violation("Tactical Controls only before turn 1; later only CCP via 4.2.1l [RULE 2.4.1 p.10]")
    z = s.setdefault("ziele", {})
    kind = args[0]
    prot = []
    if kind == "phaseline":
        n, row = args[1], int(args[2])
        z.setdefault("phaselines", {})[n] = row
        prot.append(f"Phase Line {n} between row {row} and {row + 1}")
    elif kind == "route":
        nr, kid = int(args[1]), args[2]
        c = state.card(s, kid)
        if (
            not s.get("patrouille_mission")
            or nr not in (1, 2, 3, 4)
            or not 2 <= c["reihe"] <= state.top_row(s)
            or c.get("ausserhalb")
        ):
            raise rules.Violation("objective route <1-4> <card in rows 2-4> (Combat Patrol) [Normandy M3 MSR 2]")
        r = z.setdefault("route", {})
        if kid in [v for k_, v in r.items() if int(k_) != nr]:
            raise rules.Violation("Route Points on four different cards [MSR 2]")
        r[str(nr)] = kid
        prot.append(f"Route Point {nr} on {kid}; enter in order 1-4, remove the marker on entering [MSR 2]")
    elif kind == "konzentration":
        # L56: Artillery Concentration before the mission starts or before each patrol (7.16.5, Normandy M3 p.24)
        if len(args) < 3:
            raise rules.Violation("objective concentration <card> <fire asset, e.g. '105mm HE'> [RULE 7.16.5 p.59]")
        kid, ag = args[1], " ".join(args[2:])
        state.card(s, kid)
        if ag not in (s.get("fm_werte") or {}):
            raise rules.Violation(f"Unknown fire asset: {ag}; available: {', '.join(s.get('fm_werte', {}))}")
        s.setdefault("target_marker", {})[commands.target_marker_key(s, ag)] = kid
        s["konzentration_gesetzt"] = True
        prot.append(
            f"Artillery Concentration: Target marker {commands.target_marker_key(s, ag)} on {kid}; Call for Fire of this fire asset on {kid} +1 card [RULE 7.16.5 p.59, Normandy M3 p.24]"
        )
    else:
        kid = args[1]
        c = state.card(s, kid)
        top = state.top_row(s)
        if kind in ("primaer", "sekundaer"):
            if c["reihe"] != top or c.get("staging"):
                raise rules.Violation(
                    f"Primary/Secondary only on the top mission row (tool row {top}) [Normandy M1 p.16, M2 p.20]"
                )
            other = z.get("sekundaer" if kind == "primaer" else "primaer")
            if other == kid:
                raise rules.Violation("Primary and Secondary on different cards")
        elif kind == "ap":
            if c["reihe"] != top - 1:
                raise rules.Violation(
                    f"Attack Position on the second-to-last mission row (tool row {top - 1}) [Normandy M1 p.16, M2 p.20]"
                )
            objs = [z.get("primaer"), z.get("sekundaer")]
            if not any(o_ and geometry.adjacent(s, kid, o_) for o_ in objs):
                raise rules.Violation(
                    "Attack Position must be adjacent to Primary or Secondary; place the Objectives first [Normandy M1 p.16]"
                )
        elif kind == "ccp":
            s["ccp"] = kid
        elif kind == "cop":
            if c["reihe"] != 2 or not s.get("patrouille_mission"):
                raise rules.Violation(
                    "Combat Outpost on a card in row 2 (Combat Patrol mission) [Normandy M3 p.24, 2.6.1]"
                )
            if c.get("pc"):
                c["pc"] = None
                s.get("pc_start", {}).pop(kid, None)
                prot.append(f"PC marker removed from {kid} (no PC on the COP) [Normandy M3 p.24, 2.6.1]")
            n_fh = sum(1 for cv in c.get("cover", []) if cv["typ"] == "Foxholes")
            for _ in range(max(0, 2 - n_fh)):
                prot.append(f"Foxholes marker {commands.new_cover_marker(s, kid, 'Foxholes', 1)} (+1) on {kid}")
        else:
            raise rules.Violation(
                "objective primary|secondary|ap|ccp|cop <card> | objective route <1-4> <card> | objective phaseline <n> <row>"
            )
        if kind != "ccp":
            z[kind] = kid
        prot.append(
            f"{ {'primaer': 'Primary Objective', 'sekundaer': 'Secondary Objective', 'ap': 'Attack Position', 'ccp': 'Casualty Collection Point', 'cop': 'Combat Outpost'}[kind] } on {kid}"
        )
    state.save_state(s, "Tactical Control: " + "; ".join(prot), "2.4.1 p.10")
    briefing.print_board(prot, s)


VALUE_FIELDS = ("vof_rating", "reichweite", "ft_vof", "ft_reichweite", "erfahrung", "steps")


def cmd_values(s, args):
    """Enter unverified counter values from the components (setup only). Every entry is logged."""
    if not state.in_setup(s):
        raise rules.Violation("Enter counter values only before turn 1 or during Reattempt preparation")
    n = args[0]
    e = state.unit(s, n)
    prot = []
    for a in args[1:]:
        k, v = a.split("=", 1)
        if k not in VALUE_FIELDS:
            raise rules.Violation(f"Field {k} cannot be changed; allowed: {', '.join(VALUE_FIELDS)}")
        v2 = None if v in ("null", "-") else (int(v) if k == "steps" else v)
        e[k] = v2
        prot.append(f"{n}: {k} = {v2} (from the counter)")
    state.save_state(s, "; ".join(prot), None)
    briefing.print_board(prot, s)


def setup_v4(s, n, e, o, prot):
    """Extra options of 'setup' for the campaign (CSR 1, CSR 2, 2.3.4, 4.4.1)."""
    if "--netz" in o:
        if n != s.get("co_hq"):
            raise rules.Violation('give --net with the CO HQ: setup "CO HQ" --net=radio|phone')
        if o["--netz"] not in ("funk", "telefon"):
            raise rules.Violation("--net=radio|phone")
        old = s.get("co_tac_mittel")
        s["co_tac_mittel"] = o["--netz"]
        type_new, type_old = ("EE8", "SCR536") if o["--netz"] == "telefon" else ("SCR536", "EE8")
        for m, x in s["einheiten"].items():
            for g in x.get("funk", []):
                if g["netz"] == "CO TAC" and g["typ"] == type_old:
                    g["typ"] = type_new
        if o["--netz"] == "telefon":
            s["leitungen_pool"] = s.get("telefon_leitungen", 4) - sum(
                x.get("leitungen", 0) for x in s["einheiten"].values()
            )
        else:
            for x in s["einheiten"].values():
                x.pop("leitungen", None)
            s.pop("leitungen_pool", None)
        prot.append(
            f"CO TAC Net with {'EE8 Field Phones, ' + str(s.get('telefon_leitungen', 4)) + ' Phone Lines' if o['--netz'] == 'telefon' else 'SCR536 radio'}"
            + (f" (previously {old})" if old and old != o["--netz"] else "")
            + "; BN TAC and FD nets stay radio [CSR 1 p.13, 4.3.3 p.27]"
        )
    if "--moerser" in o:
        if o["--moerser"] not in ("sektion", "teams"):
            raise rules.Violation("--mortar=section|teams")
        if s.get("moerser_wahl") == o["--moerser"]:
            pass
        elif o["--moerser"] == "teams":
            section = s["einheiten"].pop("Mtr Sec", None)
            if section is None:
                raise rules.Violation("Mtr Sec no longer in play")
            for tn, td in s.get("reserve_einheiten", {}).items():
                te = copy.deepcopy(td)
                te.update(
                    karte=section["karte"],
                    platoon=section.get("platoon"),
                    attached_an=list(section.get("attached_an", [])),
                    bereich="offen",
                    status=[],
                )
                te["funk"] = []
                s["einheiten"][tn] = te
            s["mtr_sec_funk_frei"] = section.get("funk", [])
            prot.append(
                "CSR 2: three 1-step Mortar Teams 1/Mtr, 2/Mtr, 3/Mtr (G!, 4 Mtr ammo each, each carries 2) instead of the Section; the Section radio "
                "can be assigned freely: setup <unit> --device=SCR536 [CSR 2 p.13]"
            )
        else:
            if "Mtr Sec" in s["einheiten"]:
                pass
            else:
                teams = [tn for tn in s.get("reserve_einheiten", {}) if tn in s["einheiten"]]
                ref = s["einheiten"][teams[0]] if teams else {}
                for tn in teams:
                    del s["einheiten"][tn]
                section = copy.deepcopy(s["aufbau_einheiten"]["Mtr Sec"])
                section.update(
                    karte=ref.get("karte"), platoon=ref.get("platoon"), attached_an=list(ref.get("attached_an", []))
                )
                section["funk"] = s.pop("mtr_sec_funk_frei", section.get("funk", []))
                s["einheiten"]["Mtr Sec"] = section
            prot.append("CSR 2: 60mm Mortar Section (H, 3 steps, 4 Mtr ammo, abstracted carriers) [CSR 2 p.13]")
        s["moerser_wahl"] = o["--moerser"]
    if "--geraet" in o:
        free = s.get("mtr_sec_funk_frei", [])
        g = [x for x in free if x["typ"] == o["--geraet"]]
        if not g:
            raise rules.Violation(
                "Only the Mortar Section's device can be assigned freely, and only if teams were chosen [CSR 2 p.13]"
            )
        free.remove(g[0])
        e.setdefault("funk", []).append(g[0])
        prot.append(f"{n} receives {g[0]['typ']} {g[0]['netz']} (Section device, CSR 2)")
    if "--asset" in o:
        pool = s.setdefault("assets_pool", {})
        for type_ in o["--asset"].split(","):
            if pool.get(type_, 0) <= 0:
                raise rules.Violation(
                    f"Asset {type_} not (or no longer) in the pool: {', '.join(f'{k} {v}' for k, v in pool.items() if v)} [Normandy p.13]"
                )
            if type_ == "Rifle Grenade":
                if e["typ"] != "Squad" and not state.is_lat(e):
                    s.setdefault("_hinweise", []).append("Rifle Grenade: intended for Rifle Squads (Unit Guide p.11)")
                pl = e.get("platoon")
                already = [
                    m
                    for m, x in s["einheiten"].items()
                    if "Rifle Grenade" in x.get("assets", []) and x.get("platoon") == pl
                ]
                if pl and already:
                    raise rules.Violation(
                        f"Rifle Grenades: at most 1 per platoon, platoon {pl} already has one ({already[0]}) [Normandy p.13]"
                    )
            pool[type_] -= 1
            e.setdefault("assets", []).append(type_)
            prot.append(f"{n} receives asset {type_} [2.3.4 p.10]")
    if "--leitungen" in o:
        if s.get("co_tac_mittel") != "telefon":
            raise rules.Violation(
                'Phone Lines only if the CO TAC Net uses telephones: setup "CO HQ" --net=telefon [CSR 1 p.13]'
            )
        k = int(o["--leitungen"])
        free = s.get("leitungen_pool", 0) + e.get("leitungen", 0)
        if k > free:
            raise rules.Violation(f"Only {free} Phone Lines available [CSR 1 p.13]")
        s["leitungen_pool"] = free - k
        e["leitungen"] = k
        prot.append(f"{n} carries {k} Phone Line(s); lays one each time it leaves a card [4.3.4 p.28]")
    if "--pyro" in o:
        type_, code = o["--pyro"].split(":", 1)
        if type_ not in rules.PYRO_AERIAL + rules.PYRO_COLOR:
            raise rules.Violation(f"Signal devices: {', '.join(rules.PYRO_AERIAL[:4] + rules.PYRO_COLOR)} [4.4.1 p.30]")
        if s.get("patrouille_mission"):
            # [RULE 4.4.1 p.30] Patrol Mission Pyrotechnic Signal Options
            if code not in rules.PYRO_CODES_PAT and not re.fullmatch(r"M2RP[1-4]", code):
                raise rules.Violation("code from the patrol list: CF, M2RP<1-4>, M2PO, M2S [4.4.1 p.30]")
        elif code not in rules.PYRO_CODES_OFF and not re.fullmatch(r"XPL\d+", code):
            raise rules.Violation(
                f"Code from the offensive list: {', '.join(rules.PYRO_CODES_OFF)}, XPL<n> [4.4.1 p.30]"
            )
        s.setdefault("pyro_belegung", {})[type_] = code
        prot.append(f"Mission Log: {type_} = {code} [4.4.1 p.30]")


def setup_notes_v4(s):
    """L77 [RULE 2.3.4 p.10]: assets not handed out, signal assets without an order, CCP missing (not blocking)."""
    h = []
    remainder = {k: v for k, v in (s.get("assets_pool") or {}).items() if v}
    if remainder:
        h.append(
            "assets still in the pool: "
            + ", ".join(f"{k} {v}" for k, v in remainder.items())
            + " (setup <unit> --asset=<type>)"
        )
    sig = {"RSP", "RSC", "GSP", "GSC", "Red Smoke", "Green Smoke", "Yellow Smoke", "Purple Smoke"}
    distributed = {a for e in s["einheiten"].values() for a in e.get("assets", []) if a in sig}
    without = sorted(distributed - set(s.get("pyro_belegung") or {}))
    if without:
        h.append("signals without an order: " + ", ".join(without) + " (setup <unit> --pyro=<type>:<code>, 4.4.1)")
    if "ccp" in s.get("ziele", {}) and not (s.get("ccp") or s["ziele"].get("ccp")):  # objective ccp writes s["ccp"]
        h.append("CCP: objective ccp <card> (5.1.7)")
    return h


def check_setup_v4(s):
    """Before the first 'phase next': mandatory mission choices done?"""
    f = []
    without = [
        n
        for n, e in s["einheiten"].items()
        if e["seite"] == "US"
        and not e.get("karte")
        and (not s.get("patrouille_mission") or n in (s.get("patrouille") or {}).get("mitglieder", []))
    ]
    if without:
        f.append("no starting card: " + ", ".join(without) + " (setup <unit> <11-14>)")
    if s.get("co_tac_mittel") is None and "telefon_leitungen" in s:
        f.append('CSR 1: setup "CO HQ" --net=radio|phone')
    if s.get("moerser_wahl") is None and s.get("reserve_einheiten"):
        f.append('CSR 2: setup "Mtr Sec" --mortar=section|teams')
    z = s.get("ziele", {})
    for k, t in (("primaer", "Primary Objective"), ("sekundaer", "Secondary Objective"), ("ap", "Attack Position")):
        if k in z and not z.get(k):
            f.append(f"{t}: objective {({'primaer': 'primary', 'sekundaer': 'secondary'}).get(k, k)} <card>")
    if s.get("patrouille_mission"):
        if s.get("licht") is None:
            f.append("Patrol visibility: draw R#4 (1=+2 ... 4=+5), fof.py visibility <light> [Normandy M3 p.24, M3-2]")
        z = s.get("ziele", {})
        if not z.get("cop"):
            f.append("Combat Outpost: objective cop <card in row 2> [p.24]")
        if not z.get("primaer"):
            f.append("Primary Objective: objective primary <card in row 4> [p.24]")
        if len(z.get("route", {})) < 4:
            f.append("Route Points: objective route <1-4> <card in rows 2-4> [MSR 2]")
        if not (s.get("patrouille") or {}).get("platoon"):
            f.append("Patrol: patrol start <1|2|3> [--with=..] [MSR 1]")
    oh = [k for k, c in s["karten"].items() if not c.get("staging") and not c.get("terrain")]
    if oh:
        f.append("Terrain missing: " + ", ".join(sorted(oh)) + " (terrain <card> <type>)")
    nv = [
        n
        for n, e in s["einheiten"].items()
        if e["seite"] == "US"
        and e["typ"] in ("Squad", "Weapons Team")
        and e.get("vof_rating") is None
        and (e.get("karte") or not s.get("patrouille_mission"))
    ]
    if nv:
        f.append("VOF missing (from the counter): " + ", ".join(nv) + " (set <unit> vof_rating=.. reichweite=..)")
    return f
