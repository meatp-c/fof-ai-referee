"""L539-L549, code review 07.11.2026 block C: edge cases (Out-of-Ammo flip, casualties, Litter Teams, contact grenade,
tank Move & Fire, retreat, pre-draw refusals, response Jam, option parsing, jeep, working fields)."""

import pytest

from conftest import _hq_board, card, german, t34, unit
from fof import grenades  # L556: split from commands

# ---- C1 (review C3/E8): the Out-of-Ammo flip


def test_deliberate_flip_to_front_clears_the_ooa_flag(board, monkeypatch):
    from fof import combat, commands

    s = _hq_board(board, monkeypatch)
    mg = s["units"]["MG"] = unit(
        "22",
        vof="A",
        rng="L",
        steps=1,
        type="Weapons Team",
        platoon="1",
        fire_team_side=True,
        ft_vof="S",
        ammo={"type": "MG", "points": 1},
    )
    combat.ammo_use(s, "MG", mg, 1, "test", [])
    assert mg.get("ooa_flip")
    commands.cmd_order(s, ["1st PLT HQ", "MG", "4.2.3f", "--ooa-flip=yes"])
    assert "ooa_flip" not in mg
    combat.reduce_unit(s, "MG", "F", [])  # HIT-caused flip now
    s["cards"]["22"]["ammo"] = {"MG": 2}
    combat.ammo_pick_up(s, mg, "MG", "MG:2", [])
    assert "Fire Team side" in mg["status"]  # resupply does not undo a HIT-caused flip


def test_enemy_rally_does_not_undo_the_ooa_flip(b342):
    from fof import combat, enemy

    s = b342
    s["campaign"] = {}
    s["units"]["US1"] = unit("12")
    hmg = german(
        "32",
        vof="H",
        type="Weapons Team",
        steps=1,
        fire_team_side=True,
        ft_vof="S",
        type_name="German HMG",
        ammo={"type": "MG", "points": 1, "start": 6},
        spotted=False,
        check_open=True,
        target="12",
    )
    s["units"]["HMG"] = hmg
    combat.ammo_use(s, "HMG", hmg, 1, "test", [])
    enemy.cmd_enemy_action(s, ["HMG", "Rally"])
    assert "Fire Team side" in hmg["status"] and hmg.get("ooa_flip")


# ---- C2 (review E7): Fall Back with Casualty


def test_litter_team_takes_one_casualty_along(b342):
    from fof import combat, enemy

    s = b342
    s["units"]["US1"] = unit("11", target="32")
    s["cards"]["32"]["casualties_enemy"] = 2
    lt = german("32", type="Litter Team", vof=None, check_open=True)
    combat.set_lat_values(lt, "Litter Team")
    s["units"]["LT"] = lt
    enemy.cmd_enemy_action(s, ["LT", "Fall Back with Casualty", "--target=42"])
    assert s["cards"]["32"]["casualties_enemy"] == 1 and s["cards"]["42"]["casualties_enemy"] == 1


# ---- C3 (review E3/E9)


def test_litter_team_does_not_move_towards_a_casualty_under_vof(b342):
    from fof import combat, enemy, rules

    s = b342
    s["units"]["US1"] = unit("12", target="22")
    s["cards"]["21"]["casualties_enemy"] = 1
    lt = german("32", type="Litter Team", vof=None, check_open=True)
    combat.set_lat_values(lt, "Litter Team")
    s["units"]["LT"] = lt
    with pytest.raises(rules.Violation, match="VOF against it"):
        enemy.cmd_enemy_action(s, ["LT", "Move towards closest Casualty", "--target=22"])
    assert lt["card"] == "32"


