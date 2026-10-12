"""Enemy behaviour: activity check hierarchy, enemy actions, snipers, spotters, leaders (8.x)."""

import types

from . import briefing, combat, commands, comms, contact, fire, geometry, options, rules, state


OFFENSIVE_TACTICS = ("Offensive Assault", "Assault", "Overrun")


def enemy_row(s, n):
    """v4 wrapper: Sniper/Spotter/Out-of-Ammo (8.8, 8.10, 8.11), With Leader column (8.9), Offensive hierarchy (counterattack), G! unit without PDF."""
    e = s["einheiten"][n]
    if state.is_v4(s) or s.get("feind_taktik") in OFFENSIVE_TACTICS:
        z4 = enemy_row_v4(s, n)
        if z4:
            return z4
    row_, column, result = enemy_row_basic(s, n)
    row_id = row_.split(" ")[0]
    if row_id in LAT_WITH_LEADER and leader_present(s, e):
        column, result = LAT_WITH_LEADER[row_id]
        return row_ + " (With Leader, 8.9)", column, result
    if not (state.pinned(e) or state.is_lat(e) or state.fire_team_side(e)):
        kid = e["karte"]
        opponent_present = bool(state.valid_target(s, kid, "Feind"))
        cover = e.get("bereich", "offen") != "offen"
        if s.get("feind_taktik") in OFFENSIVE_TACTICS:
            z, sp, er = enemy_row_offensive(s, n, opponent_present, cover, fire.is_firing(e))
            return z + f" [Enemy Offensive Activity Check Hierarchy, {s['feind_taktik']}]", sp, er
        if (
            state.is_v4(s)
            and e.get("vof_rating") == "G"
            and not fire.is_firing(e)
            and row_id in ("Z4", "keine", "none")
            and fire_candidates_g(s, n)
        ):
            T = tactic_index(s)
            return (
                "Z5 G! unit without PDF with target in LOS (player aid)",
                ["3", "2", "Auto"][T],
                [
                    {"1-2": "No Action", "3": "Grenade Attack (or Concentrate Fire)"},
                    {"1": "No Action", "2": "Grenade Attack (or Concentrate Fire)"},
                    {"Auto": "Grenade Attack (or Concentrate Fire)"},
                ][T],
            )
        rgz = leader_rg_target(s, n) if state.is_v4(s) else None
        if rgz and row_id == "keine":
            T = tactic_index(s)
            if fire.vof_against(s, kid, "Feind", ignore_mines=True) is None:
                return (
                    f"Z5 Leader with Rifle Grenade ({e.get('rifle_grenades')} rounds) as G! along the PDF to {rgz} [8.9 p.67]",
                    ["3", "2", "Auto"][T],
                    [
                        {"1-2": "No Action", "3": "Grenade Attack"},
                        {"1": "No Action", "2": "Grenade Attack"},
                        {"Auto": "Grenade Attack"},
                    ][T],
                )
            # L86 (K28): Leader under fire. His 'own PDF' is the PDF of his card (8.9 'along their card's existing PDF').
            if not cover:
                return (
                    f"Z6 Leader with Rifle Grenade under fire, no cover (as G!, target {rgz}) [8.9 p.67, K28]",
                    ["5", "5", "3"][T],
                    [
                        {"1": "No Action", "2": "Move into or Seek Cover", "3-4": "Fall Back", "5": "Grenade Attack"},
                        {"1": "No Action", "2-3": "Move into or Seek Cover", "4": "Fall Back", "5": "Grenade Attack"},
                        {"1-2": "Move into or Seek Cover", "3": "Grenade Attack"},
                    ][T],
                )
            if any(k != rgz for k in fire.pdfs_to(s, kid, "Feind")):
                return (
                    f"Z7 Leader with Rifle Grenade under fire from a direction other than his card's PDF (as G!, target {rgz}; Shift PDF lapses without a VOF = No Action) [8.9 p.67, K28]",
                    ["5", "5", "4"][T],
                    [
                        {
                            "1": "No Action",
                            "2": "Grenade Attack",
                            "3": "No Action (Shift PDF not possible)",
                            "4-5": "Fall Back",
                        },
                        {
                            "1": "No Action",
                            "2": "Grenade Attack",
                            "3-4": "No Action (Shift PDF not possible)",
                            "5": "Fall Back",
                        },
                        {"1": "No Action", "2": "Grenade Attack", "3-4": "No Action (Shift PDF not possible)"},
                    ][T],
                )
            return (
                f"Z10 Leader with Rifle Grenade in a firefight (as G! -4, target {rgz}; compare with the best opposing VOF on the chart) [8.9 p.67, K28]",
                ["3", "2", "3"][T],
                [
                    {"1-2": "No Action", "3": "Grenade Attack"},
                    {"1": "No Action", "2": "Grenade Attack"},
                    {"1": "No Action", "2-3": "Grenade Attack"},
                ][T],
            )
    return row_, column, result


def tactic_index(s):
    """Column index of the enemy tactic on the Enemy Activity Check Hierarchy: Delay 0, Hasty 1, Deliberate 2."""
    return {"Delay": 0, "Hasty": 1, "Deliberate": 2}.get(s.get("feind_taktik", "Hasty"), 2)


