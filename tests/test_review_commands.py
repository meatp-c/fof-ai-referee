"""Fixes of the code review of 23.10.2026 in commands.py (L230 to L257), one test per fix on the synthetic board."""

import pytest
from conftest import unit

from fof import briefing, commands, rules, state


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protokoll"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)


def plt_hq(board, name="1st PLT HQ", kid="22", platoon="1", available=6):
    board["kommandos"][name] = {"verfuegbar": available, "gespart": 0, "aktiviert": True, "fertig": False}
    board["einheiten"][name] = unit(kid, vof=None, typ="HQ", ebene="PLT", platoon=platoon, steps=1)
    board["aktiver_hq"] = name
    return board["einheiten"][name]


# ---------------------------------------------------------------- H8 (L230)


def test_parse_per_unit_accepts_english_and_german():
    assert commands.parse_per_unit("1/1:yes,2/1:no, MG:JA ,1st PLT HQ:Nein") == {
        "1/1": "ja",
        "2/1": "nein",
        "MG": "ja",
        "1st PLT HQ": "nein",
    }
    assert commands.parse_per_unit(None) == {} and commands.parse_per_unit("ja") == {}
    with pytest.raises(rules.Violation, match="yes or no"):
        commands.parse_per_unit("1/1:maybe")


def test_platoon_infiltrate_marks_exposed_with_english_no(board, quiet):
    """H8: '2/1:no' used to be read as a success, so the unit infiltrated without Exposed [RULE 4.2.2d, 5.1.4]."""
    s = board
    plt_hq(s)
    s["einheiten"]["1/1"] = unit("22", platoon="1")
    s["einheiten"]["2/1"] = unit("22", platoon="1")
    s["einheiten"]["Enemy 1"] = unit("23", side="Feind", vof="A", ziel="22")  # VOF on the origin card (5.1.4)
    commands.cmd_order(
        s, ["1st PLT HQ", "1st PLT HQ", "4.2.2d", "--target=32", "--success=1st PLT HQ:yes,1/1:yes,2/1:no"]
    )
    assert s["einheiten"]["2/1"]["karte"] == "32" and "Exposed" in s["einheiten"]["2/1"]["status"]
    assert "Exposed" not in s["einheiten"]["1/1"]["status"]


# ---------------------------------------------------------------- H9 (L231)


def test_grenade_response_lapsed_record_does_not_block_newer(board, quiet):
    s = board
    s["zug"] = 3
    s["einheiten"]["Enemy 1"] = unit("22", side="Feind", vof="S", ziel="22")
    s["einheiten"]["1/1"] = unit("22", vof="S", ziel="22")
    s["granate_antworten"] = [
        {"werfer": "Enemy 1", "angreifer": "Gone Team", "karte": "22", "zug": 3, "phase": "3.3.1b"},  # attacker removed
        {"werfer": "Enemy 1", "angreifer": "1/1", "karte": "22", "zug": 2, "phase": "3.3.1b"},  # earlier turn
        {"werfer": "Enemy 1", "angreifer": "1/1", "karte": "22", "zug": 3, "phase": "3.3.1b"},
    ]
    with pytest.raises(rules.Violation, match="free response throw at 1/1"):
        commands.cmd_grenade(s, ["response", "Enemy 1"])
    commands.cmd_grenade(s, ["response", "Enemy 1", "--success=ja"])
    assert s["einheiten"]["1/1"]["grenade"] == [rules.GRENADE_VOF_DEFAULT] and s["granate_antworten"] == []


def test_grenade_response_record_carries_turn_and_phase(board, quiet):
    s = board
    plt_hq(s)
    s["einheiten"]["1/1"] = unit("22", vof="S", platoon="1", ziel="22")
    s["einheiten"]["Enemy 1"] = unit("22", side="Feind", vof="S", ziel="22")
    commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.4d", "--success=ja", "--unit=Enemy 1"])
    rec = s["granate_antworten"][0]
    assert rec["zug"] == s["zug"] and rec["phase"] == s["phase"] and rec["angreifer"] == "1/1"


# ---------------------------------------------------------------- H12, M14 (L232, L233)


