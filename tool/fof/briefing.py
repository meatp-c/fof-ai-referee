"""Consistency check, check stamp and the board briefing (status)."""

from . import campaign, comms, contact, fire, geometry, messages, rules, setup, state


def consistency_check(s):
    f = []
    for n, e in s["einheiten"].items():
        if e["karte"] is None and state.is_v4(s) and state.in_setup(s):
            continue  # v4: start card is chosen with 'setup'
        if e["karte"] not in s["karten"]:
            f.append(f"{n} on unknown card {e['karte']}")
            continue
        for m in set(e["status"]):
            if e["status"].count(m) > 1:
                f.append(f"{n} duplicate {m}")
        if e.get("bereich", "offen") != "offen" and fire.cover_of(s, e) is None:
            f.append(f"{n}: area {e['bereich']} does not exist on {e['karte']}")
        if e.get("ziel") and e["ziel"] not in s["karten"]:
            f.append(f"{n} fires at unknown card {e['ziel']}")
        if e.get("letzter_step") and e.get("fire_team_seite"):
            f.append(f"{n}: letzter_step and fire_team_seite are mutually exclusive")
    for kid in s["karten"]:
        fe = [s["einheiten"][n] for n in state.units_on(s, kid, "Feind")]
        if fe and len({bool(x.get("spotted")) for x in fe}) > 1:
            f.append(f"{kid}: enemies mixed Spotted/Unspotted [8.5]")
        for cv in state.card(s, kid).get("cover", []):
            sides = {
                s["einheiten"][n]["seite"]
                for n in state.units_on(s, kid)
                if s["einheiten"][n].get("bereich") == cv["id"]
            }
            if len(sides) > 1:
                f.append(f"{kid}: cover {cv['id']} occupied by both sides [5.3]")
            if cv.get("kapazitaet"):
                st = sum(
                    state.steps(s["einheiten"][n])
                    for n in state.units_on(s, kid)
                    if s["einheiten"][n].get("bereich") == cv["id"]
                )
                if st > cv["kapazitaet"]:
                    f.append(f"{kid}: {cv['typ']} {cv['id']} with {st} steps, capacity {cv['kapazitaet']} [5.3.2]")
    for n, k in s["kommandos"].items():
        if k["verfuegbar"] < 0 or k["gespart"] < 0:
            f.append(f"{n}: negative Commands")
    if s["phase"] not in dict(state.sop(s)):
        f.append(f"Phase {s['phase']} not in the sequence of play")
    if s.get("aktivitaet") is not None and s["phase"] != "3.7.4" and fire.expected_activity(s) != s["aktivitaet"]:
        f.append(f"Activity level is {s['aktivitaet']}, the board implies {fire.expected_activity(s)} [8.1]")
    if s.get("ccp") and s["ccp"] not in s["karten"]:
        f.append(f"CCP on unknown card {s['ccp']}")
    return f


def check_stamp(s):
    f = consistency_check(s)
    if f:
        return f"{messages.CHECKSTAMP}: ERROR " + "; ".join(f)
    off = [n for n, e in s["einheiten"].items() if e.get("ziel_offen")]
    return f"{messages.CHECKSTAMP} OK Turn {s['zug']} Phase {s['phase']} Entry {len(s['protokoll'])}" + (
        f" (open: fire target {', '.join(off)})" if off else ""
    )


def radio_overview(s):
    """Connections of the CO HQ: BN TAC and CO TAC to every other radio."""
    co = s["co_hq"]
    out = []
    ok, g = comms.bn_link(s)
    out.append(f"BN HQ (off-map) with {co}: {'yes' if ok else 'NO'}, {g}")
    if co not in s["einheiten"]:
        out.append(
            f"{co} not in play: no hub for the CO TAC Net [RULE 4.3.3 p.27]; reconstitution per 6.5.2 p.49/50 (new CO HQ needs a BN TAC device, FM1 p.38)"
        )
    for n, e in s["einheiten"].items():
        if n == co or not [g for g in e.get("funk", []) if "FD" not in g.get("netz", "")] or co not in s["einheiten"]:
            continue
        if e.get("karte") is None or s["einheiten"][co].get("karte") is None:
            out.append(f"{co} with {n}: start card still missing")
            continue
        ok, g = comms.radio_link(s, co, n)
        out.append(f"{co} with {n}: {'yes' if ok else 'no'}, {g}")
    for n, e in s["einheiten"].items():
        if e["typ"] == "FO":
            fd = [x for x in comms.radios_of(e) if "FD" in x["netz"]]
            out.append(
                f"{n}: {'FD radio ' + fd[0]['netz'] if fd else ('FD radio implied' + state.open_reading(s, 'U2_fo_fd_funk') if state.option(s, 'U2_fo_fd_funk') else 'no FD radio' + state.open_reading(s, 'U2_fo_fd_funk'))}"
            )
    return out


