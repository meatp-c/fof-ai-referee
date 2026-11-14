"""Fixes collected during Naktong Mission 1 (rulings K48, K49 and the gap list of that game)."""

import pytest

from conftest import unit

from fof import briefing, campaign, combat, commands, comms, enemy, events, fire, fire_support, phase, rules, state


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protocol"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)


def _hq(platoon):
    return {"side": "US", "type": "HQ", "level": "PLT", "platoon": platoon, "card": None, "status": [], "steps": 1}


def test_unit_on_its_fire_team_side_takes_orders_from_any_hq(board):
    """K48: a weapons team flipped to its Fire Team side is a LAT (4.0 p.18) until it is back on its front side."""
    team = {"side": "US", "type": "Weapons Team", "platoon": None, "card": None, "status": [], "steps": 1}
    board["units"].update({"1st PLT HQ": _hq("1"), "1/75mm RCL": team})
    with pytest.raises(rules.Violation):
        comms.chain_of_command(board, "1st PLT HQ", "1/75mm RCL")
    team["status"].append(rules.FIRE_TEAM_SIDE)
    assert comms.chain_of_command(board, "1st PLT HQ", "1/75mm RCL")


def test_gi_skill_any_time_in_the_gi_impulse(board, quiet):
    """K49 (BGG 3597449): the General Initiative skill may be used after the draw and after other GI Commands."""
    board["phase"] = "3.3.2d"
    board["units"]["1st PLT HQ"] = dict(_hq("1"), card="11", skills=["General Initiative"])
    with pytest.raises(rules.Violation, match="after the draw"):
        commands.cmd_gi(board, ["skill", "1st PLT HQ"])
    commands.cmd_gi(board, ["?", "1"])
    commands.cmd_done(board, [])
    commands.cmd_gi(board, ["skill", "1st PLT HQ"])
    assert board["commands"]["GI"]["available"] == 1 and board["active_hq"] == "GI"
    assert board["units"]["1st PLT HQ"]["skills"] == []
    with pytest.raises(rules.Violation, match="does not hold"):
        commands.cmd_gi(board, ["skill", "1st PLT HQ"])


def test_staff_initiative_command_is_granted_once(board, quiet):
    """3.3.2c p.16: a second 'hq' call of the same CO Staff in the impulse grants no further Command."""
    board["phase"] = "3.3.2c"
    board["units"]["CO XO"] = {"side": "US", "type": "Staff", "card": "11", "status": [], "steps": 1}
    board["commands"]["CO XO"] = {"available": 0, "saved": 0, "activated": False, "done": False}
    commands.cmd_hq(board, ["CO XO"])
    assert board["commands"]["CO XO"]["available"] == 1
    board["commands"]["CO XO"]["available"] = 0  # spent
    commands.cmd_hq(board, ["CO XO"])
    assert board["commands"]["CO XO"]["available"] == 0


def test_grenaded_enemy_falling_back_off_map_leaves_a_grenade_miss(board, quiet):
    """7.10.4 p.55: a target that moves before the Combat Effects Segment turns the hit into a Grenade Miss."""
    board["units"]["G"] = e = unit("31", side="Enemy", grenade=[-4])
    ctx = enemy.EnemyActionCtx(a="fall back", action="Fall Back", e=e, n="G", o={"--target": "off-map"})
    enemy._enemy_fall_back(board, ctx)
    assert "G" not in board["units"] and board["cards"]["31"]["grenade_miss"]
    assert any("becomes Grenade Miss" in line for line in ctx.prot)


def test_us_unit_in_a_deep_bunker_places_no_vof(board):
    """CSR Deep Bunkers: 'the units inside do not exert a VOF and may not Spot, deploy pyrotechnics or make Grenade
    Attacks' holds for both sides."""
    board["cards"]["21"]["cover"] = [{"id": "C1", "type": "Deep Bunker", "value": 5, "field": True}]
    board["units"]["1/1"] = e = unit("21", target="31")
    commands.set_area(board, e, "C1")
    assert e["target"] is None and not fire.can_fire(e)
    for action_id in ("4.2.4a", "4.2.4b", "4.2.4d", "4.2.1c"):
        with pytest.raises(rules.Violation, match="Deep Bunker"):
            comms.action_allowed(e, "1/1", action_id)
    comms.action_allowed(e, "1/1", "4.2.2f")
    commands.set_area(board, e, "open")
    assert fire.can_fire(e) and "deep_bunker" not in e


