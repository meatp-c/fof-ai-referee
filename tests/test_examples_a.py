"""Worked examples of the rulebook (Series Rules 3rd Ed.), part A: 4.1, 4.3, 7.10, 7.16, 7.18.
Each test rebuilds the situation of the example on the synthetic board and checks the result of the tool
against the example. Line numbers refer to rulebook.txt."""

import pytest
from conftest import card, unit

from fof import briefing, combat, commands, comms, fire, rules, state
from fof import grenades  # L556: split from commands

RADIO = {"type": "SCR536", "net": "CO TAC"}
PHONE = {"type": "EE8", "net": "CO TAC"}


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protocol"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)


def hq(board, name, available=0, saved=0, activated=True):
    board["commands"][name] = {"available": available, "saved": saved, "activated": activated, "done": False}


def total(rows):
    return sum(v for _, v in rows)


# ---------------------------------------------------------------- 4.1.1 / 4.1.2 Command draw


def _co_hq_impulse(board, experience):
    s = board
    s.update(phase="3.3.1b", co_hq="CO HQ")
    s["units"]["CO HQ"] = unit("22", vof=None, type="HQ", level="CO", steps=1, experience=experience)
    s["units"]["1st PLT HQ"] = unit("22", vof=None, type="HQ", level="PLT", platoon="1", steps=1)
    s["units"]["2nd PLT HQ"] = unit("22", vof=None, type="HQ", level="PLT", platoon="2", steps=1)
    hq(s, "CO HQ", activated=True)  # activated by the BN HQ in the previous impulse
    hq(s, "1st PLT HQ", activated=False)
    hq(s, "2nd PLT HQ", activated=False)
    commands.cmd_hq(s, ["CO HQ"])
    commands.cmd_card(s, ["1", "4"])  # card shows 4/3, helmet number 4
    return s


def test_co_hq_impulse_draws_four_commands_and_saves_two(board, quiet):
    """[RULE 4.1.1 p.19, 4.1.2 p.20, 4.1.3 p.20] Lines 1941 and 1976: activated CO HQ (Line) draws 4/3 and gets 4
    Commands, as Green only 3; two Commands activate the 1st and 2nd PLT HQ, the other two are saved."""
    s = _co_hq_impulse(board, "Line")
    assert s["commands"]["CO HQ"]["available"] == 4
    commands.cmd_activate(s, ["1st PLT HQ"])
    commands.cmd_activate(s, ["2nd PLT HQ"])
    assert s["commands"]["1st PLT HQ"]["activated"] and s["commands"]["2nd PLT HQ"]["activated"]
    assert s["commands"]["CO HQ"]["available"] == 2
    commands.cmd_done(s, [])
    assert s["commands"]["CO HQ"]["saved"] == 2 and s["commands"]["CO HQ"]["available"] == 0


def test_co_hq_impulse_green_hq_draws_one_less(board, quiet):
    """[RULE 4.1.2A p.20] Line 1944: the same draw with a Green CO HQ gives 4 - 1 = 3 Commands."""
    s = _co_hq_impulse(board, "Green")
    assert s["commands"]["CO HQ"]["available"] == 3


