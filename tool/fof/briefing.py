"""Consistency check, check stamp and the board briefing (status)."""

from . import campaign, comms, contact, fire, geometry, messages, rules, setup, state


def vehicle_type_errors(s):
    """a unit whose 'vehicle' or 'at_weapon' is not a line of the AT chart would only crash in 3.6;
    the check names the valid chart keys (vehicles.chart / chart_line raise the Violation with them)."""
    from . import vehicles  # lazy: vehicles imports briefing indirectly

    f = []
    for n, e in s["units"].items():
        try:
            if e.get("vehicle"):
                vehicles.chart(e)
            if e.get("at_weapon"):
                vehicles.chart_line(e["at_weapon"])
        except rules.Violation as v:
            f.append(f"{n}: {v}")
    return f


def _unit_errors(s, f):
    """Units on unknown cards, duplicate markers, missing cover areas, impossible targets and flags."""
    for n, e in s["units"].items():
        if e["card"] is None and state.is_campaign(s) and state.in_setup(s):
            continue  # campaign: start card is chosen with 'setup'
        if e["card"] not in s["cards"]:
            f.append(f"{n} on unknown card {e['card']}")
            continue
        for m in set(e["status"]):
            if e["status"].count(m) > 1:
                f.append(f"{n} duplicate {m}")
        if e.get("area", "open") != "open" and fire.cover_of(s, e) is None:
            f.append(f"{n}: area {e['area']} does not exist on {e['card']}")
        if e.get("target") and e["target"] not in s["cards"]:
            f.append(f"{n} fires at unknown card {e['target']}")
        if e.get("last_step") and e.get("fire_team_side"):
            f.append(f"{n}: last_step and fire_team_side are mutually exclusive")


def _card_errors(s, f):
    """Cards with mixed Spotted status, cover shared by both sides or over capacity."""
    for card_id in s["cards"]:
        fe = [s["units"][n] for n in state.units_on(s, card_id, "Enemy")]
        if fe and len({bool(x.get("spotted")) for x in fe}) > 1:
            f.append(f"{card_id}: enemies mixed Spotted/Unspotted [8.5]")
        for cv in state.card(s, card_id).get("cover", []):
            sides = {s["units"][n]["side"] for n in state.units_on(s, card_id) if s["units"][n].get("area") == cv["id"]}
            if len(sides) > 1:
                f.append(f"{card_id}: cover {cv['id']} occupied by both sides [5.3]")
            if cv.get("capacity"):
                st = sum(
                    state.steps(s["units"][n])
                    for n in state.units_on(s, card_id)
                    if s["units"][n].get("area") == cv["id"]
                )
                if st > cv["capacity"]:
                    f.append(f"{card_id}: {cv['type']} {cv['id']} with {st} steps, capacity {cv['capacity']} [5.3.2]")


def consistency_check(s):
    """Errors of the game state that must never be saved; an empty list if it is consistent."""
    f = vehicle_type_errors(s)
    _unit_errors(s, f)
    _card_errors(s, f)
    for n, k in s["commands"].items():
        if k["available"] < 0 or k["saved"] < 0:
            f.append(f"{n}: negative Commands")
    if s["phase"] not in dict(state.sop(s)):
        f.append(f"Phase {s['phase']} not in the sequence of play")
    if s.get("activity") is not None and s["phase"] != "3.7.4" and fire.expected_activity(s) != s["activity"]:
        f.append(f"Activity level is {s['activity']}, the board implies {fire.expected_activity(s)} [8.1]")
    if s.get("ccp") and s["ccp"] not in s["cards"]:
        f.append(f"CCP on unknown card {s['ccp']}")
    return f


def check_stamp(s):
    notes = [f"{messages.BOARD}: " + x for x in dict.fromkeys(state.MARKER_NOTES)]
    state.MARKER_NOTES.clear()
    return "\n".join(notes + [_check_stamp(s)])


def _check_stamp(s, errors=None):
    """errors: result of a consistency_check that just ran on this unchanged state (save_state), so it is not repeated."""
    f = consistency_check(s) if errors is None else errors
    if f:
        return f"{messages.CHECKSTAMP}: ERROR " + "; ".join(f)
    off = [n for n, e in s["units"].items() if e.get("target_open")]
    return f"{messages.CHECKSTAMP} OK Turn {s['turn']} Phase {s['phase']} Entry {len(s['protocol'])}" + (
        f" (open: fire target {', '.join(off)})" if off else ""
    )


