"""Durchgerechnete Beispiele des Regelbuchs (Series Rules 3rd Ed.), Teil C: 7.2.2 bis 7.2.4, 8.3/8.4, 12.4, 12.6.
Jeder Test baut die Lage des Beispiels auf dem synthetischen Brett nach und prueft das Ergebnis des Werkzeugs
gegen das Beispiel. Zeilenangaben beziehen sich auf regelbuch.txt. Reihe 1 ist die dem Spieler naechste Reihe,
"vorne" ist Reihe +1; Spalte +1 ist rechts."""

import copy

import pytest
from conftest import card, unit

from fof import briefing, campaign, combat, commands, comms, contact, fire, rules, state


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protokoll"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)


def tripod_mg(kid, **extra):
    return unit(kid, vof="A", rng="V", typ="Weapons Team", steps=1, tripod=True, **extra)


# ---------------------------------------------------------------- 7.2.3 Overhead Fire


def test_overhead_fire_example_1_mg_on_level_2_fires_over_level_1_at_level_3(board):
    """[RULE 7.2.3 p.52, 7.2.1 p.51] Zeile 5517, Overhead Fire Example 1: Ein Tripod-MG auf Hoehe 2, eine eigene
    Einheit benachbart auf Hoehe 1, ein Feind auf Long Range auf Hoehe 3. Das MG eroeffnet das Feuer auf den Feind,
    auf der eigenen Karte dazwischen liegt kein VOF-Marker.
    Werkzeug seit L147 (15.10.2026)."""
    s = board
    s["karten"]["11"]["elevation"] = 2
    s["karten"]["12"]["elevation"] = 1
    s["karten"]["13"]["elevation"] = 3
    s["einheiten"]["MG"] = tripod_mg("11")
    s["einheiten"]["1/1"] = unit("12")
    s["einheiten"]["Feind 1"] = unit("13", side="Feind")
    assert fire.overhead_possible(s, "11", "12", "13") is True
    fire.open_fire(s, [])
    assert s["einheiten"]["MG"]["ziel"] == "13"
    assert fire.effective_fire_target(s, "MG") == "13"
    assert fire.vof_against(s, "13", "Feind")[:2] == ("A", -1)
    assert (
        "MG" not in (fire.vof_against(s, "12", "US") or (None, None, []))[2]
    )  # kein VOF des MG auf der ueberschossenen Karte (der Feind selbst feuert auf 12)


def test_overhead_fire_example_2_mg_on_level_1_fires_over_level_1_at_hill_level_2(board):
    """[RULE 7.2.3 p.52, 7.2.1 p.51] Zeile 5533, Overhead Fire Example 2: Tripod-MG auf Hoehe 1, eigene Einheit
    benachbart ebenfalls auf Hoehe 1, Feind auf Long Range auf einem Huegel Hoehe 2. Das MG kann auf den Feind feuern,
    auf der eigenen Karte liegt kein VOF.
    Werkzeug seit L147 (15.10.2026)."""
    s = board
    s["karten"]["13"]["elevation"] = 2
    s["einheiten"]["MG"] = tripod_mg("11")
    s["einheiten"]["1/1"] = unit("12")
    s["einheiten"]["Feind 1"] = unit("13", side="Feind")
    assert fire.overhead_possible(s, "11", "12", "13") is True
    fire.open_fire(s, [])
    assert s["einheiten"]["MG"]["ziel"] == "13"
    assert fire.effective_fire_target(s, "MG") == "13"
    assert fire.vof_against(s, "13", "Feind")[:2] == ("A", -1)
    assert "MG" not in (fire.vof_against(s, "12", "US") or (None, None, []))[2]


# ---------------------------------------------------------------- 7.2.2 / 7.2.4 Grazing Fire und FPL (Diagramm 7.2.5)