def test_sniper_example_2nd_plt_hq_commands_and_orders(board, quiet):
    """[RULE 4.1.2 p.20, 4.2.2a/b/e p.23, 6.2.4 p.42, 7.15 p.57] Line 1998: Veteran 2nd PLT HQ under Sniper VOF draws
    5/4 and gets 5 + 1 - 3 = 3 Commands, 4 with one saved Command. Use: 1/2 into the Gully (Exposed, PDF,
    Crossfire on the Sniper), LMG Seek Cover with 3 cards (+1 Cover, Exposed), Platoon Move of HQ, 2/2 and 3/2 into the
    Woods (all Exposed); LMG and Fire Team stay in the Hedgerow and keep firing."""
    s = board
    s.update(phase="3.3.1c", co_hq="CO HQ")
    s["cards"]["22"].update(terrain="Hedgerow", cover_draw=3)
    s["cards"]["21"]["terrain"] = "Gully"
    s["cards"]["23"]["terrain"] = "Woods"
    s["cards"]["32"]["terrain"] = "Orchard"
    s["units"]["CO HQ"] = unit("11", vof=None, type="HQ", level="CO", steps=1)
    s["units"]["2nd PLT HQ"] = unit("22", vof=None, type="HQ", level="PLT", platoon="2", steps=1, experience="Veteran")
    for n in ("1/2", "2/2", "3/2"):
        s["units"][n] = unit("22", vof="S", platoon="2", target="32")
    s["units"]["LMG"] = unit("22", vof="A", type="Weapons Team", platoon="2", steps=1, target="32")
    s["units"]["Fire Team 1"] = unit(
        "22", vof="S", rng="C", type="Fire Team", platoon="2", steps=1, experience="Green", target="32"
    )
    s["units"]["Sniper"] = unit("32", side="Enemy", vof="S!", rng="V", steps=1, target="22", type_name="Sniper")
    hq(s, "CO HQ", activated=True)
    hq(s, "2nd PLT HQ", saved=1, activated=True)
    s["commands"]["CO HQ"]["done"] = True
    assert fire.crossfire(s, "32", "Enemy") is False

    commands.cmd_hq(s, ["2nd PLT HQ"])
    commands.cmd_card(s, ["7", "5"])  # card shows 5/4
    k = s["commands"]["2nd PLT HQ"]
    assert k["available"] == 3 and k["saved"] == 1
    assert "Veteran +1" in s["protocol"][-1]["text"] and "-3" in s["protocol"][-1]["text"]

    # 1: one Command, 1/2 into the Gully (Move to Adjacent Card)
    commands.cmd_order(s, ["2nd PLT HQ", "1/2", "4.2.2a", "--target=21", "--plain=yes"])
    half = s["units"]["1/2"]
    assert half["card"] == "21" and "Exposed" in half["status"] and half["target"] == "32"  # PDF Gully to the Sniper
    assert fire.crossfire(s, "32", "Enemy") is True  # fire from two cards: Crossfire marker on the Sniper
    assert k["available"] == 2

    # 2: one Command, LMG seeks cover with three cards
    with pytest.raises(rules.Violation, match="draw 3 Action cards"):
        commands.cmd_order(s, ["2nd PLT HQ", "LMG", "4.2.2e"])
    commands.cmd_order(s, ["2nd PLT HQ", "LMG", "4.2.2e", "--success=yes"])
    # L567: the booked line names the draw as well
    assert "attempt successful (3 Action cards (base 3" in s["protocol"][-1]["text"]
    assert "success on word Cover" in s["protocol"][-1]["text"]
    assert "(save limit " in s["protocol"][-1]["text"]  # L568: the save limit next to the remaining Commands
    lmg = s["units"]["LMG"]
    cover = [c for c in s["cards"]["22"]["cover"] if c["id"] == lmg["area"]]
    assert cover and cover[0]["value"] == 1 and "Exposed" in lmg["status"]
    assert k["available"] == 1

    # 3: two Commands, Platoon Move of HQ, 2/2 and 3/2 into the Woods
    commands.cmd_order(s, ["2nd PLT HQ", "2nd PLT HQ", "4.2.2b", "--target=23"])
    for n in ("2nd PLT HQ", "2/2", "3/2"):
        assert s["units"][n]["card"] == "23" and "Exposed" in s["units"][n]["status"]
    assert s["units"]["2/2"]["target"] == "32"  # PDF Woods to the Sniper
    for n in ("LMG", "Fire Team 1"):  # stay in the Hedgerow and keep the PDF to the Orchard
        assert s["units"][n]["card"] == "22" and s["units"][n]["target"] == "32"
    assert k["available"] == 0 and k["saved"] == 0


# ---------------------------------------------------------------- 4.3 Kommunikation


def _phone_board(board):
    s = board
    s.update(co_hq="CO HQ", radio_active=True, co_tac_medium="phone")
    return s


