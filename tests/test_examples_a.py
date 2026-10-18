"""Durchgerechnete Beispiele des Regelbuchs (Series Rules 3rd Ed.), Teil A: 4.1, 4.3, 7.10, 7.16, 7.18.
Jeder Test baut die Lage des Beispiels auf dem synthetischen Brett nach und prueft das Ergebnis des Werkzeugs
gegen das Beispiel. Zeilenangaben beziehen sich auf regelbuch.txt."""

import pytest
from conftest import card, unit

from fof import briefing, combat, commands, comms, fire, rules, state

RADIO = {"typ": "SCR536", "netz": "CO TAC"}
PHONE = {"typ": "EE8", "netz": "CO TAC"}


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protokoll"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)


def hq(board, name, available=0, saved=0, activated=True):
    board["kommandos"][name] = {"verfuegbar": available, "gespart": saved, "aktiviert": activated, "fertig": False}


def total(rows):
    return sum(v for _, v in rows)


# ---------------------------------------------------------------- 4.1.1 / 4.1.2 Command draw


def _co_hq_impulse(board, experience):
    s = board
    s.update(phase="3.3.1b", co_hq="CO HQ")
    s["einheiten"]["CO HQ"] = unit("22", vof=None, typ="HQ", ebene="CO", steps=1, erfahrung=experience)
    s["einheiten"]["1st PLT HQ"] = unit("22", vof=None, typ="HQ", ebene="PLT", platoon="1", steps=1)
    s["einheiten"]["2nd PLT HQ"] = unit("22", vof=None, typ="HQ", ebene="PLT", platoon="2", steps=1)
    hq(s, "CO HQ", activated=True)  # vom BN HQ im vorigen Impuls aktiviert
    hq(s, "1st PLT HQ", activated=False)
    hq(s, "2nd PLT HQ", activated=False)
    commands.cmd_hq(s, ["CO HQ"])
    commands.cmd_card(s, ["1", "4"])  # Karte zeigt 4/3, Helmzahl 4
    return s


def test_co_hq_impulse_draws_four_commands_and_saves_two(board, quiet):
    """[RULE 4.1.1 p.19, 4.1.2 p.20, 4.1.3 p.20] Zeile 1941 und 1976: Aktivierter CO HQ (Line) zieht 4/3 und erhaelt 4
    Commands, als Green nur 3; zwei Commands aktivieren 1st und 2nd PLT HQ, die restlichen zwei werden gespart."""
    s = _co_hq_impulse(board, "Line")
    assert s["kommandos"]["CO HQ"]["verfuegbar"] == 4
    commands.cmd_activate(s, ["1st PLT HQ"])
    commands.cmd_activate(s, ["2nd PLT HQ"])
    assert s["kommandos"]["1st PLT HQ"]["aktiviert"] and s["kommandos"]["2nd PLT HQ"]["aktiviert"]
    assert s["kommandos"]["CO HQ"]["verfuegbar"] == 2
    commands.cmd_done(s, [])
    assert s["kommandos"]["CO HQ"]["gespart"] == 2 and s["kommandos"]["CO HQ"]["verfuegbar"] == 0


def test_co_hq_impulse_green_hq_draws_one_less(board, quiet):
    """[RULE 4.1.2A p.20] Zeile 1944: derselbe Zug mit einem Green CO HQ ergibt 4 - 1 = 3 Commands."""
    s = _co_hq_impulse(board, "Green")
    assert s["kommandos"]["CO HQ"]["verfuegbar"] == 3


