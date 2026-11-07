"""Grenade Attacks (7.10), Grenade Miss, the free response throw (7.10.5) and Jam (7.12). Split from commands.py (L556)."""

from __future__ import annotations

from . import briefing, campaign, combat, commands, comms, enemy, fire, geometry, options, rules, state


def grenade_stack(s, name):
    """[RULE 7.10.1 p.54] Target of a Grenade Attack: one unit out of cover or the whole stack under its Cover marker."""
    f = state.unit(s, name)
    if f.get("bereich", "offen") == "offen":
        return [name]
    return [m for m in state.units_on(s, f["karte"], f["seite"]) if s["einheiten"][m].get("bereich") == f["bereich"]]


def grenade_back_note(s, thrower, target, success, name=None):
    """7.10.5 Free Grenade Attack Response. K31 (BGG Shonai_Dweller 3563964, 3517434, 3780916): only against a Point Blank
    attack from the same card; never from inside a Bunker/Pillbox, never while Pinned; a LAT only with a VOF and only after
    a successful attack; the attacker must be Spotted."""
    who = name or target.get("typname", "Target")
    if thrower["karte"] != target["karte"]:
        return f"{who}: no response throw, the attack did not come from the same card (Point Blank only) [7.10.5, K31]"
    if not (thrower["seite"] == "US" or thrower.get("spotted")):
        return f"{who}: no response throw, the attacker is Unspotted [7.10.5]"
    if state.pinned(target):
        return f"{who}: no response throw, Pinned [7.10.5, K31]"
    cv = geometry.cover_marker(s, target)
    if cv and (cv["typ"] in rules.STRUCTURES or "Bunker" in cv["typ"]):
        return f"{who}: no response throw from the {cv['typ']} (no Point Blank attack from inside) [5.3.2, 7.10.5, K31]"
    if target["typ"] not in ("Paralyzed Team", "Litter Team", "Fire Team", "Assault Team"):
        return f"{who}: free response throw at the attacker (Good Order, same card) [7.10.5]"
    if target.get("vof_rating") and success:
        return f"{who} (unpinned LAT with VOF): free response throw at the attacker [7.10.5]"
    return f"{who}: no response throw (a LAT only with a VOF and only after a successful attack) [7.10.5]"


def grenade_back_notes(s, thrower, names, success, prot, thrower_name=None):
    """7.10.5 for every unit of the attacked stack (rule note: every eligible unit of a stack responds); one line at range.
    Eligible responses are recorded in s['granate_antworten'] for 'grenade response' (L144)."""
    if names and s["einheiten"][names[0]]["karte"] != thrower["karte"]:
        prot.append("No response throw: the attack did not come from the same card (Point Blank only) [7.10.5, K31]")
        return
    tn = thrower_name or next((k for k, v in s["einheiten"].items() if v is thrower), None)
    for m in names:
        note = grenade_back_note(s, thrower, s["einheiten"][m], success, m)
        prot.append(note)
        if "free response throw" in note and tn:
            s.setdefault("granate_antworten", []).append(
                {"werfer": m, "angreifer": tn, "karte": thrower["karte"], "zug": s["zug"], "phase": s["phase"]}
            )
            prot[-1] += f': fof.py grenade response "{m}" --success=yes|no'


def open_grenade_response(s, name, e):
    """L231 (review H9): the first response record of `name` whose attacker is still on the card; records of earlier
    turns and records whose attacker left the card (or play) lapse silently, they no longer block newer ones."""
    records = s.get("granate_antworten", [])
    live = []
    for x in records:
        if x.get("zug", s["zug"]) != s["zug"]:
            continue  # response throws are booked right after the attack, never in a later turn [7.10.5]
        att = s["einheiten"].get(x["angreifer"])
        if x["werfer"] == name and (not att or att["karte"] != e["karte"]):
            continue
        live.append(x)
    records[:] = live
    for x in records:
        if x["werfer"] == name:
            return x
    raise rules.Violation(
        f"{name} has no open free response throw (7.10.5); responses are offered right after a Point Blank Grenade Attack"
    )