def test_co_tac_net_field_phones_network_a(board):
    """[RULE 4.3.3 p.27, 4.3.4 p.28, 2.5 p.12] Line 3265, Phone Network A: four units are linked to the CO HQ by
    phones, laid lines and the built-in lines of the Staging Area; every phone counts as a line itself. Without the
    Staging Area the chain breaks for the units that are linked only through it."""
    s = _phone_board(board)
    s["cards"]["01"] = card(0, 1, staging=True)
    s["cards"]["03"] = card(0, 3, staging=True)
    s["cards"]["21"]["lines"] = [{"cut": False}]
    s["units"]["CO HQ"] = unit("11", vof=None, type="HQ", level="CO", steps=1, radio=[dict(PHONE)])
    s["units"]["1st PLT HQ"] = unit("13", vof=None, type="HQ", level="PLT", platoon="1", steps=1, radio=[dict(PHONE)])
    s["units"]["2nd PLT HQ"] = unit("31", vof=None, type="HQ", level="PLT", platoon="2", steps=1, radio=[dict(PHONE)])
    s["units"]["3rd PLT HQ"] = unit("33", vof=None, type="HQ", level="PLT", platoon="3", steps=1, radio=[dict(PHONE)])
    s["units"]["Wpns PLT HQ"] = unit("32", vof=None, type="HQ", level="PLT", platoon="4", steps=1, radio=[dict(PHONE)])
    s["units"]["1/1"] = unit("22", vof="S", platoon="1")  # ohne Telefon
    for n in ("1st PLT HQ", "2nd PLT HQ", "3rd PLT HQ", "Wpns PLT HQ"):
        assert comms.communication(s, "CO HQ", n) is True, n
    with pytest.raises(rules.Violation, match="no EE8"):
        comms.communication(s, "CO HQ", "1/1")
    for k in ("01", "03"):  # without the Staging Area 13 is cut off; 31, 32, 33 hang on the line of 21
        s["cards"][k]["staging"] = False
    with pytest.raises(rules.Violation, match="no unbroken line chain"):
        comms.communication(s, "CO HQ", "1st PLT HQ")
    for n in ("2nd PLT HQ", "3rd PLT HQ", "Wpns PLT HQ"):
        assert comms.communication(s, "CO HQ", n) is True, n
    for k in ("01", "03"):
        s["cards"][k]["staging"] = True
    s["cards"]["21"]["lines"][0]["cut"] = True  # cut line: the chain through 21 is broken
    assert comms.communication(s, "CO HQ", "1st PLT HQ") is True
    for n in ("2nd PLT HQ", "3rd PLT HQ", "Wpns PLT HQ"):
        with pytest.raises(rules.Violation, match="line cut or missing"):
            comms.communication(s, "CO HQ", n)


def test_co_tac_net_field_phones_network_b_hub_without_staging(board):
    """[RULE 4.3.3 p.27, 4.3.4 p.28] Line 3276, Phone Network B: four units hang directly on the phone of the CO HQ,
    which as the hub of the CO TAC Net needs no link to the Staging Area; two PLT HQs also talk through the hub."""
    s = _phone_board(board)
    assert not any(c.get("staging") for c in s["cards"].values())
    s["units"]["CO HQ"] = unit("22", vof=None, type="HQ", level="CO", steps=1, radio=[dict(PHONE)])
    for n, k in (("1st PLT HQ", "12"), ("2nd PLT HQ", "21"), ("3rd PLT HQ", "23"), ("CO XO", "32")):
        s["units"][n] = unit(k, vof=None, type="HQ", level="PLT", steps=1, radio=[dict(PHONE)])
    for n in ("1st PLT HQ", "2nd PLT HQ", "3rd PLT HQ", "CO XO"):
        assert comms.communication(s, "CO HQ", n) is True, n
    assert comms.communication(s, "1st PLT HQ", "CO XO") is True
    s["units"]["CO HQ"]["radio"] = []  # without the hub's phone the net fails
    with pytest.raises(rules.Violation):
        comms.communication(s, "CO HQ", "1st PLT HQ")