def radio_overview(s):
    """Connections of the CO HQ: BN TAC and CO TAC to every other radio."""
    co = s["co_hq"]
    out = []
    ok, g = comms.bn_link(s)
    out.append(f"BN HQ (off-map) with {co}: {'yes' if ok else 'NO'}, {g}")
    if co not in s["units"]:
        out.append(
            f"{co} not in play: no hub for the CO TAC Net [RULE 4.3.3 p.27]; reconstitution per 6.5.2 p.49/50 (new CO HQ needs a BN TAC device, FM1 p.38)"
        )
    for n, e in s["units"].items():
        if n == co or not [g for g in e.get("radio", []) if "FD" not in g.get("net", "")] or co not in s["units"]:
            continue
        if e.get("card") is None or s["units"][co].get("card") is None:
            out.append(f"{co} with {n}: start card still missing")
            continue
        ok, g = comms.radio_link(s, co, n)
        out.append(f"{co} with {n}: {'yes' if ok else 'no'}, {g}")
    for n, e in s["units"].items():
        if e["type"] == "FO":
            fd = [x for x in comms.radios_of(e) if "FD" in x["net"]]
            out.append(
                f"{n}: {'FD radio ' + fd[0]['net'] if fd else ('FD radio implied' + state.open_reading(s, 'U2_fo_fd_radio') if state.option(s, 'U2_fo_fd_radio') else 'no FD radio' + state.open_reading(s, 'U2_fo_fd_radio'))}"
            )
    return out


def objective_status(s):
    """Mission objective CAC: eliminate all enemies [FM1 p.36], clear all PC markers [FM1 p.48]. campaign: secure objectives, clear rows."""
    if "secure" in s.get("objective_rules", {}):
        ok, txt = campaign.campaign_objective_status(s)
        return (
            txt
            + f"; objective {'FULFILLED' if ok else 'open'}, turn {s['turn']} of {s['max_turns']}, attempt {s['campaign'].get('attempt', 1)} of {s['campaign'].get('attempts_max', 1)}"
        )
    enemies = [n for n, e in s["units"].items() if e["side"] == "Enemy"]
    pcs = [k for k, c in s["cards"].items() if c.get("pc")]
    t = f"{len(enemies)} enemy units on the board" + (f" ({', '.join(enemies)})" if enemies else "")
    if s["objective_rules"].get("clear_pcs"):
        t += f", {len(pcs)} PC markers open" + (f" ({', '.join(pcs)})" if pcs else "")
    fulfilled = not enemies and not (s["objective_rules"].get("clear_pcs") and pcs)
    t += f"; objective {'FULFILLED' if fulfilled else 'open'}, turn {s['turn']} of {s['max_turns']}"
    if "options" in s:
        t += f"; 'eliminate' per reading {state.option(s, 'U9_objective_reading')}{state.open_reading(s, 'U9_objective_reading')}"
    return t


def unit_text(n, e):
    t = n
    if state.steps(e) != 1 and not (e.get("arty_jeep") or e.get("company_jeep")):  # crewless jeeps show no steps
        t += f"({state.steps(e)}St)"
    st = list(e["status"])
    if e["side"] == "Enemy":
        st.append("spotted" if e.get("spotted") else "unspotted")
    if e.get("area", "open") != "open":
        st.append(f"in {e['area']}")
    if e.get("target"):
        st.append("fires at " + e["target"])
    if e.get("target_open"):
        st.append("TARGET OPEN")
    if e.get("cf"):
        st.append(f"CF x{e['cf']}")
    if e.get("on_board"):
        st.append(f"on board the {e['on_board']}")
    if e.get("radio"):
        st.append(
            "Radio "
            + "/".join(
                g["type"]
                + ("(destroyed)" if g.get("destroyed") else "")
                + (f"(mounted in {g['mounted']})" if g.get("mounted") else "")
                for g in e["radio"]
            )
        )
    if e.get("carries_casualties"):
        st.append(f"carries {e['carries_casualties']} Casualty")
    if e.get("indirect"):
        st.append("Indirect Lay")
    if e.get("ammo"):
        st.append(f"{e['ammo']['type']} {e['ammo']['points']}" + (" OUT OF AMMO" if e.get("out_of_ammo") else ""))
    if e.get("carries_ammo"):
        st.append(f"carries {e['carries_ammo']['points']} {e['carries_ammo']['type']}")
    if e.get("mine_hit"):
        st.append("under Mine marker")
    if e.get("assets"):
        st.append("Assets " + "/".join(e["assets"]))
    if e.get("lines"):
        st.append(f"{e['lines']} Phone Line(s)")
    if e.get("runner_target"):
        st.append(f"Runner for {e['runner_target']}")
    if e.get("pdf_only"):
        st.append("PDF (Grenade Attack)")
    if e.get("no_fire_until_clean_up"):
        st.append("opens fire in Clean Up")
    if e.get("card") is None:
        st.append("START CARD OPEN")
    return t + (" [" + ", ".join(st) + "]" if st else "")


