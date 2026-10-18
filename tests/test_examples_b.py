"""Durchgerechnete Beispiele des Regelbuchs (Series Rules 3rd Ed.), Teil B: 5.1.6, 5.2, 5.3, 6.0 bis 6.5.
Jeder Test baut die Lage des Beispiels auf dem synthetischen Brett nach und prueft das Ergebnis des Werkzeugs
gegen das Beispiel. Zeilenangaben beziehen sich auf regelbuch.txt. Reihe 1 ist die dem Spieler naechste Reihe,
"vorne" ist Reihe +1; Spalte +1 ist rechts."""

import pytest
from conftest import unit

from fof import briefing, combat, commands, enemy, fire, geometry, rules, state


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protokoll"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)


def hq(board, name, available=0, saved=0, activated=True):
    board["kommandos"][name] = {"verfuegbar": available, "gespart": saved, "aktiviert": activated, "fertig": False}


def total(rows):
    return sum(v for _, v in rows)


def labels(rows):
    return [t for t, _ in rows]


# ---------------------------------------------------------------- 5.1.6 Transportkapazitaet


def test_transport_capacity_demo_team_and_co_hq(board):
    """[RULE 5.1.6A p.33] Zeile 3757: Ein 1-Step Demolition Team traegt 3 RKT-Munition (mehr nicht) plus beliebige
    Assets (Smoke, WP Smoke); ein 1-Step CO HQ traegt zwei Funkgeraete und vier Pyrotechnik-Assets. Das Werkzeug kennt
    keine Demolition Charges als Ladung, geprueft werden Munitionsgrenze und unbegrenzte Assets."""
    s = board
    s["karten"]["22"]["munition"] = {"RKT": 4}
    s["karten"]["22"]["assets_boden"] = ["Smoke", "WP Smoke", "RSP", "GSP", "Red Smoke", "Green Smoke"]
    s["einheiten"]["Demo Team"] = unit("22", vof="S", rng="C", typ="Weapons Team", steps=1)
    s["einheiten"]["CO HQ"] = unit(
        "22",
        vof=None,
        typ="HQ",
        ebene="CO",
        steps=1,
        funk=[{"typ": "SCR300", "netz": "BN TAC"}, {"typ": "SCR536", "netz": "CO TAC"}],
    )
    demo, co = s["einheiten"]["Demo Team"], s["einheiten"]["CO HQ"]
    prot = []
    combat.ammo_pick_up(s, demo, "Demo Team", "RKT:3", prot)
    assert demo["traegt_munition"] == {"typ": "RKT", "punkte": 3}
    with pytest.raises(rules.Violation, match="at most 3 RKT"):
        combat.ammo_pick_up(s, demo, "Demo Team", "RKT:1", prot)
    for a in ("Smoke", "WP Smoke"):
        commands.pick_up(s, demo, "Demo Team", a, prot)
    assert demo["assets"] == ["Smoke", "WP Smoke"]
    for a in ("RSP", "GSP", "Red Smoke", "Green Smoke"):
        commands.pick_up(s, co, "CO HQ", a, prot)
    assert len(co["assets"]) == 4 and len(co["funk"]) == 2


# ---------------------------------------------------------------- 5.2.1 / 5.2.2 Reciprocal LOS


def test_reciprocal_los_hedgerow_and_upper_story(board):
    """[RULE 5.2.1 p.34, 5.2.2 p.35] Zeile 3948, Fig 1 und Fig 2: Die dunklen Raender der Hedgerow blockieren die LOS
    zwischen 1/1 und dem deutschen Squad; sobald die US LMG in das Upper Story (Stufe 2) wechselt, geht die LOS ueber
    die Hedgerow hinweg, und zwar in beide Richtungen (reziprok): der Feind kann einen VOF auf die US-Karte legen."""
    s = board
    s["karten"]["12"].update(terrain="Hedgerow", raender="dunkel")
    s["karten"]["11"]["cover"] = [
        {"id": "C1", "typ": "Light Building", "wert": 2},
        {"id": "U1", "typ": "Upper Story", "wert": 2},
    ]
    s["einheiten"]["1/1"] = unit("11", vof="S")
    s["einheiten"]["LMG"] = unit("11", vof="A", typ="Weapons Team", steps=1)
    s["einheiten"]["4/Gp"] = unit("13", side="Feind", vof="S")
    assert not geometry.los(s, "11", "13")[0] and not geometry.los(s, "13", "11")[0]
    assert fire.fire_candidates(s, "1/1") == [] and fire.fire_candidates(s, "4/Gp") == []
    s["einheiten"]["LMG"]["bereich"] = "U1"
    lmg = s["einheiten"]["LMG"]
    assert geometry.los(s, "11", "13", ha=geometry.height_bonus(s, lmg))[0]
    assert geometry.los(s, "13", "11", hb=geometry.card_height_bonus(s, "11", "US"))[0]
    assert fire.fire_candidates(s, "LMG") == ["13"] and fire.fire_candidates(s, "4/Gp") == ["11"]
    assert fire.fire_candidates(s, "1/1") == []  # the squad on the ground floor still has no LOS of its own
    fire.open_fire(s, [])
    assert s["einheiten"]["4/Gp"]["ziel"] == "11" and fire.vof_against(s, "11", "US")[:2] == ("S", 0)


