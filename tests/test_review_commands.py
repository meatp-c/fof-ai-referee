"""Fixes of the code review of 23.10.2026 in commands.py (L230 to L257), one test per fix on the synthetic board."""

import pytest
from conftest import unit

from fof import briefing, commands, rules, state
from fof import fire_support  # L556: split from commands
from fof import grenades  # L556: split from commands
from fof import pyro  # L556: split from commands


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protocol"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)


def plt_hq(board, name="1st PLT HQ", card_id="22", platoon="1", available=6):
    board["commands"][name] = {"available": available, "saved": 0, "activated": True, "done": False}
    board["units"][name] = unit(card_id, vof=None, type="HQ", level="PLT", platoon=platoon, steps=1)
    board["active_hq"] = name
    return board["units"][name]


# ---------------------------------------------------------------- H8 (L230)


def test_parse_per_unit_accepts_english_and_german():
    assert commands.parse_per_unit("1/1:yes,2/1:no, MG:JA ,1st PLT HQ:Nein") == {
        "1/1": "yes",
        "2/1": "no",
        "MG": "yes",
        "1st PLT HQ": "no",
    }
    assert commands.parse_per_unit(None) == {} and commands.parse_per_unit("yes") == {}
    with pytest.raises(rules.Violation, match="yes or no"):
        commands.parse_per_unit("1/1:maybe")


def test_platoon_infiltrate_marks_exposed_with_english_no(board, quiet):
    """H8: '2/1:no' used to be read as a success, so the unit infiltrated without Exposed [RULE 4.2.2d, 5.1.4]."""
    s = board
    plt_hq(s)
    s["units"]["1/1"] = unit("22", platoon="1")
    s["units"]["2/1"] = unit("22", platoon="1")
    s["units"]["Enemy 1"] = unit("23", side="Enemy", vof="A", target="22")  # VOF on the origin card (5.1.4)
    commands.cmd_order(
        s, ["1st PLT HQ", "1st PLT HQ", "4.2.2d", "--target=32", "--success=1st PLT HQ:yes,1/1:yes,2/1:no"]
    )
    assert s["units"]["2/1"]["card"] == "32" and "Exposed" in s["units"]["2/1"]["status"]
    assert "Exposed" not in s["units"]["1/1"]["status"]


# ---------------------------------------------------------------- H9 (L231)


def test_grenade_response_lapsed_record_does_not_block_newer(board, quiet):
    s = board
    s["turn"] = 3
    s["units"]["Enemy 1"] = unit("22", side="Enemy", vof="S", target="22")
    s["units"]["1/1"] = unit("22", vof="S", target="22")
    s["grenade_responses"] = [
        {
            "launcher": "Enemy 1",
            "attacker": "Gone Team",
            "card": "22",
            "turn": 3,
            "phase": "3.3.1b",
        },  # attacker removed
        {"launcher": "Enemy 1", "attacker": "1/1", "card": "22", "turn": 2, "phase": "3.3.1b"},  # earlier turn
        {"launcher": "Enemy 1", "attacker": "1/1", "card": "22", "turn": 3, "phase": "3.3.1b"},
    ]
    with pytest.raises(rules.Violation, match="free response throw at 1/1"):
        grenades.cmd_grenade(s, ["response", "Enemy 1"])
    grenades.cmd_grenade(s, ["response", "Enemy 1", "--success=yes"])
    assert s["units"]["1/1"]["grenade"] == [rules.GRENADE_VOF_DEFAULT] and s["grenade_responses"] == []


def test_grenade_response_record_carries_turn_and_phase(board, quiet):
    s = board
    plt_hq(s)
    s["units"]["1/1"] = unit("22", vof="S", platoon="1", target="22")
    s["units"]["Enemy 1"] = unit("22", side="Enemy", vof="S", target="22")
    commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.4d", "--success=yes", "--unit=Enemy 1"])
    rec = s["grenade_responses"][0]
    assert rec["turn"] == s["turn"] and rec["phase"] == s["phase"] and rec["attacker"] == "1/1"


# ---------------------------------------------------------------- H12, M14 (L232, L233)