def test_handlers_refuse_missing_or_bad_arguments(board):
    s = board
    s["einheiten"]["1/1"] = unit("22")
    s["einheiten"]["CO HQ"] = unit("22", vof=None, typ="HQ", ebene="CO", steps=1)
    s["kommandos"]["CO HQ"] = {"verfuegbar": 2, "gespart": 0, "aktiviert": True, "fertig": False}
    for handler, args in (
        (commands.cmd_activate, []),
        (commands.cmd_hq, []),
        (commands.cmd_order, ["CO HQ", "1/1"]),
        (commands.cmd_fire, ["1/1"]),
        (commands.cmd_grenade, ["response"]),
        (commands.cmd_correct, ["munition", "1/1"]),
        (commands.cmd_correct, ["status", "1/1", "Pinned"]),
        (commands.cmd_correct, ["granate", "1/1", "verfallen"]),
    ):
        with pytest.raises(rules.Violation):
            handler(s, args)
    s["einheiten"]["1/1"]["munition"] = {"typ": "MG", "punkte": 3, "start": 6}
    with pytest.raises(rules.Violation, match="whole number"):
        commands.cmd_correct(s, ["munition", "1/1", "x", "--grund=test"])
    with pytest.raises(rules.Violation, match="whole number"):
        commands.cmd_correct(s, ["casualty", "22", "two", "--grund=test"])
    with pytest.raises(rules.Violation, match="not an HQ"):  # M14: hq <squad> was a KeyError
        commands.cmd_hq(s, ["1/1"])


# ---------------------------------------------------------------- M7 (L234)


def test_impulse_cap_checked_before_draw_prompt(board):
    s = board
    plt_hq(s, available=4)
    s["impuls_ausgegeben"] = {"1st PLT HQ": 6}
    s["einheiten"]["Enemy 1"] = unit("23", side="Feind", spotted=False)
    with pytest.raises(rules.Violation) as ex:
        commands.cmd_order(s, ["1st PLT HQ", "1st PLT HQ", "4.2.4a", "--target=23"])
    assert "per impulse" in str(ex.value) and "draw" not in str(ex.value)
    s["einheiten"]["Runner 1"] = unit("22", typ="Runner", steps=1)
    s["runner_box"] = ["Runner 1"]
    s["co_hq"] = "1st PLT HQ"
    s["kampagne"] = {}
    with pytest.raises(rules.Violation, match="per impulse"):
        commands.cmd_order(s, ["1st PLT HQ", "Runner 1", "4.2.1g", "--target=1st PLT HQ"])


# ---------------------------------------------------------------- M8 (L235)


def test_platoon_infiltrate_checks_every_member_before_the_draw(board, quiet):
    s = board
    plt_hq(s)
    s["einheiten"]["1/1"] = unit("22", platoon="1")
    s["einheiten"]["Enemy 1"] = unit("23", side="Feind", vof="A", ziel="22")
    s["einheiten"]["1/1"]["mine_hit"] = True  # one member may not move this turn [RULE 7.9.1]
    with pytest.raises(rules.Violation) as ex:
        commands.cmd_order(s, ["1st PLT HQ", "1st PLT HQ", "4.2.2d", "--target=32"])
    assert "Mine marker" in str(ex.value) and "draws itself" not in str(ex.value)


# ---------------------------------------------------------------- M9 (L236)


def test_bn_on_board_activation_refuses_duplicate_and_fire_team_side(board, quiet):
    s = board
    s["phase"] = "3.3.1a"
    s["aktiver_hq"] = "BN HQ"
    s["einheiten"]["BN HQ"] = unit("22", vof=None, typ="HQ", ebene="BN", steps=1)
    s["einheiten"]["CO HQ"] = unit("22", vof=None, typ="HQ", ebene="CO", steps=1)
    s["kommandos"]["BN HQ"] = {"verfuegbar": 4, "gespart": 0, "aktiviert": True, "fertig": False}
    s["kommandos"]["CO HQ"] = {"verfuegbar": 0, "gespart": 0, "aktiviert": False, "fertig": False}
    commands.cmd_activate(s, ["CO HQ"])
    assert s["kommandos"]["BN HQ"]["verfuegbar"] == 3
    with pytest.raises(rules.Violation, match="already activated"):
        commands.cmd_activate(s, ["CO HQ"])
    assert s["kommandos"]["BN HQ"]["verfuegbar"] == 3
    s["kommandos"]["CO HQ"]["aktiviert"] = False
    s["einheiten"]["CO HQ"]["status"].append("Fire Team side")
    with pytest.raises(rules.Violation, match="Fire Team side"):
        commands.cmd_activate(s, ["CO HQ"])


# ---------------------------------------------------------------- M10 (L237)