def briefing(s, errors=None):
    """Board briefing, also written to <game>/BRIEFING.md. errors: see _check_stamp."""
    lines = [
        f"# BRIEFING {s['mission']}",
        f"Turn {s['turn']} of {s['max_turns']}, Phase {s['phase']} {state.phase_name(s)}",
        f"Visibility {({'limited': 'limited', 'day': 'day'}).get(s['sight'], s['sight'])}"
        + (" (light {:+d}, weather {:+d})".format(*geometry.light_weather(s)) if sum(geometry.light_weather(s)) else "")
        + f", activity {s.get('activity') or 'not tracked'}, active HQ {s.get('active_hq') or 'none'}",
        "",
    ]
    if s.get("patrol_mission") and s.get("patrol"):
        lines.extend(patrol_lines(s))
    lines.append("## Commands")
    for n, k in s["commands"].items():
        lines.append(
            f"- {n}: available {k['available']}, saved {k['saved']}, activated {'yes' if k['activated'] else 'no'}, done {'yes' if k['done'] else 'no'}"
        )
    lines.append("")
    lines.append("## Board (card terrain (C&C) [markers]: units)")
    for card_id, k in sorted(s["cards"].items(), key=lambda x: (-x[1]["row"], x[1]["column"])):
        lines.append(card_line(s, card_id, k))
    lines.extend(board_totals(s))
    if state.company(s) and state.radio_active(s):
        lines.append("")
        lines.append("## Radio (CO TAC Net, BN TAC)")
        lines.extend("- " + t for t in radio_overview(s))
    if state.is_campaign(s):
        lines.extend(campaign_lines(s))
    if s.get("objective_rules"):
        lines.append("")
        lines.append("## Objective")
        lines.append("- " + objective_status(s))
    lines.append("")
    lines.append("## Last entries")
    for p in s["protocol"][-8:]:
        lines.append(
            f"- {p['number']} T{p['turn']} {p['phase']}: {p['text']}"
            + (f" [RULE {p['rule']}]" if p.get("rule") else "")
        )
    lines.append("")
    lines.append(_check_stamp(s, errors))
    txt = "\n".join(lines) + "\n"
    try:
        state.write_atomic(state.game_dir() / "BRIEFING.md", txt)
    except OSError as err:  # the entry is saved already; the briefing file is a convenience
        print(f"NOTE: BRIEFING.md not written ({err}); fof.py status shows the same text")
    return txt


def patrol_lines(s):
    """Patrol mission: route, progress and success of the Patrol Platoon [Normandy M3]."""
    lines = []
    p = s["patrol"]
    zr = s.get("objectives", {}).get("route", {})
    lines.append(
        f"Patrol Platoon {p.get('platoon') or '-'}: route "
        + ", ".join(f"{i}:{zr.get(str(i)) or '-'}" for i in (1, 2, 3, 4))
        + f", reached {p.get('route_index', 0)}/4, Primary {'passed' if p.get('primary_visited') else 'open'}, success {'yes' if p.get('success') else 'no'}; done: {', '.join(p.get('completed', [])) or '-'}"
    )
    lines.append("")
    return lines