def test_handlers_refuse_missing_or_bad_arguments(board):
    s = board
    s["units"]["1/1"] = unit("22")
    s["units"]["CO HQ"] = unit("22", vof=None, type="HQ", level="CO", steps=1)
    s["commands"]["CO HQ"] = {"available": 2, "saved": 0, "activated": True, "done": False}
    for handler, args in (
        (commands.cmd_activate, []),
        (commands.cmd_hq, []),
        (commands.cmd_order, ["CO HQ", "1/1"]),
        (commands.cmd_fire, ["1/1"]),
        (grenades.cmd_grenade, ["response"]),
        (commands.cmd_correct, ["ammo", "1/1"]),
        (commands.cmd_correct, ["status", "1/1", "Pinned"]),
        (commands.cmd_correct, ["grenade", "1/1", "expired"]),
    ):
        with pytest.raises(rules.Violation):
            handler(s, args)
    s["units"]["1/1"]["ammo"] = {"type": "MG", "points": 3, "start": 6}
    with pytest.raises(rules.Violation, match="whole number"):
        commands.cmd_correct(s, ["ammo", "1/1", "x", "--reason=test"])
    with pytest.raises(rules.Violation, match="whole number"):
        commands.cmd_correct(s, ["casualty", "22", "two", "--reason=test"])
    with pytest.raises(rules.Violation, match="not an HQ"):  # M14: hq <squad> was a KeyError
        commands.cmd_hq(s, ["1/1"])


# ---------------------------------------------------------------- M7 (L234)


def test_impulse_cap_checked_before_draw_prompt(board):
    s = board
    plt_hq(s, available=4)
    s["impulse_spent"] = {"1st PLT HQ": 6}
    s["units"]["Enemy 1"] = unit("23", side="Enemy", spotted=False)
    with pytest.raises(rules.Violation) as ex:
        commands.cmd_order(s, ["1st PLT HQ", "1st PLT HQ", "4.2.4a", "--target=23"])
    assert "per impulse" in str(ex.value) and "draw" not in str(ex.value)
    s["units"]["Runner 1"] = unit("22", type="Runner", steps=1)
    s["runner_box"] = ["Runner 1"]
    s["co_hq"] = "1st PLT HQ"
    s["campaign"] = {}
    with pytest.raises(rules.Violation, match="per impulse"):
        commands.cmd_order(s, ["1st PLT HQ", "Runner 1", "4.2.1g", "--target=1st PLT HQ"])


# ---------------------------------------------------------------- M8 (L235)


def test_platoon_infiltrate_checks_every_member_before_the_draw(board, quiet):
    s = board
    plt_hq(s)
    s["units"]["1/1"] = unit("22", platoon="1")
    s["units"]["Enemy 1"] = unit("23", side="Enemy", vof="A", target="22")
    s["units"]["1/1"]["mine_hit"] = True  # one member may not move this turn [RULE 7.9.1]
    with pytest.raises(rules.Violation) as ex:
        commands.cmd_order(s, ["1st PLT HQ", "1st PLT HQ", "4.2.2d", "--target=32"])
    assert "Mine marker" in str(ex.value) and "draws itself" not in str(ex.value)


# ---------------------------------------------------------------- M9 (L236)


def test_bn_on_board_activation_refuses_duplicate_and_fire_team_side(board, quiet):
    s = board
    s["phase"] = "3.3.1a"
    s["active_hq"] = "BN HQ"
    s["units"]["BN HQ"] = unit("22", vof=None, type="HQ", level="BN", steps=1)
    s["units"]["CO HQ"] = unit("22", vof=None, type="HQ", level="CO", steps=1)
    s["commands"]["BN HQ"] = {"available": 4, "saved": 0, "activated": True, "done": False}
    s["commands"]["CO HQ"] = {"available": 0, "saved": 0, "activated": False, "done": False}
    commands.cmd_activate(s, ["CO HQ"])
    assert s["commands"]["BN HQ"]["available"] == 3
    with pytest.raises(rules.Violation, match="already activated"):
        commands.cmd_activate(s, ["CO HQ"])
    assert s["commands"]["BN HQ"]["available"] == 3
    s["commands"]["CO HQ"]["activated"] = False
    s["units"]["CO HQ"]["status"].append("Fire Team side")
    with pytest.raises(rules.Violation, match="Fire Team side"):
        commands.cmd_activate(s, ["CO HQ"])