def apply_grenade(s, ze, value, critical, prot, rule):
    """[RULE 7.10.1 p.54, 7.10.3 p.55] Grenade VOF on one unit out of cover or on the whole stack under its Cover
    marker; a Critical Hit under cover removes the cover benefit (combined marker, E61), out of cover it is a second
    Grenade VOF marker. L252: one loop for the order and the free response. Returns (stack, under_cover)."""
    f = state.unit(s, ze)
    under = f.get("bereich", "offen") != "offen"
    stack = grenade_stack(s, ze)
    for m in stack:
        g = s["einheiten"][m]
        g.setdefault("grenade", []).append(value)
        if critical and under:
            g["grenade_critical"] = True
        elif critical:
            g["grenade"].append(value)
    where = f" (stack under {f['bereich']})" if under else ""
    prot.append(f"Grenade VOF {value} on {', '.join(stack)}{where} (cumulative) [{rule}]")
    if critical:
        prot.append(
            f"Critical Hit: use the combined Grenade/Critical Hit marker instead of the plain Grenade VOF marker (E61); the stack loses the benefit of cover {f['bereich']} in Combat Effects [7.10.3 p.55]"
            if under
            else f"Critical Hit: a second Grenade VOF marker on {ze} (both count) [7.10.3 p.55]"
        )
    return stack, under


def cmd_grenade(s, args):
    """grenade response <responder> --success=yes|no [--critical=yes]: 7.10.5 Free Grenade Attack Response, no Command,
    booked right after the attack (also in the Enemy Activity Phase). L144. The response is always Point Blank (K31),
    where the Jam icon has no effect (7.12): no --jam (L546, review C4)."""
    usage = 'grenade response "<responder>" --success=yes|no [--critical=yes]'
    if not args or args[0] not in ("antwort", "response"):
        raise rules.Violation(usage)
    rules.need(args, 2, usage)
    name = args[1]
    o = options.parse_opts(args[2:])
    e = state.unit(s, name)
    rec = open_grenade_response(s, name, e)
    if o.get("--erfolg") not in ("ja", "nein"):
        n_cards, who, base = comms.card_count(s, "4.2.4d", e, e)
        n_cards += 1 if e["seite"] == "Feind" and enemy.leader_present(s, e) else 0
        raise rules.Violation(
            f"{name}: free response throw at {rec['angreifer']}: draw {n_cards} Action cards (base {base}, experience {comms.experience(who)}"
            + (", Leader +1" if e["seite"] == "Feind" and enemy.leader_present(s, e) else "")
            + "), Grenade symbol; then --success=yes|no [RULE 7.10.5 p.55] "
            + draw_watch(s, "grenade", e, False)
        )
    prot = [f"{name}: free response throw at {rec['angreifer']} (no Command) [7.10.5]"]
    s["granate_antworten"].remove(rec)
    if o.get("--jam") == "ja":
        prot.append("Jam icon: no effect at Point Blank [7.12]")
    if o["--erfolg"] == "ja":
        # L257 (review M27): one default for the enemy Grenade VOF (Normandy p.13: German Grenade Attacks are -4 too)
        default = -4 if e["seite"] == "US" else s.get("granate_vof", rules.GRENADE_VOF_DEFAULT)
        value = options.int_opt(o, "--wert", "Grenade VOF value", default)
        apply_grenade(s, rec["angreifer"], value, o.get("--kritisch") == "ja", prot, "7.10.1, 7.10.5")
        if e["seite"] == "US" and state.is_v4(s) and e["typ"] not in ("Fire Team", "Assault Team"):
            campaign.book_xp(
                s,
                campaign.xp_table(s, "pb_granate") or 1,
                f"successful Point Blank Grenade Attack ({name}, response)",
                prot,
            )
    else:
        prot.append(place_grenade_miss(s, e["karte"]))
    ak = fire.update_activity(s)
    if ak:
        prot.append(ak)
    state.save_state(s, "; ".join(prot), "7.10.5 p.55")
    briefing.print_board(prot, s)


def grenade_expires(s, e, name, prot):
    """7.10.4: if the target of a successful Grenade Attack moves before 3.7.4 (card change or within the card), it becomes a Grenade Miss on the original card."""
    if e.get("grenade"):
        rest = [
            m
            for m in state.units_on(s, e["karte"], e["seite"])
            if m != name and s["einheiten"][m].get("grenade") and s["einheiten"][m].get("bereich") == e.get("bereich")
        ]
        e["grenade"] = []
        e.pop("grenade_critical", None)
        if rest:
            # K32: the target was the stack; while part of it stays, the Grenade marker stays with it, no Grenade Miss
            prot.append(
                f"{name} leaves the grenaded stack; the Grenade marker stays with {', '.join(rest)} [7.10.4, K32]"
            )
            return
        state.card(s, e["karte"])["grenade_miss"] = True
        prot.append(
            f"Grenade marker on {name} becomes Grenade Miss (-1) on {e['karte']}: target moved before 3.7.4 [7.10.4]"
        )