def test_reciprocal_los_concentrate_fire_only_on_the_upper_story(board, quiet):
    """[RULE 5.2.2 p.35] Zeile 3948, Fig 3: Der feindliche Squad konzentriert Feuer auf die US-Karte; nur die LMG im
    Upper Story ist in echter LOS und darf Ziel sein, der Basic VOF deckt weiter die ganze Karte.
    Werkzeug seit L150 (15.10.2026)."""
    s = board
    s.update(phase="3.4.2")
    s["karten"]["12"].update(terrain="Hedgerow", raender="dunkel")
    s["karten"]["11"]["cover"] = [
        {"id": "C1", "typ": "Light Building", "wert": 2},
        {"id": "U1", "typ": "Upper Story", "wert": 2},
    ]
    s["einheiten"]["2/1"] = unit("11", vof="S")
    s["einheiten"]["LMG"] = unit("11", vof="A", typ="Weapons Team", steps=1, bereich="U1")
    s["einheiten"]["4/Gp"] = unit("13", side="Feind", vof="S", ziel="11")
    assert fire.vof_against(s, "11", "US")[:2] == ("S", 0)
    with pytest.raises(rules.Violation):
        enemy.cmd_enemy_action(s, ["4/Gp", "concentrate", "--success=ja", "--unit=2/1"])
    assert not s["einheiten"]["2/1"].get("cf")
    enemy.cmd_enemy_action(s, ["4/Gp", "concentrate", "--success=ja", "--unit=LMG"])
    assert s["einheiten"]["LMG"]["cf"] == 1
    assert total(combat.ncm_rows(s, "LMG")) == 0 + 2 - 1  # S +0, Upper Story +2, Concentrated Fire -1
    assert total(combat.ncm_rows(s, "2/1")) == 0  # Basic VOF on the whole card, no marker


def test_hill_sees_over_hedgerows_reciprocally(board):
    """[RULE 5.2.2A p.35] Zeile 4065: Ein deutscher Squad auf einem Huegel (Stufe 2) hat LOS ueber die Hedgerows auf das
    US LMG Team dahinter; die LOS ist reziprok, das LMG Team sieht den Squad auf dem Huegel. Ohne Huegel blockieren
    die dunklen Raender."""
    s = board
    s["karten"]["12"].update(terrain="Hedgerow", raender="dunkel")
    s["karten"]["13"].update(terrain="Hill", elevation=2)
    s["einheiten"]["LMG"] = unit("11", vof="A", typ="Weapons Team", steps=1)
    s["einheiten"]["4/Gp"] = unit("13", side="Feind", vof="S")
    assert geometry.los(s, "13", "11")[0] and geometry.los(s, "11", "13")[0]
    assert fire.fire_candidates(s, "4/Gp") == ["11"] and fire.fire_candidates(s, "LMG") == ["13"]
    s["karten"]["13"]["elevation"] = 1
    ok, reason = geometry.los(s, "13", "11")
    assert not ok and "dark edges" in reason
    assert not geometry.los(s, "11", "13")[0]


# ---------------------------------------------------------------- 5.3 Cover


def test_canal_cover_potential_one_basic_cover_three_cards(board, quiet):
    """[RULE 5.3 p.36, 4.2.2e p.23] Zeile 4087: Der Canal hat Cover Potential 1, gefundene Deckung ist Basic +1 Cover,
    der Seek-Cover-Versuch zieht 3 Karten. Ein zweiter Marker ist auf der Karte nicht moeglich."""
    s = board
    s.update(phase="3.3.1c", aktiver_hq="1st PLT HQ")
    s["karten"]["22"].update(terrain="Canal", cc=0, cover_max=1, cover_draw=3)
    hq(s, "1st PLT HQ", available=3)
    s["einheiten"]["1st PLT HQ"] = unit("22", vof=None, typ="HQ", ebene="PLT", platoon="1", steps=1)
    s["einheiten"]["1/1"] = unit("22", vof="S", platoon="1")
    s["einheiten"]["2/1"] = unit("22", vof="S", platoon="1")
    with pytest.raises(rules.Violation, match="draw 3 Action cards"):
        commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.2e"])
    commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.2e", "--success=ja"])
    cover = s["karten"]["22"]["cover"]
    assert len(cover) == 1 and cover[0]["typ"] == "Basic Cover" and cover[0]["wert"] == 1
    assert s["einheiten"]["1/1"]["bereich"] == cover[0]["id"] and "Exposed" in s["einheiten"]["1/1"]["status"]
    with pytest.raises(rules.Violation, match="Cover Potential"):
        commands.cmd_order(s, ["1st PLT HQ", "2/1", "4.2.2e", "--success=ja"])
    assert len(s["karten"]["22"]["cover"]) == 1