# ---------------------------------------------------------------- M10 (L237)


def test_supplement_and_reconstitute_remove_teams_via_remove_from_play(board, quiet):
    s = board
    plt_hq(s)
    s["units"]["1/1"] = unit("22", platoon="1", steps=2)
    s["units"]["Fire Team 1"] = unit("22", type="Fire Team", platoon="1", steps=1, carries_casualties=1)
    commands.cmd_order(s, ["1st PLT HQ", "Fire Team 1", "4.2.3h", "--squad=1/1"])
    assert "Fire Team 1" not in s["units"] and "Fire Team 1" in s["removed_from_play"]
    assert s["units"]["1/1"]["steps"] == 3 and s["cards"]["22"]["casualties"] == 1  # casualty back on the card
    s["removed_from_play"].append("2/1")
    s["units"]["Fire Team 2"] = unit("22", type="Fire Team", platoon="1", steps=1)
    s["units"]["Assault Team 1"] = unit("22", type="Assault Team", platoon="1", steps=1, assets=["Rifle Grenade"])
    commands.cmd_order(
        s, ["1st PLT HQ", "Fire Team 2", "4.2.3i", "--squad=2/1", "--with=Assault Team 1", "--success=yes"]
    )
    assert s["units"]["2/1"]["steps"] == 2
    assert {"Fire Team 2", "Assault Team 1"} <= set(s["removed_from_play"])
    assert s["cards"]["22"]["assets_ground"] == ["Rifle Grenade"]


# ---------------------------------------------------------------- M11 (L238)


def test_grenade_unit_must_be_a_spotted_enemy_on_the_target_card(board, quiet):
    s = board
    plt_hq(s)
    s["units"]["1/1"] = unit("22", vof="S", platoon="1", target="22")
    s["units"]["2/1"] = unit("22", vof="S", platoon="1", target="22")
    s["units"]["Enemy 1"] = unit("22", side="Enemy", vof="S", target="22")
    s["units"]["Enemy 2"] = unit("23", side="Enemy", vof="S", target="22")
    with pytest.raises(rules.Violation, match="not an opposing unit on the target card"):
        commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.4d", "--success=yes", "--unit=2/1"])
    with pytest.raises(rules.Violation, match="not an opposing unit on the target card"):
        commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.4d", "--success=yes", "--unit=Enemy 2"])
    assert "grenade" not in s["units"]["2/1"] and "grenade" not in s["units"]["Enemy 2"]
    s["units"]["Enemy 3"] = unit("22", side="Enemy", vof="S", target="22", spotted=False)
    with pytest.raises(rules.Violation, match="Unspotted"):
        commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.4d", "--success=yes", "--unit=Enemy 3"])


# ---------------------------------------------------------------- M12 (L239)


def test_pick_up_comma_list_with_ammo_and_casualty(board, quiet):
    s = board
    plt_hq(s)
    s["units"]["MG"] = unit("22", vof="A", type="Weapons Team", platoon="1", steps=2, ammo={"type": "MG", "points": 2})
    s["cards"]["22"].update(ammo={"MG": 3}, casualties=2, line_assets=1)
    commands.cmd_order(s, ["1st PLT HQ", "MG", "4.2.2h", "--what=MG:2,Casualty:1,Leitung:1"])
    mg = s["units"]["MG"]
    assert mg["ammo"]["points"] == 4 and s["cards"]["22"]["ammo"]["MG"] == 1
    assert mg["carries_casualties"] == 1 and s["cards"]["22"]["casualties"] == 1
    assert mg["lines"] == 1 and s["cards"]["22"]["line_assets"] == 0
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
    s["units"]["1/1"] = unit("22", platoon="1", steps=3)
    commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.3g", "--team=fire"])
    assert s["units"]["Fire Team 1"]["type"] == "Fire Team" and s["units"]["1/1"]["steps"] == 2


# ---------------------------------------------------------------- M15 (L241)