def test_grazing_fire_lays_vof_along_all_cards_same_level_or_one_slope(board):
    """[RULE 7.2.2 p.51, 7.2.4 p.53, Diagramm 7.2.5] Zeile 5627: Grazing Fire (und FPL) legen VOF auf alle Karten in
    Reichweite auf gleicher Hoehe in gerader Linie; bergauf oder bergab, aber nicht beides. Bei einer Wahl (bergab oder
    geradeaus ueber ein Tal) zielt das MG auf den naechsten Feind entlang des PDF. FPL ist im Werkzeug nicht gebaut,
    geprueft wird nur Grazing Fire mit einem Tripod-MG."""
    s = board
    s["einheiten"]["MG"] = tripod_mg("11", ziel="12")
    s["einheiten"]["Feind 1"] = unit("12", side="Feind")
    s["einheiten"]["Feind 2"] = unit("13", side="Feind")
    # a) gerade Linie, alles gleiche Hoehe: VOF auf 12 und 13
    assert fire.grazing_cards(s, "MG") == ["12", "13"]
    assert fire.vof_against(s, "13", "Feind")[:2] == ("A", -1)
    # b) alles bergauf 1-2-3: VOF auf 12 und 13
    s["karten"]["12"]["elevation"], s["karten"]["13"]["elevation"] = 2, 3
    assert fire.grazing_cards(s, "MG") == ["12", "13"]
    # c) alles bergab 3-2-1: VOF auf 12 und 13
    s["karten"]["11"]["elevation"], s["karten"]["12"]["elevation"], s["karten"]["13"]["elevation"] = 3, 2, 1
    assert fire.grazing_cards(s, "MG") == ["12", "13"]
    # d) eben, dann bergauf 1-1-2: VOF nur auf 12, nicht beides
    s["karten"]["11"]["elevation"], s["karten"]["12"]["elevation"], s["karten"]["13"]["elevation"] = 1, 1, 2
    assert fire.grazing_cards(s, "MG") == ["12"]
    assert fire.vof_against(s, "13", "Feind") is None
    # e) Tal 2-1-2: bergab und wieder bergauf geht nicht, das MG zielt auf den naechsten Feind (12), 13 bleibt frei
    s["karten"]["11"]["elevation"], s["karten"]["12"]["elevation"], s["karten"]["13"]["elevation"] = 2, 1, 2
    s["einheiten"]["MG"]["ziel"] = None
    fire.open_fire(s, [])
    assert s["einheiten"]["MG"]["ziel"] == "12"
    assert fire.effective_fire_target(s, "MG") == "12"
    assert fire.vof_against(s, "12", "Feind")[:2] == ("A", -1)
    assert fire.vof_against(s, "13", "Feind") is None


# ---------------------------------------------------------------- 8.3 / 8.4 Paketplatzierung


def _package_example_1_board(board):
    """Ausloeser auf 11 (Hoehe 1), feindlicher CCF Rifle Squad auf 22 (Hoehe 1) im Feuerkampf mit dem Ausloeser,
    Rocky Hill 33 (Hoehe 3) rechts vorne auf Long Range, Hilfskarte 44 dahinter (LOS vom Huegel verdeckt)."""
    s = board
    s["karten"]["44"] = card(4, 4)
    s["karten"]["33"].update(terrain="Rocky Hill", elevation=3)
    s["karten"]["11"]["pc"] = "A"
    # Ausloeser: im Beispiel 1/75mm RCL (H, Overhead-faehig); hier als Infanterie-Weapons-Team mit VOF H nachgebaut
    s["einheiten"]["RCL"] = unit("11", vof="H", rng="V", typ="Weapons Team", steps=1, ziel="22")
    s["einheiten"]["CCF Rifle Squad"] = unit("22", side="Feind", ziel="11")
    return s


def _package(name, **unit_fields):
    return {"name": name, "spotted": False, "einheiten": [dict(unit_fields, einheit=name, platz="max", steps=1)]}