def test_five_steps_under_cover_grenade_stacking_penalty(board):
    """[RULE 5.3 p.36] Zeile 4108: Fuenf Steps unter einem +1 Cover Marker erhalten gegen Grenade VOF -2 Stacking
    (zwei Steps ueber dem Limit von drei), netto -1 aus Deckung und Stacking; gegen direkten VOF gibt es keinen
    Stacking-Abzug."""
    s = board
    s["karten"]["22"]["cover"] = [{"id": "C1", "typ": "Basic Cover", "wert": 1}]
    s["einheiten"]["1/1"] = unit("22", vof="S", steps=3, bereich="C1", grenade=[-4])
    s["einheiten"]["2/1"] = unit("22", vof="S", steps=2, bereich="C1", grenade=[-4])
    for n in ("1/1", "2/1"):
        rows = combat.ncm_rows(s, n)
        assert ("Cover C1 Basic Cover", 1) in rows and ("Stacking 5 steps under cover", -2) in rows
        assert total(rows) == -4 + 1 - 2, rows
    for n in ("1/1", "2/1"):
        s["einheiten"][n].pop("grenade")
    s["einheiten"]["Enemy 1"] = unit("23", side="Feind", vof="A", ziel="22")
    rows = combat.ncm_rows(s, "1/1")
    assert not any("Stacking" in t for t in labels(rows)) and total(rows) == -1 + 1


def test_hmg_in_bunker_keeps_firing_off_card_while_squad_shifts_to_point_blank(board):
    """[RULE 5.3.2 p.37, 6.2.1 p.41, 6.3.5 p.44] Zeile 4136: 2/1/HMG im Bunker und 2/1 (ohne Deckung) feuern nach vorn
    auf einen deutschen Squad. Ein deutsches Assault Team dringt in ihre Karte ein: 2/1 wechselt auf Point Blank, das
    HMG Team im Bunker feuert weiter nach vorn. Zieht sich das Assault Team spaeter in das Enclosed Field (seitlich)
    zurueck, folgt das Feuer von 2/1 dem Assault Team dorthin (6.3.4 'in any direction', wie im Beispiel 6.3.5, wo 1/1
    dem Squad ins Village folgt, obwohl der PDF von 1/LMG auf der Karte liegt); das HMG im Bunker feuert weiter
    nach vorn. Lesart Claude 15.10.2026 (L149)."""
    s = board
    s["karten"]["22"]["cover"] = [{"id": "B1", "typ": "Bunker", "wert": 3, "kapazitaet": 3, "richtung": [1, 0]}]
    s["karten"]["23"]["terrain"] = "Enclosed Field"
    s["einheiten"]["2/1/HMG"] = unit("22", vof="H", rng="V", typ="Weapons Team", steps=1, tripod=True, bereich="B1")
    s["einheiten"]["2/1"] = unit("22", vof="S")
    s["einheiten"]["4/Gp"] = unit("32", side="Feind", vof="S", ziel="22")
    fire.open_fire(s, [])
    assert s["einheiten"]["2/1/HMG"]["ziel"] == "32" and s["einheiten"]["2/1"]["ziel"] == "32"
    s["einheiten"]["Assault Team"] = unit("12", side="Feind", vof="A", rng="P", typ="Assault Team", steps=1)
    prot = []
    commands.move_unit(s, "Assault Team", "22", None, exposed=False, prot=prot)
    assert s["einheiten"]["2/1"]["ziel"] == "22"  # Point Blank against the Assault Team
    assert s["einheiten"]["2/1/HMG"]["ziel"] == "32"  # the bunker keeps firing straight ahead
    assert fire.vof_against(s, "22", "Feind")[:2] == ("S", 0)
    assert fire.vof_against(s, "32", "Feind")[:2] == ("H", -3)
    commands.move_unit(s, "Assault Team", "23", None, exposed=False, prot=prot)
    assert s["einheiten"]["2/1/HMG"]["ziel"] == "32"
    assert s["einheiten"]["2/1"]["ziel"] == "23"  # fire follows the last Point Blank target (6.3.4), PDF 22 to 23
    assert fire.vof_against(s, "23", "Feind")[:2] == ("S", 0)
    assert fire.vof_against(s, "32", "Feind")[:2] == ("H", -3)


# ---------------------------------------------------------------- 6.0 Basic Combat Principle


def test_rain_stops_units_open_fire_at_long_range(board):
    """[RULE 6.0 p.39, 9.1 p.69, 6.1.1 p.39] Zeile 4292: 1/3 und das 2/W/3 MG Team suchen bei starkem Regen (Sicht nur
    Close Range) den Feind. Der Regen hoert auf, die Karte wird sofort geprueft, beide eroeffnen das Feuer auf ein
    nordkoreanisches Fire Team in Long Range."""
    s = board
    s.update(wetter=2)
    geometry.update_visibility(s)
    assert s["sicht"] == "eingeschraenkt"
    s["einheiten"]["1/3"] = unit("11", vof="S", platoon="3")
    s["einheiten"]["2/W/3"] = unit("11", vof="A", rng="V", typ="Weapons Team", steps=1, tripod=True, platoon="3")
    s["einheiten"]["NK Fire Team"] = unit("13", side="Feind", vof="S", typ="Fire Team", steps=1)
    fire.open_fire(s, [])
    assert s["einheiten"]["1/3"]["ziel"] is None and s["einheiten"]["2/W/3"]["ziel"] is None
    s["wetter"] = 0
    geometry.update_visibility(s)
    prot = []
    fire.open_fire(s, prot)
    assert s["einheiten"]["1/3"]["ziel"] == "13" and s["einheiten"]["2/W/3"]["ziel"] == "13"
    assert fire.vof_against(s, "13", "Feind")[:2] == ("A", -1)