def test_event_fulfilled_line_reaches_the_protocol_once(board, quiet):
    s = board
    s["campaign"] = {}
    s["event_flank"] = {"id": "company_ahead", "turn": 1, "row": 1}
    plt_hq(s, card_id="12")
    s["units"]["1/1"] = unit("12", platoon="1")
    commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.2a", "--target=22", "--area=open", "--plain=yes"])
    text = s["protocol"][-1]["text"]
    assert text.count("fulfilled") == 1 and s["event_flank"]["fulfilled"] is True
    s["event_flank"] = {"id": "company_ahead", "turn": 1, "row": 1}
    commands.event_move_check(s, s["units"]["1st PLT HQ"], "22")
    assert "fulfilled" not in s["event_flank"]  # the check-only call leaves the flag to move_unit


# ---------------------------------------------------------------- M16 (L242)


def test_gi_plt_hq_may_originate_its_own_platoon_move(board, quiet):
    s = board
    s["phase"] = "3.3.2d"
    plt_hq(s)
    s["active_hq"] = "GI"
    s["commands"]["GI"] = {"available": 4, "saved": 0, "activated": False, "done": False}
    s["units"]["1/1"] = unit("22", platoon="1")
    with pytest.raises(rules.Violation, match="needs the responsible HQ as originator"):
        commands.cmd_order(s, ["GI", "1/1", "4.2.2b", "--target=32"])
    commands.cmd_order(s, ["GI", "1st PLT HQ", "4.2.2b", "--target=32", "--originator=1st PLT HQ"])
    assert s["units"]["1/1"]["card"] == "32" and s["units"]["1st PLT HQ"]["card"] == "32"
    assert s["commands"]["GI"]["available"] == 2


# ---------------------------------------------------------------- M17 (L243)


def test_second_indirect_lay_on_the_same_mortar_is_refused(board):
    s = board
    hq = unit("22", vof=None, type="HQ", level="PLT", platoon="1", steps=1)
    s["units"]["1st PLT HQ"] = hq
    s["units"]["Mtr"] = unit("22", vof="H", type="Weapons Team", platoon="1", steps=2, mortar=True)
    s["cards"]["23"]["external"].append({"type": "Indirect", "value": -3, "source": "Mtr", "side": "US"})
    with pytest.raises(rules.Violation, match="already fires an Indirect Lay"):
        fire_support.indirect_lay(s, "1st PLT HQ", hq, "Mtr", s["units"]["Mtr"], {"--target": "23"}, [], False)


# ---------------------------------------------------------------- M18 (L244)


def test_platoon_fire_books_the_single_action_too(board, quiet):
    s = board
    plt_hq(s)
    s["units"]["1/1"] = unit("22", vof="S", platoon="1", target="23")
    s["units"]["Enemy 1"] = unit("23", side="Enemy", vof="A", target="22")
    commands.cmd_order(s, ["1st PLT HQ", "1st PLT HQ", "4.2.4c", "--success=1/1:yes", "--unit=Enemy 1"])
    assert s["impulse_actions"]["1/1"] == ["4.2.4c", "4.2.4b"]
    with pytest.raises(rules.Violation, match="already carried out"):
        commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.4b", "--success=yes", "--unit=Enemy 1"])
    with pytest.raises(rules.Violation, match="No eligible unit"):  # and the other way round
        commands.cmd_order(s, ["1st PLT HQ", "1st PLT HQ", "4.2.4c", "--success=1/1:yes", "--unit=Enemy 1"])


# ---------------------------------------------------------------- LOW (L245 to L250)


def test_concentrate_fire_books_and_names_one_ammo(board, quiet):
    s = board
    plt_hq(s)
    s["units"]["MG"] = unit(
        "22", vof="A", type="Weapons Team", platoon="1", steps=1, target="23", ammo={"type": "MG", "points": 4}
    )
    s["units"]["Enemy 1"] = unit("23", side="Enemy", vof="A", target="22")
    commands.cmd_order(s, ["1st PLT HQ", "MG", "4.2.4b", "--success=yes", "--unit=Enemy 1"])
    assert s["units"]["MG"]["ammo"]["points"] == 3
    assert "1 ammo" in s["protocol"][-1]["text"] and "2 ammo" not in s["protocol"][-1]["text"]