def enemy_row_basic(s, n):
    """Hierarchy row of an enemy (Enemy Activity Check Hierarchy Chart; Defensive Delay/Hasty/Deliberate or LAT/Pinned without Leader)."""
    e = s["einheiten"][n]
    kid = e["karte"]
    opponent_present = bool(state.valid_target(s, kid, "Feind"))
    cover = e.get("bereich", "offen") != "offen"
    # [PLAYER AID Key 'Under Fire'] without unactivated Mines and Pending (BGG E35); mine hit = active VOF
    under_fire = fire.vof_against(s, kid, "Feind", ignore_mines=True) is not None or bool(e.get("mine_hit"))
    T = tactic_index(s)
    if state.pinned(e) or state.is_lat(e) or state.fire_team_side(e):
        if state.pinned(e):
            if opponent_present and not cover:
                return (
                    "P1 Pinned, opponent on card, without cover",
                    "5",
                    {"1": "No Action", "2": "Move into or Seek Cover", "3": "Rally", "4-5": "Fall Back"},
                )
            if opponent_present:
                return (
                    "P2 Pinned, opponent on card, under cover",
                    "5",
                    {"1-2": "No Action", "3": "Rally", "4-5": "Fall Back"},
                )
            if not cover:
                return (
                    "P3 Pinned, without cover",
                    "5",
                    {"1-2": "No Action", "3": "Move into or Seek Cover", "4": "Rally", "5": "Fall Back"},
                )
            return "P4 Pinned, under cover", "4", {"1-2": "No Action", "3": "Rally", "4": "Fall Back"}
        if e["typ"] == "Assault Team":
            if opponent_present:
                return "P6 Assault Team on opponent's card", "2", {"1": "No Action", "2": "Grenade Attack"}
            return (
                "P7 Assault Team not on opponent's card",
                "2",
                {"1": "No Action", "2": "Infiltrate to nearest opponent"},
            )
        if e["typ"] == "Fire Team" and opponent_present:
            if not cover:
                return (
                    "P8 Fire Team without cover on opponent's card",
                    "5",
                    {"1": "No Action", "2": "Move into or Seek Cover", "3-5": "Fall Back"},
                )
            return (
                "P9 Fire Team under cover on opponent's card",
                "5",
                {"1-2": "No Action", "3": "Grenade Attack", "4-5": "Fall Back"},
            )
        if state.fire_team_side(e):
            if state.is_hq(e):
                return "P10 Leader on Fire Team side", "3", {"1": "No Action", "2-3": "Rally"}
            return "P11 Spotter/Sniper/Weapon Team on Fire Team side", "2", {"1": "No Action", "2": "Rally"}
        if e["typ"] == "Litter Team":
            if state.card(s, kid).get("casualties_feind"):
                return "P12 Litter Team with Casualty", "3", {"1": "No Action", "2-3": "Fall Back with Casualty"}
            if any(
                c.get("casualties_feind") and geometry.los(s, kid, k)[0] for k, c in s["karten"].items() if k != kid
            ):
                return (
                    "P13 Litter Team with Casualty in LOS",
                    "3",
                    {"1": "No Action", "2-3": "Move towards closest Casualty"},
                )
            return "P14 Litter Team without Casualty in LOS", "3", {"1-2": "No Action", "3": "Rally"}
        if e["typ"] == "Paralyzed Team":
            return "P15 Paralyzed Team", "Auto", {"Auto": "No Action"}
        return "none (no LAT row applies)", "Auto", {"Auto": "No Action"}
    has_los = bool(fire.fire_candidates(s, n))
    if state.company(s) or "optionen" in s or s.get("sonderregeln"):
        # [PLAYER AID Enemy Activity Hierarchy] 'no LOS to an opposing unit' is pure LOS (5.2), independent of weapon range
        # and bunker fire arc [RULE 5.3.2 p.37 'Being in a Bunker ... does not affect a unit's LOS']
        has_los = has_los or any(
            geometry.los(
                s, kid, k, ha=geometry.card_height_bonus(s, kid, "Feind"), hb=geometry.card_height_bonus(s, k, "US")
            )[0]
            for k in s["karten"]
            if k != kid and state.units_on(s, k, "US")
        )
    if opponent_present and not cover:
        return (
            "Z1 opponent on card, without cover",
            ["5", "4", "3"][T],
            [
                {"1": "No Action", "2": "Move into or Seek Cover", "3-4": "Fall Back", "5": "Grenade Attack"},
                {"1": "No Action", "2": "Move into or Seek Cover", "3": "Fall Back", "4": "Grenade Attack"},
                {"1": "Move into or Seek Cover", "2": "Fall Back", "3": "Grenade Attack"},
            ][T],
        )
    if opponent_present:
        return (
            "Z2 opponent on card, under cover",
            ["4", "3", "3"][T],
            [
                {"1": "No Action", "2-3": "Fall Back", "4": "Grenade Attack"},
                {"1": "No Action", "2": "Fall Back", "3": "Grenade Attack"},
                {"1": "No Action", "2-3": "Grenade Attack"},
            ][T],
        )
    if e.get("out_of_ammo") and e.get("vof_rating") in ("A", "G", "H"):
        return (
            "Z3 A/G!/H with Out of Ammo",
            ["Auto", "3", "2"][T],
            [{"Auto": "Fall Back"}, {"1": "No Action", "2-3": "Fall Back"}, {"1": "No Action", "2": "Fall Back"}][T],
        )
    if not under_fire and not has_los and not fire.is_firing(e):
        if s.get("sonderregeln", {}).get("remove_pc_no_action"):
            # [FM1 p.36] Deliberate Defense: 'ignore a "Remove unit, place PC marker" action result and do "No Action" instead'
            return (
                "Z4 not under fire, no LOS to opponents (special rule FM1 p.36: No Action instead of Remove)",
                "Auto",
                {"Auto": "No Action"},
            )
        if "optionen" in s and state.option(s, "U1_remove_pc_no_action"):
            return (
                "Z4 not under fire, no LOS to opponents (special rule FM1 p.36 also in Run 2/3: No Action)"
                + state.open_reading(s, "U1_remove_pc_no_action"),
                "Auto",
                {"Auto": "No Action"},
            )
        return "Z4 not under fire, no LOS to opponents", "Auto", {"Auto": "Remove unit; place PC marker"}
    if not under_fire and fire.is_firing(e):
        return (
            "Z5 not under fire, target along PDF",
            ["3", "2", "Auto"][T],
            [
                {"1-2": "No Action", "3": "Grenade Attack (or Concentrate Fire)"},
                {"1": "No Action", "2": "Grenade Attack (or Concentrate Fire)"},
                {"Auto": "Grenade Attack (or Concentrate Fire)"},
            ][T],
        )
    if under_fire and not cover:
        return (
            "Z6 under fire, without cover",
            ["5", "5", "3"][T],
            [
                {
                    "1": "No Action",
                    "2": "Move into or Seek Cover",
                    "3-4": "Fall Back",
                    "5": "Grenade Attack (or Concentrate Fire)",
                },
                {
                    "1": "No Action",
                    "2-3": "Move into or Seek Cover",
                    "4": "Fall Back",
                    "5": "Grenade Attack (or Concentrate Fire)",
                },
                {"1-2": "Move into or Seek Cover", "3": "Grenade Attack (or Concentrate Fire)"},
            ][T],
        )
    if under_fire and fire.is_firing(e) and any(k != e["ziel"] for k in fire.pdfs_to(s, kid, "Feind")):
        return (
            "Z7 under fire from a direction other than own PDF",
            ["5", "5", "4"][T],
            [
                {"1": "No Action", "2": "Grenade Attack (or Concentrate Fire)", "3": "Shift PDF", "4-5": "Fall Back"},
                {"1": "No Action", "2": "Grenade Attack (or Concentrate Fire)", "3-4": "Shift PDF", "5": "Fall Back"},
                {"1": "No Action", "2": "Grenade Attack (or Concentrate Fire)", "3-4": "Shift PDF"},
            ][T],
        )
    a_rating = ("A", "H", "A/S") if ("optionen" in s and state.option(s, "U4_as_zaehlt_als_a")) else ("A", "H")
    if fire.is_firing(e) and e.get("vof_rating") in a_rating and e["ziel"] != kid and not e.get("konzentriert"):
        return (
            "Z8 A/H unit that has opened fire"
            + (state.open_reading(s, "U4_as_zaehlt_als_a") if e.get("vof_rating") == "A/S" else ""),
            ["3", "3", "Auto"][T],
            [
                {"1-2": "No Action", "3": "Attempt to Concentrate Fire"},
                {"1": "No Action", "2-3": "Attempt to Concentrate Fire"},
                {"Auto": "Attempt to Concentrate Fire"},
            ][T],
        )
    if under_fire and fire.is_firing(e):
        own_unit = rules.VOF_VALUE.get(fire.current_vof_rating(e, e["ziel"] == kid), 0)
        if own_unit < fire.vof_against(s, kid, "Feind")[1]:
            return (
                "Z9 Trading fire, own VOF better",
                ["3", "2", "3"][T],
                [
                    {"1-2": "No Action", "3": "Grenade Attack (or Concentrate Fire)"},
                    {"1": "No Action", "2": "Grenade Attack (or Concentrate Fire)"},
                    {"1": "No Action", "2-3": "Grenade Attack (or Concentrate Fire)"},
                ][T],
            )
        return (
            "Z10 Trading fire, own VOF equal or worse",
            ["3", "5", "2"][T],
            [
                {"1": "No Action", "2": "Grenade Attack (or Concentrate Fire)", "3": "Fall Back"},
                {"1-2": "No Action", "3-4": "Grenade Attack (or Concentrate Fire)", "5": "Fall Back"},
                {"1": "No Action", "2": "Grenade Attack (or Concentrate Fire)"},
            ][T],
        )
    return "none (no row applies)", "Auto", {"Auto": "No Action"}