# ---------------------------------------------------------------- 6.1 Opening Fire / Continuing to Fire


def test_opening_fire_example_1_wp_smoke_on_the_firing_card(board):
    """[RULE 6.1.2 p.40, 5.4 p.38] Zeile 4402, Example 1: 1/Gp (A VOF) auf 23 und ein US Squad (S VOF) im Village 22
    feuern aufeinander. Eine WP-Mission legt Rauch auf 23: 1/Gp verliert die LOS, der PDF wird entfernt, sein
    Automatic VOF bleibt auf der eigenen Karte und trifft US-Einheiten, die sie betreten. Der US Squad hat LOS in den
    Rauch hinein, sein Small Arms VOF auf 23 bleibt.
    Werkzeug seit L148 (15.10.2026)."""
    s = board
    s["karten"]["22"].update(terrain="Village", cc=3)
    s["einheiten"]["1/1"] = unit("22", vof="S", ziel="23")
    s["einheiten"]["1/Gp"] = unit("23", side="Feind", vof="A", ziel="22")
    assert fire.vof_against(s, "22", "US")[:2] == ("A", -1)
    s["karten"]["23"]["extern"].append({"typ": "Smoke", "wert": 1, "quelle": "WP"})
    prot = []
    fire.cease_fire_on_los_loss(s, prot)
    assert s["einheiten"]["1/1"]["ziel"] == "23" and fire.vof_against(s, "23", "Feind")[:2] == ("S", 0)
    assert fire.vof_against(s, "22", "US") is None  # no PDF from 23 any more
    assert fire.is_firing(s["einheiten"]["1/Gp"]) and fire.effective_fire_target(s, "1/Gp") == "23"
    assert fire.vof_against(s, "23", "US")[:2] == ("A", -1)  # the German VOF waits on its own card


def test_opening_fire_example_2_no_fire_past_own_litter_team(board):
    """[RULE 6.1.1 p.40] Zeile 4417, Example 2: 1/1 betritt die linke Karte; ein NKPA HMG ist in LOS, aber der VOF
    wuerde auf dem naechsten besetzten Feld beim eigenen Litter Team liegen bleiben, also eroeffnet 1/1 nicht das Feuer.
    Das HMG trifft dank Grazing Fire beide US-Einheiten."""
    s = board
    s["einheiten"]["Litter Team"] = unit("12", vof=None, typ="Litter Team", steps=1)
    s["einheiten"]["NKPA HMG"] = unit(
        "13", side="Feind", vof="A", rng="V", typ="Weapons Team", steps=1, tripod=True, ziel="12"
    )
    s["einheiten"]["1/1"] = unit("11", vof="S")
    assert geometry.los(s, "11", "13")[0]
    assert "13" not in fire.fire_candidates(s, "1/1")
    prot = []
    fire.open_fire(s, prot, only=["1/1"])
    assert s["einheiten"]["1/1"]["ziel"] is None
    assert fire.grazing_cards(s, "NKPA HMG") == ["12", "11"]
    assert fire.vof_against(s, "12", "US")[:2] == ("A", -1) and fire.vof_against(s, "11", "US")[:2] == ("A", -1)


def test_opening_fire_example_3_vof_moves_to_the_closer_card(board):
    """[RULE 6.1.2 p.40, 7.2.2 p.51] Zeile 4411, Example 3: 1/1 feuert ueber ein Open Field auf ein Litter Team in der
    Farm (S VOF auf der Farm). Ein Exposed LMG Team erscheint im Feld: der VOF wandert von der Farm ins Feld. Mit
    Grazing Fire traefe 1/1 beide; ein Unspotted LMG Team wuerde durchschossen."""
    s = board
    s["karten"]["23"]["terrain"] = "Farm"
    s["einheiten"]["1/1"] = unit("21", vof="S", ziel="23")
    s["einheiten"]["Litter Team"] = unit("23", side="Feind", vof=None, typ="Litter Team", steps=1)
    assert fire.effective_fire_target(s, "1/1") == "23" and fire.vof_against(s, "23", "Feind")[:2] == ("S", 0)
    s["einheiten"]["LMG Team"] = unit(
        "22", side="Feind", vof="A", typ="Weapons Team", steps=1, tripod=True, status=["Exposed"], spotted=True
    )
    assert fire.effective_fire_target(s, "1/1") == "22"
    assert fire.vof_against(s, "22", "Feind")[:2] == ("S", 0) and fire.vof_against(s, "23", "Feind") is None
    s["einheiten"]["1/1"].update(vof_rating="A", reichweite="V", tripod=True)  # with Grazing Fire: both cards
    assert fire.grazing_cards(s, "1/1") == ["22", "23"]
    assert fire.vof_against(s, "23", "Feind")[:2] == ("A", -1)
    s["einheiten"]["1/1"].update(vof_rating="S", reichweite="L", tripod=False)
    s["einheiten"]["LMG Team"]["spotted"] = False  # Unspotted: fired through, the VOF stays on the farm
    assert fire.effective_fire_target(s, "1/1") == "23" and fire.vof_against(s, "22", "Feind") is None