def test_enemy_seek_cover_on_a_mined_card_asks_for_a_mine_check(b342):
    from fof import enemy

    s = b342
    s["campaign"] = {}
    s["options"] = {"U20_mine_on_seek_cover": True}
    s["cards"]["32"]["external"].append(
        {"type": "Mines", "value": -4, "source": "Mines!", "side": "Enemy", "active": False}
    )
    s["cards"]["32"]["cover"].append({"id": "C1", "type": "Basic Cover", "value": 1, "field": False})
    s["units"]["US1"] = unit("12", target="32")
    s["units"]["G1"] = german("32", target="12", check_open=True)
    enemy.cmd_enemy_action(s, ["G1", "Seek Cover"])
    assert s["units"]["G1"]["area"] == "C1" and "G1" in s.get("mine_checks", [])


# ---- C4 (review E4): the G! grenade at contact hits the whole stack


def test_contact_grenade_hits_the_whole_stack(b342):
    import copy

    from fof import contact

    s = b342
    s["campaign"] = {}
    s["cards"]["11"]["pc"] = "A"
    s["cards"]["11"]["cover"].append({"id": "C1", "type": "Basic Cover", "value": 1, "field": False})
    s["units"]["1/1"] = unit("11", area="C1")
    s["units"]["1/2"] = unit("11", area="C1")
    pk = {
        "name": "G! team",
        "spotted": True,
        "place_vof": True,
        "units": [
            {
                "unit": "Rifle Grenade Team",
                "type": "Weapons Team",
                "vof_rating": "G",
                "range": "L",
                "steps": 1,
                "place": "max",
                "grenade_ranged": True,
            }
        ],
    }
    contact.pc_contact_campaign(
        s, "11", "A1", copy.deepcopy(pk), {"--direction": "Front", "--grenade": "yes", "--unit": "1/1"}
    )
    assert s["units"]["1/1"]["grenade"] and s["units"]["1/2"]["grenade"]


# ---- C5 (review V5/V6): enemy tank Move & Fire


def _big36(b36):
    s = b36
    s["cards"] = {f"{r}{c}": card(r, c) for r in range(1, 6) for c in range(1, 6)}
    s["cards"]["44"]["cc"] = 2
    return s


def sherman(card_id):
    return unit(card_id, type="Vehicle", vehicle="M4 Sherman 75mm", vof=None, rng=None, steps=2)


def test_no_move_and_fire_without_the_chart_capability(b36):
    from fof import vehicles

    s = _big36(b36)
    s["units"]["SU 1"] = t34("55", vehicle="SU-76M")
    s["units"]["Sherman 1"] = sherman("14")
    vehicles.enter_3_6(s, [])
    vehicles.cmd_vehicle(s, ["enemy"])
    plan = [x["kind"] for x in s["at36"]["action"]["plan"]]
    assert "fire" not in plan and "choose" not in plan


def test_move_and_fire_target_choice_comes_after_the_vof(b36):
    from fof import vehicles

    s = _big36(b36)
    s["units"]["T-34 1"] = t34("55")
    s["units"]["Sherman 1"] = sherman("14")
    s["units"]["Sherman 2"] = sherman("41")
    s["units"]["1/1"] = unit("43", target="44")
    vehicles.enter_3_6(s, [])
    vehicles.cmd_vehicle(s, ["enemy"])
    st = s["at36"]
    assert st["queue"][0]["kind"] == "vof" and not st.get("choice")
    assert [x["kind"] for x in st["action"]["plan"]][:2] == ["react", "choose"]


# ---- C6 (review V9): retreat through the move path


def test_retreat_leaves_the_grenade_marker_with_the_stack(board, monkeypatch):
    from fof import briefing, phase, rules, state

    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protocol"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)
    s = board
    s.update(phase="3.5.2", mission="x")
    s["units"]["E1"] = unit("33", side="Enemy", target="22")
    s["units"]["PT"] = unit("22", type="Paralyzed Team", steps=1, vof=None, grenade=[-4])
    s["units"]["FT"] = unit("22", type="Fire Team", steps=1, grenade=[-4], status=[rules.PINNED])
    phase.cmd_retreat(s, ["PT", "12"])
    assert s["units"]["PT"]["card"] == "12" and not s["units"]["PT"].get("grenade")
    assert s["units"]["FT"]["grenade"] == [-4]


