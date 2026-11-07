"""Pick Up (4.2.2h, 5.1.6): ammo, Phone Lines, casualties, devices, getting on and off a jeep. Split from commands.py (L556)."""

from __future__ import annotations

from . import combat, commands, rules, state


def pick_up(s, z, name, what, prot):
    """4.2.2h p.23 Pick up: pick up a Casualty or radio from the card (5.1.6B)."""
    c = state.card(s, z["karte"])
    if what.lower() == "casualty":
        if not c.get("casualties"):
            raise rules.Violation(f"There is no friendly Casualty on {z['karte']} [RULE 5.1.6 p.33]")
        c["casualties"] -= 1
        z["traegt_casualties"] = z.get("traegt_casualties", 0) + 1
        prot.append(
            f"{name} picks up a Casualty (marker under the counter or in the Assets box) [5.1.6B p.33, FM1 p.43]"
        )
        return
    ground = c.get("assets_boden", [])
    if what in ground:  # [RULE 5.1.6B p.33] pick up a dropped Asset (e.g. Rifle Grenade, smoke)
        ground.remove(what)
        z.setdefault("assets", []).append(what)
        prot.append(f"{name} picks up Asset {what} from the card [5.1.6B p.33]")
        return
    lies = [g for g in c.get("assets", []) if g["typ"] == what or f"{g['typ']} {g['netz']}" == what]
    if not lies:
        raise rules.Violation(
            f"On {z['karte']} there is no device '{what}'" + (f"; on the ground: {', '.join(ground)}" if ground else "")
        )
    if lies[0].get("schaden_offen"):
        raise rules.Violation(
            f"First draw R# 1/2 for {lies[0]['typ']}: fof.py radio damage {z['karte']} {lies[0]['typ']} intact|destroyed [RULE 4.3.5 p.30]"
        )
    c["assets"].remove(lies[0])
    z.setdefault("funk", []).append({"typ": lies[0]["typ"], "netz": lies[0]["netz"]})
    prot.append(f"{name} picks up {lies[0]['typ']} {lies[0]['netz']} [4.3.5 p.30, 5.1.6B p.33]")


def order_pick_up(s, ctx):
    """Order handler for: akt == '4.2.2h'"""
    what = commands.text_opt(ctx.o, "--was")
    if not what:
        # L211: without --what nothing was picked up, but the Command was booked; name what lies on the card
        c = ctx.zk
        items = list(c.get("assets_boden", []))
        items += [f"{g['typ']} {g['netz']}" if g.get("netz") else g["typ"] for g in c.get("assets", [])]
        if c.get("casualties"):
            items.append(f"Casualty:{c['casualties']}")
        items += [f"{k}:{v}" for k, v in (c.get("munition") or {}).items() if v]
        if c.get("leitung_assets"):
            items.append(f"Leitung:{c['leitung_assets']}")
        raise rules.Violation(
            f"Pick Up: specify --what=<item>[,<item>]; on {ctx.z['karte']}: {', '.join(items) if items else 'nothing to pick up'} [RULE 5.1.6 p.32]"
        )
    # L71 [RULE 5.1.6 p.32] 'One Command to have a unit pick up any ammo, assets and casualties in their card area':
    # several items in one order, comma separated. L239 (review M12): split first, then dispatch every part
    # ('MG:2' ammo, 'Casualty:<n>', 'Leitung:<n>', assets and radios)
    for part in [x.strip() for x in what.split(",") if x.strip()]:
        pick_up_item(s, ctx, part)
    if ctx.z.get("traegt_casualties", 0) > state.steps(ctx.z):
        raise rules.Violation(
            f"{ctx.target_name} can carry at most {state.steps(ctx.z)} casualties (1 per step) [RULE 5.1.6A p.32]"
        )
    commands.mark(ctx.z, rules.EXPOSED)
    ctx.prot.append(f"{ctx.target_name}: pick up/load, Exposed [5.1.6]")