def card_markers(s, card_id, k):
    """The bracketed markers of one card line: cover, VOF, external markers, casualties, assets, objectives, ..."""
    extra = []
    for cv in k.get("cover", []):
        extra.append(
            f"Cover {cv['id']} {cv['type']} +{cv['value']}"
            + (f" ({cv['capacity']})" if cv.get("capacity") else "")
            + (
                f" arrow {rules.SIDE_NAME.get(tuple(cv['direction']), 'diagonal')} {tuple(cv['direction'])}"
                if cv.get("direction")
                else ""
            )
        )
    vu, vf = (
        fire.vof_against(s, card_id, "US", ignore_mines=True),
        fire.vof_against(s, card_id, "Enemy", ignore_mines=True),
    )
    if vu and state.units_on(s, card_id, "US"):
        extra.append(
            f"VOF on US: {rules.VOF_NAME.get(vu[0], vu[0])} {vu[1]:+d} from {','.join(vu[2])}"
            + (" +Crossfire" if fire.crossfire(s, card_id, "US") else "")
        )
    if vf and state.units_on(s, card_id, "Enemy"):
        extra.append(
            f"VOF on enemy: {rules.VOF_NAME.get(vf[0], vf[0])} {vf[1]:+d} from {','.join(vf[2])}"
            + (" +Crossfire" if fire.crossfire(s, card_id, "Enemy") else "")
        )
    if (vu or vf) and not state.units_on(s, card_id):
        v = vu or vf
        extra.append(f"VOF on empty card: {rules.VOF_NAME.get(v[0], v[0])} from {','.join(v[2])}")
    for x in k.get("external", []):
        if x["type"] == "Pending":
            extra.append(f"Pending Fire Mission {x['value']}" + (f" ({x['agency']})" if x.get("agency") else ""))
    if k.get("grenade_miss"):
        extra.append("Grenade Miss")
    for m in k.get("illum", []):
        extra.append(
            f"Illumination {m['top']:+d}"
            + (f"/{m['bottom']:+d}" if m.get("bottom") is not None else "")
            + f" ({m.get('source', '?')})"
        )
    if s["sight"] == "limited" and geometry.is_illuminated(s, card_id):
        extra.append(f"illuminated (visibility {geometry.visibility_on_card(s, card_id):+d})")
    if k.get("pc"):
        extra.append("PC " + k["pc"])
    if k.get("casualties"):
        extra.append(f"US casualties {k['casualties']}")
    if k.get("casualties_enemy"):
        extra.append(f"enemy casualties {k['casualties_enemy']}")
    for g in k.get("assets", []):
        extra.append(
            f"lying here: {g['type']} {g['net']}"
            + (" (R# 1/2 open: fof.py radio damage)" if g.get("damage_open") else "")
        )
    if k.get("assets_ground"):
        extra.append("lying here: " + ", ".join(k["assets_ground"]))  # dropped Assets, Pick Up 4.2.2h
    if s.get("ccp") == card_id:
        extra.append("CCP")
    for x in k.get("external", []):
        if x["type"] == "Mines":
            extra.append("Mines! " + ("triggered" if x.get("active") else "(Draw 3)"))
        if x["type"] == "Smoke":
            extra.append(f"Smoke {x.get('source', '')} +{x.get('value', 0)}")
    for l in k.get("lines", []):
        extra.append("Phone Line" + (" CUT" if l.get("cut") else ""))
    if k.get("line_assets"):
        extra.append(f"{k['line_assets']} Phone Line(s) lying here")
    for mt, mz in k.get("ammo", {}).items():
        if mz:
            extra.append(f"Ammo {mt} {mz}")
    for py in k.get("pyro", []):
        extra.append(f"Signal {py}")
    if k.get("pc2"):
        extra.append("second PC " + k["pc2"])
    for objective, objective_card in s.get("objectives", {}).items():
        if objective_card == card_id and objective != "phaselines":
            extra.append(
                {
                    "primary": "Primary Objective",
                    "secondary": "Secondary Objective",
                    "ap": "Attack Position",
                    "ccp": "CCP (preset)",
                }.get(objective, objective)
            )
    if k.get("outside"):
        extra.append("outside the boundaries")
    for spotter, marker_card in s.get("enemy_target", {}).items():
        if marker_card == card_id:
            extra.append(f"enemy Target marker ({spotter})")
    for ag, marker_card in s.get("target_marker", {}).items():
        if marker_card == card_id:
            extra.append(f"Target marker {ag}")
    return extra


def card_line(s, card_id, k):
    """One board line: card, terrain, C&C, markers and the units on it."""
    extra = card_markers(s, card_id, k)
    one = [unit_text(n, s["units"][n]) for n in state.units_on(s, card_id)]
    cc_txt = (
        f"+{k.get('cc', 0)}" + (f"/+{k['cc2']}" if k.get("cc2") is not None else "")
        if k.get("cc") is not None
        else "C&C open"
    )
    return f"- {card_id} {k['terrain'] or 'TERRAIN NOT SET'} ({cc_txt}){' [' + '; '.join(extra) + ']' if extra else ''}: {', '.join(one) if one else '-'}"