def test_opening_fire_example_4_grazing_fire_stops_at_wp_smoke(board):
    """[RULE 6.1.2 p.41, 7.2.2 p.51, 5.4 p.38] Zeile 4445, Example 4: Ein NVA HMG im Bunker feuert ueber offenes
    Gelaende auf US-Einheiten und legt per Grazing Fire Heavy Weapons VOF auf alle Karten in LOS. Nach einer
    WP-Mission auf die Karte dazwischen reicht sein Feuer nur noch bis zum Rauch."""
    s = board
    s["karten"]["13"]["cover"] = [{"id": "B1", "typ": "Bunker", "wert": 3, "kapazitaet": 3, "richtung": [0, -1]}]
    s["einheiten"]["NVA HMG"] = unit(
        "13", side="Feind", vof="H", rng="V", typ="Weapons Team", steps=1, tripod=True, bereich="B1"
    )
    s["einheiten"]["1/1"] = unit("11", vof="S", ziel="13")
    s["einheiten"]["2/1"] = unit("11", vof="S", ziel="13")
    fire.open_fire(s, [])
    assert s["einheiten"]["NVA HMG"]["ziel"] == "11"
    assert fire.grazing_cards(s, "NVA HMG") == ["12", "11"]
    assert fire.vof_against(s, "11", "US")[:2] == ("H", -3) and fire.vof_against(s, "12", "US")[:2] == ("H", -3)
    s["karten"]["12"]["extern"].append({"typ": "Smoke", "wert": 1, "quelle": "WP"})
    assert fire.grazing_cards(s, "NVA HMG") == ["12"]
    assert fire.effective_fire_target(s, "NVA HMG") == "12"
    assert fire.vof_against(s, "11", "US") is None and fire.vof_against(s, "12", "US")[:2] == ("H", -3)


# ---------------------------------------------------------------- 6.2.1 Placing VOF Markers


def test_vof_example_1_best_vof_from_outside_and_crossfire(board):
    """[RULE 6.2.1a p.41, 6.2.4 p.42] Zeile 4488, Example 1: 1st PLT HQ, 2/1 und 1/W/1 MG Team werden von links mit
    Small Arms (+0) und von rechts von einem HMG mit Automatic Weapons (-1) beschossen; es wirkt nur der Automatic VOF,
    dazu Crossfire -1."""
    s = board
    s["einheiten"]["1st PLT HQ"] = unit("22", vof=None, typ="HQ", ebene="PLT", platoon="1", steps=1)
    s["einheiten"]["2/1"] = unit("22", vof="S", platoon="1")
    s["einheiten"]["1/W/1"] = unit("22", vof="A", rng="V", typ="Weapons Team", steps=1, tripod=True, platoon="1")
    s["einheiten"]["Squad L"] = unit("21", side="Feind", vof="S", ziel="22")
    s["einheiten"]["HMG R"] = unit(
        "23", side="Feind", vof="A", rng="V", typ="Weapons Team", steps=1, tripod=True, ziel="22"
    )
    typ, value, sources = fire.vof_against(s, "22", "US")
    assert (typ, value) == ("A", -1) and set(sources) == {"Squad L", "HMG R"}
    assert fire.crossfire(s, "22", "US") is True
    for n in ("1st PLT HQ", "2/1", "1/W/1"):
        rows = combat.ncm_rows(s, n)
        assert rows[0] == ("VOF Automatic Weapons from HMG R", -1)
        assert ("Crossfire (two PDF directions)", -1) in rows and total(rows) == -2, rows


def test_vof_example_2_artillery_beats_panzerschreck(board):
    """[RULE 6.2.1 p.41, 6.4 p.45] Zeile 4502, Example 2: Artillerie (-5) trifft die Karte mit 1st PLT HQ, 2/1 und
    1/Mtr Team; 2/1 ist zusaetzlich Ziel eines erfolgreichen Panzerschreck-Angriffs (-4). Alle drei werden mit
    Artillery -5 aufgeloest, der Panzerschreck-VOF wird ignoriert."""
    s = board
    s["karten"]["22"]["extern"].append({"typ": "Incoming", "wert": -5, "quelle": "Arty"})
    s["einheiten"]["1st PLT HQ"] = unit("22", vof=None, typ="HQ", ebene="PLT", platoon="1", steps=1)
    s["einheiten"]["2/1"] = unit("22", vof="S", platoon="1", grenade=[-4])
    s["einheiten"]["1/Mtr"] = unit("22", vof="G", rng="C-L", typ="Weapons Team", steps=1, moerser=True, platoon="1")
    assert fire.vof_against(s, "22", "US")[:2] == ("Incoming", -5)
    for n in ("1st PLT HQ", "2/1", "1/Mtr"):
        rows = combat.ncm_rows(s, n)
        assert rows[0] == ("VOF Incoming! (Arty)", -5) and total(rows) == -5, rows


