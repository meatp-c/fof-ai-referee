"""Rules added before Normandy M5 from the coverage list (L138 to L146)."""

import types

import pytest
from conftest import unit

from fof import briefing, campaign, commands, enemy, rules, state


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protokoll"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)


def test_colored_smoke_not_at_night(board):
    """[RULE 4.4.1 p.30] colored smoke cannot signal during night missions (Moon +2 or higher). L138"""
    board["sicht"], board["licht"] = "eingeschraenkt", 2
    board["einheiten"]["CO XO"] = unit("11", vof=None, typ="Staff", assets=["Red Smoke", "RSP"])
    with pytest.raises(rules.Violation, match="colored smoke"):
        commands.execute_pyro(board, board["einheiten"]["CO XO"], "CO XO", {"--asset": "Red Smoke"}, [])
    board["licht"] = 1
    board["einheiten"]["CO XO"]["assets"] = ["Red Smoke"]
    try:
        commands.execute_pyro(board, board["einheiten"]["CO XO"], "CO XO", {"--asset": "Red Smoke"}, [])
    except rules.Violation as ex:  # other checks may follow, but not the night ban
        assert "colored smoke" not in str(ex)


def test_concentrate_fire_target_must_be_spotted_enemy_on_target_card(board):
    """[RULE 7.11.1 p.56] L140"""
    board["einheiten"]["Enemy 1"] = unit("13", side="Feind", spotted=False)
    board["einheiten"]["Enemy 2"] = unit("12", side="Feind")
    with pytest.raises(rules.Violation, match="Unspotted"):
        commands.cf_target_check(board, "13", "Enemy 1")
    with pytest.raises(rules.Violation, match="not an opposing unit on the target card"):
        commands.cf_target_check(board, "13", "Enemy 2")
    commands.cf_target_check(board, "12", "Enemy 2")


def test_largest_target_first_on_own_card(board):
    """[RULE 8.6.1B p.66] L143: a stack under a cover marker counts as one target."""
    board["karten"]["12"]["cover"] = [{"id": "C1", "typ": "Foxholes", "wert": 1}]
    board["einheiten"]["1/1"] = unit("12", steps=3)
    board["einheiten"]["1/2"] = unit("12", steps=2, bereich="C1")
    board["einheiten"]["1/3"] = unit("12", steps=2, bereich="C1")
    assert set(enemy.largest_targets(board, "12")) == {"1/2", "1/3"}  # stack of 4 beats the single squad of 3
    board["einheiten"]["1/1"]["steps"] = 4
    assert set(enemy.largest_targets(board, "12")) == {"1/1", "1/2", "1/3"}  # tie: random


def test_fall_back_candidates_prefer_hidden_then_cover(board):
    """[RULE 8.6.3 p.66] L141: priority 2 out of US LOS, priority 3 highest cover value."""
    board["einheiten"]["Enemy 1"] = unit("21", side="Feind")
    board["einheiten"]["1/1"] = unit(
        "11"
    )  # US on 11 sees 31 straight up the column but not 32 (not a straight line? 11-32 is not)
    board["karten"]["32"]["cc"] = 2
    board["karten"]["31"]["cc"] = 3
    # 11 to 31: straight column, LOS; 11 to 32: no straight line, so out of LOS
    assert enemy.fall_back_candidates(board, board["einheiten"]["Enemy 1"]) == ["32"]
    board["einheiten"].pop("1/1")
    assert enemy.fall_back_candidates(board, board["einheiten"]["Enemy 1"]) == ["31"]  # now only cover decides


def test_enemy_leader_extra_card(board):
    """[RULE 8.9 p.67] L142"""
    board["einheiten"]["Enemy 1"] = unit("21", side="Feind", erfahrung="Line")
    assert enemy.enemy_attempt_cards(board, board["einheiten"]["Enemy 1"]) == 2
    board["einheiten"]["Leader"] = unit("21", side="Feind", typ="HQ", vof=None, leader=True, steps=1)
    assert enemy.enemy_attempt_cards(board, board["einheiten"]["Enemy 1"]) == 3
    board["einheiten"]["Enemy 1"]["tripod"] = True
    assert enemy.enemy_attempt_cards(board, board["einheiten"]["Enemy 1"], concentrate=True) == 4