def test_package_example_1_overhead_capable_hmg_placed_behind_its_own_blocking_squad(board, quiet):
    """[RULE 8.4.3 p.63/64, 7.2.1 p.51, 7.2.3 p.52, 8.2.4 p.62] Zeile 6813, Example 1: 1/75mm RCL loest einen
    A-Kontakt aus. Paket: HMG, Unspotted, rechts auf Max LOS (Rocky Hill, Hoehe 3). Normalerweise ginge rechts nichts,
    weil der (feindliche) CCF Rifle Squad die Linie blockiert; das HMG kann aber Overhead Fire, wird auf dem Huegel
    platziert und feuert ueber den Squad auf das RCL. PC-Marker weg, Unspotted-Marker beim HMG. Das RCL (ebenfalls
    Overhead-faehig) koennte spaeter per Shift Fire auf das gespottete HMG feuern. Nachbau: RCL als Infanterie-Team
    mit VOF H, Richtung "Rechts" = Right Front (Diagonale).
    Werkzeug seit L147/L151 (15.10.2026)."""
    s = _package_example_1_board(board)
    control = copy.deepcopy(s)
    assert fire.overhead_possible(s, "33", "22", "11") is True
    pk = _package("HMG", typ="Weapons Team", reichweite="V", vof_rating="A", tripod=True)
    contact.pc_contact_v4(s, "11", "A1", pk, {"--richtung": "Rechts"})
    hmg = s["einheiten"]["HMG 1"]
    assert hmg["karte"] == "33" and hmg["spotted"] is False
    assert hmg["ziel"] == "11" and fire.effective_fire_target(s, "HMG 1") == "11"
    assert fire.vof_against(s, "22", "Feind") == ("H", -3, ["RCL"])  # nur das RCL-Feuer, kein VOF vom HMG
    assert "HMG 1" in fire.vof_against(s, "11", "US")[2]
    assert s["karten"]["11"]["pc"] is None
    assert s["einheiten"]["RCL"]["ziel"] == "22"  # HMG Unspotted: kein Gegenfeuer, das RCL bleibt am Squad
    # spaeter: HMG gespottet, Shift Fire des RCL (H, Overhead ueber die gleich hohe Karte 22 auf Hoehe 3)
    hmg["spotted"] = True
    assert fire.overhead_possible(s, "11", "22", "33") is True
    s["einheiten"]["RCL"]["ziel"] = "33"
    assert fire.effective_fire_target(s, "RCL") == "33"
    assert fire.vof_against(s, "33", "Feind")[:2] == ("H", -3)
    # Gegenprobe "Ordinarily": ein LMG ohne Overhead Fire kann rechts nicht platziert werden
    pk2 = _package("LMG", typ="Weapons Team", reichweite="L", vof_rating="A")
    with pytest.raises(rules.Violation):
        contact.pc_contact_v4(control, "11", "A1", pk2, {"--richtung": "Rechts"})


def test_package_example_2_spotter_at_very_long_range_on_the_hill_with_us_units(board, quiet):
    """[RULE 8.4.3 p.63/64, 8.4.1 p.63] Zeile 6847, Example 2: 1/LMG betritt einen Woods und loest einen B-Kontakt
    aus: Incoming Artillery mit Spotter in Foxholes, links auf Max LOS. Der Huegel ganz links sieht den Woods auf
    Very Long Range (3 Karten); der Spotter sitzt dort Unspotted im Foxhole und ruft Artillerie auf den Woods,
    waehrend die US-Einheiten "in the same area" weiter den Huegel hinab in den Marsh auf ein deutsches Litter Team
    feuern. Lesart: dieselbe Karte wie der Spotter; ein Spotter setzt keinen PDF, das Verbot eigener Einheiten auf der
    Platzierungskarte gilt nur fuer Einheiten mit PDF. Richtung "Links" = Left Front (Diagonale), Huegel als Karte 40.
    Werkzeug seit L151 (15.10.2026)."""
    s = board
    s["karten"]["13"]["terrain"] = "Woods"
    s["karten"]["13"]["pc"] = "B"
    s["karten"]["40"] = card(4, 0, elevation=3, terrain="Hill")
    s["karten"]["41"] = card(4, 1, terrain="Marsh")
    s["einheiten"]["1/LMG"] = unit("13", vof="A", typ="Weapons Team", steps=1)
    s["einheiten"]["1/2"] = unit("40", ziel="41")
    s["einheiten"]["2/2"] = unit("40", ziel="41")
    s["einheiten"]["German Litter Team"] = unit("41", side="Feind", vof=None, typ="Litter Team", steps=1)
    pk = {
        "name": "Incoming Artillery with Spotter",
        "spotted": False,
        "marker": [{"typ": "Incoming", "wert": -3}],
        "einheiten": [
            {
                "einheit": "Spotter",
                "typ": "Spotter",
                "spotter": True,
                "platz": "max_los",
                "cover": "Foxhole",
                "cover_wert": 1,
                "steps": 1,
            }
        ],
    }
    contact.pc_contact_v4(s, "13", "B1", pk, {"--richtung": "Links"})
    sp = s["einheiten"]["Spotter 1"]
    assert sp["karte"] == "40" and sp["spotted"] is False
    foxhole = [c for c in s["karten"]["40"]["cover"] if c["id"] == sp["bereich"]]
    assert foxhole and foxhole[0]["typ"] == "Foxhole"
    assert any(x["typ"] == "Incoming" and x["wert"] == -3 for x in s["karten"]["13"]["extern"])
    assert s["karten"]["13"]["pc"] is None
    for n in ("1/2", "2/2"):  # die US-Einheiten feuern weiter in den Marsh
        assert s["einheiten"][n]["ziel"] == "41"


# ---------------------------------------------------------------- 12.4 Replacements (Normandy)


