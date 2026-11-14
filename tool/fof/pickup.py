"""Pick Up (4.2.2h, 5.1.6): ammo, Phone Lines, casualties, devices, getting on and off a jeep. Split from commands.py."""

from __future__ import annotations

from . import combat, commands, migrate, rules, state


def pick_up(s, recipient, name, what, prot):
    """4.2.2h p.23 Pick up: pick up a Casualty or radio from the card (5.1.6B)."""
    c = state.card(s, recipient["card"])
    if what.lower() == "casualty":
        if not c.get("casualties"):
            raise rules.Violation(f"There is no friendly Casualty on {recipient['card']} [RULE 5.1.6 p.33]")
        c["casualties"] -= 1
        recipient["carries_casualties"] = recipient.get("carries_casualties", 0) + 1
        prot.append(
            f"{name} picks up a Casualty (marker under the counter or in the Assets box) [5.1.6B p.33, FM1 p.43]"
        )
        return
    ground = c.get("assets_ground", [])
    if what in ground:  # [RULE 5.1.6B p.33] pick up a dropped Asset (e.g. Rifle Grenade, smoke)
        ground.remove(what)
        recipient.setdefault("assets", []).append(what)
        prot.append(f"{name} picks up Asset {what} from the card [5.1.6B p.33]")
        return
    lies = [g for g in c.get("assets", []) if what in (g["type"], f"{g['type']} {g['net']}")]
    if not lies:
        raise rules.Violation(
            f"On {recipient['card']} there is no device '{what}'"
            + (f"; on the ground: {', '.join(ground)}" if ground else "")
        )
    if lies[0].get("damage_open"):
        raise rules.Violation(
            f"First draw R# 1/2 for {lies[0]['type']}: fof.py radio damage {recipient['card']} {lies[0]['type']} intact|destroyed [RULE 4.3.5 p.30]"
        )
    c["assets"].remove(lies[0])
    recipient.setdefault("radio", []).append({"type": lies[0]["type"], "net": lies[0]["net"]})
    prot.append(f"{name} picks up {lies[0]['type']} {lies[0]['net']} [4.3.5 p.30, 5.1.6B p.33]")


def order_pick_up(s, ctx):
    """Order handler for: action_id == '4.2.2h'"""
    what = commands.text_opt(ctx.o, "--what")
    if not what:
        # without --what nothing was picked up, but the Command was booked; name what lies on the card
        c = ctx.recipient_card
        items = list(c.get("assets_ground", []))
        items += [f"{g['type']} {g['net']}" if g.get("net") else g["type"] for g in c.get("assets", [])]
        if c.get("casualties"):
            items.append(f"Casualty:{c['casualties']}")
        items += [f"{k}:{v}" for k, v in (c.get("ammo") or {}).items() if v]
        if c.get("line_assets"):
            items.append(f"Line:{c['line_assets']}")
        raise rules.Violation(
            f"Pick Up: specify --what=<item>[,<item>]; on {ctx.recipient['card']}: {', '.join(items) if items else 'nothing to pick up'} [RULE 5.1.6 p.32]"
        )
    # [RULE 5.1.6 p.32] 'One Command to have a unit pick up any ammo, assets and casualties in their card area':
    # several items in one order, comma separated. split first, then dispatch every part
    # ('MG:2' ammo, 'Casualty:<n>', 'Line:<n>', assets and radios)
    for part in [x.strip() for x in what.split(",") if x.strip()]:
        pick_up_item(s, ctx, part)
    if ctx.recipient.get("carries_casualties", 0) > state.steps(ctx.recipient):
        raise rules.Violation(
            f"{ctx.target_name} can carry at most {state.steps(ctx.recipient)} casualties (1 per step) [RULE 5.1.6A p.32]"
        )
    commands.mark(ctx.recipient, rules.EXPOSED)
    ctx.prot.append(f"{ctx.target_name}: pick up/load, Exposed [5.1.6]")


