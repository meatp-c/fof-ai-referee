"""Review 23.10.2026, vehicles.py (H5, H12, M29-M32, M35, M36, M38, LOW): in-process on the synthetic board."""

import pytest
from conftest import unit

from fof import briefing, rules, state, vehicles


def sherman(kid, side="US", **extra):
    e = unit(kid, side=side, typ="Vehicle", fahrzeug="M4 Sherman 75mm", platoon="Tank", vof="H", rng="V", steps=2)
    e["munition"] = {"typ": "Tank", "punkte": 5, "start": 5}
    e.update(extra)
    return e


def pak(kid, **extra):
    e = unit(kid, side="Feind", typ="AT Gun", vof="S", rng="C", at_waffe="75mm AT Gun", steps=1, status=["Activated"])
    e["munition"] = {"typ": "AT", "punkte": 5, "start": 5}
    e.update(extra)
    return e


@pytest.fixture
def game(board, monkeypatch):
    """Board in 3.6 with saving and printing stubbed; nothing touches a game folder."""
    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protokoll"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)
    board["phase"] = "3.6"
    vehicles.at36(board)["naechste"] = "US"
    return board


def last(s):
    return s["protokoll"][-1]["text"]


# ---- H5: MSR 2 group order must not skip the enemy AT action


def test_h5_leave_3_6_refuses_while_lower_group_us_unit_has_not_passed(game):
    game["sonderregeln"] = {"fahrzeug_reihenfolge": "MSR 2"}
    game["einheiten"]["Jeep 1"] = unit("21", typ="Vehicle", fahrzeug="Jeep", vof=None, status=["Activated"])
    game["einheiten"]["PAK"] = pak("31")
    assert vehicles.current_group(game) == 2
    assert vehicles.enemy_actors(game) == []  # PAK (group 3) filtered out, the old leave_3_6 let the phase end here
    with pytest.raises(rules.Violation, match="Jeep 1"):
        vehicles.leave_3_6(game, [])
    vehicles.cmd_vehicle(game, ["done", "Jeep 1"])
    assert vehicles.moved_fired(game["einheiten"]["Jeep 1"])
    assert vehicles.current_group(game) == 3 and vehicles.enemy_actors(game) == ["PAK"]
    assert vehicles.at36(game)["naechste"] == "Feind"
    with pytest.raises(rules.Violation, match="vehicle enemy"):
        vehicles.leave_3_6(game, [])
    vehicles.cmd_vehicle(game, ["enemy"])
    assert vehicles.at36(game)["queue"][0]["schuetze"] == "PAK"
    vehicles.cmd_at(game, ["11"])  # net -5 (C -3, Jeep -2) + 11 = 6: Missed
    assert vehicles.moved_fired(game["einheiten"]["PAK"])
    vehicles.leave_3_6(game, [])
    assert vehicles.at36(game)["ende"]


# ---- M29: pending Quick Shot target choice is an open draw


def test_m29_target_choice_blocks_lock_and_is_validated(game):
    game["einheiten"]["PAK"] = pak("31")
    game["einheiten"]["Sherman 1"] = sherman("21", status=["Activated"])
    game["einheiten"]["Sherman 2"] = sherman("22", status=["Activated"])
    st = vehicles.at36(game)
    st["wahl"] = vehicles.make_item("wahl", schuetze="PAK", ziele=["Sherman 1", "Sherman 2"], reaction=True)
    with pytest.raises(rules.Violation, match="target choice"):
        vehicles.lock(game)
    with pytest.raises(rules.Violation, match="Usage"):
        vehicles.cmd_vehicle(game, ["target"])
    with pytest.raises(rules.Violation, match="whole number"):
        vehicles.cmd_vehicle(game, ["target", "x"])
    with pytest.raises(rules.Violation, match="not in the choice list"):
        vehicles.cmd_vehicle(game, ["target", "3"])
    assert "wahl" in st  # a refused choice stays open
    vehicles.cmd_vehicle(game, ["target", "2"])
    assert "wahl" not in st
    q = st["queue"][0]
    assert (q["schuetze"], q["ziel"], q["typ"], q["reaction"]) == ("PAK", "Sherman 2", "quick", True)