def prepare_enemy_check(s, prot):
    if state.is_v4(s):
        for n, e in s["einheiten"].items():
            if (
                e["seite"] == "Feind"
                and e.get("leader")
                and not state.fire_team_side(e)
                and not [m for m in state.units_on(s, e["karte"], "Feind") if m != n]
            ):
                commands.mark(e, "Fire Team side")
                prot.append(f"{n}: Leader alone on {e['karte']}, flipped to Fire Team side [8.9 p.67]")
    enemies = [n for n, e in s["einheiten"].items() if e["seite"] == "Feind"]
    for n in enemies:
        s["einheiten"][n]["check_offen"] = True
    # L60: units from an Enemy Higher HQ Event this turn do not check again [RULE 3.4.1 p.16]
    without = (
        [n for n in s.get("ereignis_einheiten", []) if n in enemies]
        if s.get("ereignis_erledigt") == [s["zug"], "3.4.1"]
        else []
    )
    if without:
        prot.append(
            f"no Activity Check for {', '.join(without)} (already affected by the Enemy Higher HQ Event) [3.4.1 p.16]"
        )
        enemies = [n for n in enemies if n not in without]
        if not enemies:
            prot.append("no further enemies to check")
            return
    cards = sorted({s["einheiten"][n]["karte"] for n in enemies})
    if not enemies:
        prot.append("no enemies on the board, Activity Check skipped")
    elif len(cards) > 1:
        prot.append(
            f"card order by R# (column {len(cards)}) for {', '.join(cards)}; per card first Pinned/LAT, then Good Order, then Leader; then fof.py enemycheck [8.6.2]"
        )
    else:
        prot.append(f"Activity Check for {', '.join(enemies)}: fof.py enemycheck [8.6.2]")


def cmd_enemy_check(s, args):
    if s["phase"] != "3.4.2":
        print(f"Note: Activity Check belongs in 3.4.2, currently {s['phase']}")
    for n, e in s["einheiten"].items():
        if e["seite"] != "Feind":
            continue
        row_, column, result = enemy_row(s, n)
        print(
            f"{n} on {e['karte']}"
            + ("" if e.get("check_offen") else " (check done)")
            + f": {row_} [Enemy Activity Chart, {s.get('feind_taktik', 'Hasty')}]"
        )
        if column == "Auto":
            print(f'  Auto: {list(result.values())[0]}   fof.py enemyaction "{n}" "{list(result.values())[0]}" ...')
        else:
            print(f"  R# column {column}: " + "; ".join(f"{k} = {v}" for k, v in result.items()))
            print(f'  then fof.py enemyaction "{n}" "<action>" [--target=K] [--success=yes|no] [--unit=<target unit>]')


def cf_stack(s, ze):
    """[RULE 7.11.2 p.56] Target under a cover marker: CF affects all units under that marker."""
    z = s["einheiten"][ze]
    b = z.get("bereich", "offen")
    if b in (None, "offen"):
        return [ze]
    return [
        n
        for n, e in s["einheiten"].items()
        if e.get("karte") == z.get("karte") and e.get("seite") == z.get("seite") and e.get("bereich") == b
    ]


def _enemy_no_action(s, ctx):
    """cmd_feindaktion: a.startswith('no action')"""
    ctx.prot.append(f"{ctx.n}: No Action, fire continues [Chart]")


def _is_no_action(s, ctx):
    return ctx.a.startswith("no action")


def _enemy_call_for_fire(s, ctx):
    """cmd_feindaktion: a.startswith('call for fire')"""
    if not ctx.e.get("spotter") or ctx.e.get("missionen", 0) <= 0:
        raise rules.Violation(f"{ctx.n} is not a Spotter with fire missions")
    target = ctx.o.get("--ziel")
    if not target:
        raise rules.Violation("--target=<card by priority (enemycheck)>")
    tk = s.get("feind_target", {}).get(ctx.e.get("typname"))
    if ctx.o.get("--erfolg") not in ("ja", "nein"):
        raise rules.Violation(
            f"Call for Fire: {ctx.e.get('karten_folge', 3) + (1 if tk == target else 0)} cards, Burst symbol; --success=yes|no [8.10 p.68]"
        )
    if ctx.o["--erfolg"] == "ja":
        state.card(s, target).setdefault("extern", []).append(
            {"typ": "Pending", "wert": ctx.e.get("fm_wert", -3), "quelle": ctx.n, "seite": "Feind"}
        )
        ctx.e["missionen"] -= 1
        s.setdefault("feind_target", {})[ctx.e.get("typname")] = target
        ctx.prot.append(
            f"{ctx.n}: Pending Fire Mission ({ctx.e.get('fm_wert', -3):+d}) on {target}, enemy Target marker moved there; becomes active in 3.7.1; {ctx.e['missionen']} mission(s) left [8.10 p.68, 3.7.1]"
        )
    else:
        ctx.prot.append(f"{ctx.n}: Call for Fire failed, no mission used up (BGG E19)")