def test_xp_promote_takes_the_unit_level_from_table_12_6(board, quiet):
    """12.6 p.82: one promoted step of three does not lift the unit (L+G+G is Green), the second does (L+L+G)."""
    board.update(campaign={"attempt": 1}, mission_end=True, xp=[{"turn": 1, "attempt": 1, "points": 9, "reason": "t"}])
    board["units"]["1/1"] = e = unit("11", experience="Green")
    campaign.cmd_xp(board, ["promote", "1/1", "--from=Green"])
    assert e["experience"] == "Green" and board["promoted"]["1/1"] == 1
    campaign.cmd_xp(board, ["promote", "1/1", "--from=Green"])
    assert e["experience"] == "Line"
    campaign.cmd_xp(board, ["promote", "1/1", "--from=Green"])
    assert e["experience"] == "Line"
    board["units"]["2/1"] = e2 = unit("11", experience="Veteran")
    with pytest.raises(rules.Violation, match="--result"):
        campaign.cmd_xp(board, ["promote", "2/1", "--from=Green"])
    assert e2["experience"] == "Veteran"


def test_marker_changes_name_a_vof_that_goes_beneath_the_top_marker(board):
    """6.2.2: the strongest VOF is the marker; a weaker one beneath it that ends is announced too."""
    import copy

    board["cards"]["21"]["external"] = [{"type": "Incoming", "value": -4, "source": "81mm HE"}]
    board["units"]["G"] = unit("31", side="Enemy", target="21")
    new = copy.deepcopy(board)
    new["units"]["G"]["target"] = None
    lines = state.marker_changes(board, new)
    assert any(x.startswith("21: beneath the Incoming") and "Small Arms +0 (G) no longer applies" in x for x in lines)
    assert any("now applies as well" in x for x in state.marker_changes(new, board))


def test_fall_back_names_the_priority_card(board, quiet, monkeypatch):
    """8.6.3 p.66: one card left by the priorities is taken without --target; a tie asks for R# among the tied cards."""
    board["units"]["G"] = e = unit("21", side="Enemy")
    monkeypatch.setattr(enemy, "fall_back_candidates", lambda s, e: ["31", "32"])
    ctx = enemy.EnemyActionCtx(a="fall back", action="Fall Back", e=e, n="G", o={})
    with pytest.raises(rules.Violation, match="tie between 31, 32, draw R# column 2"):
        enemy._enemy_fall_back(board, ctx)
    monkeypatch.setattr(enemy, "fall_back_candidates", lambda s, e: ["31"])
    enemy._enemy_fall_back(board, ctx)
    assert e["card"] == "31"


def test_call_for_fire_prompt_names_friendly_fire_and_the_short_card(board):
    """7.16.4 p.59: a Short lands one card closer to the observer; own units there or on the target are named."""
    board["units"].update({"FO": unit("11"), "1/1": unit("21"), "AT": unit("31")})
    note = fire_support.cff_friendly_fire(board, board["units"]["FO"], "31")
    assert "own units on 31 (AT)" in note and "a Short lands on 21, on own units (1/1)" in note
    assert fire_support.cff_friendly_fire(board, board["units"]["FO"], "11").endswith("random adjacent card [7.16.4]")


def test_cover_marker_id_names_the_grenade_or_fire_target(board):
    """7.10.1 p.54: the target is a unit or the stack under a Cover marker; --unit takes the marker id as well."""
    board["units"].update(
        {"G1": unit("21", side="Enemy", spotted=True, area="C1"), "G2": unit("21", side="Enemy", spotted=False)}
    )
    assert commands.named_target(board, "21", "C1") == "G1"
    assert commands.named_target(board, "21", None) == "G1"  # the only Spotted enemy
    assert commands.named_target(board, "21", "G2") == "G2"


def test_new_team_is_named_by_card_at_once(board):
    board["lat_names"] = "card"
    board["units"]["AT 21"] = unit("21", type="Assault Team", steps=1)
    assert commands.new_name(board, "Assault Team", side="US", card="21") == "AT 21b"
    assert commands.new_name(board, "Fire Team", side="US", card="21") == "FT 21"
    board["enemy_prefix"] = "NKPA"
    assert commands.new_name(board, "Paralyzed Team", side="Enemy", card="31") == "NKPA P 31"
    board["lat_names"] = None
    assert commands.new_name(board, "Assault Team", side="US", card="21") == "Assault Team 1"