def test_enemy_fall_back_drops_surplus_ammo(board, quiet):
    """[RULE 8.11 p.68] L145: HMG with 8 ammo carries 6, the rest stays on the card."""
    hmg = unit(
        "21",
        side="Feind",
        vof="A",
        typ="Weapons Team",
        steps=1,
        tripod=True,
        munition={"typ": "MG", "punkte": 8, "start": 8},
    )
    board["einheiten"]["HMG"] = hmg
    board["phase"] = "3.4.2"
    ctx = types.SimpleNamespace(n="HMG", e=hmg, o={"--ziel": "31"}, prot=[], a="fall back")
    enemy._enemy_fall_back(board, ctx)
    assert hmg["munition"]["punkte"] == 6 and board["karten"]["21"]["munition"] == {"MG": 2}
    assert hmg["karte"] == "31"


def test_grenade_response_is_offered_and_booked(board, quiet):
    """[RULE 7.10.5 p.55] L144"""
    board.update(zug=2, aktiver_hq="1st PLT HQ", xp=[])
    board["kommandos"]["1st PLT HQ"] = {"verfuegbar": 6, "gespart": 0, "aktiviert": True, "fertig": False}
    board["einheiten"]["1st PLT HQ"] = unit("22", vof=None, typ="HQ", ebene="PLT", platoon="1", steps=1)
    board["einheiten"]["1/1"] = unit("22", vof="S", platoon="1", ziel="22")
    board["einheiten"]["Enemy 1"] = unit("22", side="Feind", vof="S", ziel="22")
    commands.cmd_order(board, ["1st PLT HQ", "1/1", "4.2.4d", "--success=ja", "--unit=Enemy 1"])
    rec = board["granate_antworten"]
    assert len(rec) == 1 and {k: rec[0][k] for k in ("werfer", "angreifer", "karte")} == {
        "werfer": "Enemy 1",
        "angreifer": "1/1",
        "karte": "22",
    }
    assert rec[0]["zug"] == 2  # L231 (review H9): records carry the turn
    with pytest.raises(rules.Violation, match="draw 2 Action cards"):
        commands.cmd_grenade(board, ["response", "Enemy 1"])
    commands.cmd_grenade(board, ["response", "Enemy 1", "--success=ja"])
    assert board["einheiten"]["1/1"]["grenade"] == [rules.GRENADE_VOF_DEFAULT] and board["granate_antworten"] == []
    with pytest.raises(rules.Violation, match="no open free response"):
        commands.cmd_grenade(board, ["response", "Enemy 1", "--success=ja"])


def test_xp_promote_and_skill(board, quiet):
    """[RULE 12.3 p.81, 12.7 p.82] L146"""
    board.update(
        kampagne={"versuch": 1}, missionsende=True, xp=[{"zug": 1, "versuch": 1, "punkte": 6, "grund": "test"}]
    )
    board["einheiten"]["1/1"] = unit("11", erfahrung="Green")
    board["einheiten"]["Eng"] = unit("11", erfahrung="Green", attachment=True)
    board["einheiten"]["1st PLT HQ"] = unit("11", vof=None, typ="HQ", ebene="PLT", platoon="1", steps=1)
    campaign.cmd_xp(board, ["promote", "1/1", "--from=Green", "--steps=3"])
    assert board["einheiten"]["1/1"]["erfahrung"] == "Line" and sum(x["punkte"] for x in board["xp"]) == 3
    with pytest.raises(rules.Violation, match="already promoted"):
        campaign.cmd_xp(board, ["promote", "1/1", "--from=Line", "--steps=1"])
    with pytest.raises(rules.Violation, match="attachment"):
        campaign.cmd_xp(board, ["promote", "Eng", "--from=Green"])
    campaign.cmd_xp(board, ["skill", "1st PLT HQ", "General Initiative"])
    assert (
        board["einheiten"]["1st PLT HQ"]["skills"] == ["General Initiative"]
        and sum(x["punkte"] for x in board["xp"]) == 1
    )
    with pytest.raises(rules.Violation, match="Not enough"):
        campaign.cmd_xp(board, ["skill", "1st PLT HQ", "Paralyzed to Assault Team"])


def test_draw_watch_names_jam_and_critical_hit(board):
    """L153: Jam for jam-prone units (7.12: A, G!, H weapons teams, A squads with ammo), Critical Hit (7.10.3, 7.11.4)."""
    bazooka = unit("11", vof="G", rng="C", typ="Weapons Team", steps=1)
    squad = unit("11", vof="S")
    w = commands.draw_watch(board, "grenade", bazooka, ranged=True)
    assert "Jam icon = weapon malfunction" in w and "Critical Hit" in w
    assert "no effect at Point Blank" in commands.draw_watch(board, "grenade", bazooka, ranged=False)
    assert "never counts as Crosshairs" in commands.draw_watch(board, "cf", squad)
    assert "Short" in commands.draw_watch(board, "cff", squad)