def test_co_tac_net_scr536_network_a_from_staging(board):
    """[RULE 4.3.5A p.29, 4.3.3 p.27, 2.5 p.12] Line 3331, Radio Network A: the SCR536 needs LOS and does not work
    under cover; from the Staging Area there is radio LOS only to the adjacent cards of row 1. Four units are
    linked to the CO HQ, three are not; units without LOS to the hub do not talk to each other either."""
    s = board
    s.update(co_hq="CO HQ", radio_active=True)
    s["cards"]["02"] = card(0, 2, staging=True)
    s["cards"]["12"]["cover"] = [{"id": "C1", "type": "Basic Cover", "value": 1}]
    s["units"]["CO HQ"] = unit("02", vof=None, type="HQ", level="CO", steps=1, radio=[dict(RADIO)])
    on = {"1st PLT HQ": "11", "2nd PLT HQ": "12", "3rd PLT HQ": "13", "CO XO": "12"}
    off = {"Mtr Sec": "22", "1st Sgt": "23", "Wpns PLT HQ": "12"}
    for n, k in {**on, **off}.items():
        s["units"][n] = unit(k, vof=None, type="HQ", level="PLT", steps=1, radio=[dict(RADIO)])
    s["units"]["Wpns PLT HQ"]["area"] = "C1"
    for n in on:
        assert comms.communication(s, "CO HQ", n) is True, n
    with pytest.raises(rules.Violation, match="SCR536 does not work there"):
        comms.communication(s, "CO HQ", "Wpns PLT HQ")
    for n in ("Mtr Sec", "1st Sgt"):
        with pytest.raises(rules.Violation, match="no radio LOS"):
            comms.communication(s, "CO HQ", n)
    with pytest.raises(rules.Violation):  # 22 and 23 see each other, but neither sees the hub
        comms.communication(s, "Mtr Sec", "1st Sgt")


def test_co_tac_net_scr536_network_b_hill_as_hub(board):
    """[RULE 4.3.5A p.29, 5.2.1 p.34, 5.2.2 p.35] Line 3353, Radio Network B: the CO HQ on the hill top left is the
    hub without a Staging Area; three units with LOS are linked, one behind a hill of the same height with dark
    edges is not."""
    s = board
    s.update(co_hq="CO HQ", radio_active=True)
    s["cards"]["31"]["elevation"] = 2  # hill top left (row 3 = top)
    s["cards"]["22"].update(elevation=2, edges="dunkel")
    s["cards"]["13"]["elevation"] = 2
    s["units"]["CO HQ"] = unit("31", vof=None, type="HQ", level="CO", steps=1, radio=[dict(RADIO)])
    for n, k in (("1st PLT HQ", "21"), ("2nd PLT HQ", "11"), ("3rd PLT HQ", "33"), ("CO XO", "13")):
        s["units"][n] = unit(k, vof=None, type="HQ", level="PLT", steps=1, radio=[dict(RADIO)])
    for n in ("1st PLT HQ", "2nd PLT HQ", "3rd PLT HQ"):
        assert comms.communication(s, "CO HQ", n) is True, n
    with pytest.raises(rules.Violation, match="dark edges"):
        comms.communication(s, "CO HQ", "CO XO")
    assert comms.communication(s, "1st PLT HQ", "3rd PLT HQ") is True  # both through the hub


# ---------------------------------------------------------------- 7.10 Grenade Attacks