def jam_prone(e):
    """[RULE 7.12 p.56] A, G! and H weapons teams, AT guns, A squads with ammo tracking."""
    if rules.FIRE_TEAM_SIDE in e.get("status", []):
        return False  # L549 (review C11): the Fire Team side is S rated, no jam-prone weapon
    r = e.get("vof_rating")
    if e.get("out_of_ammo"):
        return False  # L176, K43 [RULE 7.18.2 p.61]: with an Out of Ammo marker the unit is S rated, whatever the counter shows
    if e["typ"] in ("Weapons Team", "AT Gun") and r in ("A", "G", "H"):
        return True
    # L174, K42: G! superscript (S G! rocket teams such as the Bazooka) is a G!-rated weapons team, also after the rockets ran out
    if e["typ"] == "Weapons Team" and (e.get("grenade_ranged") or e.get("rkt_leer")):
        return True
    return e["typ"] == "Squad" and r == "A" and bool(e.get("munition"))


def draw_watch(s, kind, e, ranged=False, skill=False):
    """L153: what to look for on the drawn Action cards besides the success symbol, so the player does
    not miss it. kind: 'cf' Concentrate Fire, 'grenade' Grenade Attack, 'cff' Call for Fire, 'spot', 'mine', 'other'."""
    w = []
    if kind == "cf":
        w.append("2 or more Crosshairs = Critical Hit (--critical=yes) [7.11.4]")
        if jam_prone(e):
            w.append(
                "Jam icon = weapon malfunction: cancels every success, unit leaves play, its steps become Fire Teams (--jam=yes) [7.12]"
            )
        else:
            w.append("Jam icon: no malfunction for this unit, but it never counts as Crosshairs [7.11.3, 7.12]")
    elif kind == "grenade":
        w.append("2 or more Grenade icons = Critical Hit (--critical=yes) [7.10.3]")
        if ranged and jam_prone(e):
            w.append(
                "Jam icon = weapon malfunction (ranged Grenade Attack of a G!/A/H unit): cancels every success, unit leaves play, steps become Fire Teams (--jam=yes) [7.12]"
            )
        elif ranged:
            w.append("Jam icon: no effect for this unit [7.12]")
        else:
            w.append("Jam icon: no effect at Point Blank [7.12]")
    elif kind == "cff":
        w.append("Burst with 'Short' takes precedence over every other card: fire lands short (--short=yes) [7.16.4]")
    elif kind == "spot":
        w.append("Jam icon has no effect on spotting [8.5]")
    elif kind == "mine":
        w.append("multi-burst and Short also count as a Burst [7.9.1]")
    if skill:
        w.append("Auto skill: success is certain, the cards are still drawn for Critical Hit and Jam [12.7]")
    return ("WATCH: " + "; ".join(w) + ".") if w else ""


def jam(s, n, prot):
    """[RULE 7.12 p.56] Jam: unit immediately out of play, its steps become generic Fire Teams; success of the attempt is lost."""
    e = s["einheiten"][n]
    new_units = []
    for _ in range(state.steps(e)):
        nn = commands.new_name(s, "Fire Team")
        s["einheiten"][nn] = combat.new_lat(e, "Fire Team", n)
        s["einheiten"][nn]["status"] = []
        new_units.append(nn)
    combat.remove_from_play(
        s,
        n,
        prot,
        f"JAM: weapon out of action, steps become {', '.join(new_units)}",
        successor=new_units[0] if new_units else None,
    )
    prot.append("Jam cancels any success of this attempt [7.12 p.56]")
    fire.open_fire(s, prot, only=new_units)  # L178 [RULE 6.1.1 p.39]: the new Fire Teams open fire at once