def test_sniper_example_2nd_plt_hq_commands_and_orders(board, quiet):
    """[RULE 4.1.2 p.20, 4.2.2a/b/e p.23, 6.2.4 p.42, 7.15 p.57] Zeile 1998: Veteran 2nd PLT HQ unter Sniper-VOF zieht
    5/4 und erhaelt 5 + 1 - 3 = 3 Commands, mit einem gesparten Command 4. Verwendung: 1/2 in die Gully (Exposed, PDF,
    Crossfire auf dem Sniper), LMG Seek Cover mit 3 Karten (+1 Cover, Exposed), Platoon Move von HQ, 2/2 und 3/2 in den
    Woods (alle Exposed); LMG und Fire Team bleiben in der Hedgerow und feuern weiter."""
    s = board
    s.update(phase="3.3.1c", co_hq="CO HQ")
    s["karten"]["22"].update(terrain="Hedgerow", cover_draw=3)
    s["karten"]["21"]["terrain"] = "Gully"
    s["karten"]["23"]["terrain"] = "Woods"
    s["karten"]["32"]["terrain"] = "Orchard"
    s["einheiten"]["CO HQ"] = unit("11", vof=None, typ="HQ", ebene="CO", steps=1)
    s["einheiten"]["2nd PLT HQ"] = unit(
        "22", vof=None, typ="HQ", ebene="PLT", platoon="2", steps=1, erfahrung="Veteran"
    )
    for n in ("1/2", "2/2", "3/2"):
        s["einheiten"][n] = unit("22", vof="S", platoon="2", ziel="32")
    s["einheiten"]["LMG"] = unit("22", vof="A", typ="Weapons Team", platoon="2", steps=1, ziel="32")
    s["einheiten"]["Fire Team 1"] = unit(
        "22", vof="S", rng="C", typ="Fire Team", platoon="2", steps=1, erfahrung="Green", ziel="32"
    )
    s["einheiten"]["Sniper"] = unit("32", side="Feind", vof="S!", rng="V", steps=1, ziel="22", typname="Sniper")
    hq(s, "CO HQ", activated=True)
    hq(s, "2nd PLT HQ", saved=1, activated=True)
    s["kommandos"]["CO HQ"]["fertig"] = True
    assert fire.crossfire(s, "32", "Feind") is False

    commands.cmd_hq(s, ["2nd PLT HQ"])
    commands.cmd_card(s, ["7", "5"])  # Karte zeigt 5/4
    k = s["kommandos"]["2nd PLT HQ"]
    assert k["verfuegbar"] == 3 and k["gespart"] == 1
    assert "Veteran +1" in s["protokoll"][-1]["text"] and "-3" in s["protokoll"][-1]["text"]

    # 1: ein Command, 1/2 in die Gully (Move to Adjacent Card)
    commands.cmd_order(s, ["2nd PLT HQ", "1/2", "4.2.2a", "--target=21"])
    half = s["einheiten"]["1/2"]
    assert half["karte"] == "21" and "Exposed" in half["status"] and half["ziel"] == "32"  # PDF Gully zum Sniper
    assert fire.crossfire(s, "32", "Feind") is True  # Feuer aus zwei Karten: Crossfire-Marker auf dem Sniper
    assert k["verfuegbar"] == 2

    # 2: ein Command, LMG sucht Deckung mit drei Karten
    with pytest.raises(rules.Violation, match="draw 3 Action cards"):
        commands.cmd_order(s, ["2nd PLT HQ", "LMG", "4.2.2e"])
    commands.cmd_order(s, ["2nd PLT HQ", "LMG", "4.2.2e", "--success=ja"])
    lmg = s["einheiten"]["LMG"]
    cover = [c for c in s["karten"]["22"]["cover"] if c["id"] == lmg["bereich"]]
    assert cover and cover[0]["wert"] == 1 and "Exposed" in lmg["status"]
    assert k["verfuegbar"] == 1

    # 3: zwei Commands, Platoon Move von HQ, 2/2 und 3/2 in den Woods
    commands.cmd_order(s, ["2nd PLT HQ", "2nd PLT HQ", "4.2.2b", "--target=23"])
    for n in ("2nd PLT HQ", "2/2", "3/2"):
        assert s["einheiten"][n]["karte"] == "23" and "Exposed" in s["einheiten"][n]["status"]
    assert s["einheiten"]["2/2"]["ziel"] == "32"  # PDF Woods zum Sniper
    for n in ("LMG", "Fire Team 1"):  # bleiben in der Hedgerow und halten den PDF zum Orchard
        assert s["einheiten"][n]["karte"] == "22" and s["einheiten"][n]["ziel"] == "32"
    assert k["verfuegbar"] == 0 and k["gespart"] == 0


# ---------------------------------------------------------------- 4.3 Kommunikation


def _phone_board(board):
    s = board
    s.update(co_hq="CO HQ", funk_aktiv=True, co_tac_mittel="telefon")
    return s