def embark_jeep(s, ctx):
    """[4.2.2h p.23, 10.8.1, 10.8.8, Normandy CSR 1 p.13, Naktong p.12] get on or off a crewless jeep.
    The Arty Jeep carries a single step, the Arty FO; the company Jeep carries infantry up to its chart capacity."""
    from . import vehicles

    recipient, n = ctx.recipient, ctx.target_name
    if recipient.get("on_board"):
        jeep = recipient.pop("on_board")
        if s["units"].get(jeep, {}).get("arty_jeep"):
            ctx.prot.append(
                f"{n} gets off the {jeep} on {recipient['card']}; the SCR610 stays mounted in the jeep and works only on board [Normandy CSR 1 p.13]"
            )
        else:
            vehicles.update_jeep_experience(s, jeep)
            ctx.prot.append(f"{n} gets off the {jeep} on {recipient['card']} [4.2.2h, 10.8.1]")
        return
    jeeps = [m for m in state.units_on(s, recipient["card"], "US") if vehicles.crewless_jeep(s["units"][m])]
    if not jeeps:
        raise rules.Violation(f"No jeep on {recipient['card']} [10.8.1]")
    arty = [m for m in jeeps if s["units"][m].get("arty_jeep")]
    company = [m for m in jeeps if s["units"][m].get("company_jeep")]
    if arty and any(g.get("mounted") == arty[0] for g in recipient.get("radio", [])):
        if vehicles.passengers(s, arty[0]):
            raise rules.Violation(f"{arty[0]} is already occupied [Normandy CSR 1 p.13]")
        recipient["on_board"] = arty[0]
        recipient["area"] = "open"
        ctx.prot.append(f"{n} gets on the {arty[0]} [4.2.2h, 10.8.1]")
        return
    if not company:
        raise rules.Violation(
            f"The {arty[0]} can only carry a single step, the Arty FO [Normandy CSR 1 p.13 'this Jeep can only carry a single step (the Arty FO)']"
        )
    if vehicles.is_vehicle(recipient):
        raise rules.Violation(f"{n} is a vehicle; only infantry rides on the jeep [10.8.1]")
    cap = vehicles.chart(s["units"][company[0]])[8]
    free = [
        m
        for m in company
        if sum(state.steps(s["units"][p]) for p in vehicles.passengers(s, m)) + state.steps(recipient) <= cap
    ]
    if not free:
        aboard = "; ".join(f"{m}: {', '.join(vehicles.passengers(s, m)) or 'empty'}" for m in company)
        raise rules.Violation(
            f"{n} ({state.steps(recipient)} step(s)) does not fit: a jeep carries {cap} steps ({aboard}) [10.8.1, Vehicle and Anti-Tank Weapons Chart]"
        )
    recipient["on_board"] = free[0]
    recipient["area"] = "open"
    vehicles.update_jeep_experience(s, free[0])
    ctx.prot.append(
        f"{n} gets on the {free[0]} [4.2.2h, 10.8.1]; passengers fire and are fired upon like infantry, Exposed whenever the jeep moves"
    )


def pick_up_item(s, ctx, part):
    """One item of a Pick Up order."""
    head, _, count = part.partition(":")
    if count and head in rules.AMMO_CAPACITY:
        n = rules.int_value(count, f"{head} ammo count")
        combat.ammo_pick_up(s, ctx.recipient, ctx.target_name, f"{head}:{n}", ctx.prot)
    elif head.lower() in (
        "line",
        *migrate.german("line"),
    ):  # case and English word as for casualty/jeep
        number = rules.int_value(count, "Phone Line count") if count else 1
        if ctx.recipient_card.get("line_assets", 0) < number:
            raise rules.Violation(f"On {ctx.recipient['card']} there are not {number} Phone Line(s)")
        ctx.recipient_card["line_assets"] -= number
        ctx.recipient["lines"] = ctx.recipient.get("lines", 0) + number
        ctx.prot.append(f"{ctx.target_name} picks up {number} Phone Line(s) [4.3.4, 5.1.6]")
    elif head.lower() in ("jeep", "arty jeep"):
        embark_jeep(s, ctx)
    elif head.lower() == "casualty" and count:
        for _ in range(rules.int_value(count, "casualty count")):
            pick_up(s, ctx.recipient, ctx.target_name, "Casualty", ctx.prot)
    else:
        pick_up(s, ctx.recipient, ctx.target_name, part, ctx.prot)