def test_m29_target_choice_lapses_when_targets_are_gone(game):
    game["einheiten"]["PAK"] = pak("31")
    game["einheiten"]["Sherman 1"] = sherman("21", status=["Activated"])
    st = vehicles.at36(game)
    st["wahl"] = vehicles.make_item("wahl", schuetze="PAK", ziele=["Sherman 1", "Sherman 9"])
    with pytest.raises(rules.Violation, match="target choice"):
        vehicles.lock(game)  # Sherman 9 missing, Sherman 1 valid: still live
    del game["einheiten"]["Sherman 1"]
    vehicles.lock(game)  # stale: does not block
    vehicles.cmd_vehicle(game, ["target", "1"])  # lapses and saves instead of a Violation
    assert "wahl" not in st and "lapses" in last(game)


def test_m29_target_choice_outside_phase_and_at_rows_without_los(game):
    game["einheiten"]["PAK"] = pak("31")
    game["karten"]["15"] = dict(game["karten"]["11"], spalte=5)  # 4 cards away: beyond V
    game["einheiten"]["Sherman 1"] = sherman("15", status=["Activated"])
    assert vehicles.line_of_fire(game, game["einheiten"]["PAK"], "15") is None
    with pytest.raises(rules.Violation, match="LOS/range"):
        vehicles.at_rows(game, "PAK", "Sherman 1")  # formerly TypeError on RANGE_LETTER[None]
    game["phase"] = "3.7.1"
    with pytest.raises(rules.Violation, match="3.6"):
        vehicles.cmd_vehicle(game, ["target", "1"])


# ---- M30: Concentrate Fire and Spot act after the VOF before the action


def _sherman_under_fire(game):
    game["einheiten"]["Sherman 1"] = sherman("22", status=["Activated"], ziel="23")
    game["einheiten"]["FJ"] = unit("23", side="Feind", vof="S", rng="L", ziel="22")  # S VOF on the tank's card
    return game


def test_m30_cf_marker_only_after_the_vof_draw(game):
    _sherman_under_fire(game)
    vehicles.cmd_vehicle(game, ["cf", "Sherman 1", "--einheit=FJ", "--erfolg=ja"])
    st = vehicles.at36(game)
    assert st["queue"][0]["art"] == "vof" and "cf" not in game["einheiten"]["FJ"]
    assert [p["art"] for p in st["aktion"]["plan"]] == ["cf", "react", "ende"]
    vehicles.cmd_at(game, ["9"])  # Missed, the action goes on
    assert game["einheiten"]["FJ"]["cf"] == 1 and st["aktion"] is None
    assert vehicles.moved_fired(game["einheiten"]["Sherman 1"])


def test_m30_brewed_up_before_cf_leaves_no_marker(game):
    _sherman_under_fire(game)
    vehicles.cmd_vehicle(game, ["cf", "Sherman 1", "--einheit=FJ", "--erfolg=ja", "--kritisch=ja"])
    vehicles.cmd_at(game, ["-9"])  # Brewed Up by the VOF before the action
    assert "Sherman 1" not in game["einheiten"]
    assert "cf" not in game["einheiten"]["FJ"] and "cf_critical" not in game["einheiten"]["FJ"]
    assert vehicles.at36(game)["aktion"] is None


def test_m30_spot_flips_only_after_the_vof_draw(game):
    _sherman_under_fire(game)
    game["einheiten"]["FJ"]["spotted"] = False
    vehicles.cmd_vehicle(game, ["spot", "Sherman 1", "--ziel=23", "--erfolg=ja"])
    assert game["einheiten"]["FJ"]["spotted"] is False
    vehicles.cmd_at(game, ["-9"])
    assert "Sherman 1" not in game["einheiten"] and game["einheiten"]["FJ"]["spotted"] is False