def test_grenade_example_1_village_point_blank(board, quiet):
    """[RULE 7.10.4 p.55, 7.10.5 p.55, 6.4 p.45, 5.3 p.37] Line 5914, Example 1: 1/3 in the Village (+3) throws at the
    Germans under +1 Cover and misses; 1/1 PLT and 1/LMG respond for free (Miss, Hit), the Assault Team does not.
    German NCM +3 (+3 terrain, +1 Cover, -1 Grenade Miss, +0 Small Arms); US NCM 0 (+3, +3, -4 Grenade,
    -1 Grenade Miss, -1 Stacking for 4 steps under cover)."""
    s = board
    s.update(phase="3.3.1c", active_hq="3rd PLT HQ")
    s["cards"]["22"].update(
        terrain="Village",
        cc=3,
        cover=[{"id": "C1", "type": "Basic Cover", "value": 3}, {"id": "C2", "type": "Basic Cover", "value": 1}],
    )
    hq(s, "3rd PLT HQ", available=3)
    s["units"]["3rd PLT HQ"] = unit("22", vof=None, type="HQ", level="PLT", platoon="3", steps=1, area="C1")
    s["units"]["1/3"] = unit("22", vof="S", platoon="3", area="C1", target="22")
    s["units"]["1/1 PLT"] = unit("22", side="Enemy", vof="S", area="C2", target="22")
    s["units"]["1/LMG"] = unit("22", side="Enemy", vof="A", type="Weapons Team", steps=1, area="C2", target="22")
    s["units"]["Assault Team"] = unit(
        "22", side="Enemy", vof="A", rng="P", type="Assault Team", steps=1, area="C2", target="22"
    )
    with pytest.raises(rules.Violation, match="draw 2 Action cards"):
        commands.cmd_order(s, ["3rd PLT HQ", "1/3", "4.2.4d"])
    commands.cmd_order(s, ["3rd PLT HQ", "1/3", "4.2.4d", "--success=no", "--unit=1/1 PLT"])
    assert s["cards"]["22"].get("grenade_miss") is True
    assert {x["launcher"] for x in s["grenade_responses"]} == {"1/1 PLT", "1/LMG"}
    grenades.cmd_grenade(s, ["response", "1/1 PLT", "--success=no"])
    grenades.cmd_grenade(s, ["response", "1/LMG", "--success=yes", "--value=-4"])
    with pytest.raises(rules.Violation, match="no open free response"):
        grenades.cmd_grenade(s, ["response", "Assault Team", "--success=yes"])
    assert s["units"]["1/3"]["grenade"] == [-4] and s["units"]["3rd PLT HQ"]["grenade"] == [-4]
    for n in ("1/1 PLT", "1/LMG", "Assault Team"):
        assert total(combat.ncm_rows(s, n)) == 3, n
    for n in ("1/3", "3rd PLT HQ"):
        rows = combat.ncm_rows(s, n)
        assert total(rows) == 0, (n, rows)
        assert any("Stacking 4 steps" in t for t, _ in rows)


def test_grenade_example_2_cumulative_grenades_and_miss(board):
    """[RULE 7.10.6 p.55, 7.10.4 p.55, 6.4 p.45] Line 5959, Example 2: 1/1, 1/LMG and 1/Mtr under Automatic VOF (-1),
    terrain +2, Grenade Miss -1; 1/1 takes two -4 Grenades. NCM 1/LMG and 1/Mtr = 0, NCM 1/1 = -7."""
    s = board
    s["cards"]["22"].update(terrain="Brush", cc=2, grenade_miss=True)
    s["units"]["1/1"] = unit("22", vof="S", platoon="1", grenade=[-4, -4])
    s["units"]["1/LMG"] = unit("22", vof="A", type="Weapons Team", platoon="1", steps=1)
    s["units"]["1/Mtr"] = unit("22", vof="G", rng="C-L", type="Weapons Team", platoon="1", steps=1, mortar=True)
    s["units"]["MG 1"] = unit("23", side="Enemy", vof="A", type="Weapons Team", steps=1, target="22")
    assert fire.vof_against(s, "22", "US")[:2] == ("A", -1)
    assert total(combat.ncm_rows(s, "1/LMG")) == 0
    assert total(combat.ncm_rows(s, "1/Mtr")) == 0
    rows = combat.ncm_rows(s, "1/1")
    assert total(rows) == -7, rows
    assert ("Grenade VOF (cumulative)", -8) in rows