def objective_status(s):
    """Mission objective CAC: eliminate all enemies [FM1 p.36], clear all PC markers [FM1 p.48]. v4: secure objectives, clear rows."""
    if "sichern" in s.get("ziel_regeln", {}):
        ok, txt = campaign.objective_status_v4(s)
        return (
            txt
            + f"; objective {'FULFILLED' if ok else 'open'}, turn {s['zug']} of {s['max_zuege']}, attempt {s['kampagne'].get('versuch', 1)} of {s['kampagne'].get('versuche_max', 1)}"
        )
    enemies = [n for n, e in s["einheiten"].items() if e["seite"] == "Feind"]
    pcs = [k for k, c in s["karten"].items() if c.get("pc")]
    t = f"{len(enemies)} enemy units on the board" + (f" ({', '.join(enemies)})" if enemies else "")
    if s["ziel_regeln"].get("pc_klaeren"):
        t += f", {len(pcs)} PC markers open" + (f" ({', '.join(pcs)})" if pcs else "")
    fulfilled = not enemies and not (s["ziel_regeln"].get("pc_klaeren") and pcs)
    t += f"; objective {'FULFILLED' if fulfilled else 'open'}, turn {s['zug']} of {s['max_zuege']}"
    if "optionen" in s:
        t += f"; 'eliminate' per reading {state.option(s, 'U9_ziel_lesart')}{state.open_reading(s, 'U9_ziel_lesart')}"
    return t


def unit_text(n, e):
    t = n
    if state.steps(e) != 1:
        t += f"({state.steps(e)}St)"
    st = list(e["status"])
    if e["seite"] == "Feind":
        st.append("spotted" if e.get("spotted") else "unspotted")
    if e.get("bereich", "offen") != "offen":
        st.append(f"in {e['bereich']}")
    if e.get("ziel"):
        st.append("fires at " + e["ziel"])
    if e.get("ziel_offen"):
        st.append("TARGET OPEN")
    if e.get("cf"):
        st.append(f"CF x{e['cf']}")
    if e.get("funk"):
        st.append("Radio " + "/".join(g["typ"] + ("(destroyed)" if g.get("zerstoert") else "") for g in e["funk"]))
    if e.get("traegt_casualties"):
        st.append(f"carries {e['traegt_casualties']} Casualty")
    if e.get("indirekt"):
        st.append("Indirect Lay")
    if e.get("munition"):
        st.append(
            f"{e['munition']['typ']} {e['munition']['punkte']}" + (" OUT OF AMMO" if e.get("out_of_ammo") else "")
        )
    if e.get("traegt_munition"):
        st.append(f"carries {e['traegt_munition']['punkte']} {e['traegt_munition']['typ']}")
    if e.get("mine_hit"):
        st.append("under Mine marker")
    if e.get("assets"):
        st.append("Assets " + "/".join(e["assets"]))
    if e.get("leitungen"):
        st.append(f"{e['leitungen']} Phone Line(s)")
    if e.get("runner_ziel"):
        st.append(f"Runner for {e['runner_ziel']}")
    if e.get("nur_pdf"):
        st.append("PDF (Grenade Attack)")
    if e.get("kein_feuer_bis_clean_up"):
        st.append("opens fire in Clean Up")
    if e.get("karte") is None:
        st.append("START CARD OPEN")
    return t + (" [" + ", ".join(st) + "]" if st else "")