def test_m30_spot_success_after_missed_vof(game):
    _sherman_under_fire(game)
    game["einheiten"]["FJ"]["spotted"] = False
    vehicles.cmd_vehicle(game, ["spot", "Sherman 1", "--ziel=23", "--erfolg=ja"])
    vehicles.cmd_at(game, ["9"])
    assert game["einheiten"]["FJ"]["spotted"] is True


# ---- M31 / M32: no action after the end-of-phase VOF; side alternation for the enemy too


def test_m31_no_action_after_leave_3_6_started_the_end_vof(game):
    game["einheiten"]["Sherman 1"] = sherman("21", status=["Activated"])
    game["einheiten"]["PAK"] = pak("31")
    vehicles.at36(game)["ende"] = True
    with pytest.raises(rules.Violation, match="phase is ending"):
        vehicles.cmd_vehicle(game, ["move", "Sherman 1", "22"])
    with pytest.raises(rules.Violation, match="phase is ending"):
        vehicles.cmd_vehicle(game, ["enemy"])


def test_m32_enemy_must_wait_for_the_us_action(game):
    game["einheiten"]["Sherman 1"] = sherman("21", status=["Activated"])
    game["einheiten"]["PAK"] = pak("31")
    with pytest.raises(rules.Violation, match="US side's turn"):
        vehicles.cmd_vehicle(game, ["enemy"])
    vehicles.cmd_vehicle(game, ["done", "Sherman 1"])
    assert vehicles.at36(game)["naechste"] == "Feind"
    vehicles.cmd_vehicle(game, ["enemy"])
    assert vehicles.at36(game)["queue"][0]["schuetze"] == "PAK"


# ---- M35: enemy crew casualties under the enemy key


def test_m35_enemy_vehicle_brewed_up_books_enemy_casualties(game):
    game["einheiten"]["Panzer"] = sherman("22", side="Feind")
    game["us_casualties_gesamt"] = 3
    vehicles.apply_result(game, "Panzer", "Brewed Up", [])
    c = game["karten"]["22"]
    assert c.get("casualties_feind") == 2 and not c.get("casualties") and game["us_casualties_gesamt"] == 3
    game["einheiten"]["Sherman 1"] = sherman("21")
    vehicles.apply_result(game, "Sherman 1", "Brewed Up", [])
    assert game["karten"]["21"]["casualties"] == 2 and game["us_casualties_gesamt"] == 5


# ---- M36: the reaction flag survives the Quick Shot chain


def test_m36_us_reaction_quick_shot_chain_keeps_unit_open_on_stop(game):
    game["einheiten"]["Sherman 1"] = sherman("21")
    game["einheiten"]["Panzer"] = sherman("23", side="Feind")
    vehicles.cmd_vehicle(game, ["react", "Sherman 1", "Panzer"])
    st = vehicles.at36(game)
    assert st["queue"][0]["reaction"] is True
    vehicles.cmd_at(game, ["3"])  # net 1 (gunnery L) + 3 = 4: Pinned, Quick Shot
    assert st["queue"][0]["typ"] == "quick_offer" and st["queue"][0]["reaction"] is True
    vehicles.cmd_at(game, ["again"])
    assert st["queue"][0]["typ"] == "quick" and st["queue"][0]["reaction"] is True
    vehicles.cmd_at(game, ["4"])  # net 0 (target Pinned) + 4 = 4: Pinned, second offer keeps the flag
    assert st["queue"][0]["typ"] == "quick_offer" and st["queue"][0]["reaction"] is True
    vehicles.cmd_at(game, ["stop"])
    assert not vehicles.moved_fired(game["einheiten"]["Sherman 1"])