def test_co_tac_net_field_phones_network_a(board):
    """[RULE 4.3.3 p.27, 4.3.4 p.28, 2.5 p.12] Zeile 3265, Phone Network A: vier Einheiten sind ueber Telefone, gelegte
    Leitungen und die integrierten Leitungen der Staging Area mit dem CO HQ verbunden; jedes Telefon zaehlt selbst als
    Leitung. Ohne die Staging Area reisst die Kette fuer die Einheiten, die nur ueber sie angebunden sind."""
    s = _phone_board(board)
    s["karten"]["01"] = card(0, 1, staging=True)
    s["karten"]["03"] = card(0, 3, staging=True)
    s["karten"]["21"]["leitungen"] = [{"cut": False}]
    s["einheiten"]["CO HQ"] = unit("11", vof=None, typ="HQ", ebene="CO", steps=1, funk=[dict(PHONE)])
    s["einheiten"]["1st PLT HQ"] = unit("13", vof=None, typ="HQ", ebene="PLT", platoon="1", steps=1, funk=[dict(PHONE)])
    s["einheiten"]["2nd PLT HQ"] = unit("31", vof=None, typ="HQ", ebene="PLT", platoon="2", steps=1, funk=[dict(PHONE)])
    s["einheiten"]["3rd PLT HQ"] = unit("33", vof=None, typ="HQ", ebene="PLT", platoon="3", steps=1, funk=[dict(PHONE)])
    s["einheiten"]["Wpns PLT HQ"] = unit(
        "32", vof=None, typ="HQ", ebene="PLT", platoon="4", steps=1, funk=[dict(PHONE)]
    )
    s["einheiten"]["1/1"] = unit("22", vof="S", platoon="1")  # ohne Telefon
    for n in ("1st PLT HQ", "2nd PLT HQ", "3rd PLT HQ", "Wpns PLT HQ"):
        assert comms.communication(s, "CO HQ", n) is True, n
    with pytest.raises(rules.Violation, match="no EE8"):
        comms.communication(s, "CO HQ", "1/1")
    for k in ("01", "03"):  # ohne Staging Area haengt 13 in der Luft; 31, 32, 33 haengen an der Leitung 21
        s["karten"][k]["staging"] = False
    with pytest.raises(rules.Violation, match="no unbroken line chain"):
        comms.communication(s, "CO HQ", "1st PLT HQ")
    for n in ("2nd PLT HQ", "3rd PLT HQ", "Wpns PLT HQ"):
        assert comms.communication(s, "CO HQ", n) is True, n
    for k in ("01", "03"):
        s["karten"][k]["staging"] = True
    s["karten"]["21"]["leitungen"][0]["cut"] = True  # gekappte Leitung: die Kette ueber 21 ist unterbrochen
    assert comms.communication(s, "CO HQ", "1st PLT HQ") is True
    for n in ("2nd PLT HQ", "3rd PLT HQ", "Wpns PLT HQ"):
        with pytest.raises(rules.Violation, match="line cut or missing"):
            comms.communication(s, "CO HQ", n)


def test_co_tac_net_field_phones_network_b_hub_without_staging(board):
    """[RULE 4.3.3 p.27, 4.3.4 p.28] Zeile 3276, Phone Network B: vier Einheiten haengen direkt am Telefon des CO HQ,
    das als Hub des CO TAC Net keine Verbindung zur Staging Area braucht; auch zwei PLT HQs sprechen ueber den Hub."""
    s = _phone_board(board)
    assert not any(c.get("staging") for c in s["karten"].values())
    s["einheiten"]["CO HQ"] = unit("22", vof=None, typ="HQ", ebene="CO", steps=1, funk=[dict(PHONE)])
    for n, k in (("1st PLT HQ", "12"), ("2nd PLT HQ", "21"), ("3rd PLT HQ", "23"), ("CO XO", "32")):
        s["einheiten"][n] = unit(k, vof=None, typ="HQ", ebene="PLT", steps=1, funk=[dict(PHONE)])
    for n in ("1st PLT HQ", "2nd PLT HQ", "3rd PLT HQ", "CO XO"):
        assert comms.communication(s, "CO HQ", n) is True, n
    assert comms.communication(s, "1st PLT HQ", "CO XO") is True
    s["einheiten"]["CO HQ"]["funk"] = []  # ohne das Telefon des Hubs faellt das Netz
    with pytest.raises(rules.Violation):
        comms.communication(s, "CO HQ", "1st PLT HQ")