def test_supplement_and_reconstitute_remove_teams_via_remove_from_play(board, quiet):
    s = board
    plt_hq(s)
    s["einheiten"]["1/1"] = unit("22", platoon="1", steps=2)
    s["einheiten"]["Fire Team 1"] = unit("22", typ="Fire Team", platoon="1", steps=1, traegt_casualties=1)
    commands.cmd_order(s, ["1st PLT HQ", "Fire Team 1", "4.2.3h", "--squad=1/1"])
    assert "Fire Team 1" not in s["einheiten"] and "Fire Team 1" in s["removed_from_play"]
    assert s["einheiten"]["1/1"]["steps"] == 3 and s["karten"]["22"]["casualties"] == 1  # casualty back on the card
    s["removed_from_play"].append("2/1")
    s["einheiten"]["Fire Team 2"] = unit("22", typ="Fire Team", platoon="1", steps=1)
    s["einheiten"]["Assault Team 1"] = unit("22", typ="Assault Team", platoon="1", steps=1, assets=["Rifle Grenade"])
    commands.cmd_order(
        s, ["1st PLT HQ", "Fire Team 2", "4.2.3i", "--squad=2/1", "--with=Assault Team 1", "--success=ja"]
    )
    assert s["einheiten"]["2/1"]["steps"] == 2
    assert {"Fire Team 2", "Assault Team 1"} <= set(s["removed_from_play"])
    assert s["karten"]["22"]["assets_boden"] == ["Rifle Grenade"]


# ---------------------------------------------------------------- M11 (L238)


def test_grenade_unit_must_be_a_spotted_enemy_on_the_target_card(board, quiet):
    s = board
    plt_hq(s)
    s["einheiten"]["1/1"] = unit("22", vof="S", platoon="1", ziel="22")
    s["einheiten"]["2/1"] = unit("22", vof="S", platoon="1", ziel="22")
    s["einheiten"]["Enemy 1"] = unit("22", side="Feind", vof="S", ziel="22")
    s["einheiten"]["Enemy 2"] = unit("23", side="Feind", vof="S", ziel="22")
    with pytest.raises(rules.Violation, match="not an opposing unit on the target card"):
        commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.4d", "--success=ja", "--unit=2/1"])
    with pytest.raises(rules.Violation, match="not an opposing unit on the target card"):
        commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.4d", "--success=ja", "--unit=Enemy 2"])
    assert "grenade" not in s["einheiten"]["2/1"] and "grenade" not in s["einheiten"]["Enemy 2"]
    s["einheiten"]["Enemy 3"] = unit("22", side="Feind", vof="S", ziel="22", spotted=False)
    with pytest.raises(rules.Violation, match="Unspotted"):
        commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.4d", "--success=ja", "--unit=Enemy 3"])


# ---------------------------------------------------------------- M12 (L239)


def test_pick_up_comma_list_with_ammo_and_casualty(board, quiet):
    s = board
    plt_hq(s)
    s["einheiten"]["MG"] = unit(
        "22", vof="A", typ="Weapons Team", platoon="1", steps=2, munition={"typ": "MG", "punkte": 2}
    )
    s["karten"]["22"].update(munition={"MG": 3}, casualties=2, leitung_assets=1)
    commands.cmd_order(s, ["1st PLT HQ", "MG", "4.2.2h", "--what=MG:2,Casualty:1,Leitung:1"])
    mg = s["einheiten"]["MG"]
    assert mg["munition"]["punkte"] == 4 and s["karten"]["22"]["munition"]["MG"] == 1
    assert mg["traegt_casualties"] == 1 and s["karten"]["22"]["casualties"] == 1
    assert mg["leitungen"] == 1 and s["karten"]["22"]["leitung_assets"] == 0
    with pytest.raises(rules.Violation, match="whole number"):
        commands.cmd_order(s, ["1st PLT HQ", "1st PLT HQ", "4.2.2h", "--what=Casualty:one"])


# ---------------------------------------------------------------- M13 (L240)


def test_team_option_validates_and_capitalizes(board, quiet):
    assert commands.team_option({"--team": "fire"}, "Assault") == "Fire"
    assert commands.team_option({}, "Assault") == "Assault"
    with pytest.raises(rules.Violation, match="--team=fire|assault"):
        commands.team_option({"--team": "mortar"}, "Assault")
    s = board
    plt_hq(s)
    s["einheiten"]["1/1"] = unit("22", platoon="1", steps=3)
    commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.3g", "--team=fire"])
    assert s["einheiten"]["Fire Team 1"]["typ"] == "Fire Team" and s["einheiten"]["1/1"]["steps"] == 2