def _is_call_for_fire(s, ctx):
    return ctx.a.startswith("call for fire")


def _enemy_no_fire_missions(s, ctx):
    """cmd_feindaktion: 'keine feuerauftraege' in a or 'no fire missions' in a"""
    remove_enemy(s, ctx.n, ctx.prot, reason="Spotter without fire missions [8.10 p.68]")


def _is_no_fire_missions(s, ctx):
    return "keine feuerauftraege" in ctx.a or "no fire missions" in ctx.a


def _enemy_advance(s, ctx):
    """cmd_feindaktion: 'advance' in a"""
    c = state.card(s, ctx.e["karte"])
    target = geometry.card_at(s, c["reihe"] - 1, c["spalte"])
    if c["reihe"] == geometry.first_card_row(s):
        if s.get("feind_taktik") == "Overrun":
            remove_enemy(s, ctx.n, ctx.prot, reason="Overrun: Advance from row 1 leaves the board")
            target = None
        else:
            target = ctx.o.get("--ziel")
            if (
                not target
                or not geometry.adjacent(s, ctx.e["karte"], target)
                or (state.card(s, target).get("staging") and not state.option(s, "U24_assault_in_staging"))
            ):
                raise rules.Violation(
                    "Assault from row 1: --target=<adjacent card towards the nearest US unit>"
                    + state.open_reading(s, "U24_assault_in_staging")
                )
    if target:
        commands.grenade_expires(s, ctx.e, ctx.n, ctx.prot)
        ctx.e["karte"], ctx.e["bereich"] = target, "offen"
        commands.mark(ctx.e, "Exposed")
        ctx.prot.append(f"{ctx.n}: Advance Straight Ahead to {target}, Exposed [Offensive Hierarchy, 8.6.1C]")
        fire.fire_after_move(s, ctx.n, ctx.prot)


def _is_advance(s, ctx):
    return "advance" in ctx.a


def _enemy_seek_cover(s, ctx):
    """cmd_feindaktion: 'seek cover' in a or 'move into' in a"""
    kk = state.card(s, ctx.e["karte"])
    free = [
        c
        for c in kk.get("cover", [])
        if not any(
            s["einheiten"][m]["seite"] == "US" and s["einheiten"][m].get("bereich") == c["id"]
            for m in state.units_on(s, ctx.e["karte"])
        )
    ]
    if free and ctx.e.get("bereich", "offen") == "offen":
        ctx.e["bereich"] = free[0]["id"]
        commands.mark(ctx.e, "Exposed")
        ctx.prot.append(f"{ctx.n} moves under {free[0]['id']} ({free[0]['typ']}), Exposed [8.6.1C]")
    else:
        if ctx.o.get("--erfolg") not in ("ja", "nein"):
            n_cards = (kk.get("cover_draw") or 2) + {"Green": -1, "Veteran": 1}.get(comms.experience(ctx.e), 0)
            raise rules.Violation(
                f"Seek Cover: draw {n_cards} cards (cover draw of the card, experience {comms.experience(ctx.e)}), word 'Cover'; --success=yes|no"
            )
        if ctx.o["--erfolg"] == "ja":
            cid = commands.new_cover_marker(s, ctx.e["karte"], "Basic Cover", 1)
            ctx.e["bereich"] = cid
            commands.mark(ctx.e, "Exposed")
            ctx.prot.append(
                f"{ctx.n}: new cover marker {cid} (+1) on {ctx.e['karte']}, {ctx.n} under it, Exposed [4.2.2e]"
            )
        else:
            ctx.prot.append(f"{ctx.n}: Seek Cover failed")


def _is_seek_cover(s, ctx):
    return "seek cover" in ctx.a or "move into" in ctx.a


def _enemy_fall_back(s, ctx):
    """cmd_feindaktion: 'fall back' in a"""
    target = ctx.o.get("--ziel")
    if target == "off-map":
        remove_enemy(s, ctx.n, ctx.prot, reason="Fall Back off-map")
    else:
        if not target:
            raise rules.Violation(
                "Fall Back: --target=<card> (priority: off-map at own edge; card outside every US LOS; highest cover value; random on a tie) or --target=off-map [8.6.3]"
            )
        state.card(s, target)
        if not geometry.adjacent(s, ctx.e["karte"], target):
            raise rules.Violation(f"{target} not adjacent to {ctx.e['karte']}")
        commands.grenade_expires(
            s, ctx.e, ctx.n, ctx.prot
        )  # L92 [RULE 7.10.4] Grenade marker becomes a Grenade Miss on the origin card
        ctx.e["karte"], ctx.e["bereich"] = target, "offen"
        commands.mark(ctx.e, "Exposed")
        free = [
            c
            for c in state.card(s, target).get("cover", [])
            if not any(
                s["einheiten"][m]["seite"] == "US" and s["einheiten"][m].get("bereich") == c["id"]
                for m in state.units_on(s, target)
            )
        ]
        if free:
            ctx.e["bereich"] = max(free, key=lambda c: c["wert"])["id"]
            ctx.prot.append(f"{ctx.n} falls back to {target} under {ctx.e['bereich']}, Exposed [8.6.3, 8.6.1E]")
        else:
            ctx.prot.append(f"{ctx.n} falls back to {target} (open), Exposed [8.6.3]")
        fire.fire_after_move(s, ctx.n, ctx.prot)


def _is_fall_back(s, ctx):
    return "fall back" in ctx.a