def test_gi_skill_command_serves_the_holders_platoon_only(board):
    """12.7 p.82: a PLT HQ's skill is used by units of that platoon, a CO HQ's or Staff's only by that unit."""
    import types

    board["units"].update(
        {"1st PLT HQ": dict(_hq("1"), card="11"), "1/1": unit("11", platoon="1"), "1/2": unit("11", platoon="2")}
    )
    board["commands"]["GI"] = {
        "available": 1,
        "saved": 0,
        "activated": True,
        "done": False,
        "skill_for": ["1st PLT HQ"],
    }

    def order(name):
        return types.SimpleNamespace(recipient=board["units"][name], target_name=name, cost=1)

    with pytest.raises(rules.Violation, match="skill of 1st PLT HQ"):
        commands.gi_skill_scope(board, order("1/2"))
    board["commands"]["GI"]["available"] = 2  # one ordinary GI Command besides the skill's
    commands.gi_skill_scope(board, order("1/2"))
    assert board["commands"]["GI"]["skill_for"] == ["1st PLT HQ"]
    commands.gi_skill_scope(board, order("1/1"))
    assert board["commands"]["GI"]["skill_for"] == []


def test_open_flank_event_is_named_at_the_start_of_an_impulse(board):
    board["event_flank"] = {"id": "screaming", "turn": 1, "row": 2}
    assert "still open" in events.open_flank_note(board) and "PC marker" in events.open_flank_note(board)
    board["event_flank"]["fulfilled"] = True
    assert events.open_flank_note(board) is None


def _reconstitute_board(board):
    board["packages"] = {
        "2": {
            "units": [
                {
                    "unit_choice": ["1/Gp", "2/Gp"],
                    "type": "Squad",
                    "vof_rating": "A",
                    "steps": 3,
                    "last_step": "Fire Team",
                }
            ]
        }
    }
    board.update(countermix={"1/Gp": 1, "2/Gp": 1}, counter_vof={"1/Gp": "A", "2/Gp": "S"}, removed_from_play=[])
    team = dict(side="Enemy", type="Fire Team", steps=1, rng="C", spotted=True)
    board["units"].update(
        {
            "Fire Team 1": unit("21", vof="A", **team),
            "Fire Team 2": unit("21", vof="S", **team),
            "Leader": unit("21", side="Enemy", vof=None, type="HQ", steps=1, leader=True, experience="Line"),
        }
    )
    return board["units"]["Fire Team 1"]


def test_enemy_teams_with_a_leader_reconstitute_within_their_firepower(board, quiet):
    """6.5.2 p.49: an A-rated and an S-rated Fire Team may become an A-rated squad, two S-rated ones only an S-rated
    one; the Enemy Activity Chart gives the result only with a Leader, and only while a counter is free."""
    e = _reconstitute_board(board)
    assert enemy.reconstitute_choices(board, e) == ["1/Gp", "2/Gp"]
    e["vof_rating"] = "S"
    assert enemy.reconstitute_choices(board, e) == ["2/Gp"]
    board["units"]["Leader"]["status"].append(rules.PINNED)
    assert enemy.reconstitute_choices(board, e) == []
    board["units"]["Leader"]["status"].clear()
    e["vof_rating"] = "A"
    ctx = enemy.EnemyActionCtx(a="attempt to reconstitute squad", action=enemy.REC, e=e, n="Fire Team 1", o={})
    with pytest.raises(rules.Violation, match="2 cards .* of the Leader"):
        enemy._enemy_reconstitute(board, ctx)
    ctx.o = {"--success": "yes"}
    with pytest.raises(rules.Violation, match="R# column 2: 1 = 1/Gp, 2 = 2/Gp"):
        enemy._enemy_reconstitute(board, ctx)
    ctx.o["--type"] = "1/Gp"
    enemy._enemy_reconstitute(board, ctx)
    squads = {n: x for n, x in board["units"].items() if x["type"] == "Squad"}
    assert "Fire Team 1" not in board["units"] and "Fire Team 2" not in board["units"] and len(squads) == 1
    sq = next(iter(squads.values()))
    assert (sq["type_name"], sq["steps"], sq["vof_rating"], sq["experience"]) == ("1/Gp", 2, "A", "Green")