def test_retreat_updates_the_activity_level(board, monkeypatch):
    """L579: the retreating team was the only target of a VOF; with it gone the level drops and is announced."""
    from fof import briefing, fire, phase, state

    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protocol"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)
    s = board
    s.update(phase="3.5.2", mission="x")
    s["units"]["US1"] = unit("12", target="22")
    s["units"]["US2"] = unit("11", vof=None)
    s["units"]["E1"] = unit("23", side="Enemy", target="11", spotted=True)
    s["units"]["PT"] = unit("22", side="Enemy", type="Paralyzed Team", steps=1, vof=None, spotted=True)
    s["activity"] = fire.expected_activity(s)
    assert s["activity"] == "Engaged"
    phase.cmd_retreat(s, ["PT", "31"])  # off the PDF of US1, its fire cannot follow
    assert s["activity"] == fire.expected_activity(s) == "Contact"
    assert "Activity level Engaged becomes Contact" in s["protocol"][-1]["text"]


# ---- C7 (review C5): refusals before the draw prompt


def test_infiltrate_within_a_card_without_vof_is_refused_before_the_draw(board, monkeypatch):
    from fof import commands, rules

    s = _hq_board(board, monkeypatch)
    s["units"]["1/1"] = unit("22", platoon="1")
    s["cards"]["22"]["cover"] = [{"id": "C1", "type": "Basic Cover", "value": 1, "field": False}]
    with pytest.raises(rules.Violation, match="requires a VOF"):
        commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.2g", "--area=C1"])


def test_rally_of_an_unpinned_unit_is_refused_before_the_draw(board, monkeypatch):
    from fof import commands, rules

    s = _hq_board(board, monkeypatch)
    s["units"]["1/1"] = unit("22", platoon="1")
    s["units"]["Enemy 1"] = unit("23", side="Enemy", vof="A", target="22")
    with pytest.raises(rules.Violation, match="not Pinned"):
        commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.3a"])


def test_reconstitute_squad_without_squad_is_refused_before_the_draw(board, monkeypatch):
    from fof import commands, rules

    s = _hq_board(board, monkeypatch)
    s["units"]["Fire Team 1"] = unit("22", type="Fire Team", steps=1, platoon="1")
    s["units"]["Fire Team 2"] = unit("22", type="Fire Team", steps=1, platoon="1")
    s["units"]["Enemy 1"] = unit("23", side="Enemy", vof="A", target="22")
    with pytest.raises(rules.Violation, match="--squad"):
        commands.cmd_order(s, ["1st PLT HQ", "Fire Team 1", "4.2.3i", "--with=Fire Team 2"])


def test_passenger_cannot_move_under_cover(board, monkeypatch):
    from fof import commands, rules, vehicles

    s = _hq_board(board, monkeypatch)
    s["cards"]["22"]["cover"] = [{"id": "C1", "type": "Basic Cover", "value": 1, "field": False}]
    s["units"]["Jeep"] = vehicles.company_jeep_unit("22")
    s["units"]["1/W/1"] = unit("22", type="Weapons Team", platoon="1", steps=1, on_board="Jeep")
    with pytest.raises(rules.Violation, match="on board the Jeep"):
        commands.cmd_order(s, ["1st PLT HQ", "1/W/1", "4.2.2f", "--area=C1"])


# ---- C9 (review K6/K7): option and argument translation


def test_plain_no_is_not_a_yes(board, monkeypatch):
    from fof import commands, rules

    s = _hq_board(board, monkeypatch)
    s["units"]["1/1"] = unit("22", platoon="1", target="22")
    s["units"]["Enemy 1"] = unit("22", side="Enemy", vof="S", target=None)
    with pytest.raises(rules.Violation, match="could infiltrate"):
        commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.2a", "--target=32", "--plain=no"])