def check_grenade(s, z, target_name, o):
    """7.10.1: legality of a Grenade Attack (before the card draw and when booking). v4: Rifle Grenade (7.6), Mortar Team (7.3), ammo."""
    zt = o.get("--ziel", z["karte"])
    state.card(s, zt)
    # L549 (review C11): the G! rating of the side the counter shows (a G!/A team on its S Fire Team side is not G!)
    g_ranged = not state.fire_team_side(z) and (fire.current_vof_rating(z, False) == "G" or z.get("grenade_ranged"))
    rg = state.is_v4(s) and "Rifle Grenade" in z.get("assets", []) and not g_ranged
    if zt != z["karte"] and not g_ranged and not rg:
        raise rules.Violation("Grenade Attack without G! rating only Point Blank (own card) [RULE 7.10.1 p.54]")
    if zt != z["karte"]:
        if rg:
            hi = rules.RANGE_CARDS.get(s.get("rifle_grenade_reichweite", "C"), 1)
            cv = geometry.cover_marker(s, z)
            if cv and cv["typ"] in rules.NO_FIRE_FROM_COVER:  # L253: one constant instead of spelled-out tuples
                raise rules.Violation(
                    "Rifle Grenades cannot be fired from Building/Bunker/Cave/Pillbox cover, nor from Upper Story/Church Tower (E55) [RULE 7.6 p.54, 5.2.2B p.36]"
                )
            if (
                geometry.distance(s, z["karte"], zt) > hi
                or not geometry.los(
                    s, z["karte"], zt, ha=geometry.height_bonus(s, z), hb=geometry.card_height_bonus(s, zt, "Feind")
                )[0]
            ):
                raise rules.Violation(
                    f"Rifle Grenade: target in LOS up to {s.get('rifle_grenade_reichweite', 'C')} (range per Asset counter UNVERIFIED) [RULE 7.10.1 p.55]"
                )
        elif (
            not geometry.in_range(s, z, zt)
            or not geometry.los(
                s, z["karte"], zt, ha=geometry.height_bonus(s, z), hb=geometry.card_height_bonus(s, zt, "Feind")
            )[0]
        ):
            raise rules.Violation("Ranged Grenade Attack: target must be in LOS and range [RULE 7.10.1 p.55]")
        if not rg and combat.ammo(z) and combat.ammo(z)["typ"] in ("RKT", "RCL"):  # L480: RCL too
            cv = geometry.cover_marker(s, z)  # L97 [RULE 7.4 p.54]
            if cv and cv["typ"] in rules.NO_FIRE_FROM_COVER:
                raise rules.Violation(
                    "Rocket launchers (Bazooka/Panzerschreck/RCL) cannot fire from Building/Bunker/Cave/Pillbox cover, nor from Upper Story/Church Tower (E55); Point Blank with hand grenades stays allowed [RULE 7.4 p.54, 7.10.1 p.54]"
                )
        if combat.ammo(z) and combat.ammo(z)["punkte"] <= 0 and not rg:
            raise rules.Violation(f"{target_name} has no ammo left for ranged Grenade Attacks [RULE 7.18.2 p.61]")
        if state.is_mortar(z):
            vb = fire.fire_position_forbidden(s, z)
            if vb or rules.EXPOSED in z["status"]:
                raise rules.Violation(vb or "Mortar with Exposed marker does not fire [RULE 7.3.1 p.53]")
        pdf_targets = {
            fire.effective_fire_target(s, m)
            for m in state.units_on(s, z["karte"], z["seite"])
            if fire.is_firing(s["einheiten"][m])
        }
        pdf_targets.discard(z["karte"])
        if pdf_targets and zt not in pdf_targets:
            raise rules.Violation(
                f"Ranged Grenade Attack must follow the card's PDF (PDF from {z['karte']} to {', '.join(sorted(pdf_targets))}); Shift Fire first [RULE 7.10.1 p.55]"
            )
        if state.units_on(s, z["karte"], "Feind"):
            raise rules.Violation("No Ranged Grenade Attack out of Point Blank combat [RULE 7.10.1 p.55]")
        if any(
            state.units_on(s, between, None if not state.is_mortar(z) else state.opponent_of_side(z["seite"]))
            for between in (geometry.line_between(s, z["karte"], zt) or [])
        ):
            raise rules.Violation(
                "Ranged Grenade Attack not through other units (mortar: over friendly units, 7.3.1) [RULE 7.10.1 p.55]"
            )
    if not commands.spotted_enemies(s, zt):
        raise rules.Violation(f"No Spotted enemy on {zt} [7.10]")
    return zt