def _enemy_grenade_concentrate(s, ctx):
    """cmd_feindaktion: 'grenade' in a or 'concentrate' in a"""
    if ctx.o.get("--erfolg") not in ("ja", "nein"):
        raise rules.Violation(
            "Grenade Attack (only Point Blank or G! rating) or Attempt to Concentrate Fire: 2 cards (enemy experience, +1 with Leader), Grenade symbol or Crosshairs; --success=yes|no --unit=<target unit or cover stack> [7.10, 7.11]"
        )
    grenade_pb = "grenade" in ctx.a and bool(state.valid_target(s, ctx.e["karte"], "Feind"))
    g_without_pdf = state.is_v4(s) and ctx.e.get("vof_rating") == "G" and not fire.is_firing(ctx.e) and not grenade_pb
    rg = leader_rg_target(s, ctx.n) if (state.is_v4(s) and "grenade" in ctx.a and not grenade_pb) else None  # L67 [8.9]
    if not fire.is_firing(ctx.e) and not grenade_pb and not g_without_pdf and not rg:
        raise rules.Violation(f"{ctx.n} is not firing, no Concentrate Fire possible [4.2.4b]")
    if g_without_pdf:
        zk_g = ctx.o.get("--ziel")
        if zk_g not in fire_candidates_g(s, ctx.n):
            raise rules.Violation(
                f"G! unit without PDF: --target=<card with target in LOS/range> from {', '.join(fire_candidates_g(s, ctx.n)) or 'none'}"
            )
        ctx.e["ziel"], ctx.e["nur_pdf"] = zk_g, True
        ctx.prot.append(f"{ctx.n} places PDF towards {zk_g} [7.3.2 p.53]")
    zk = ctx.e["karte"] if grenade_pb else (rg or fire.effective_fire_target(s, ctx.n))
    if rg:
        ctx.e["rifle_grenades"] -= 1
        ctx.prot.append(
            f"{ctx.n} fires a Rifle Grenade along the PDF to {rg}; {ctx.e['rifle_grenades']} round(s) left [8.9 p.67, Normandy p.23]"
        )
    if (
        state.is_v4(s)
        and "grenade" in ctx.a
        and not grenade_pb
        and combat.ammo(ctx.e)
        and (ctx.e.get("vof_rating") == "G" or ctx.e.get("grenade_ranged"))
    ):
        combat.ammo_use(s, ctx.n, ctx.e, 1, "Grenade Attack at range", ctx.prot)
    if state.is_v4(s) and ctx.o.get("--jam") == "ja" and not grenade_pb and commands.jam_prone(ctx.e):
        commands.jam(s, ctx.n, ctx.prot)
        ctx.o["--erfolg"] = "nein"
    cv = geometry.cover_marker(s, ctx.e)
    if grenade_pb and cv and cv["typ"] in rules.STRUCTURES:
        # [RULE 5.3 p.37] Grenade Attack against a Point Blank opponent: unit leaves Bunker/Pillbox and becomes Exposed
        ctx.e["bereich"] = "offen"
        commands.mark(ctx.e, "Exposed")
        ctx.prot.append(f"{ctx.n} leaves {cv['typ']} {cv['id']} for the Point Blank attack, Exposed [5.3 p.37]")
    if ctx.o["--erfolg"] == "ja":
        ze = ctx.o.get("--einheit")
        if not ze:
            raise rules.Violation(f"specify --unit=<target unit> (cover stack or random unit without cover on {zk})")
        z = state.unit(s, ze)
        gw = int(ctx.o.get("--wert", s.get("granate_vof", -3)))  # Normandy p.13: German Grenade Attacks are also -4
        if "grenade" in ctx.a and (zk == ctx.e["karte"] or ctx.e.get("vof_rating") == "G" or rg):
            z.setdefault("grenade", []).append(gw)
            if zk != ctx.e["karte"]:
                against = "no grenade thrown back (attack not from the same card) [7.10.5 p.55]"
            elif not ctx.e.get("spotted"):
                against = "no grenade thrown back (attacker Unspotted) [7.10.5 p.55]"
            else:
                against = "a Good Order target throws back for free [7.10.5 p.55]"
            ctx.prot.append(f"{ctx.n}: Grenade VOF {gw} on {ze}; {against}")
        else:
            for _m in cf_stack(s, ze):
                s["einheiten"][_m]["cf"] = s["einheiten"][_m].get("cf", 0) + 1
            ctx.e["konzentriert"] = True
            ctx.prot.append(
                f"{ctx.n}: Concentrated Fire marker on {ze} (stack: {', '.join(cf_stack(s, ze))}; -1 NCM, cumulative) [7.11]"
            )
            if combat.ammo(ctx.e):
                combat.ammo_use(s, ctx.n, ctx.e, 1, "successful Concentrate Fire", ctx.prot)
    else:
        if "grenade" in ctx.a and zk == ctx.e["karte"]:
            state.card(s, zk)["grenade_miss"] = True
            ctx.prot.append(f"{ctx.n}: Grenade Miss (-1) on {zk}; target may freely throw back [7.10]")
        else:
            ctx.prot.append(f"{ctx.n}: attempt failed")


def _is_grenade_concentrate(s, ctx):
    return "grenade" in ctx.a or "concentrate" in ctx.a


def _enemy_shift(s, ctx):
    """cmd_feindaktion: 'shift' in a"""
    target = ctx.o.get("--ziel")
    if geometry.arc_direction(s, ctx.e) or ctx.e.get("bunker_richtung"):
        raise rules.Violation(f"{ctx.n} is in a Bunker/Pillbox: draw the 'Shift Fire' result again [RULE 5.3.2 p.37]")
    if not target:
        raise rules.Violation("Shift PDF: --target=<card the fire comes from> (random if several; Bunker: draw again)")
    state.card(s, target)
    # L59: Chart 'Shift Fire if possible to place VOF on opposing units' - only with LOS, range and a valid target
    _los = geometry.los(
        s,
        ctx.e["karte"],
        target,
        ha=geometry.height_bonus(s, ctx.e),
        hb=geometry.card_height_bonus(s, target, geometry.opponent_of(ctx.e)),
    )
    if not _los[0] or not geometry.in_range(s, ctx.e, target) or not state.valid_target(s, target, ctx.e["seite"]):
        reason = (
            _los[1]
            if not _los[0]
            else ("out of range" if not geometry.in_range(s, ctx.e, target) else "no valid target")
        )
        ctx.prot.append(
            f"{ctx.n}: Shift PDF to {target} not possible ({reason}); fire continues [Enemy Activity Chart: 'Shift Fire if possible', 9.2.1]"
        )
    else:
        ctx.e["ziel"] = target
        ctx.e.pop("konzentriert", None)
        ctx.prot.append(f"{ctx.n} shifts its PDF to {target} [Chart, 6.3.3]")


def _is_shift(s, ctx):
    return "shift" in ctx.a