def test_co_tac_net_scr536_network_a_from_staging(board):
    """[RULE 4.3.5A p.29, 4.3.3 p.27, 2.5 p.12] Zeile 3331, Radio Network A: SCR536 braucht LOS und arbeitet nicht
    unter Cover; aus der Staging Area besteht Funk-LOS nur zu den angrenzenden Karten der Reihe 1. Vier Einheiten
    sind mit dem CO HQ verbunden, drei nicht; Einheiten ohne LOS zum Hub sprechen auch nicht miteinander."""
    s = board
    s.update(co_hq="CO HQ", funk_aktiv=True)
    s["karten"]["02"] = card(0, 2, staging=True)
    s["karten"]["12"]["cover"] = [{"id": "C1", "typ": "Basic Cover", "wert": 1}]
    s["einheiten"]["CO HQ"] = unit("02", vof=None, typ="HQ", ebene="CO", steps=1, funk=[dict(RADIO)])
    on = {"1st PLT HQ": "11", "2nd PLT HQ": "12", "3rd PLT HQ": "13", "CO XO": "12"}
    off = {"Mtr Sec": "22", "1st Sgt": "23", "Wpns PLT HQ": "12"}
    for n, k in {**on, **off}.items():
        s["einheiten"][n] = unit(k, vof=None, typ="HQ", ebene="PLT", steps=1, funk=[dict(RADIO)])
    s["einheiten"]["Wpns PLT HQ"]["bereich"] = "C1"
    for n in on:
        assert comms.communication(s, "CO HQ", n) is True, n
    with pytest.raises(rules.Violation, match="SCR536 does not work there"):
        comms.communication(s, "CO HQ", "Wpns PLT HQ")
    for n in ("Mtr Sec", "1st Sgt"):
        with pytest.raises(rules.Violation, match="no radio LOS"):
            comms.communication(s, "CO HQ", n)
    with pytest.raises(rules.Violation):  # 22 und 23 sehen sich, aber keiner sieht den Hub
        comms.communication(s, "Mtr Sec", "1st Sgt")


def test_co_tac_net_scr536_network_b_hill_as_hub(board):
    """[RULE 4.3.5A p.29, 5.2.1 p.34, 5.2.2 p.35] Zeile 3353, Radio Network B: CO HQ auf dem Huegel oben links ist
    Hub ohne Staging Area; drei Einheiten mit LOS sind verbunden, eine hinter einem gleich hohen Huegel mit dunklen
    Raendern nicht."""
    s = board
    s.update(co_hq="CO HQ", funk_aktiv=True)
    s["karten"]["31"]["elevation"] = 2  # Huegel oben links (Reihe 3 = oben)
    s["karten"]["22"].update(elevation=2, raender="dunkel")
    s["karten"]["13"]["elevation"] = 2
    s["einheiten"]["CO HQ"] = unit("31", vof=None, typ="HQ", ebene="CO", steps=1, funk=[dict(RADIO)])
    for n, k in (("1st PLT HQ", "21"), ("2nd PLT HQ", "11"), ("3rd PLT HQ", "33"), ("CO XO", "13")):
        s["einheiten"][n] = unit(k, vof=None, typ="HQ", ebene="PLT", steps=1, funk=[dict(RADIO)])
    for n in ("1st PLT HQ", "2nd PLT HQ", "3rd PLT HQ"):
        assert comms.communication(s, "CO HQ", n) is True, n
    with pytest.raises(rules.Violation, match="dark edges"):
        comms.communication(s, "CO HQ", "CO XO")
    assert comms.communication(s, "1st PLT HQ", "3rd PLT HQ") is True  # beide ueber den Hub


# ---------------------------------------------------------------- 7.10 Grenade Attacks