def order_grenade_attack(s, ctx):
    """Order handler for: akt == '4.2.4d'"""
    zt = check_grenade(s, ctx.z, ctx.target_name, ctx.o)
    ze = ctx.o.get("--einheit")
    if ze:
        # L238 (review M11): like Concentrate Fire, the named target must be a Spotted enemy on the target card;
        # checked before ammo or a Rifle Grenade is spent
        commands.target_unit_check(s, zt, ze, "a Grenade Attack", "7.10.1 p.54")
    if zt != ctx.z["karte"] and state.is_v4(s):
        has_rifle = "Rifle Grenade" in ctx.z.get("assets", []) and ctx.z.get("vof_rating") != "G"
        own_ranged = bool(ctx.z.get("grenade_ranged")) and (combat.ammo(ctx.z) or {}).get("punkte", 0) > 0
        w = (commands.text_opt(ctx.o, "--waffe") or "").lower()
        if has_rifle and own_ranged and w not in ("rifle", "own"):
            # L216 [RULE 7.6 p.54]: a unit with its own ranged G! weapon (e.g. Bazooka) and a picked-up Rifle Grenade chooses
            raise rules.Violation(
                f"{ctx.target_name} has its own ranged G! weapon ({(combat.ammo(ctx.z) or {}).get('punkte', 0)} ammo) and a Rifle Grenade: --weapon=rifle|own [RULE 7.6 p.54, 7.10]"
            )
        if has_rifle and (w == "rifle" or not ctx.z.get("grenade_ranged")):
            ctx.z["assets"].remove("Rifle Grenade")
            ctx.prot.append(f"{ctx.target_name}: Rifle Grenade used up (1 shot, hit or not) [7.6 p.54]")
        elif combat.ammo(ctx.z):
            combat.ammo_use(s, ctx.target_name, ctx.z, 1, "ranged Grenade Attack", ctx.prot)  # [RULE 8.1 p.61 box]
        if state.is_mortar(ctx.z) and not fire.is_firing(ctx.z):
            ctx.z["ziel"], ctx.z["nur_pdf"] = zt, True
            ctx.prot.append(
                f"{ctx.target_name} (Mortar Team) lays its own PDF to {zt} (counts for Crossfire, removed in Clean Up) [7.3.2 p.53]"
            )
        if ctx.o.get("--jam") == "ja" and jam_prone(ctx.z):
            jam(s, ctx.target_name, ctx.prot)
            ctx.success = "nein"
            # L246: like the Concentrate Fire path, a Jam ends the attempt: no Grenade Miss marker, no Exhort for a
            # unit that left play [7.12 p.56]
            return
    if ctx.success == "ja" and zt == ctx.z["karte"] and state.is_v4(s):
        campaign.book_xp(
            s,
            campaign.xp_table(s, "pb_granate") or 1,
            f"successful Point Blank Grenade Attack ({ctx.target_name})",
            ctx.prot,
        )
    if ctx.success == "ja":
        if not ze:
            raise rules.Violation("--unit=<target enemy or cover stack>")
        # [RULE 7.10.1 p.54] "Direct a Grenade Attack at one specific unit out of cover or a stack of units under a Cover marker" (L112)
        value = options.int_opt(ctx.o, "--wert", "Grenade VOF value", rules.GRENADE_VOF_DEFAULT)
        stack, _under = apply_grenade(s, ze, value, ctx.o.get("--kritisch") == "ja", ctx.prot, "7.10.1, 7.10.6")
        grenade_back_notes(s, ctx.z, stack, True, ctx.prot)
    else:
        ctx.prot.append(place_grenade_miss(s, zt))
        grenade_back_notes(s, ctx.z, grenade_stack(s, ze) if ze else state.units_on(s, zt, "Feind"), False, ctx.prot)
        s["letzter_versuch"] = [ctx.target_name, ctx.akt, s["phase"]]


def place_grenade_miss(s, kid):
    """[RULE 7.10.4, 6.3.2 p.43] 'Place only one Miss Modifier regardless of the number of failed attempts' (L464)."""
    c = state.card(s, kid)
    if c.get("grenade_miss"):
        return f"Grenade Miss Modifier already on {kid}: no second marker, still -1 [7.10.4, 6.3.2]"
    c["grenade_miss"] = True
    return f"Grenade Miss Modifier (-1) on {kid} [7.10.4]"