def test_normandy_replacements_six_green_plus_two_veteran_for_ten_casualties(board, quiet):
    """[RULE 12.4 p.81/82] Zeile 8566: Normandy, sechs Replacement-Steps je Mission; zehn Casualty-Steps in der Mission
    ergeben sechs Green und zwei Veteran Replacements (1 je 4 Casualties, abgerundet), die Kompanie startet zwei Steps
    unter Soll."""
    s = board
    s.update(
        kampagne={"versuch": 1, "versuche_max": 2, "xp_tabelle": {}, "ersatz_green": 6, "veteran_je_casualties": 4},
        ziel_regeln={"sichern": [], "reihen_klaeren": []},
        us_casualties_gesamt=10,
        co_hq="CO HQ",
    )
    s["einheiten"]["CO HQ"] = unit("11", vof=None, typ="HQ", ebene="CO", steps=1)
    prot = []
    campaign.mission_end_v4(s, prot)
    text = "\n".join(prot)
    assert s["missionsende"] is True
    assert "replacements 6 Green plus 2 Veteran" in text
    assert "10 casualty steps" in text
    assert 10 - (6 + 2) == 2  # zwei Steps unter Soll (Rechnung des Beispiels, das Werkzeug nennt sie nicht)


# ---------------------------------------------------------------- 12.6 Multi-Step Unit Experience Levels

# Zeilen der Tabelle 12.6, soweit die Beispiele sie belegen (Steps als Liste, Ergebnis).
EXPERIENCE_TABLE_12_6 = [
    (["Line", "Line", "Green", "Green"], "Green"),
    (["Line", "Line", "Line", "Green"], "Line"),
    (["Veteran", "Veteran", "Green"], "Line"),
    (["Veteran", "Veteran", "Line"], "Veteran"),
    (["Line", "Line", "Green"], "Line"),
]


def _unit_experience_function():
    """Sucht im Werkzeug eine Funktion, die aus Step-Stufen die Einheitenstufe nach 12.6 ableitet."""
    names = (
        "unit_experience",
        "multi_step_experience",
        "experience_from_steps",
        "combined_experience",
        "erfahrung_einheit",
        "stufe_aus_steps",
    )
    for mod in (campaign, comms, rules, combat, commands):
        for name in names:
            f = getattr(mod, name, None)
            if callable(f):
                return f
    return None


def test_multi_step_experience_line_squad_with_two_green_lats(board, quiet):
    """[RULE 12.6 p.82, 12.2 p.81, 12.3 p.81] Zeile 8665: Line-Squad 2/3 (4 Steps) verlor zwei Steps; zwei LATs (Green)
    fuellen ihn auf. Ohne Beforderung ist die Einheit Green (L+L+G+G); ein Experience Point hebt einen Green-Step auf
    Line, die ganze Einheit ist dann Line (L+L+L+G). Dazu die weiteren Zeilen des Beispiels (3-Step: V+V+G = Line,
    V+V+L = Veteran, L+L+G = Line).
    Werkzeug seit L152 (15.10.2026): campaign.experience_from_steps, in cmd_reconstitute angewandt."""
    s = board
    s.update(
        reattempt_setup=True,
        kampagne={"versuch": 2, "versuche_max": 2},
        aufbau_einheiten={"2/3": dict(unit("11", platoon="3"), steps=4)},
        xp=[{"zug": 1, "versuch": 1, "punkte": 1, "grund": "test"}],
    )
    s["einheiten"]["2/3"] = unit("11", platoon="3", steps=2)
    s["einheiten"]["Fire Team 1"] = unit("11", vof="S", rng="C", typ="Fire Team", steps=1, erfahrung="Green")
    s["einheiten"]["Fire Team 2"] = unit("11", vof="S", rng="C", typ="Fire Team", steps=1, erfahrung="Green")
    campaign.cmd_reconstitute(s, ["2/3", "--from=Fire Team 1,Fire Team 2"])
    squad = s["einheiten"]["2/3"]
    assert squad["steps"] == 4
    f = _unit_experience_function()
    if f is None:
        pytest.fail(
            "FEHLT: keine Funktion fuer die Tabelle 12.6 (Einheitenstufe aus Step-Stufen); "
            f"cmd_reconstitute laesst 2/3 auf {squad['erfahrung']} statt Green (L+L+G+G)"
        )
    for steps, expected in EXPERIENCE_TABLE_12_6:
        assert f(steps) == expected, f"{'+'.join(x[0] for x in steps)} muss {expected} ergeben"
    assert squad["erfahrung"] == "Green"
    campaign.cmd_xp_promote(s, ["2/3", "--from=Green", "--steps=1"])
    assert squad["erfahrung"] == "Line"