# ---------------------------------------------------------------- M15 (L241)


def test_event_fulfilled_line_reaches_the_protocol_once(board, quiet):
    s = board
    s["kampagne"] = {}
    s["ereignis_flanke"] = {"id": "company_ahead", "zug": 1, "reihe": 1}
    plt_hq(s, kid="12")
    s["einheiten"]["1/1"] = unit("12", platoon="1")
    commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.2a", "--target=22", "--area=offen"])
    text = s["protokoll"][-1]["text"]
    assert text.count("fulfilled") == 1 and s["ereignis_flanke"]["erfuellt"] is True
    s["ereignis_flanke"] = {"id": "company_ahead", "zug": 1, "reihe": 1}
    commands.event_move_check(s, s["einheiten"]["1st PLT HQ"], "22")
    assert "erfuellt" not in s["ereignis_flanke"]  # the check-only call leaves the flag to move_unit


# ---------------------------------------------------------------- M16 (L242)


def test_gi_plt_hq_may_originate_its_own_platoon_move(board, quiet):
    s = board
    s["phase"] = "3.3.2d"
    plt_hq(s)
    s["aktiver_hq"] = "GI"
    s["kommandos"]["GI"] = {"verfuegbar": 4, "gespart": 0, "aktiviert": False, "fertig": False}
    s["einheiten"]["1/1"] = unit("22", platoon="1")
    with pytest.raises(rules.Violation, match="needs the responsible HQ as originator"):
        commands.cmd_order(s, ["GI", "1/1", "4.2.2b", "--target=32"])
    commands.cmd_order(s, ["GI", "1st PLT HQ", "4.2.2b", "--target=32", "--originator=1st PLT HQ"])
    assert s["einheiten"]["1/1"]["karte"] == "32" and s["einheiten"]["1st PLT HQ"]["karte"] == "32"
    assert s["kommandos"]["GI"]["verfuegbar"] == 2


# ---------------------------------------------------------------- M17 (L243)


def test_second_indirect_lay_on_the_same_mortar_is_refused(board):
    s = board
    hq = unit("22", vof=None, typ="HQ", ebene="PLT", platoon="1", steps=1)
    s["einheiten"]["1st PLT HQ"] = hq
    s["einheiten"]["Mtr"] = unit("22", vof="H", typ="Weapons Team", platoon="1", steps=2, moerser=True)
    s["karten"]["23"]["extern"].append({"typ": "Indirect", "wert": -3, "quelle": "Mtr", "seite": "US"})
    with pytest.raises(rules.Violation, match="already fires an Indirect Lay"):
        commands.indirect_lay(s, "1st PLT HQ", hq, "Mtr", s["einheiten"]["Mtr"], {"--ziel": "23"}, [], False)


# ---------------------------------------------------------------- M18 (L244)


def test_platoon_fire_books_the_single_action_too(board, quiet):
    s = board
    plt_hq(s)
    s["einheiten"]["1/1"] = unit("22", vof="S", platoon="1", ziel="23")
    s["einheiten"]["Enemy 1"] = unit("23", side="Feind", vof="A", ziel="22")
    commands.cmd_order(s, ["1st PLT HQ", "1st PLT HQ", "4.2.4c", "--success=1/1:yes", "--unit=Enemy 1"])
    assert s["impuls_aktionen"]["1/1"] == ["4.2.4c", "4.2.4b"]
    with pytest.raises(rules.Violation, match="already carried out"):
        commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.4b", "--success=ja", "--unit=Enemy 1"])
    with pytest.raises(rules.Violation, match="No eligible unit"):  # and the other way round
        commands.cmd_order(s, ["1st PLT HQ", "1st PLT HQ", "4.2.4c", "--success=1/1:yes", "--unit=Enemy 1"])


# ---------------------------------------------------------------- LOW (L245 to L250)


def test_concentrate_fire_books_and_names_one_ammo(board, quiet):
    s = board
    plt_hq(s)
    s["einheiten"]["MG"] = unit(
        "22", vof="A", typ="Weapons Team", platoon="1", steps=1, ziel="23", munition={"typ": "MG", "punkte": 4}
    )
    s["einheiten"]["Enemy 1"] = unit("23", side="Feind", vof="A", ziel="22")
    commands.cmd_order(s, ["1st PLT HQ", "MG", "4.2.4b", "--success=ja", "--unit=Enemy 1"])
    assert s["einheiten"]["MG"]["munition"]["punkte"] == 3
    assert "1 ammo" in s["protokoll"][-1]["text"] and "2 ammo" not in s["protokoll"][-1]["text"]