def _enemy_rally(s, ctx):
    """cmd_feindaktion: a.startswith('rally')"""
    if state.pinned(ctx.e):
        if ctx.under_vof and ctx.o.get("--erfolg") not in ("ja", "nein"):
            kz, ez = comms.enemy_rally_cards(ctx.e)
            raise rules.Violation(
                f"Rally under VOF: {kz} cards (base 2, experience {ez}), word 'Rally'; --success=yes|no [6.5.1]"
            )
        if not ctx.under_vof or ctx.o["--erfolg"] == "ja":
            ctx.e["status"].remove("Pinned")
            ctx.prot.append(f"{ctx.n}: Pinned marker removed, VOF Basic again [6.5.1]")
        else:
            ctx.prot.append(f"{ctx.n}: Rally failed")
    elif state.fire_team_side(ctx.e):
        if ctx.under_vof and ctx.o.get("--erfolg") not in ("ja", "nein"):
            raise rules.Violation("Flip to Front under VOF: 2 cards, word 'Rally'; --success=yes|no [4.2.3f]")
        if not ctx.under_vof or ctx.o["--erfolg"] == "ja":
            ctx.e["status"].remove("Fire Team side")
            ctx.prot.append(f"{ctx.n}: back to the front side [4.2.3f]")
        else:
            ctx.prot.append(f"{ctx.n}: Rally failed")
    elif state.is_lat(ctx.e):
        nearest = {"Paralyzed Team": "Litter Team", "Litter Team": "Fire Team", "Fire Team": "Assault Team"}.get(
            ctx.e["typ"]
        )
        if ctx.under_vof and ctx.o.get("--erfolg") not in ("ja", "nein"):
            kz, ez = comms.enemy_rally_cards(ctx.e)
            raise rules.Violation(
                f"LAT Rally under VOF: {kz} cards (base 2, experience {ez}), word 'Rally'; --success=yes|no [6.5.1]"
            )
        if nearest and (not ctx.under_vof or ctx.o["--erfolg"] == "ja"):
            ctx.e["typ"] = nearest
            combat.set_lat_values(ctx.e, nearest)
            ctx.prot.append(f"{ctx.n} becomes {nearest} [6.5.1]")
        else:
            ctx.prot.append(f"{ctx.n}: Rally failed")


def _is_rally(s, ctx):
    return ctx.a.startswith("rally")


def _enemy_remove(s, ctx):
    """cmd_feindaktion: 'remove' in a"""
    remove_enemy(s, ctx.n, ctx.prot, reason="Z4: no LOS, no fire", pc=True)


def _is_remove(s, ctx):
    return "remove" in ctx.a


def _enemy_move_towards(s, ctx):
    """cmd_feindaktion: 'move towards' in a"""
    target = ctx.o.get("--ziel")
    if not target or not geometry.adjacent(s, ctx.e["karte"], target):
        raise rules.Violation(
            "Move towards closest Casualty: --target=<adjacent card towards the closest Casualty> [LAT/Pinned Hierarchy]"
        )
    commands.grenade_expires(s, ctx.e, ctx.n, ctx.prot)
    ctx.e["karte"], ctx.e["bereich"] = target, "offen"
    commands.mark(ctx.e, "Exposed")
    ctx.prot.append(f"{ctx.n} to {target} (towards Casualty), Exposed [8.6.1C]")
    fire.fire_after_move(s, ctx.n, ctx.prot)


def _is_move_towards(s, ctx):
    return "move towards" in ctx.a


def _enemy_infiltrate(s, ctx):
    """cmd_feindaktion: 'infiltrate' in a"""
    target = ctx.o.get("--ziel")
    if not target or ctx.o.get("--erfolg") not in ("ja", "nein"):
        raise rules.Violation(
            "Infiltrate: --target=<card towards nearest opponent> --success=yes|no (2 cards, Infiltrate symbol); failure = normal move with Exposed [8.6, 5.1.4]"
        )
    ctx.e["karte"], ctx.e["bereich"] = target, "offen"
    if ctx.o["--erfolg"] == "nein":
        commands.mark(ctx.e, "Exposed")
    ctx.prot.append(
        f"{ctx.n} to {target}" + (", not Exposed (infiltrated)" if ctx.o["--erfolg"] == "ja" else ", Exposed")
    )
    fire.fire_after_move(s, ctx.n, ctx.prot)


def _is_infiltrate(s, ctx):
    return "infiltrate" in ctx.a


ENEMY_ACTION_HANDLERS = [
    (_is_no_action, _enemy_no_action),
    (_is_call_for_fire, _enemy_call_for_fire),
    (_is_no_fire_missions, _enemy_no_fire_missions),
    (_is_advance, _enemy_advance),
    (_is_seek_cover, _enemy_seek_cover),
    (_is_fall_back, _enemy_fall_back),
    (_is_grenade_concentrate, _enemy_grenade_concentrate),
    (_is_shift, _enemy_shift),
    (_is_rally, _enemy_rally),
    (_is_remove, _enemy_remove),
    (_is_move_towards, _enemy_move_towards),
    (_is_infiltrate, _enemy_infiltrate),
]


def cmd_enemy_action(s, args):
    n = args[0]
    e = state.unit(s, n)
    if e["seite"] != "Feind":
        raise rules.Violation(f"{n} is not an enemy")
    action = args[1]
    event_rally = s["phase"] == "3.4.1" and n in s.get("rally_offen", []) and action.lower().startswith("rally")
    if s["phase"] != "3.4.2" and not event_rally:
        raise rules.Violation(f"Enemy actions only in the Enemy Activity Check segment 3.4.2, currently {s['phase']}")
    o = options.parse_opts(args[2:])
    prot = []
    a = action.lower()
    if event_rally:
        s["rally_offen"].remove(n)
    if e.get("unbeweglich") and any(w in a for w in ("fall back", "move", "infiltrate", "advance")):
        raise rules.Violation(f"{n} is an immobile AT gun: draw the result again [RULE 8.12 p.68]")
    origin_card = e["karte"]
    under_vof = fire.vof_against(s, e["karte"], "Feind") is not None
    ctx = types.SimpleNamespace(
        a=a, action=action, e=e, n=n, o=o, prot=prot, under_vof=under_vof, origin_card=origin_card
    )
    for test, handler in ENEMY_ACTION_HANDLERS:
        if test(s, ctx):
            handler(s, ctx)
            break
    else:
        raise rules.Violation(f"Action '{ctx.action}' unknown")
    if n in s["einheiten"]:
        s["einheiten"][n]["check_offen"] = False
        e2 = s["einheiten"][n]
        if state.is_v4(s) and e2["karte"] != origin_card:
            contact.request_mine_check(s, [n], e2["karte"], prot, "enemy enters mine card")
            if is_sniper(e2) and not any(
                geometry.los(
                    s, e2["karte"], k, ha=geometry.height_bonus(s, e2), hb=geometry.card_height_bonus(s, k, "US")
                )[0]
                for k in s["karten"]
                if state.units_on(s, k, "US") and not state.card(s, k).get("staging")
            ):
                for m in state.units_on(s, e2["karte"], "Feind"):
                    s["einheiten"][m]["spotted"] = False
                prot.append(f"{n} out of LOS of all US units: Unspotted again [8.8 p.67]")
    ak = fire.update_activity(s)
    if ak:
        prot.append(ak)
    state.save_state(s, f"Activity Check {n}: {action}; " + "; ".join(prot), "8.6.2 p.66, Enemy Activity Chart")
    briefing.print_board(prot, s)