def test_vof_example_3_mortar_heavy_weapons_hits_both_sides(board):
    """[RULE 6.2.1a/b p.41] Zeile 4517, Example 3: 1st PLT HQ, 1/LMG und 2/1 teilen die Karte mit 4/Gp und 5/Gp. Eine
    deutsche 81mm Mortar Section feuert von aussen Heavy Weapons (-3) auf die Karte; das trifft alle Einheiten beider
    Seiten. Der US Automatic VOF (-1) und der deutsche Small Arms VOF (+0) werden nicht gelegt."""
    s = board
    s["einheiten"]["1st PLT HQ"] = unit("22", vof=None, typ="HQ", ebene="PLT", platoon="1", steps=1)
    s["einheiten"]["1/LMG"] = unit("22", vof="A", typ="Weapons Team", steps=1, platoon="1", ziel="22")
    s["einheiten"]["2/1"] = unit("22", vof="S", platoon="1", ziel="22")
    s["einheiten"]["4/Gp"] = unit("22", side="Feind", vof="S", ziel="22")
    s["einheiten"]["5/Gp"] = unit("22", side="Feind", vof="S", ziel="22")
    s["einheiten"]["81mm Mtr"] = unit(
        "32", side="Feind", vof="H", rng="C-L", typ="Weapons Team", steps=3, moerser=True, ziel="22"
    )
    assert fire.vof_against(s, "22", "US")[:2] == ("H", -3) and fire.vof_against(s, "22", "Feind")[:2] == ("H", -3)
    for n in ("1st PLT HQ", "1/LMG", "2/1", "4/Gp", "5/Gp"):
        rows = combat.ncm_rows(s, n)
        assert rows[0] == ("VOF Heavy Weapons from 81mm Mtr", -3) and total(rows) == -3, rows


def test_vof_example_4_point_blank_vof_better_than_outside_vof(board):
    """[RULE 6.2.1b p.41, 6.3.6 p.45] Zeile 4534, Example 4: 1st PLT HQ, 2/AT Bazooka Team und 2/1 teilen die Karte mit
    einer deutschen 88. 1/LMG feuert von aussen Automatic (-1) auf die Karte. Der US Small Arms VOF (+0) wird nicht
    gelegt; die 88 feuert Heavy Weapons (-3), das trifft die US-Einheiten, die 88 selbst nur der Automatic VOF."""
    s = board
    s["einheiten"]["1st PLT HQ"] = unit("22", vof=None, typ="HQ", ebene="PLT", platoon="1", steps=1)
    s["einheiten"]["2/AT"] = unit("22", vof="S", rng="C", typ="Weapons Team", steps=1, platoon="2", ziel="22")
    s["einheiten"]["2/1"] = unit("22", vof="S", platoon="1", ziel="22")
    s["einheiten"]["88mm"] = unit("22", side="Feind", vof="H", rng="V", typ="Weapons Team", steps=1, ziel="22")
    s["einheiten"]["1/LMG"] = unit("32", side="Feind", vof="A", typ="Weapons Team", steps=1, ziel="22")
    typ, value, sources = fire.vof_against(s, "22", "US")
    assert (typ, value) == ("H", -3) and set(sources) == {"88mm", "1/LMG"}
    typ, value, sources = fire.vof_against(s, "22", "Feind")
    assert (typ, value) == ("A", -1) and "1/LMG" in sources  # the US Small Arms VOF (+0) is not the marker placed
    assert "88mm" not in sources  # Point Blank fire hits only the opposing side
    for n in ("1st PLT HQ", "2/AT", "2/1"):
        assert total(combat.ncm_rows(s, n)) == -3
    assert total(combat.ncm_rows(s, "88mm")) == -1


# ---------------------------------------------------------------- 6.3 PDF


def test_out_of_ammo_vof_moves_to_the_adjacent_card_pdf_stays(board):
    """[RULE 6.3.2 p.43, 7.18.2 p.61] Zeile 4717: Das 2/W/3 MG Team (A VOF, L Range) beschiesst einen Feind zwei Karten
    rechts. Ohne Munition sinkt sein VOF auf Small Arms (+0) und die Reichweite auf Close; der PDF bleibt nach rechts,
    der VOF wandert auf die Nachbarkarte.
    Werkzeug seit L147 (15.10.2026)."""
    s = board
    s["einheiten"]["2/W/3"] = unit(
        "11",
        vof="A",
        rng="L",
        typ="Weapons Team",
        steps=1,
        tripod=True,
        ziel="13",
        platoon="3",
        munition={"typ": "MG", "punkte": 1, "start": 6},
    )
    s["einheiten"]["Enemy 1"] = unit("13", side="Feind", vof="S", ziel="11")
    assert fire.vof_against(s, "13", "Feind")[:2] == ("A", -1)
    mg = s["einheiten"]["2/W/3"]
    prot = []
    combat.ammo_use(s, "2/W/3", mg, 1, "fire", prot)
    assert mg["out_of_ammo"] and fire.current_vof_rating(mg, False) == "S"
    assert state.range_limits(s, mg) == (0, 1)
    assert fire.is_firing(mg) and mg["ziel"] == "13"  # the PDF marker stays (right)
    assert fire.effective_fire_target(s, "2/W/3") == "12"
    assert fire.vof_against(s, "13", "Feind") is None and fire.vof_against(s, "12", "Feind")[:2] == ("S", 0)