def test_free_text_keeps_its_english_words():
    from fof import cli

    out = cli.normalize_argv(["xp", "add", "2", "we", "did", "spend", "a", "promote", "add"])
    assert out == ["xp", "add", "2", "we", "did", "spend", "a", "promote", "add"]
    assert cli.normalize_argv(["fire", "1/1", "off"])[1:] == ["1/1", "off"]
    assert cli.normalize_argv(["correct", "status", "1/1", "Pinned", "remove"])[1:] == [
        "status",
        "1/1",
        "Pinned",
        "remove",
    ]


# ---- C10 (review V10): the jeep's experience follows a passenger that changes


def test_jeep_experience_follows_a_flipped_passenger(board):
    from fof import vehicles

    s = board
    s["units"]["Jeep"] = vehicles.company_jeep_unit("21")
    s["units"]["V"] = unit(
        "21", type="Weapons Team", steps=1, experience="Veteran", on_board="Jeep", fire_team_side=True
    )
    vehicles.refresh_jeeps(s)
    assert s["units"]["Jeep"]["experience"] == "Veteran"
    s["units"]["V"]["status"].append("Fire Team side")
    vehicles.refresh_jeeps(s)
    assert s["units"]["Jeep"]["experience"] == "Green"


# ---- C11 (review C10/C11/C12/C13/V15): working fields


def test_indirect_lay_clears_the_direct_lay_working_fields(board, monkeypatch):
    from fof import commands

    s = _hq_board(board, monkeypatch)
    s["units"]["1st PLT HQ"]["card"] = "12"
    m = s["units"]["Mtr"] = unit(
        "12",
        vof="H",
        rng="C-L",
        steps=2,
        type="Weapons Team",
        platoon="1",
        mortar=True,
        target="12",
        _smoke_target="32",
        target_open=["32"],
    )
    s["units"]["Enemy 1"] = unit("32", side="Enemy", vof="S", target=None)
    commands.cmd_order(s, ["1st PLT HQ", "Mtr", "4.2.4j", "--target=32"])
    assert m.get("indirect") and "_smoke_target" not in m and "target_open" not in m


def test_fire_team_side_is_not_jam_prone():

    assert grenades.jam_prone({"type": "Weapons Team", "vof_rating": "A", "status": []})
    assert not grenades.jam_prone({"type": "Weapons Team", "vof_rating": "A", "status": ["Fire Team side"]})


def test_point_blank_shift_clears_old_working_fields(board):
    from fof import fire

    e = unit("22", target="33", _vof_blocked="32", _range_vof="32", concentrated=True)
    fire.set_target(e, "22")
    assert e["target"] == "22" and not {"_vof_blocked", "_range_vof", "concentrated"} & set(e)


# ---- C12 (review E10/E12/E13/E15/K10)


def test_enemy_correction_accepts_the_english_words(b342):
    from fof import contact

    s = b342
    s["campaign"] = {}
    s["units"]["US1"] = unit("11")
    s["units"]["G1"] = german("31")
    contact.cmd_enemy(s, ["G1", "card=32"])
    assert s["units"]["G1"]["card"] == "32"
    contact.cmd_enemy(s, ["G1", "remove"])
    assert "G1" not in s["units"]
    s["cards"]["22"]["external"].append({"type": "Smoke", "value": 1, "source": "x"})
    contact.cmd_external(s, ["22", "remove"])
    assert s["cards"]["22"]["external"] == []


def test_second_face_up_pc_marker_applies_8_2_3_and_a_hidden_one_is_promoted(b342):
    from fof import contact, state

    s = b342
    s["activity"] = "No Contact"
    s["cards"]["23"]["pc"] = "B"
    contact.cmd_pc_campaign(s, ["set", "23", "A"])
    assert s["cards"]["23"]["pc"] == "A" and "pc2" not in s["cards"]["23"]
    s["cards"]["13"]["pc"] = "A"
    contact.cmd_pc_campaign(s, ["set", "13", "?"])
    state.clear_pc(s["cards"]["13"])
    assert s["cards"]["13"]["pc"] == "?" and "pc2" not in s["cards"]["13"]