def test_grenade_jam_leaves_no_miss_marker_and_no_exhort(board, quiet):
    s = board
    s["campaign"] = {}
    plt_hq(s)
    s["units"]["Baz"] = unit(
        "22",
        vof="S",
        rng="C",
        type="Weapons Team",
        platoon="1",
        steps=1,
        grenade_ranged=True,
        ammo={"type": "RKT", "points": 2},
    )
    s["units"]["Enemy 1"] = unit("23", side="Enemy", vof="A", target="22")
    commands.cmd_order(
        s, ["1st PLT HQ", "Baz", "4.2.4d", "--target=23", "--success=yes", "--unit=Enemy 1", "--jam=yes"]
    )
    assert "Baz" not in s["units"] and "Fire Team 1" in s["units"]
    assert not s["cards"]["23"].get("grenade_miss") and not s.get("last_attempt")
    assert "grenade" not in s["units"]["Enemy 1"]


def test_legacy_unlimited_fire_missions_do_not_crash(board, quiet):
    s = board
    plt_hq(s)
    s["units"]["FO"] = unit("22", vof=None, type="FO", platoon="1", steps=1)
    s["units"]["Enemy 1"] = unit("23", side="Enemy", vof="A", target="22")
    s["fire_missions"] = "unlimited"
    commands.cmd_order(s, ["1st PLT HQ", "FO", "4.2.4i", "--target=23", "--success=yes"])
    assert s["fire_missions"] == "unlimited"
    assert s["cards"]["23"]["external"][-1]["type"] == "Pending"


def test_shift_fire_recipient_need_not_fire(board, quiet):
    s = board
    plt_hq(s)
    s["units"]["1/1"] = unit("22", vof="S", platoon="1", target="23")
    s["units"]["Enemy 1"] = unit("23", side="Enemy", vof="A", target="22")
    s["units"]["Enemy 2"] = unit("32", side="Enemy", vof="A", target="22")
    commands.cmd_order(s, ["1st PLT HQ", "1st PLT HQ", "4.2.4l", "--target=32"])  # the HQ itself has no VOF
    assert s["units"]["1/1"]["target"] == "32"


def test_short_only_forces_success_for_call_for_fire(board, quiet):
    s = board
    plt_hq(s)
    s["units"]["1/1"] = unit("22", platoon="1")
    s["units"]["Enemy 1"] = unit("23", side="Enemy", vof="A", target="22")
    with pytest.raises(rules.Violation, match="draw"):  # --short no longer skips the draw of an Infiltrate
        commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.2c", "--target=32", "--short=yes"])


def test_stacking_precheck_uses_the_handler_member_set(board, quiet):
    """The old pre-check counted every unexposed unit of the platoon; the handler takes only Good Order units in
    communication. A Pinned 4-step squad therefore no longer blocks a Platoon Move of the others."""
    s = board
    plt_hq(s)
    s["units"]["1/1"] = unit("22", platoon="1", steps=4)
    s["units"]["2/1"] = unit("22", platoon="1", steps=4, status=["Pinned"])
    s["units"]["1/2"] = unit("32", platoon="2", steps=4)
    s["units"]["2/2"] = unit("32", platoon="2", steps=4)
    s["units"]["3/2"] = unit("32", platoon="2", steps=3)  # 11 on the card + 4 + 1 HQ = 16: allowed
    commands.cmd_order(s, ["1st PLT HQ", "1st PLT HQ", "4.2.2b", "--target=32"])
    assert s["units"]["1/1"]["card"] == "32" and s["units"]["2/1"]["card"] == "22"
    s["units"]["3/1"] = unit("22", platoon="1", steps=1)
    s["impulse_actions"] = {}
    s["commands"]["1st PLT HQ"]["available"] = 6
    plt_hq(s)  # new HQ on 22 with 3/1: 16 + 1 + 1 = 18
    with pytest.raises(rules.Violation, match="Stacking"):
        commands.cmd_order(s, ["1st PLT HQ", "1st PLT HQ", "4.2.2b", "--target=32"])


# ---------------------------------------------------------------- structure (L252 to L256)