def test_m36_enemy_reaction_chain_without_target_left_keeps_unit_open(game):
    game["einheiten"]["Sherman 1"] = sherman("22", status=["Activated"])
    game["einheiten"]["PAK"] = pak("31")
    vehicles.queue_reactions(game, "Sherman 1", [])
    st = vehicles.at36(game)
    assert st["queue"][0]["typ"] == "reaction"
    vehicles.cmd_at(game, ["7"])  # net -3 (C) + 7 = 4: Pinned, enemy fires again at the only target
    assert st["queue"][0]["typ"] == "quick" and st["queue"][0]["reaction"] is True
    vehicles.cmd_at(game, ["0"])  # net -4 (target Pinned) + 0 = -4: Brewed Up, Quick Shot sum without a target left
    assert "Sherman 1" not in game["einheiten"]
    assert not vehicles.moved_fired(game["einheiten"]["PAK"])  # 10.6.1: a Quick Shot draw as Reaction Fire


def test_m36_action_chain_flips_on_stop(game):
    game["einheiten"]["Sherman 1"] = sherman("21", status=["Activated"])
    game["einheiten"]["Panzer"] = sherman("23", side="Feind")
    vehicles.cmd_vehicle(game, ["fire", "Sherman 1", "Panzer"])
    vehicles.cmd_at(game, ["3"])
    st = vehicles.at36(game)
    assert st["queue"][0]["typ"] == "quick_offer" and st["queue"][0]["reaction"] is False
    vehicles.cmd_at(game, ["stop"])
    assert vehicles.moved_fired(game["einheiten"]["Sherman 1"])


# ---- M38: unknown vehicle type


def test_m38_unknown_vehicle_type_is_a_violation(game):
    game["einheiten"]["Tank"] = sherman("21", fahrzeug="M4 Sherman", status=["Activated"])
    game["einheiten"]["PAK"] = pak("31")
    with pytest.raises(rules.Violation, match="M4 Sherman 75mm"):
        vehicles.at_rows(game, "PAK", "Tank")
    with pytest.raises(rules.Violation, match="Unknown vehicle type"):
        vehicles.check_move_vehicle(game, "Tank", "22")
    with pytest.raises(rules.Violation, match="Unknown vehicle type"):
        vehicles.apply_result(game, "Tank", "Missed", [])


# ---- H12: argument checks


def test_h12_missing_arguments_are_violations(game):
    game["einheiten"]["Sherman 1"] = sherman("21", status=["Activated"])
    for args in (
        ["move", "Sherman 1"],
        ["fire"],
        ["done"],
        ["cf"],
        ["spot"],
        ["react", "Sherman 1"],
        ["traffic", "Woods"],
    ):
        with pytest.raises(rules.Violation, match="Usage"):
            vehicles.cmd_vehicle(game, args)
    vehicles.at36(game)["queue"].append(vehicles.make_item("vof", ziel="Sherman 1", zeilen=[], label="x"))
    with pytest.raises(rules.Violation, match="Usage"):
        vehicles.cmd_at(game, [])
    with pytest.raises(rules.Violation, match="whole number"):
        vehicles.cmd_at(game, ["abc"])
    with pytest.raises(rules.Violation, match="needs no Grenade"):
        vehicles.cmd_at(game, ["grenade"])


# ---- LOW: resume, wreck cover, legacy plan steps


def test_resume_runs_the_plan_and_names_the_next_step(game):
    game["einheiten"]["Sherman 1"] = sherman("21", status=["Activated"])
    st = vehicles.at36(game)
    st["aktion"] = {"einheit": "Sherman 1", "plan": [("ende", None)], "bewegt": False}  # legacy tuple step
    prot = []
    vehicles.resume(game, prot)
    assert st["aktion"] is None and vehicles.moved_fired(game["einheiten"]["Sherman 1"])
    assert "No Activated unit left" in prot[-1]


def test_add_wreck_cover_takes_the_next_free_id(game):
    c = game["karten"]["22"]
    c["cover"] = [{"id": "C1", "typ": "Basic", "wert": 1}, {"id": "C3", "typ": "Basic", "wert": 1}]
    assert vehicles.add_wreck_cover(game, c, 1) == "C2"
    assert vehicles.add_wreck_cover(game, c, 2) == "C4"
    assert c["cover"][-1] == {"id": "C4", "typ": "Wreck", "wert": 2, "feld": False, "wrack": True}