def test_enemy_infiltration_must_step_towards_the_closest_opponent(b342):
    from fof import enemy, rules

    s = b342
    s["units"]["US1"] = unit("11", target="31")
    s["units"]["G1"] = german("31", target="11", check_open=True)
    with pytest.raises(rules.Violation, match="does not bring G1 closer"):
        enemy.cmd_enemy_action(s, ["G1", "Infiltrate towards closest opposing unit", "--target=41", "--success=yes"])


def test_drop_ammo_names_the_types(board, monkeypatch):
    from fof import rules, setup

    s = _hq_board(board, monkeypatch, phase="3.3.1b")
    s["units"]["MG"] = unit("22", type="Weapons Team", steps=1, ammo={"type": "MG", "points": 4})
    with pytest.raises(rules.Violation, match="MG\\|MTR\\|RKT\\|RCL"):
        setup.cmd_drop(s, ["MG", "AMMO:1"])


# ---- C13 small findings (review V12, V16, K9, K12, K14, E11)


def test_enemy_litter_team_at_its_edge_retreats_off_the_map_with_its_casualty(board):
    from fof import combat, phase

    s = board
    s.update(phase="3.5.1", mission="x")
    s["units"]["US1"] = unit("21", target="31")
    s["cards"]["31"]["casualties_enemy"] = 1
    lt = unit("31", side="Enemy", type="Litter Team", steps=1, vof=None)
    combat.set_lat_values(lt, "Litter Team")
    s["units"]["LT"] = lt
    phase.check_retreat(s, [])
    assert "LT" not in s["units"] and s["cards"]["31"]["casualties_enemy"] == 0


def test_enemy_tank_route_needs_recorded_trafficability(b36):
    from fof import rules, vehicles

    s = b36
    s["terrain_catalog"] = {}
    s["cards"]["32"]["cc"] = 2
    s["units"]["T-34 1"] = t34("33")
    with pytest.raises(rules.Violation, match="Trafficability not recorded"):
        vehicles.tank_better_cards(s, "T-34 1")


def test_undo_refuses_a_snapshot_of_another_entry(cli_game, fof_cli):
    import json

    from fof import state

    game = cli_game()
    for i in range(3):
        assert fof_cli("note", f"n{i}")[0] == 0
    snap = game / state.HISTORY_DIR / "2.json"
    data = json.loads(snap.read_text(encoding="utf-8"))
    data["protocol_entries"] = 1  # as if an old file had been reused under this number
    snap.write_text(json.dumps(data), encoding="utf-8")
    code, out = fof_cli("undo", "2")
    assert code == 2 and "holds the state after entry 1" in out


def test_this_turn_only_needs_a_weather_value(board, monkeypatch):
    from fof import rules, setup

    s = _hq_board(board, monkeypatch, phase="3.1")
    s["weather_this_turn_only"] = True
    with pytest.raises(rules.Violation, match="needs a weather value"):
        setup.cmd_visibility(s, ["0", "--this-turn-only=yes"])
    setup.cmd_visibility(s, ["0", "1"])
    assert "weather_this_turn_only" not in s


def test_extend_refuses_ambiguous_card_ids(board, monkeypatch):
    from fof import rules, setup

    s = _hq_board(board, monkeypatch)
    with pytest.raises(rules.Violation, match="not unique"):
        setup.cmd_extend(s, ["2", "10", "Woods"])


def test_command_log_keeps_the_commands_that_changed_the_game(cli_game, fof_cli):
    from fof import state

    game = cli_game()
    assert fof_cli("note", "first note")[0] == 0
    assert fof_cli("status")[0] == 0  # reads only
    assert fof_cli("undo", "99")[0] == 2  # refused
    assert fof_cli("note", "second")[0] == 0
    lines = (game / state.COMMAND_LOG).read_text(encoding="utf-8").splitlines()
    assert lines[-2:] == ["note 'first note'", "note second"]