def remove_enemy(s, n, prot, reason="", pc=False):
    e = s["einheiten"][n]
    kid = e["karte"]
    if pc and not state.card(s, kid).get("pc"):
        state.card(s, kid)["pc"] = e.get("pc_herkunft", "A")
        prot.append(f"Place PC marker {state.card(s, kid)['pc']} on {kid} [8.6.1]")
    pk = s.get("pakete", {}).get(str(e.get("paket")))
    if pk:
        pk["im_spiel"] = False
    ammo_lost(e, n, prot)
    del s["einheiten"][n]
    prot.append(f"{n} off the board ({reason}), counter back to the pool [8.3]")


def ammo_lost(e, name, prot):
    """L62 (the player 09.10.2026): remove the ammo marker of a counter removed from the board; 5.1.6E only drops Assets and
    Casualties, enemy ammo is not captured (BGG 3498471)."""
    m = e.get("munition")
    if m and m.get("punkte"):
        prot.append(
            f"Remove ammo marker of {name} ({m['punkte']} {m.get('typ', '')}) from {e.get('karte')}: ammo lost, "
            f"no capture [5.1.6E, BGG 3498471]"
        )


def is_sniper(e):
    return e.get("vof_rating") == "S!" and not state.fire_team_side(e) and not state.is_lat(e)


def sniper_on_card(s, kid):
    """Firing, non-pinned snipers whose VOF lies on kid (7.15: HQs there -3 Command draw)."""
    return [
        n
        for n, e in s["einheiten"].items()
        if is_sniper(e) and fire.is_firing(e) and not state.pinned(e) and fire.effective_fire_target(s, n) == kid
    ]


def choose_sniper_targets(s, prot):
    """[RULE 7.15 p.57] At the start of 3.7.4: random target on the card, Exposed first."""
    s["sniper_ziele"] = {}
    s["sniper_offen"] = {}
    for n in [m for m, e in s["einheiten"].items() if is_sniper(e) and fire.is_firing(e) and not state.pinned(e)]:
        kid = fire.effective_fire_target(s, n)
        candidate = [m for m in state.units_on(s, kid, state.opponent_of_side(s["einheiten"][n]["seite"]))]
        exp = [m for m in candidate if "Exposed" in s["einheiten"][m]["status"]]
        if exp:
            candidate = exp
        if len(candidate) == 1:
            s["sniper_ziele"][n] = candidate[0]
            prot.append(f"Sniper VOF (-3) from {n} on {candidate[0]}; rest of the card Small Arms only [7.15 p.57]")
        elif candidate:
            s["sniper_offen"][n] = candidate
            prot.append(
                f"Sniper {n}: target by R# (column {len(candidate)}) from {', '.join(candidate)}"
                + (" (Exposed only)" if exp else "")
                + f'; then fof.py sniper "{n}" <target> [7.15 p.57]'
            )


def cmd_sniper(s, args):
    n, z = args[0], args[1]
    candidate = s.get("sniper_offen", {}).get(n)
    if not candidate:
        raise rules.Violation(f"No target choice pending for {n}")
    if z not in candidate:
        raise rules.Violation(f"{z} not among {', '.join(candidate)}")
    s["sniper_offen"].pop(n)
    s.setdefault("sniper_ziele", {})[n] = z
    if z in s.get("kampf_ncm", {}) or z in s.get("kampf_offen", []):
        s.setdefault("kampf_ncm", {})[z] = [list(x) for x in combat.ncm_rows(s, z)]
    prot = [f"Sniper VOF (-3) from {n} on {z} [7.15 p.57]"]
    state.save_state(s, "; ".join(prot), "7.15 p.57")
    briefing.print_board(prot, s)


def enemy_row_v4(s, n):
    """Returns a hierarchy row for cases v3 does not know, otherwise None."""
    e = s["einheiten"][n]
    if e.get("ooa_fallback") and state.fire_team_side(e) and e.get("spotted"):
        return (
            "O-A Out-of-Ammo team on Fire Team side, Spotted: Fall Back instead of hierarchy [8.11 p.68]",
            "Auto",
            {"Auto": "Fall Back"},
        )
    if state.pinned(e) or state.is_lat(e) or state.fire_team_side(e):
        return None
    if is_sniper(e):
        cv = geometry.cover_marker(s, e)
        if cv and cv["typ"] in ("Foxholes", "Trench", "Bunker", "Pillbox", "Deep Bunker", "Cave"):
            return (
                "S3 Sniper in a field fortification stays put even when Spotted [8.8 Exception]",
                "Auto",
                {"Auto": "No Action"},
            )
        if e.get("spotted"):
            return (
                "S1 Sniper Spotted: Fall Back until out of LOS, then Unspotted again [8.8 p.67]",
                "Auto",
                {"Auto": "Fall Back"},
            )
        return "S2 Sniper Unspotted: fires by target priority or does nothing [8.8 p.67]", "Auto", {"Auto": "No Action"}
    if e.get("spotter"):
        if e.get("missionen", 0) <= 0:
            return (
                "SP0 Spotter without fire missions: remove [8.10 p.68]",
                "Auto",
                {"Auto": "Remove (no fire missions left)"},
            )
        z = spotter_target(s, n)
        if not z:
            return "SP2 Spotter without target in LOS: nothing [8.10 p.68]", "Auto", {"Auto": "No Action"}
        tk = s.get("feind_target", {}).get(e.get("typname"))
        k = e.get("karten_folge", 3) + (1 if tk == z else 0)
        return (
            f"SP1 Spotter: Call for Fire on {z} ({k} cards{' incl. +1 Target marker' if tk == z else ''}, burst symbol; experience already included) [8.10 p.68]",
            "Auto",
            {"Auto": f"Call for Fire --ziel={z}"},
        )
    return None


def spotter_target(s, n):
    """[RULE 8.10 p.68] Priority: Target Marker card, vehicle, most steps, nearest card, random."""
    e = s["einheiten"][n]
    candidate = [
        k
        for k in s["karten"]
        if state.units_on(s, k, "US")
        and not state.card(s, k).get("staging")
        and (
            k == e["karte"]
            or geometry.los(
                s, e["karte"], k, ha=geometry.height_bonus(s, e), hb=geometry.card_height_bonus(s, k, "US")
            )[0]
        )
    ]
    if not candidate:
        return None
    tk = s.get("feind_target", {}).get(e.get("typname"))
    if tk in candidate:
        return tk
    st = {k: sum(state.steps(s["einheiten"][m]) for m in state.units_on(s, k, "US")) for k in candidate}
    best = max(st.values())
    candidate = [k for k in candidate if st[k] == best]
    d = min(geometry.distance(s, e["karte"], k) for k in candidate)
    candidate = [k for k in candidate if geometry.distance(s, e["karte"], k) == d]
    if len(candidate) > 1:
        s.setdefault("_hinweise", []).append(f"Spotter targets tied: {', '.join(candidate)}; choose by R# [8.10]")
    return candidate[0]