def test_grenade_jam_leaves_no_miss_marker_and_no_exhort(board, quiet):
    s = board
    s["kampagne"] = {}
    plt_hq(s)
    s["einheiten"]["Baz"] = unit(
        "22",
        vof="S",
        rng="C",
        typ="Weapons Team",
        platoon="1",
        steps=1,
        grenade_ranged=True,
        munition={"typ": "RKT", "punkte": 2},
    )
    s["einheiten"]["Enemy 1"] = unit("23", side="Feind", vof="A", ziel="22")
    commands.cmd_order(s, ["1st PLT HQ", "Baz", "4.2.4d", "--target=23", "--success=ja", "--unit=Enemy 1", "--jam=ja"])
    assert "Baz" not in s["einheiten"] and "Fire Team 1" in s["einheiten"]
    assert not s["karten"]["23"].get("grenade_miss") and not s.get("letzter_versuch")
    assert "grenade" not in s["einheiten"]["Enemy 1"]


def test_legacy_unlimited_fire_missions_do_not_crash(board, quiet):
    s = board
    plt_hq(s)
    s["einheiten"]["FO"] = unit("22", vof=None, typ="FO", platoon="1", steps=1)
    s["einheiten"]["Enemy 1"] = unit("23", side="Feind", vof="A", ziel="22")
    s["feuermissionen"] = "unbegrenzt"
    commands.cmd_order(s, ["1st PLT HQ", "FO", "4.2.4i", "--target=23", "--success=ja"])
    assert s["feuermissionen"] == "unbegrenzt"
    assert s["karten"]["23"]["extern"][-1]["typ"] == "Pending"


def test_shift_fire_recipient_need_not_fire(board, quiet):
    s = board
    plt_hq(s)
    s["einheiten"]["1/1"] = unit("22", vof="S", platoon="1", ziel="23")
    s["einheiten"]["Enemy 1"] = unit("23", side="Feind", vof="A", ziel="22")
    s["einheiten"]["Enemy 2"] = unit("32", side="Feind", vof="A", ziel="22")
    commands.cmd_order(s, ["1st PLT HQ", "1st PLT HQ", "4.2.4l", "--target=32"])  # the HQ itself has no VOF
    assert s["einheiten"]["1/1"]["ziel"] == "32"


def test_short_only_forces_success_for_call_for_fire(board, quiet):
    s = board
    plt_hq(s)
    s["einheiten"]["1/1"] = unit("22", platoon="1")
    s["einheiten"]["Enemy 1"] = unit("23", side="Feind", vof="A", ziel="22")
    with pytest.raises(rules.Violation, match="draw"):  # --short no longer skips the draw of an Infiltrate
        commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.2c", "--target=32", "--short=ja"])


def test_stacking_precheck_uses_the_handler_member_set(board, quiet):
    """The old pre-check counted every unexposed unit of the platoon; the handler takes only Good Order units in
    communication. A Pinned 4-step squad therefore no longer blocks a Platoon Move of the others."""
    s = board
    plt_hq(s)
    s["einheiten"]["1/1"] = unit("22", platoon="1", steps=4)
    s["einheiten"]["2/1"] = unit("22", platoon="1", steps=4, status=["Pinned"])
    s["einheiten"]["1/2"] = unit("32", platoon="2", steps=4)
    s["einheiten"]["2/2"] = unit("32", platoon="2", steps=4)
    s["einheiten"]["3/2"] = unit("32", platoon="2", steps=3)  # 11 on the card + 4 + 1 HQ = 16: allowed
    commands.cmd_order(s, ["1st PLT HQ", "1st PLT HQ", "4.2.2b", "--target=32"])
    assert s["einheiten"]["1/1"]["karte"] == "32" and s["einheiten"]["2/1"]["karte"] == "22"
    s["einheiten"]["3/1"] = unit("22", platoon="1", steps=1)
    s["impuls_aktionen"] = {}
    s["kommandos"]["1st PLT HQ"]["verfuegbar"] = 6
    plt_hq(s)  # new HQ on 22 with 3/1: 16 + 1 + 1 = 18
    with pytest.raises(rules.Violation, match="Stacking"):
        commands.cmd_order(s, ["1st PLT HQ", "1st PLT HQ", "4.2.2b", "--target=32"])