# ---------------------------------------------------------------- 7.16 Call for Fire


def test_call_for_fire_arty_fo_visual_verbal_and_fd_net(board, quiet):
    """[RULE 7.16.1 p.58, 4.3.3 p.28] Line 6197: an Arty FO is ordered to Call for Fire by an HQ in visual-verbal
    communication and talks to the artillery over the Arty FD radio. On another card the order does not reach him
    (FOs are not in the CO TAC Net); without the FD radio there is no link to the firing agency."""
    s = board
    s.update(
        phase="3.3.1b",
        co_hq="CO HQ",
        active_hq="CO HQ",
        radio_active=True,
        options={"U2_fo_fd_radio": False},
        fire_missions={"Arty": 2},
        fm_values={"Arty": -3},
    )
    hq(s, "CO HQ", available=3)
    s["units"]["CO HQ"] = unit(
        "22", vof=None, type="HQ", level="CO", steps=1, radio=[dict(RADIO), {"type": "SCR300", "net": "BN TAC"}]
    )
    s["units"]["Arty FO"] = unit("23", vof=None, type="FO", steps=1, radio=[{"type": "SCR300", "net": "ARTY FD"}])
    s["units"]["Enemy 1"] = unit("32", side="Enemy", vof="S", target="22")
    with pytest.raises(rules.Violation, match="FOs may not join the CO TAC Net"):
        commands.cmd_order(s, ["CO HQ", "Arty FO", "4.2.4i", "--target=32"])
    s["units"]["Arty FO"]["card"] = "22"  # visual-verbal with the HQ
    s["units"]["Arty FO"]["radio"] = []
    with pytest.raises(rules.Violation, match="no FD radio"):
        commands.cmd_order(s, ["CO HQ", "Arty FO", "4.2.4i", "--target=32"])
    s["units"]["Arty FO"]["radio"] = [{"type": "SCR300", "net": "ARTY FD"}]
    with pytest.raises(rules.Violation, match="draw 2 Action cards"):
        commands.cmd_order(s, ["CO HQ", "Arty FO", "4.2.4i", "--target=32"])
    commands.cmd_order(s, ["CO HQ", "Arty FO", "4.2.4i", "--target=32", "--success=yes"])
    pending = [x for x in s["cards"]["32"]["external"] if x["type"] == "Pending"]
    assert pending and pending[0]["value"] == -3 and pending[0]["source"] == "Arty FO"
    assert s["fire_missions"]["Arty"] == 1 and s["commands"]["CO HQ"]["available"] == 2


# ---------------------------------------------------------------- 7.18 Munition


def test_mortar_section_split_keeps_full_ammo_per_team(board, quiet):
    """[RULE 7.18.1B p.60, 6.4.3 p.47] Line 6404: a 60mm Mortar Section with three steps and 3 ammo takes an
    FC hit; step 1 becomes the 1/Mtr Fire Team with 3 ammo, step 2 a Casualty, step 3 the 3/Mtr Team with 3 ammo.
    The tool makes the breakdown only in the campaign setting (field campaign, breakdown mtr_sec)."""
    s = board
    s.update(phase="3.7.4", campaign={"attempt": 1})
    s["units"]["Mtr Sec"] = unit(
        "22",
        vof="H",
        rng="C-L",
        type="Weapons Team",
        steps=3,
        mortar=True,
        breakdown="mtr_sec",
        ammo={"type": "MTR", "points": 3, "start": 3},
    )
    combat.cmd_hit(s, ["Mtr Sec", "HIT", "FC"])
    assert "Mtr Sec" not in s["units"]
    ft = s["units"]["1/Mtr"]
    assert "Fire Team side" in ft["status"] and ft["steps"] == 1 and ft["ammo"]["points"] == 3
    team = s["units"]["3/Mtr"]
    assert "Fire Team side" not in team["status"] and team["steps"] == 1 and team["ammo"]["points"] == 3
    assert s["cards"]["22"]["casualties"] == 1