def test_activity_chart_row_reconstitute_needs_the_leader(board):
    e = _reconstitute_board(board)
    assert enemy.enemy_row(board, "Fire Team 1")[2] == {"Auto": enemy.REC}
    del board["units"]["Leader"]
    assert enemy.REC not in enemy.enemy_row(board, "Fire Team 1")[2].values() and e["type"] == "Fire Team"


def test_co_hq_is_reconstituted_from_the_xo_first(board):
    """6.5.2 p.49: the XO first; once he is Removed from Play any PLT HQ, then the Arty FO, then the CO Staff by rank.
    A unit on its Fire Team side is not skipped."""
    staff = {"side": "US", "type": "Staff", "card": "11", "status": [], "steps": 1}
    board.update(co_hq="CO HQ", removed_from_play=["CO HQ"], rfp_data={"CO HQ": {"level": "CO"}})
    board["units"].update(
        {"CO XO": dict(staff, rank=2), "CO 1 Sgt": dict(staff, rank=3), "1st PLT HQ": dict(_hq("1"), card="11")}
    )
    assert commands.co_hq_candidates(board) == ["CO XO"]
    with pytest.raises(rules.Violation, match="from CO XO first"):
        commands.reconstitute_co_hq(board, "1st PLT HQ", [])
    board["units"]["CO XO"]["status"].append(rules.FIRE_TEAM_SIDE)
    with pytest.raises(rules.Violation, match="rally first"):
        commands.reconstitute_co_hq(board, "CO XO", [])
    del board["units"]["CO XO"]
    assert commands.co_hq_candidates(board) == ["1st PLT HQ"]
    commands.reconstitute_co_hq(board, "1st PLT HQ", [])
    assert board["units"]["CO HQ"]["level"] == "CO" and board["units"]["CO HQ"]["experience"] == "Green"
    assert "1st PLT HQ" not in board["units"]
    assert commands.originator_eligible(board["units"]["CO 1 Sgt"], "BN_STAFF")
    assert not commands.originator_eligible(board["units"]["CO HQ"], "BN_STAFF")


def test_bn_hq_lost_on_the_map_gives_no_orders_next_turn(board):
    """6.5.2 p.50 C: 'BN HQ will be unavailable to give orders in the following turn while they reconstitute'."""
    board.update(co_hq="CO HQ", bn_hq="off-map", campaign={"attempt": 1}, removed_from_play=[])
    board["units"]["BN HQ"] = {"side": "US", "type": "HQ", "level": "BN", "card": "11", "status": [], "steps": 1}
    prot = []
    combat.remove_from_play(board, "BN HQ", prot, "Casualty", as_casualty=True)
    assert board["bn_reconstituting"] == 2 and any("no orders in turn 2" in x for x in prot)
    board.update(turn=2, phase="3.3.1a")
    with pytest.raises(rules.Violation, match="being reconstituted"):
        commands.order_bn(board, "CO XO", "4.2.1e")


def test_reconstituted_us_squad_is_its_own_counter_with_the_teams_experience(board, quiet):
    """6.5.2 p.49: experience from the teams (Assault Team Line, others Green, table 12.6); never more steps or
    firepower than the squad started with."""
    import types

    board.update(
        removed_from_play=["1/1"], setup_units={"1/1": unit("11", platoon="1", rng="L", assets=["Rifle Grenade"])}
    )
    for n, kind in (("AT 21", "Assault Team"), ("AT 21b", "Assault Team"), ("FT 21", "Fire Team")):
        board["units"][n] = unit("21", type=kind, steps=1)
    ctx = types.SimpleNamespace(
        target_name="AT 21",
        recipient=board["units"]["AT 21"],
        o={"--squad": "1/1", "--with": "AT 21b,FT 21"},
        success="yes",
        prot=[],
        action_id="4.2.3i",
    )
    commands._order_reconstitute_squad(board, ctx)
    sq = board["units"]["1/1"]
    assert (sq["steps"], sq["experience"], sq["vof_rating"], sq["card"]) == (
        3,
        "Line",
        "S",
        "21",
    ) and "assets" not in sq