def test_concentrate_fire_critical_hit(board, quiet):
    """[RULE 7.11.4 p.56] L154: under cover the stack loses its cover benefit, out of cover a second CF marker."""
    board.update(zug=2, aktiver_hq="1st PLT HQ")
    board["kommandos"]["1st PLT HQ"] = {"verfuegbar": 6, "gespart": 0, "aktiviert": True, "fertig": False}
    board["einheiten"]["1st PLT HQ"] = unit("21", vof=None, typ="HQ", ebene="PLT", platoon="1", steps=1)
    board["einheiten"]["1/1"] = unit("21", vof="S", platoon="1", ziel="22")
    board["karten"]["22"]["cover"] = [{"id": "C1", "typ": "Foxholes", "wert": 1}]
    board["einheiten"]["Enemy 1"] = unit("22", side="Feind", bereich="C1")
    board["einheiten"]["Enemy 2"] = unit("22", side="Feind")
    with pytest.raises(rules.Violation, match="WATCH: 2 or more Crosshairs"):
        commands.cmd_order(board, ["1st PLT HQ", "1/1", "4.2.4b"])
    commands.cmd_order(board, ["1st PLT HQ", "1/1", "4.2.4b", "--success=ja", "--unit=Enemy 1", "--critical=ja"])
    assert board["einheiten"]["Enemy 1"]["cf_critical"] is True
    from fof import combat

    rows = combat.ncm_rows(board, "Enemy 1")
    assert any("lost (Critical Hit Concentrated Fire)" in r[0] and r[1] == 0 for r in rows)
    board["impuls_aktionen"] = {}
    commands.cmd_order(board, ["1st PLT HQ", "1/1", "4.2.4b", "--success=ja", "--unit=Enemy 2", "--critical=ja"])
    assert board["einheiten"]["Enemy 2"]["cf"] == 2


def test_ncm_groups_card_by_card_numbered(board, capsys):
    """V18/L155: Combat Effects per card and per NCM value; numbered list shows how many cards to draw."""
    from fof import combat

    board["phase"] = "3.7.4"
    board["einheiten"]["MG"] = unit("11", side="Feind", vof="A", ziel="22")
    board["einheiten"]["1/1"] = unit("22")
    board["einheiten"]["1/2"] = unit("22")
    board["einheiten"]["1/3"] = unit("22", status=["Pinned"])
    board["kampf_offen"] = ["1/1", "1/2", "1/3"]
    groups = combat.ncm_groups(board)
    assert groups == [("22", -1, ["1/1", "1/2"]), ("22", 0, ["1/3"])]
    combat.cmd_ncm(board, ["next"])
    out = capsys.readouterr().out
    assert "Draw 2 Action cards" in out and "1. 1/1" in out and "2. 1/2" in out and "group 1 of 2" in out


def test_hill_dark_edges_supersede_white_edges(board):
    """[RULE 5.2.2A p.35, BGG 3478872] L157: terrain on a Hill card always has dark edges."""
    from fof import setup

    board["terrain_katalog"] = {
        "Hedgerow/Bocage": {"cc": 2, "cc2": 1, "cover_max": 2, "cover_draw": 4, "raender": None}
    }
    setup.set_terrain(board, "12", "Hedgerow/Bocage", {"--hill": "1", "--raender": "unten:weiss"})
    assert board["karten"]["12"]["raender"] == "gruen" and board["karten"]["12"]["elevation"] == 2


def test_skill_markers_two_sided_counter_mix():
    """L158/E67: three markers carry Auto Grenade or Auto Infiltrate, one of them both faces (E38)."""
    from fof import campaign, rules

    m = rules.SKILL_MARKERS_NORMANDY
    assert campaign.skill_markers_fit(m, ["Auto Grenade", "Auto Grenade", "Auto Infiltrate", "Auto Spot"])
    assert not campaign.skill_markers_fit(m, ["Auto Grenade", "Auto Grenade", "Auto Infiltrate", "Auto Infiltrate"])
    assert campaign.skill_markers_fit(m, ["General Initiative"] * 3 + ["Extra Draw"])
    assert not campaign.skill_markers_fit(m, ["General Initiative"] * 3 + ["Extra Draw"] * 2)