def test_add_cover_marker_returns_the_marker_and_new_cover_marker_the_id(board):
    m = commands.add_cover_marker(board, "22", "Basic Cover", 1)
    assert m == {"id": "C1", "type": "Basic Cover", "value": 1, "field": False}
    assert commands.new_cover_marker(board, "22", "Upper Story", 2) == "C2"
    assert board["cards"]["22"]["cover"][1]["field"] is True
    assert commands.add_cover_marker(board, "22", "Foxholes", 1, field=False)["field"] is False


def test_apply_grenade_hits_the_stack_under_cover(board):
    s = board
    s["cards"]["23"]["cover"] = [{"id": "C1", "type": "Foxholes", "value": 1}]
    s["units"]["Enemy 1"] = unit("23", side="Enemy", area="C1")
    s["units"]["Enemy 2"] = unit("23", side="Enemy", area="C1")
    s["units"]["Enemy 3"] = unit("23", side="Enemy")
    prot = []
    stack, under = grenades.apply_grenade(s, "Enemy 1", -4, True, prot, "7.10.1")
    assert set(stack) == {"Enemy 1", "Enemy 2"} and under
    assert s["units"]["Enemy 2"]["grenade"] == [-4] and s["units"]["Enemy 2"]["grenade_critical"] is True
    assert "grenade" not in s["units"]["Enemy 3"] and any("Critical Hit" in x for x in prot)
    grenades.apply_grenade(s, "Enemy 3", -4, True, prot, "7.10.1")
    assert s["units"]["Enemy 3"]["grenade"] == [-4, -4]


# ---------------------------------------------------------------- follow-ups of the resumed run


def test_pyro_infiltration_by_signal_reads_english_no(board, quiet):
    """H8: the pyro signal parser accepted only 'no'; '1/1:no' infiltrated without Exposed [RULE 4.4.1 p.30]."""
    s = board
    s["units"]["1/1"] = unit("22")
    s["units"]["2/1"] = unit("22")
    s["units"]["Enemy 1"] = unit("23", side="Enemy", vof="A", target="22")  # VOF on the origin card (5.1.4)
    prot = []
    pyro.follow_signal(s, "InfAP2PO", {"1/1": "32", "2/1": "32"}, {"--success": "1/1:no,2/1:YES"}, prot)
    assert "Exposed" in s["units"]["1/1"]["status"] and "Exposed" not in s["units"]["2/1"]["status"]
    assert s["units"]["1/1"]["card"] == s["units"]["2/1"]["card"] == "32"


def test_attempt_text_normalizes_english_per_unit_results():
    assert commands.attempt_text("1/1:yes,2/1:no") == "1/1 successful, 2/1 failed"
    assert commands.attempt_text("yes") == "successful"


def test_bare_flag_where_a_value_is_needed_is_a_violation(board, quiet):
    s = board
    plt_hq(s)
    s["units"]["1/1"] = unit("22", platoon="1")
    with pytest.raises(rules.Violation, match="needs a value"):
        commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.2h", "--what"])
    s["phase"] = "3.3.2d"
    with pytest.raises(rules.Violation):
        commands.cmd_gi(s, ["5", "--3"])


def test_grenade_target_checked_before_ammo_is_spent(board, quiet):
    """M11: a wrong --unit used to be refused only after the ranged attack had spent its ammo."""
    s = board
    s["campaign"] = {}
    plt_hq(s)
    s["units"]["Baz"] = unit(
        "22",
        vof="S",
        rng="C",
        type="Weapons Team",
        platoon="1",
        steps=1,
        grenade_ranged=True,
        ammo={"type": "RKT", "points": 2},
    )
    s["units"]["Enemy 1"] = unit("23", side="Enemy", vof="A", target="22")
    ctx = commands.order_context(
        s, "1st PLT HQ", "Baz", "4.2.4d", {"--target": "23", "--success": "yes", "--unit": "1st PLT HQ"}, None
    )
    with pytest.raises(rules.Violation, match="not an opposing unit"):
        grenades.order_grenade_attack(s, ctx)
    assert s["units"]["Baz"]["ammo"]["points"] == 2