def test_unspotted_enemy_reacts(game):
    game["einheiten"]["Sherman 1"] = sherman("22")
    game["einheiten"]["PAK"] = pak("31", spotted=False)
    assert vehicles.reaction_shooters(game, "Sherman 1") == ["PAK"]


# ---- M38 / H12 follow-ups: unknown AT weapon, bare option flags, choices saved before the review


def test_m38_unknown_at_weapon_is_a_violation(game):
    game["einheiten"]["Sherman 1"] = sherman("22", status=["Activated"])
    game["einheiten"]["PAK"] = pak("31", at_waffe="50mm PaK")
    with pytest.raises(rules.Violation, match="75mm AT Gun"):
        vehicles.reaction_shooters(game, "Sherman 1")


def test_h12_bare_option_flags_need_a_value(game):
    _sherman_under_fire(game)
    with pytest.raises(rules.Violation, match="needs a value"):
        vehicles.cmd_vehicle(game, ["cf", "Sherman 1", "--einheit", "--erfolg=ja"])
    with pytest.raises(rules.Violation, match="needs a value"):
        vehicles.cmd_vehicle(game, ["spot", "Sherman 1", "--ziel", "--erfolg=ja"])


def test_m31_no_reaction_fire_after_the_end_vof_started(game):
    game["einheiten"]["Sherman 1"] = sherman("21")
    game["einheiten"]["Panzer"] = sherman("23", side="Feind")
    vehicles.at36(game)["ende"] = True
    with pytest.raises(rules.Violation, match="phase is ending"):
        vehicles.cmd_vehicle(game, ["react", "Sherman 1", "Panzer"])


def test_legacy_target_choice_without_kind_is_described(game):
    game["einheiten"]["PAK"] = pak("31")
    game["einheiten"]["Sherman 1"] = sherman("21", status=["Activated"])
    game["einheiten"]["Sherman 2"] = sherman("22", status=["Activated"])
    st = vehicles.at36(game)
    st["wahl"] = {"schuetze": "PAK", "ziele": ["Sherman 1", "Sherman 2"]}  # format saved before the review
    with pytest.raises(rules.Violation, match="R# column 2"):
        vehicles.lock(game)
    vehicles.cmd_vehicle(game, ["target", "1"])
    assert st["queue"][0]["ziel"] == "Sherman 1" and st["queue"][0]["reaction"] is False


def test_actors_match_the_single_lists(game):
    game["sonderregeln"] = {"fahrzeug_reihenfolge": "MSR 2"}
    game["einheiten"]["Sherman 1"] = sherman("21", status=["Activated"])
    game["einheiten"]["Jeep 1"] = unit("21", typ="Vehicle", fahrzeug="Jeep", vof=None, status=["Activated"])
    game["einheiten"]["PAK"] = pak("31")
    assert vehicles.actors(game) == (vehicles.us_actors(game), vehicles.enemy_actors(game)) == (["Sherman 1"], [])


# ---- fixture: M6 entry 569 (3.6 with four Activated Shermans under MSR 2), tests/fixtures/m6_569.json


@pytest.mark.game_data
def test_h5_m6_snapshot_phase_next_waits_for_the_us_passes(m6_game, fof_cli):
    from conftest import saved_state

    assert m6_game(569)["phase"] == "3.6"
    code, out = fof_cli("phase", "next")
    assert code == 2 and "VIOLATION" in out and "still to act or pass" in out
    code, out = fof_cli("vehicle", "spot", "M4 Sherman HQ", "--ziel")
    assert code == 2 and "VIOLATION" in out and "needs a value" in out
    for n in ("M4 Sherman HQ", "M4 Sherman 13", "M4 Sherman 14", "M4 Sherman 15"):
        assert fof_cli("vehicle", "done", n)[0] == 0
    code, out = fof_cli("phase", "next")
    assert code == 0 and "VIOLATION" not in out
    assert saved_state()["phase"] != "3.6"