def test_vof_follows_the_squad_that_leaves_the_card(board):
    """[RULE 6.3.4 p.44, 6.3.5 p.44, 6.1.1 p.39, 6.2.4 p.42] Zeile 4774: 1/1 und 1/LMG feuern im Woods; der deutsche
    Squad auf der Karte von 1/1 (Point Blank) zieht ins Village. 1/1s Small Arms VOF folgt ihm mit PDF Woods zum
    Village; 1/LMG feuert weiter in seine Richtung. Der Squad stellt das Feuer ein und eroeffnet es neu auf den Woods
    (meiste Steps), 1/1 liegt damit im Crossfire.
    Werkzeug seit L149 (15.10.2026)."""
    s = board
    s["karten"]["22"].update(terrain="Woods", cc=2)
    s["karten"]["23"].update(terrain="Village", cc=3)
    s["einheiten"]["1/1"] = unit("22", vof="S", platoon="1", ziel="22")
    s["einheiten"]["1/LMG"] = unit("22", vof="A", typ="Weapons Team", steps=1, platoon="1", ziel="32")
    s["einheiten"]["4/Gp"] = unit("22", side="Feind", vof="S", ziel="22")
    s["einheiten"]["5/Gp"] = unit("32", side="Feind", vof="S", ziel="22")
    assert fire.vof_against(s, "22", "Feind")[:2] == ("S", 0) and fire.vof_against(s, "32", "Feind")[:2] == ("A", -1)
    assert fire.crossfire(s, "22", "US") is False
    prot = []
    commands.move_unit(s, "4/Gp", "23", None, exposed=True, prot=prot)
    assert s["einheiten"]["4/Gp"]["ziel"] == "22"  # cease fire, then open fire on the Woods (most steps)
    assert s["einheiten"]["1/LMG"]["ziel"] == "32"  # not along its PDF: keeps firing in the same direction
    assert s["einheiten"]["1/1"]["ziel"] == "23"  # Small Arms VOF follows, PDF Woods to Village
    assert fire.vof_against(s, "23", "Feind")[:2] == ("S", 0)
    assert fire.crossfire(s, "22", "US") is True
    assert ("Crossfire (two PDF directions)", -1) in combat.ncm_rows(s, "1/1")


# ---------------------------------------------------------------- 6.4 Combat Resolution


def test_combat_example_1_fog_grenade_crossfire(board):
    """[RULE 6.4 p.45, 9.0 p.69, 7.10 p.54] Zeile 4937, Example 1: Nebel (+2) auf einem Open Field. 1/LMG und das Assault
    Team unter +1 Basic Cover, 1/1 Pinned im Freien. Eine 88 (H) feuert von rechts, ein Pinned deutscher Squad von links,
    ein Panzerschreck-Team trifft den Deckungsstapel mit Grenade -4. NCM 1/LMG und Assault Team -4 (Grenade ohne
    Sichtabzug, Cover +1, Crossfire -1); NCM 1/1 -1 (H -3, Nebel +2, Pinned +1, Crossfire -1)."""
    s = board
    s.update(wetter=2)
    geometry.update_visibility(s)
    s["karten"]["22"]["cover"] = [{"id": "C1", "typ": "Basic Cover", "wert": 1}]
    s["einheiten"]["1/1"] = unit("22", vof="S", platoon="1", status=["Pinned"])
    s["einheiten"]["1/LMG"] = unit("22", vof="A", typ="Weapons Team", steps=1, platoon="1", bereich="C1", grenade=[-4])
    s["einheiten"]["Assault Team"] = unit(
        "22", vof="A", rng="P", typ="Assault Team", steps=1, platoon="1", bereich="C1", grenade=[-4]
    )
    s["einheiten"]["88 Flak"] = unit("23", side="Feind", vof="H", rng="V", typ="Weapons Team", steps=1, ziel="22")
    s["einheiten"]["Pzschreck"] = unit("23", side="Feind", vof="S", rng="C", typ="Weapons Team", steps=1, ziel="22")
    s["einheiten"]["Squad L"] = unit("21", side="Feind", vof="A", ziel="22", status=["Pinned"])
    assert fire.vof_against(s, "22", "US")[:2] == ("H", -3) and fire.crossfire(s, "22", "US") is True
    for n in ("1/LMG", "Assault Team"):
        rows = combat.ncm_rows(s, n)
        assert rows[0] == ("Grenade VOF (cumulative)", -4)
        assert not any("Visibility" in t for t in labels(rows))
        assert ("Cover C1 Basic Cover", 1) in rows and ("Crossfire (two PDF directions)", -1) in rows
        assert total(rows) == -4, rows
    rows = combat.ncm_rows(s, "1/1")
    assert rows[0] == ("VOF Heavy Weapons from 88 Flak", -3)
    assert ("Pinned", 1) in rows and ("Crossfire (two PDF directions)", -1) in rows
    assert any(t.startswith("Visibility") and v == 2 for t, v in rows)
    assert total(rows) == -1, rows