def briefing(s):
    z = [
        f"# BRIEFING {s['mission']}",
        f"Turn {s['zug']} of {s['max_zuege']}, Phase {s['phase']} {state.phase_name(s)}",
        f"Visibility {({'eingeschraenkt': 'limited', 'tag': 'day'}).get(s['sicht'], s['sicht'])}"
        + (" (light {:+d}, weather {:+d})".format(*geometry.light_weather(s)) if sum(geometry.light_weather(s)) else "")
        + f", activity {s.get('aktivitaet') or 'not tracked'}, active HQ {s.get('aktiver_hq') or 'none'}",
        "",
    ]
    if s.get("patrouille_mission") and s.get("patrouille"):
        p = s["patrouille"]
        zr = s.get("ziele", {}).get("route", {})
        z.append(
            f"Patrol Platoon {p.get('platoon') or '-'}: route "
            + ", ".join(f"{i}:{zr.get(str(i)) or '-'}" for i in (1, 2, 3, 4))
            + f", reached {p.get('route_index', 0)}/4, Primary {'passed' if p.get('primaer_besucht') else 'open'}, success {'yes' if p.get('erfolg') else 'no'}; done: {', '.join(p.get('erledigt', [])) or '-'}"
        )
        z.append("")
    z.append("## Commands")
    for n, k in s["kommandos"].items():
        z.append(
            f"- {n}: available {k['verfuegbar']}, saved {k['gespart']}, activated {'yes' if k['aktiviert'] else 'no'}, done {'yes' if k['fertig'] else 'no'}"
        )
    z.append("")
    z.append("## Board (card terrain (C&C) [markers]: units)")
    for kid, k in sorted(s["karten"].items(), key=lambda x: (-x[1]["reihe"], x[1]["spalte"])):
        extra = []
        for cv in k.get("cover", []):
            extra.append(
                f"Cover {cv['id']} {cv['typ']} +{cv['wert']}"
                + (f" ({cv['kapazitaet']})" if cv.get("kapazitaet") else "")
                + (
                    f" arrow {rules.SIDE_NAME.get(tuple(cv['richtung']), 'diagonal')} {tuple(cv['richtung'])}"
                    if cv.get("richtung")
                    else ""
                )
            )
        vu, vf = fire.vof_against(s, kid, "US", ignore_mines=True), fire.vof_against(s, kid, "Feind", ignore_mines=True)
        if vu and state.units_on(s, kid, "US"):
            extra.append(
                f"VOF on US: {rules.VOF_NAME.get(vu[0], vu[0])} {vu[1]:+d} from {','.join(vu[2])}"
                + (" +Crossfire" if fire.crossfire(s, kid, "US") else "")
            )
        if vf and state.units_on(s, kid, "Feind"):
            extra.append(
                f"VOF on enemy: {rules.VOF_NAME.get(vf[0], vf[0])} {vf[1]:+d} from {','.join(vf[2])}"
                + (" +Crossfire" if fire.crossfire(s, kid, "Feind") else "")
            )
        if (vu or vf) and not state.units_on(s, kid):
            v = vu or vf
            extra.append(f"VOF on empty card: {rules.VOF_NAME.get(v[0], v[0])} from {','.join(v[2])}")
        for x in k.get("extern", []):
            if x["typ"] == "Pending":
                extra.append(f"Pending Fire Mission {x['wert']}" + (f" ({x['agentur']})" if x.get("agentur") else ""))
        if k.get("grenade_miss"):
            extra.append("Grenade Miss")
        for m in k.get("illum", []):
            extra.append(
                f"Illumination {m['oben']:+d}"
                + (f"/{m['unten']:+d}" if m.get("unten") is not None else "")
                + f" ({m.get('quelle', '?')})"
            )
        if s["sicht"] == "eingeschraenkt" and geometry.is_illuminated(s, kid):
            extra.append(f"illuminated (visibility {geometry.visibility_on_card(s, kid):+d})")
        if k.get("pc"):
            extra.append("PC " + k["pc"])
        if k.get("casualties"):
            extra.append(f"US casualties {k['casualties']}")
        if k.get("casualties_feind"):
            extra.append(f"enemy casualties {k['casualties_feind']}")
        for g in k.get("assets", []):
            extra.append(
                f"lying here: {g['typ']} {g['netz']}"
                + (" (R# 1/2 open: fof.py radio damage)" if g.get("schaden_offen") else "")
            )
        if s.get("ccp") == kid:
            extra.append("CCP")
        for x in k.get("extern", []):
            if x["typ"] == "Mines":
                extra.append("Mines! " + ("triggered" if x.get("aktiv") else "(Draw 3)"))
            if x["typ"] == "Smoke":
                extra.append(f"Smoke {x.get('quelle', '')} +{x.get('wert', 0)}")
        for l in k.get("leitungen", []):
            extra.append("Phone Line" + (" CUT" if l.get("cut") else ""))
        if k.get("leitung_assets"):
            extra.append(f"{k['leitung_assets']} Phone Line(s) lying here")
        for mt, mz in k.get("munition", {}).items():
            if mz:
                extra.append(f"Ammo {mt} {mz}")
        for py in k.get("pyro", []):
            extra.append(f"Signal {py}")
        if k.get("pc2"):
            extra.append("second PC " + k["pc2"])
        for zn, zk in s.get("ziele", {}).items():
            if zk == kid and zn != "phaselines":
                extra.append(
                    {
                        "primaer": "Primary Objective",
                        "sekundaer": "Secondary Objective",
                        "ap": "Attack Position",
                        "ccp": "CCP (preset)",
                    }.get(zn, zn)
                )
        if k.get("ausserhalb"):
            extra.append("outside the boundaries")
        for sp, tk in s.get("feind_target", {}).items():
            if tk == kid:
                extra.append(f"enemy Target marker ({sp})")
        for ag, tk in s.get("target_marker", {}).items():
            if tk == kid:
                extra.append(f"Target marker {ag}")
        one = [unit_text(n, s["einheiten"][n]) for n in state.units_on(s, kid)]
        cc_txt = (
            f"+{k.get('cc', 0)}" + (f"/+{k['cc2']}" if k.get("cc2") is not None else "")
            if k.get("cc") is not None
            else "C&C open"
        )
        z.append(
            f"- {kid} {k['terrain'] or 'TERRAIN NOT SET'} ({cc_txt}){' [' + '; '.join(extra) + ']' if extra else ''}: {', '.join(one) if one else '-'}"
        )
    without_cards = [n for n, e in s["einheiten"].items() if e.get("karte") is None]
    if without_cards:
        z.append("- Start card open: " + ", ".join(without_cards))
    if s.get("fm_werte"):
        z.append(
            f"- Fire Missions: {s.get('feuermissionen')}; "
            + ", ".join(f"{a} {w:+d}" for a, w in s["fm_werte"].items())
            + "; observers "
            + ", ".join(f"{b} {n} card(s)" for b, n in s.get("cff_beobachter", {}).items())
        )
    elif s.get("feuermissionen") is not None:
        z.append(f"- Fire Missions Mtr FO: {s['feuermissionen']}")
    if s.get("evakuiert"):
        z.append(f"- Evacuated casualties: {s['evakuiert']}")
    if s.get("pakete"):
        z.append(
            "- Enemy packages: "
            + "; ".join(f"{p} {'free' if contact.package_available(s, p) else 'in use'}" for p in s["pakete"])
        )
    if s.get("removed_from_play"):
        z.append("- Removed from Play: " + ", ".join(s["removed_from_play"]))
    if s.get("gefangene"):
        z.append(f"- Prisoners: {s['gefangene']}")
    if state.company(s) and state.radio_active(s):
        z.append("")
        z.append("## Radio (CO TAC Net, BN TAC)")
        z.extend("- " + t for t in radio_overview(s))
    if state.is_v4(s):
        z.append("")
        z.append("## Campaign")
        k = s["kampagne"]
        z.append(
            f"- Mission {k.get('mission_nr')}, attempt {k.get('versuch')} of {k.get('versuche_max')}; Experience {sum(x['punkte'] for x in s.get('xp', []))}; "
            f"US casualty steps {s.get('us_casualties_gesamt', 0)}; enemy tactic {s.get('feind_taktik')}"
            + (f" (counterattack until turn {s['gegenangriff']['bis_zug']})" if s.get("gegenangriff") else "")
        )
        z.append(
            f"- CO TAC: {s.get('co_tac_mittel') or 'choice open (CSR 1)'}; mortars: {s.get('moerser_wahl') or 'choice open (CSR 2)'}; runners in the box: {', '.join(s.get('runner_box', [])) or 'none'}"
            + (f"; phone lines in the pool {s['leitungen_pool']}" if s.get("leitungen_pool") is not None else "")
        )
        if s.get("pyro_belegung"):
            z.append("- Pyro: " + ", ".join(f"{a}={b}" for a, b in s["pyro_belegung"].items()))
        if state.in_setup(s):  # L77: note before turn 1 (2.3.4), not blocking
            for h in setup.setup_notes_v4(s):
                z.append("- Before turn 1 (note): " + h)
        if s.get("ziele", {}).get("phaselines"):
            z.append(
                "- Phase Lines: " + ", ".join(f"PL{a} across row {b}" for a, b in s["ziele"]["phaselines"].items())
            )
        akt = []
        for key in ("ereignis_pflicht", "ereignis_flanke", "fm_gesperrt", "ereignis_munition", "bn_nicht_verfuegbar"):
            w = s.get(key)
            if w is not None and (w.get("zug") if isinstance(w, dict) else w) == s["zug"]:
                akt.append(key)
        if akt:
            z.append("- Event active: " + ", ".join(akt))
        if s.get("minen_checks"):
            z.append("- MINE CHECK OPEN: " + ", ".join(s["minen_checks"]))
        if s.get("reattempt_setup"):
            z.append("- REATTEMPT PREPARATION (3.9): reconstitute, setup, then reattempt done")
    if s.get("ziel_regeln"):
        z.append("")
        z.append("## Objective")
        z.append("- " + objective_status(s))
    z.append("")
    z.append("## Last entries")
    for p in s["protokoll"][-8:]:
        z.append(
            f"- {p['nr']} T{p['zug']} {p['phase']}: {p['text']}" + (f" [RULE {p['regel']}]" if p.get("regel") else "")
        )
    z.append("")
    z.append(check_stamp(s))
    txt = "\n".join(z) + "\n"
    (state.game_dir() / "BRIEFING.md").write_text(txt, encoding="utf-8")
    return txt


def print_board(prot, s):
    for p in prot:
        print(f"{messages.BOARD}: " + p)
    for h in dict.fromkeys(s.pop("_hinweise", [])):
        print(f"{messages.NOTE}: " + h)
    print(check_stamp(s))