# ---------------------------------------------------------------- structure (L252 to L256)


def test_add_cover_marker_returns_the_marker_and_new_cover_marker_the_id(board):
    m = commands.add_cover_marker(board, "22", "Basic Cover", 1)
    assert m == {"id": "C1", "typ": "Basic Cover", "wert": 1, "feld": False}
    assert commands.new_cover_marker(board, "22", "Upper Story", 2) == "C2"
    assert board["karten"]["22"]["cover"][1]["feld"] is True
    assert commands.add_cover_marker(board, "22", "Foxholes", 1, field=False)["feld"] is False


def test_apply_grenade_hits_the_stack_under_cover(board):
    s = board
    s["karten"]["23"]["cover"] = [{"id": "C1", "typ": "Foxholes", "wert": 1}]
    s["einheiten"]["Enemy 1"] = unit("23", side="Feind", bereich="C1")
    s["einheiten"]["Enemy 2"] = unit("23", side="Feind", bereich="C1")
    s["einheiten"]["Enemy 3"] = unit("23", side="Feind")
    prot = []
    stack, under = commands.apply_grenade(s, "Enemy 1", -4, True, prot, "7.10.1")
    assert set(stack) == {"Enemy 1", "Enemy 2"} and under
    assert s["einheiten"]["Enemy 2"]["grenade"] == [-4] and s["einheiten"]["Enemy 2"]["grenade_critical"] is True
    assert "grenade" not in s["einheiten"]["Enemy 3"] and any("Critical Hit" in x for x in prot)
    commands.apply_grenade(s, "Enemy 3", -4, True, prot, "7.10.1")
    assert s["einheiten"]["Enemy 3"]["grenade"] == [-4, -4]


# ---------------------------------------------------------------- follow-ups of the resumed run


def test_pyro_infiltration_by_signal_reads_english_no(board, quiet):
    """H8: the pyro signal parser accepted only 'nein'; '1/1:no' infiltrated without Exposed [RULE 4.4.1 p.30]."""
    s = board
    s["einheiten"]["1/1"] = unit("22")
    s["einheiten"]["2/1"] = unit("22")
    s["einheiten"]["Enemy 1"] = unit("23", side="Feind", vof="A", ziel="22")  # VOF on the origin card (5.1.4)
    prot = []
    commands.follow_signal(s, "InfAP2PO", {"1/1": "32", "2/1": "32"}, {"--erfolg": "1/1:no,2/1:YES"}, prot)
    assert "Exposed" in s["einheiten"]["1/1"]["status"] and "Exposed" not in s["einheiten"]["2/1"]["status"]
    assert s["einheiten"]["1/1"]["karte"] == s["einheiten"]["2/1"]["karte"] == "32"


def test_attempt_text_normalizes_english_per_unit_results():
    assert commands.attempt_text("1/1:yes,2/1:no") == "1/1 successful, 2/1 failed"
    assert commands.attempt_text("ja") == "successful"


def test_bare_flag_where_a_value_is_needed_is_a_violation(board, quiet):
    s = board
    plt_hq(s)
    s["einheiten"]["1/1"] = unit("22", platoon="1")
    with pytest.raises(rules.Violation, match="needs a value"):
        commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.2h", "--what"])
    s["phase"] = "3.3.2d"
    with pytest.raises(rules.Violation):
        commands.cmd_gi(s, ["5", "--3"])


def test_grenade_target_checked_before_ammo_is_spent(board, quiet):
    """M11: a wrong --unit used to be refused only after the ranged attack had spent its ammo."""
    s = board
    s["kampagne"] = {}
    plt_hq(s)
    s["einheiten"]["Baz"] = unit(
        "22",
        vof="S",
        rng="C",
        typ="Weapons Team",
        platoon="1",
        steps=1,
        grenade_ranged=True,
        munition={"typ": "RKT", "punkte": 2},
    )
    s["einheiten"]["Enemy 1"] = unit("23", side="Feind", vof="A", ziel="22")
    ctx = commands.order_context(
        s, "1st PLT HQ", "Baz", "4.2.4d", {"--ziel": "23", "--erfolg": "ja", "--einheit": "1st PLT HQ"}, None
    )
    with pytest.raises(rules.Violation, match="not an opposing unit"):
        commands._order_grenade_attack(s, ctx)
    assert s["einheiten"]["Baz"]["munition"]["punkte"] == 2