def test_combat_example_2_point_blank_orchard_grenades_and_concentrated_fire(board):
    """[RULE 6.4 p.45, 7.10.4 p.55, 7.11 p.56] Zeile 4969, Example 2: Point Blank im Orchard (+1). 2/1 und 3/1 unter +1
    Basic Cover, 2/LMG Pinned im Freien, gegen einen A- und einen S-rated deutschen Squad. Der S-Squad verfehlt seinen
    Grenade Attack (Grenade Miss), 2/1 verfehlt zurueck, 3/1 trifft (-4). 2/1 konzentriert Feuer auf den A-Squad, 3/1
    auf den S-Squad. NCM: 2/1 und 3/1 +0, 2/LMG +0, A-Squad -1, S-Squad -5."""
    s = board
    s["karten"]["22"].update(terrain="Orchard", cc=1, grenade_miss=True)
    s["karten"]["22"]["cover"] = [{"id": "C1", "typ": "Basic Cover", "wert": 1}]
    s["einheiten"]["2/1"] = unit("22", vof="S", platoon="1", bereich="C1", ziel="22")
    s["einheiten"]["3/1"] = unit("22", vof="S", platoon="1", bereich="C1", ziel="22")
    s["einheiten"]["2/LMG"] = unit(
        "22", vof="A", typ="Weapons Team", steps=1, platoon="1", ziel="22", status=["Pinned"]
    )
    s["einheiten"]["Squad A"] = unit("22", side="Feind", vof="A", ziel="22", cf=1)
    s["einheiten"]["Squad S"] = unit("22", side="Feind", vof="S", ziel="22", cf=1, grenade=[-4])
    assert fire.vof_against(s, "22", "US")[:2] == ("A", -1)
    assert fire.vof_against(s, "22", "Feind")[:2] == ("S", 0)
    for n in ("2/1", "3/1"):
        rows = combat.ncm_rows(s, n)
        assert rows[0] == ("VOF Automatic Weapons from Squad A", -1) and ("Grenade Miss", -1) in rows
        assert total(rows) == 0, rows
    rows = combat.ncm_rows(s, "2/LMG")
    assert ("Pinned", 1) in rows and total(rows) == 0, rows
    rows = combat.ncm_rows(s, "Squad A")
    assert rows[0][1] == 0 and rows[0][0].startswith("VOF Small Arms")
    assert ("Concentrated Fire", -1) in rows and ("Grenade Miss", -1) in rows and total(rows) == -1, rows
    rows = combat.ncm_rows(s, "Squad S")
    assert rows[0] == ("Grenade VOF (cumulative)", -4)
    assert ("Concentrated Fire", -1) in rows and ("Grenade Miss", -1) in rows and total(rows) == -5, rows


def test_hit_effects_cf_on_japanese_squad_and_lc_on_bazooka_team(board, quiet):
    """[RULE 6.4.3 p.47] Zeile 5214: Ein 3-Step japanischer Squad erhaelt einen CF-Treffer: Step 1 Casualty, Step 2 Fire
    Team, der letzte Step wird ebenfalls Fire Team; beide Fire Teams sind Pinned. Ein 1-Step Bazooka Team erhaelt
    LC: der einzige Step wird Litter Team (Pinned), das C wird nicht mehr angewendet."""
    s = board
    s.update(phase="3.7.4")
    s["einheiten"]["Jap Squad"] = unit("22", side="Feind", vof="S", steps=3, letzter_step="Fire Team")
    s["einheiten"]["1/1"] = unit("12", vof="S", ziel="22")
    s["einheiten"]["Bazooka"] = unit("12", vof="S", rng="C", typ="Weapons Team", steps=1)
    s["einheiten"]["Enemy 2"] = unit("13", side="Feind", vof="S", ziel="12")
    combat.cmd_hit(s, ["Jap Squad", "HIT", "CF"])
    assert "Jap Squad" not in s["einheiten"] and s["karten"]["22"]["casualties_feind"] == 1
    teams = [n for n, e in s["einheiten"].items() if e["seite"] == "Feind" and e["karte"] == "22"]
    assert len(teams) == 2
    for n in teams:
        e = s["einheiten"][n]
        assert e["typ"] == "Fire Team" and e["steps"] == 1 and "Pinned" in e["status"]
    combat.cmd_hit(s, ["Bazooka", "HIT", "LC"])
    assert "Bazooka" not in s["einheiten"] and not s["karten"]["12"].get("casualties")
    lats = [e for e in s["einheiten"].values() if e["seite"] == "US" and e["karte"] == "12" and state.is_lat(e)]
    assert len(lats) == 1 and lats[0]["typ"] == "Litter Team" and "Pinned" in lats[0]["status"]


# ---------------------------------------------------------------- 6.5.2 Reconstitution


def test_reconstitute_a_rated_and_s_rated_german_fire_teams():
    """[RULE 6.5.2 p.49] Zeile 5295: Ein A-rated und ein S-rated deutsches Fire Team rekonstituieren zu einem 2-Step
    A-rated Squad (oder S-rated, wenn alle A-Squads auf der Karte sind); zwei S-rated Fire Teams nur zu einem S-Squad."""
    pytest.skip(
        "nicht nachbaubar: das Werkzeug kennt keine Rekonstitution feindlicher Squads aus Fire Teams "
        "(4.2.3i gilt nur fuer US-Einheiten und vergibt immer VOF S ohne Blick auf die Teams)"
    )