def test_concentrated_fire_marker_goes_when_shooter_or_target_changes(board):
    """7.11.5 p.56: removed 'if the unit Shifts or Ceases Fire, if the target moves away (to another card, into, out
    of, or between cover markers ...)'."""
    board["units"].update({"1/1": unit("11", target="21"), "G": unit("21", side="Enemy", spotted=True)})
    g, sh = board["units"]["G"], board["units"]["1/1"]

    def hit():
        before = fire.cf_counts(board, "21")
        g["cf"] = g.get("cf", 0) + 1
        fire.track_concentrated(board, sh, before)

    hit()
    assert fire.reconcile_concentrated(board) == [] and g["cf"] == 1
    fire.cease_fire(sh)
    assert "1/1 no longer fires at it" in fire.reconcile_concentrated(board)[0] and g["cf"] == 0 and "cf_on" not in sh
    sh["target"] = "21"
    hit()
    g["area"] = "C1"
    assert "the target moved away" in fire.reconcile_concentrated(board)[0] and g["cf"] == 0
    hit()
    board["phase"] = "3.7.4"  # frozen during Combat Effects
    g["area"] = "open"
    assert fire.reconcile_concentrated(board) == [] and g["cf"] == 1


def test_lone_g_mortar_flips_and_opens_fire(board):
    """8.6.5 p.67: a G!-rated one-step mortar alone on a card with opposing units that have a VOF rating."""
    mortar = dict(
        side="Enemy", vof="G", type="Weapons Team", steps=1, mortar=True, fire_team_side=True, ft_vof="S", spotted=True
    )
    board["units"].update({"Mtr": unit("21", **mortar), "Sq": unit("21", side="Enemy"), "1/1": unit("21")})
    assert enemy.lone_mortar_reaction(board) == []  # not alone
    del board["units"]["Sq"]
    lines = enemy.lone_mortar_reaction(board)
    m = board["units"]["Mtr"]
    assert "Fire Team side" in lines[0] and state.fire_team_side(m) and m["target"] == "21"
    assert enemy.lone_mortar_reaction(board) == []  # once


def test_unspotted_out_of_ammo_team_leaves_in_clean_up(board):
    """8.11.1 p.68: 'In the Clean Up Phase, remove from play any such team if it is Unspotted.'"""
    team = dict(side="Enemy", type="Weapons Team", steps=1, ooa_fallback=True, status=[rules.FIRE_TEAM_SIDE])
    board["units"].update({"A": unit("21", spotted=False, **team), "B": unit("22", spotted=True, **team)})
    phase.clean_up_units(board, [])
    assert "A" not in board["units"] and "B" in board["units"]


def test_concentrate_fire_needs_ammo_for_the_turn():
    """7.18.4 p.61: one for the attempt and one in the Combat Effects Segment."""
    assert combat.cf_ammo_short({"ammo": {"type": "MG", "points": 1}})
    assert not combat.cf_ammo_short({"ammo": {"type": "MG", "points": 2}})
    assert not combat.cf_ammo_short({})  # no ammo tracking


def test_sniper_opens_fire_on_the_card_with_a_leader(board):
    """6.1.1 p.39 target priorities: card with HQ, Staff or Leader present (closest), then the strongest VOF."""
    board["units"].update(
        {
            "Sniper": unit("31", side="Enemy", vof="S!", steps=1),
            "1/1": unit("21", steps=3),
            "HQ": dict(_hq("1"), card="22", area="open", target=None),
            "MG": unit("23", vof="A", steps=1),
        }
    )
    sn = board["units"]["Sniper"]
    assert fire._narrow_targets(board, "Sniper", sn, ["21", "22", "23"]) == ["22"]
    del board["units"]["HQ"]
    assert fire._narrow_targets(board, "Sniper", sn, ["21", "22", "23"]) == ["23"]  # A (-1) beats S (+0)


def test_church_tower_holds_one_step(board):
    """5.3.3 p.38: 'only a single step may be in this cover'."""
    cid = commands.add_cover_marker(board, "21", "Church Tower", 3)["id"]
    board["units"].update({"FO": unit("21", steps=1), "1/1": unit("21", steps=3)})
    with pytest.raises(rules.Violation, match="at most 1 steps"):
        commands.set_area(board, board["units"]["1/1"], cid)
    commands.set_area(board, board["units"]["FO"], cid)