def enemy_row_offensive(s, n, opponent_present, cover, firing_):
    """[PLAYER AID Enemy Offensive Activity Check Hierarchy] Columns Assault and Overrun."""
    e = s["einheiten"][n]
    ov = s.get("feind_taktik") == "Overrun"
    if opponent_present and not cover:
        return (
            "O1 on a card with opposing units, without cover",
            "6" if ov else "5",
            {"1": "No Action", "2": "Fall Back", "3-4": "Advance Straight Ahead", "5-6": "Grenade Attack"}
            if ov
            else {"1": "No Action", "2-3": "Move into or Seek Cover", "4": "Fall Back", "5": "Grenade Attack"},
        )
    if opponent_present:
        return (
            "O2 on a card with opposing units, under cover",
            "6" if ov else "5",
            {"1": "No Action", "2": "Fall Back", "3-4": "Advance Straight Ahead", "5-6": "Grenade Attack"}
            if ov
            else {"1": "No Action", "2": "Fall Back", "3-5": "Grenade Attack"},
        )
    if e.get("out_of_ammo") and e.get("vof_rating") in ("A", "G", "H"):
        return (
            "O3 A/G!/H with Out of Ammo",
            "2" if ov else "3",
            {"1": "No Action", "2": "Advance Straight Ahead"} if ov else {"1-2": "No Action", "3": "Fall Back"},
        )
    rgz = leader_rg_target(s, n) if state.is_v4(s) else None
    if rgz:
        # L89 [RULE 8.9 p.67] Leader with Rifle Grenade as a G! unit with a target along the card's PDF (offensive table O4)
        return (
            f"O4 Leader with Rifle Grenade ({e.get('rifle_grenades')} rounds) as G! along the PDF to {rgz} [8.9 p.67]",
            "Auto" if ov else "4",
            {"Auto": "Grenade Attack"}
            if ov
            else {"1": "No Action", "2-3": "Grenade Attack", "4": "Advance Straight Ahead"},
        )
    if e.get("vof_rating") in ("A", "G", "H") and (firing_ or (e.get("vof_rating") == "G" and fire_candidates_g(s, n))):
        # L89: player aid O4: Assault 1/4 No Action, 2-3/4 Grenade Attack, 4/4 Advance; Overrun Auto Grenade Attack (previously swapped)
        return (
            "O4 A/G!/H with a valid target along the PDF",
            "Auto" if ov else "4",
            {"Auto": "Grenade Attack (or Concentrate Fire)"}
            if ov
            else {"1": "No Action", "2-3": "Grenade Attack (or Concentrate Fire)", "4": "Advance Straight Ahead"},
        )
    return (
        "O5 all other cases",
        "3" if ov else "4",
        {"1": "Infiltrate towards closest opposing unit", "2-3": "Advance Straight Ahead"}
        if ov
        else {"1": "No Action", "2-3": "Infiltrate towards closest opposing unit", "4": "Advance Straight Ahead"},
    )


def fire_candidates_g(s, n):
    """G! unit without PDF: target in LOS and range (player aid: 'Also applies to a G! rated unit on a card with no PDF, but with a target in LOS')."""
    e = s["einheiten"][n]
    return [
        k
        for k in s["karten"]
        if k != e["karte"]
        and state.valid_target(s, k, e["seite"])
        and geometry.in_range(s, e, k)
        and geometry.los(
            s,
            e["karte"],
            k,
            ha=geometry.height_bonus(s, e),
            hb=geometry.card_height_bonus(s, k, geometry.opponent_of(e)),
        )[0]
    ]


def leader_rg_target(s, n):
    """L67 [RULE 8.9 p.67] Leader with Rifle Grenade: 'can fire them along their card's existing PDF ... treat them as G!-rated units on the
    Enemy Activity Chart'. Returns the target card along an existing PDF of his card (rifle grenade range), else None."""
    e = s["einheiten"][n]
    if not e.get("leader") or e.get("rifle_grenades", 0) <= 0 or not state.good_order(e) or state.fire_team_side(e):
        return None
    kid = e["karte"]
    rw = s.get("rifle_grenade_reichweite", "C")
    for m, x in s["einheiten"].items():
        if (
            m == n
            or x.get("seite") != e["seite"]
            or x.get("karte") != kid
            or not fire.is_firing(x)
            or x.get("ziel") in (None, kid)
        ):
            continue
        z = x["ziel"]
        if state.valid_target(s, z, e["seite"]) and geometry.in_range(s, dict(e, range_=rw), z):
            return z
    return None


def leader_present(s, e):
    """[RULE 8.9 p.67] Good Order leader in Visual-Verbal (same card, same area)."""
    return any(
        x.get("leader")
        and x["seite"] == e["seite"]
        and x["karte"] == e["karte"]
        and x.get("bereich", "offen") == e.get("bereich", "offen")
        and state.good_order(x)
        and x is not e
        for x in s["einheiten"].values()
    )


LAT_WITH_LEADER = {
    "P1": ("4", {"1-2": "Move into or Seek Cover", "3": "Rally", "4": "Fall Back"}),
    "P2": ("3", {"1": "No Action", "2-3": "Rally"}),
    "P3": ("3", {"1": "No Action", "2": "Move into or Seek Cover", "3": "Rally"}),
    "P4": ("Auto", {"Auto": "Rally"}),
    "P6": ("Auto", {"Auto": "Grenade Attack"}),
    "P7": ("3", {"1": "No Action", "2-3": "Infiltrate to nearest opponent"}),
    "P8": ("4", {"1": "No Action", "2-3": "Move into or Seek Cover", "4": "Fall Back"}),
    "P9": ("3", {"1": "No Action", "2": "Grenade Attack", "3": "Fall Back"}),
    "P10": ("Auto", {"Auto": "Rally"}),
    "P11": ("Auto", {"Auto": "Rally"}),
    "P12": ("Auto", {"Auto": "Fall Back with Casualty"}),
    "P13": ("2", {"1": "No Action", "2": "Move towards closest Casualty"}),
    "P14": ("2", {"1": "No Action", "2": "Rally"}),
    "P15": ("2", {"1": "No Action", "2": "Rally"}),
}