def embark_jeep(s, ctx):
    """L454/L528 [4.2.2h p.23, 10.8.1, 10.8.8, Normandy CSR 1 p.13, Naktong p.12] get on or off a crewless jeep.
    The Arty Jeep carries a single step, the Arty FO; the company Jeep carries infantry up to its chart capacity."""
    from . import vehicles

    z, n = ctx.z, ctx.target_name
    if z.get("an_bord"):
        jeep = z.pop("an_bord")
        if s["einheiten"].get(jeep, {}).get("arty_jeep"):
            ctx.prot.append(
                f"{n} gets off the {jeep} on {z['karte']}; the SCR610 stays mounted in the jeep and works only on board [Normandy CSR 1 p.13]"
            )
        else:
            vehicles.update_jeep_experience(s, jeep)
            ctx.prot.append(f"{n} gets off the {jeep} on {z['karte']} [4.2.2h, 10.8.1]")
        return
    jeeps = [m for m in state.units_on(s, z["karte"], "US") if vehicles.crewless_jeep(s["einheiten"][m])]
    if not jeeps:
        raise rules.Violation(f"No jeep on {z['karte']} [10.8.1]")
    arty = [m for m in jeeps if s["einheiten"][m].get("arty_jeep")]
    company = [m for m in jeeps if s["einheiten"][m].get("kompanie_jeep")]
    if arty and any(g.get("eingebaut") == arty[0] for g in z.get("funk", [])):
        if vehicles.passengers(s, arty[0]):
            raise rules.Violation(f"{arty[0]} is already occupied [Normandy CSR 1 p.13]")
        z["an_bord"] = arty[0]
        z["bereich"] = "offen"
        ctx.prot.append(f"{n} gets on the {arty[0]} [4.2.2h, 10.8.1]")
        return
    if not company:
        raise rules.Violation(
            f"The {arty[0]} can only carry a single step, the Arty FO [Normandy CSR 1 p.13 'this Jeep can only carry a single step (the Arty FO)']"
        )
    if vehicles.is_vehicle(z):
        raise rules.Violation(f"{n} is a vehicle; only infantry rides on the jeep [10.8.1]")
    cap = vehicles.chart(s["einheiten"][company[0]])[8]
    free = [
        m
        for m in company
        if sum(state.steps(s["einheiten"][p]) for p in vehicles.passengers(s, m)) + state.steps(z) <= cap
    ]
    if not free:
        aboard = "; ".join(f"{m}: {', '.join(vehicles.passengers(s, m)) or 'empty'}" for m in company)
        raise rules.Violation(
            f"{n} ({state.steps(z)} step(s)) does not fit: a jeep carries {cap} steps ({aboard}) [10.8.1, Vehicle and Anti-Tank Weapons Chart]"
        )
    z["an_bord"] = free[0]
    z["bereich"] = "offen"
    vehicles.update_jeep_experience(s, free[0])
    ctx.prot.append(
        f"{n} gets on the {free[0]} [4.2.2h, 10.8.1]; passengers fire and are fired upon like infantry, Exposed whenever the jeep moves"
    )


def pick_up_item(s, ctx, part):
    """One item of a Pick Up order (L239)."""
    head, _, count = part.partition(":")
    if count and head in rules.AMMO_CAPACITY:
        n = rules.int_value(count, f"{head} ammo count")
        combat.ammo_pick_up(s, ctx.z, ctx.target_name, f"{head}:{n}", ctx.prot)
    elif head.lower() in ("leitung", "line"):  # L549 (review C12): case and English word as for casualty/jeep
        nz = rules.int_value(count, "Phone Line count") if count else 1
        if ctx.zk.get("leitung_assets", 0) < nz:
            raise rules.Violation(f"On {ctx.z['karte']} there are not {nz} Phone Line(s)")
        ctx.zk["leitung_assets"] -= nz
        ctx.z["leitungen"] = ctx.z.get("leitungen", 0) + nz
        ctx.prot.append(f"{ctx.target_name} picks up {nz} Phone Line(s) [4.3.4, 5.1.6]")
    elif head.lower() in ("jeep", "arty jeep"):
        embark_jeep(s, ctx)
    elif head.lower() == "casualty" and count:
        for _ in range(rules.int_value(count, "casualty count")):
            pick_up(s, ctx.z, ctx.target_name, "Casualty", ctx.prot)
    else:
        pick_up(s, ctx.z, ctx.target_name, part, ctx.prot)