def board_totals(s):
    """Lines after the board: units without a card, Fire Missions, evacuated, packages, Removed from Play, prisoners."""
    lines = []
    without_cards = [n for n, e in s["units"].items() if e.get("card") is None]
    if without_cards:
        lines.append("- Start card open: " + ", ".join(without_cards))
    if s.get("fm_values"):
        lines.append(
            f"- Fire Missions: {s.get('fire_missions')}; "
            + ", ".join(f"{a} {w:+d}" for a, w in s["fm_values"].items())
            + "; observers "
            + ", ".join(f"{b} {n} card(s)" for b, n in s.get("cff_observers", {}).items())
        )
    elif s.get("fire_missions") is not None:
        lines.append(f"- Fire Missions Mtr FO: {s['fire_missions']}")
    if s.get("evacuated"):
        lines.append(f"- Evacuated casualties: {s['evacuated']}")
    if s.get("packages"):
        lines.append(
            "- Enemy packages: "
            + "; ".join(f"{p} {'free' if contact.package_available(s, p) else 'in use'}" for p in s["packages"])
        )
    if s.get("removed_from_play"):
        lines.append("- Removed from Play: " + ", ".join(s["removed_from_play"]))
    if s.get("prisoners"):
        lines.append(f"- Prisoners: {s['prisoners']}")
    return lines


def campaign_lines(s):
    """campaign section: mission, attempt, Experience, CO TAC, mortars, events, open checks."""
    lines = []
    lines.append("")
    lines.append("## Campaign")
    k = s["campaign"]
    lines.append(
        f"- Mission {k.get('mission_no')}, attempt {k.get('attempt')} of {k.get('attempts_max')}; Experience {sum(x['points'] for x in s.get('xp', []))}; "
        f"US casualty steps {s.get('us_casualties_total', 0)}; enemy tactic {s.get('enemy_tactic')}"
        + (f" (counterattack until turn {s['counterattack']['until_turn']})" if s.get("counterattack") else "")
    )
    lines.append(
        f"- CO TAC: {s.get('co_tac_medium') or 'choice open (CSR 1)'}; mortars: {s.get('mortar_choice') or 'choice open (CSR 2)'}; runners in the box: {', '.join(s.get('runner_box', [])) or 'none'}"
        + (f"; phone lines in the pool {s['lines_pool']}" if s.get("lines_pool") is not None else "")
    )
    if s.get("pyro_codes"):
        lines.append("- Pyro: " + ", ".join(f"{a}={b}" for a, b in s["pyro_codes"].items()))
    if state.in_setup(s):  # note before turn 1 (2.3.4), not blocking
        for h in setup.campaign_setup_notes(s):
            lines.append("- Before turn 1 (note): " + h)
    if s.get("objectives", {}).get("phaselines"):
        lines.append(
            "- Phase Lines: " + ", ".join(f"PL{a} across row {b}" for a, b in s["objectives"]["phaselines"].items())
        )
    active = []
    for key in ("event_task", "event_flank", "fm_blocked", "event_ammo", "bn_unavailable"):
        w = s.get(key)
        if w is not None and (w.get("turn") if isinstance(w, dict) else w) == s["turn"]:
            active.append(key)
    if active:
        lines.append("- Event active: " + ", ".join(active))
    if s.get("mine_checks"):
        lines.append("- MINE CHECK OPEN: " + ", ".join(s["mine_checks"]))
    if s.get("reattempt_setup"):
        lines.append("- REATTEMPT PREPARATION (3.9): reconstitute, setup, then reattempt done")
    return lines


def reveal_lines(s):
    """face-down cards now in LOS of friendly units (or of the Staging Area before turn 1).
    a card seen only over another face-down card is announced as 'wait': reveal the nearer card first,
    the tool checks the line again (a Hill there can block it, 5.2.2)."""
    cand = geometry.reveal_candidates(s)
    dep = geometry.reveal_dependencies(s, cand)
    lines = []
    for k, v in sorted(cand.items()):
        if k in dep:
            lines.append(
                f"WAIT with face-down card {k}: LOS from {', '.join(v)} passes over face-down {', '.join(dep[k])}; reveal "
                f"{', '.join(dep[k])} first, then the line is checked again (a Hill there can block it) [RULE 5.2.2 p.35]"
            )
        else:
            lines.append(
                f"Reveal face-down card {k} (LOS from {', '.join(v)}): flip it and enter fof.py terrain {k} <type> [--hill=n if it is a Hill: draw a new card on top] [RULE 5.2 p.34, 2.2.1 p.9]"
            )
    return lines


def print_board(prot, s):
    for p in prot:
        print(f"{messages.BOARD}: " + p)
    for p in reveal_lines(s):
        print(f"{messages.BOARD}: " + p)
    for h in dict.fromkeys(s.pop("_hints", [])):
        print(f"{messages.NOTE}: " + h)
    print(check_stamp(s))