def test_grenade_example_1_village_point_blank(board, quiet):
    """[RULE 7.10.4 p.55, 7.10.5 p.55, 6.4 p.45, 5.3 p.37] Zeile 5914, Example 1: 1/3 wirft im Village (+3) auf die
    Deutschen unter +1 Cover und verfehlt; 1/1 PLT und 1/LMG antworten frei (Miss, Hit), das Assault Team nicht.
    Deutsche NCM +3 (+3 Terrain, +1 Cover, -1 Grenade Miss, +0 Small Arms); US NCM 0 (+3, +3, -4 Grenade,
    -1 Grenade Miss, -1 Stacking fuer 4 Steps unter Cover)."""
    s = board
    s.update(phase="3.3.1c", aktiver_hq="3rd PLT HQ")
    s["karten"]["22"].update(
        terrain="Village",
        cc=3,
        cover=[{"id": "C1", "typ": "Basic Cover", "wert": 3}, {"id": "C2", "typ": "Basic Cover", "wert": 1}],
    )
    hq(s, "3rd PLT HQ", available=3)
    s["einheiten"]["3rd PLT HQ"] = unit("22", vof=None, typ="HQ", ebene="PLT", platoon="3", steps=1, bereich="C1")
    s["einheiten"]["1/3"] = unit("22", vof="S", platoon="3", bereich="C1", ziel="22")
    s["einheiten"]["1/1 PLT"] = unit("22", side="Feind", vof="S", bereich="C2", ziel="22")
    s["einheiten"]["1/LMG"] = unit("22", side="Feind", vof="A", typ="Weapons Team", steps=1, bereich="C2", ziel="22")
    s["einheiten"]["Assault Team"] = unit(
        "22", side="Feind", vof="A", rng="P", typ="Assault Team", steps=1, bereich="C2", ziel="22"
    )
    with pytest.raises(rules.Violation, match="draw 2 Action cards"):
        commands.cmd_order(s, ["3rd PLT HQ", "1/3", "4.2.4d"])
    commands.cmd_order(s, ["3rd PLT HQ", "1/3", "4.2.4d", "--success=nein", "--unit=1/1 PLT"])
    assert s["karten"]["22"].get("grenade_miss") is True
    assert {x["werfer"] for x in s["granate_antworten"]} == {"1/1 PLT", "1/LMG"}
    commands.cmd_grenade(s, ["response", "1/1 PLT", "--success=nein"])
    commands.cmd_grenade(s, ["response", "1/LMG", "--success=ja", "--value=-4"])
    with pytest.raises(rules.Violation, match="no open free response"):
        commands.cmd_grenade(s, ["response", "Assault Team", "--success=ja"])
    assert s["einheiten"]["1/3"]["grenade"] == [-4] and s["einheiten"]["3rd PLT HQ"]["grenade"] == [-4]
    for n in ("1/1 PLT", "1/LMG", "Assault Team"):
        assert total(combat.ncm_rows(s, n)) == 3, n
    for n in ("1/3", "3rd PLT HQ"):
        rows = combat.ncm_rows(s, n)
        assert total(rows) == 0, (n, rows)
        assert any("Stacking 4 steps" in t for t, _ in rows)


def test_grenade_example_2_cumulative_grenades_and_miss(board):
    """[RULE 7.10.6 p.55, 7.10.4 p.55, 6.4 p.45] Zeile 5959, Example 2: 1/1, 1/LMG und 1/Mtr unter Automatic VOF (-1),
    Terrain +2, Grenade Miss -1; 1/1 traegt zwei -4 Grenades. NCM 1/LMG und 1/Mtr = 0, NCM 1/1 = -7."""
    s = board
    s["karten"]["22"].update(terrain="Brush", cc=2, grenade_miss=True)
    s["einheiten"]["1/1"] = unit("22", vof="S", platoon="1", grenade=[-4, -4])
    s["einheiten"]["1/LMG"] = unit("22", vof="A", typ="Weapons Team", platoon="1", steps=1)
    s["einheiten"]["1/Mtr"] = unit("22", vof="G", rng="C-L", typ="Weapons Team", platoon="1", steps=1, moerser=True)
    s["einheiten"]["MG 1"] = unit("23", side="Feind", vof="A", typ="Weapons Team", steps=1, ziel="22")
    assert fire.vof_against(s, "22", "US")[:2] == ("A", -1)
    assert total(combat.ncm_rows(s, "1/LMG")) == 0
    assert total(combat.ncm_rows(s, "1/Mtr")) == 0
    rows = combat.ncm_rows(s, "1/1")
    assert total(rows) == -7, rows
    assert ("Grenade VOF (cumulative)", -8) in rows


# ---------------------------------------------------------------- 7.16 Call for Fire


def test_call_for_fire_arty_fo_visual_verbal_and_fd_net(board, quiet):
    """[RULE 7.16.1 p.58, 4.3.3 p.28] Zeile 6197: Ein Arty FO wird von einem HQ in Visual-Verbal-Kommunikation zum
    Call for Fire beordert und spricht mit der Artillerie ueber das Arty-FD-Funkgeraet. Auf einer anderen Karte
    erreicht ihn der Befehl nicht (FOs nicht im CO TAC Net), ohne FD-Funk keine Verbindung zur Feuereinheit."""
    s = board
    s.update(
        phase="3.3.1b",
        co_hq="CO HQ",
        aktiver_hq="CO HQ",
        funk_aktiv=True,
        optionen={"U2_fo_fd_funk": False},
        feuermissionen={"Arty": 2},
        fm_werte={"Arty": -3},
    )
    hq(s, "CO HQ", available=3)
    s["einheiten"]["CO HQ"] = unit(
        "22", vof=None, typ="HQ", ebene="CO", steps=1, funk=[dict(RADIO), {"typ": "SCR300", "netz": "BN TAC"}]
    )
    s["einheiten"]["Arty FO"] = unit("23", vof=None, typ="FO", steps=1, funk=[{"typ": "SCR300", "netz": "ARTY FD"}])
    s["einheiten"]["Enemy 1"] = unit("32", side="Feind", vof="S", ziel="22")
    with pytest.raises(rules.Violation, match="FOs may not join the CO TAC Net"):
        commands.cmd_order(s, ["CO HQ", "Arty FO", "4.2.4i", "--target=32"])
    s["einheiten"]["Arty FO"]["karte"] = "22"  # Visual-Verbal mit dem HQ
    s["einheiten"]["Arty FO"]["funk"] = []
    with pytest.raises(rules.Violation, match="no FD radio"):
        commands.cmd_order(s, ["CO HQ", "Arty FO", "4.2.4i", "--target=32"])
    s["einheiten"]["Arty FO"]["funk"] = [{"typ": "SCR300", "netz": "ARTY FD"}]
    with pytest.raises(rules.Violation, match="draw 2 Action cards"):
        commands.cmd_order(s, ["CO HQ", "Arty FO", "4.2.4i", "--target=32"])
    commands.cmd_order(s, ["CO HQ", "Arty FO", "4.2.4i", "--target=32", "--success=ja"])
    pending = [x for x in s["karten"]["32"]["extern"] if x["typ"] == "Pending"]
    assert pending and pending[0]["wert"] == -3 and pending[0]["quelle"] == "Arty FO"
    assert s["feuermissionen"]["Arty"] == 1 and s["kommandos"]["CO HQ"]["verfuegbar"] == 2


# ---------------------------------------------------------------- 7.18 Munition


def test_mortar_section_split_keeps_full_ammo_per_team(board, quiet):
    """[RULE 7.18.1B p.60, 6.4.3 p.47] Zeile 6404: Eine 60mm Mortar Section mit drei Steps und 3 Munition erhaelt einen
    FC-Hit; Step 1 wird 1/Mtr Fire Team mit 3 Munition, Step 2 Casualty, Step 3 wird 3/Mtr Team mit 3 Munition.
    Das Werkzeug fuehrt die Aufteilung nur fuer die Kampagnenlage (Feld kampagne, breakdown mtr_sec)."""
    s = board
    s.update(phase="3.7.4", kampagne={"versuch": 1})
    s["einheiten"]["Mtr Sec"] = unit(
        "22",
        vof="H",
        rng="C-L",
        typ="Weapons Team",
        steps=3,
        moerser=True,
        breakdown="mtr_sec",
        munition={"typ": "MTR", "punkte": 3, "start": 3},
    )
    combat.cmd_hit(s, ["Mtr Sec", "HIT", "FC"])
    assert "Mtr Sec" not in s["einheiten"]
    ft = s["einheiten"]["1/Mtr"]
    assert "Fire Team side" in ft["status"] and ft["steps"] == 1 and ft["munition"]["punkte"] == 3
    team = s["einheiten"]["3/Mtr"]
    assert "Fire Team side" not in team["status"] and team["steps"] == 1 and team["munition"]["punkte"] == 3
    assert s["karten"]["22"]["casualties"] == 1
