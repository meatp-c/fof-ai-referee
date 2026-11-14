"""L531-, code review 07.11.2026 block B: game results that matter for Naktong M1 (enemy tanks, bunkers, retreat)."""

import pytest

from conftest import _hq_board, bazooka, german, t34, unit


# ---- B1 (review V3): after a plan-based enemy tank action the US side acts next


def test_us_acts_after_an_enemy_tank_action(b36):
    from fof import rules, vehicles

    s = b36
    s["units"]["T-34 1"] = t34("33")
    s["units"]["T-34 2"] = t34("31")
    s["units"]["Bazooka"] = bazooka("11", status=[rules.ACTIVATED])
    s["units"]["Sherman 1"] = unit(
        "11", type="Vehicle", vehicle="M4 Sherman 75mm", vof=None, rng=None, steps=2, status=[rules.ACTIVATED]
    )
    vehicles.enter_3_6(s, [])
    vehicles.cmd_vehicle(s, ["done", "Bazooka"])
    vehicles.cmd_vehicle(s, ["enemy", "--unit=T-34 1"])
    vehicles.cmd_at(s, ["9"])  # Missed
    assert s["at36"]["reaction_open"]["shooters"] == ["Sherman 1"]  # B2: the shot opens a Reaction Fire window
    vehicles.cmd_vehicle(s, ["react", "pass"])  # the tank action ends
    assert s["at36"]["next"] == "US"
    vehicles.cmd_vehicle(s, ["move", "Sherman 1", "12"])  # no "It is the enemy's turn"


# ---- B2 (review V1/V7): US Reaction Fire window holds the enemy tank on the card of its move


def test_reaction_window_stops_the_tank_and_keeps_it_moving(b36):
    from fof import rules, vehicles

    s = b36
    s["cards"]["31"]["cc"] = 2  # the tank drives 33, 22, 31 toward the better card
    s["units"]["T-34 1"] = t34("33")
    s["units"]["Bazooka"] = bazooka("22")
    s["cards"]["22"]["cc"] = 0
    vehicles.enter_3_6(s, [])
    vehicles.cmd_vehicle(s, ["enemy"])
    e = s["units"]["T-34 1"]
    w = s["at36"].get("reaction_open")
    assert w and w["target"] == "T-34 1" and w["shooters"] == ["Bazooka"]
    stop = e["card"]
    assert e.get("in_motion")
    with pytest.raises(rules.Violation, match="First decide on Reaction Fire"):
        vehicles.lock(s)
    vehicles.cmd_vehicle(s, ["react", "Bazooka", "T-34 1"])
    item = s["at36"]["queue"][0]
    assert ("Target is moving", 1) in [tuple(z) for z in item["modifiers"]]
    assert e["card"] == stop and "reaction_open" not in s["at36"]


def test_react_pass_closes_the_window_and_the_plan_runs_on(b36):
    from fof import vehicles

    s = b36
    s["cards"]["32"]["cc"] = 2
    s["units"]["T-34 1"] = t34("33")
    s["units"]["Bazooka"] = bazooka("22")
    vehicles.enter_3_6(s, [])
    vehicles.cmd_vehicle(s, ["enemy"])
    assert s["at36"].get("reaction_open")
    vehicles.cmd_vehicle(s, ["react", "pass"])
    assert "reaction_open" not in s["at36"] and s["at36"].get("action") is None
    assert vehicles.moved_fired(s["units"]["T-34 1"])


def test_no_reaction_fire_without_an_open_window(b36):
    from fof import rules, vehicles

    s = b36
    s.pop("special_rules")
    s["units"]["T-34 1"] = t34("33")
    s["units"]["Bazooka"] = bazooka("22")
    vehicles.enter_3_6(s, [])
    with pytest.raises(rules.Violation, match="No Reaction Fire window"):
        vehicles.cmd_vehicle(s, ["react", "Bazooka", "T-34 1"])
    assert not s["at36"]["queue"]


# ---- B3 (review V2): the tank's Concentrate Fire is bookable with a target


@pytest.mark.parametrize("opt", ["--target=Bazooka 1", "--unit=Bazooka 1"])
def test_tank_concentrate_fire_with_a_target(b36, opt):
    from fof import vehicles

    s = b36
    s["units"]["T-34 1"] = t34("33", vof="H", rng="V", target="22")
    s["units"]["Bazooka 1"] = bazooka("22", vof="S")
    s["units"]["Bazooka 2"] = bazooka("22", vof="S")
    vehicles.cmd_vehicle(s, ["enemy", "--success=yes", opt])
    assert s["units"]["Bazooka 1"].get("cf") and not s["units"]["Bazooka 2"].get("cf")


# ---- B4-B6: enemy units leaving a Bunker / Deep Bunker, cover capacity (review E1, E6, E2)


def test_unit_out_of_its_bunker_fires_point_blank_and_shifts(b342):
    from fof import enemy, fire

    s = b342
    s["cards"]["32"]["cover"].append({"id": "C1", "type": "Bunker", "value": 3, "field": True, "direction": [-1, 0]})
    s["units"]["US1"] = unit("22", target="32")
    s["units"]["HMG"] = german(
        "32",
        vof="H",
        area="C1",
        no_point_blank=True,
        bunker_direction="22",
        type="Weapons Team",
        target="22",
        check_open=True,
    )
    enemy.cmd_enemy_action(s, ["HMG", "Fall Back", "--target=41"])
    e = s["units"]["HMG"]
    assert e["card"] == "41" and "no_point_blank" not in e and "bunker_direction" not in e
    s["units"]["US2"] = unit("41")
    e["target"] = None
    fire.open_fire(s, [], only=["HMG"])
    assert e["target"] == "41"


def test_deep_bunker_unit_gets_no_target_at_placement_and_fires_when_it_leaves(b342):
    import copy

    from fof import contact, enemy, fire, state

    s = b342
    s["campaign"] = {}
    s["cards"]["11"]["pc"] = "A"
    s["units"]["1/1"] = unit("11")
    pk = {
        "name": "Deep Bunker MG",
        "spotted": True,
        "place_vof": True,
        "units": [
            {
                "unit": "German HMG",
                "type": "Weapons Team",
                "vof_rating": "H",
                "range": "L",
                "steps": 1,
                "place": "max",
                "cover": "Deep Bunker",
                "cover_value": 3,
            }
        ],
    }
    contact.pc_contact_campaign(s, "11", "A1", copy.deepcopy(pk), {"--direction": "Front"})
    e = s["units"]["German HMG 1"]
    assert e.get("deep_bunker") and e["target"] is None and not fire.is_firing(e)
    assert (e["card"], "11") not in state.pdf_pairs(s)  # no PDF from the bunker (the US fire at it is fine)
    s["units"]["1/1"]["card"] = "22"
    e["check_open"] = True
    enemy.cmd_enemy_action(s, ["German HMG 1", "Grenade Attack (or Concentrate Fire)", "--success=yes", "--unit=1/1"])
    assert "deep_bunker" not in e and e["target"] == "22"


def test_fall_back_skips_a_full_foxhole(b342):
    from fof import enemy

    s = b342
    s["cards"]["42"]["cover"].append({"id": "C1", "type": "Foxholes", "value": 1, "field": True, "capacity": 1})
    s["units"]["US1"] = unit("11", target="31")
    s["units"]["G2"] = german("42", area="C1", steps=1, type="Weapons Team")
    s["units"]["G1"] = german("31", steps=3, target="11", check_open=True)
    enemy.cmd_enemy_action(s, ["G1", "Fall Back", "--target=42"])
    assert s["units"]["G1"]["card"] == "42" and s["units"]["G1"]["area"] == "open"
    assert s["units"]["G2"]["area"] == "C1"


# ---- B7 (review C1): infiltration after the own Point Blank fire


def test_infiltrate_after_own_point_blank_fire(board, monkeypatch):
    from fof import commands, rules

    s = _hq_board(board, monkeypatch)
    s["units"]["1/1"] = unit("22", platoon="1", target="22")
    s["units"]["Enemy 1"] = unit("22", side="Enemy", vof="S", target=None)
    assert commands.infiltrate_possible(s, s["units"]["1/1"], "32")
    with pytest.raises(rules.Violation, match="could infiltrate"):
        commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.2a", "--target=32"])
    commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.2c", "--target=32", "--success=yes"])
    assert s["units"]["1/1"]["card"] == "32"


# ---- B8 (review V4): a lifted Incoming gives the unit under it its old target back in 3.7.1


def test_incoming_removed_in_3_7_1_restores_the_old_target(board):
    from fof import fire, phase

    s = board
    s.update(turn=2, phase="3.7.1", mission="x")
    s["units"]["1/1"] = unit("11")
    s["units"]["E1"] = unit("22", side="Enemy", steps=2)
    fire.open_fire(s, [])
    s["cards"]["11"]["external"].append({"type": "Incoming", "value": -3, "source": "FM"})
    fire.cease_fire_on_los_loss(s, [])
    assert s["units"]["1/1"]["target"] == "11" and s["units"]["1/1"]["_smoke_target"] == "22"
    phase._enter_3_7_1(s, [])
    assert s["units"]["1/1"]["target"] == "22" and fire.vof_against(s, "22", "Enemy") is not None


# ---- B9 (review C2/C9): reconstitute a PLT HQ from the active Staff; only PLT HQs


def test_staff_handing_over_its_own_step_ends_its_impulse(board, monkeypatch):
    from fof import commands

    s = _hq_board(board, monkeypatch, phase="3.3.1c")
    s["commands"]["1st Sgt"] = {"available": 3, "saved": 1, "activated": True, "done": False}
    s["units"]["1st Sgt"] = unit("22", vof=None, type="Staff", steps=1)
    del s["units"]["1st PLT HQ"]
    s["active_hq"] = "1st Sgt"
    s["removed_from_play"] = ["1st PLT HQ"]
    s["rfp_data"] = {"1st PLT HQ": {"level": "PLT", "platoon": "1", "ft_vof": "S"}}
    commands.cmd_order(s, ["1st Sgt", "1st Sgt", "4.2.1d", "--hq=1st PLT HQ"])
    assert "1st PLT HQ" in s["units"] and "1st Sgt" not in s["units"]
    assert s["active_hq"] is None and s["commands"]["1st Sgt"]["done"]


def test_the_co_hq_is_not_reconstituted_by_4_2_1d(board, monkeypatch):
    from fof import commands, rules

    s = _hq_board(board, monkeypatch, phase="3.3.1c")
    s["commands"]["1st Sgt"] = {"available": 3, "saved": 0, "activated": True, "done": False}
    s["units"]["1st Sgt"] = unit("22", vof=None, type="Staff", steps=1)
    s["active_hq"] = "1st Sgt"
    s["removed_from_play"] = ["CO HQ"]
    s["rfp_data"] = {"CO HQ": {"level": "CO", "platoon": None, "ft_vof": "S"}}
    with pytest.raises(rules.Violation, match="not a PLT HQ"):
        commands.cmd_order(s, ["1st Sgt", "1st Sgt", "4.2.1d", "--hq=CO HQ"])


# ---- B10 (review E5/V8): a removed counter leaves no pending check behind


def test_removed_enemy_leaves_no_pending_mine_check(b342):
    from fof import contact, enemy

    s = b342
    s["campaign"] = {}
    s["cards"]["42"]["external"].append(
        {"type": "Mines", "value": -4, "source": "Mines!", "side": "Enemy", "active": False}
    )
    s["units"]["US1"] = unit("11", target="31")
    s["units"]["G1"] = german("31", target="11", check_open=True)
    enemy.cmd_enemy_action(s, ["G1", "Fall Back", "--target=42"])
    assert s["mine_checks"] == ["G1"]
    contact.cmd_enemy(s, ["G1", "remove"])
    assert s["mine_checks"] == [] and "G1" not in s.get("mine_check_info", {})
    contact.mine_lock(s)  # no longer blocks


def test_at_draw_against_a_removed_target_lapses(b36):
    from fof import vehicles

    s = b36
    s.pop("special_rules")
    s["units"]["Sherman 1"] = unit("11", type="Vehicle", vehicle="M4 Sherman 75mm", vof=None, rng=None, steps=2)
    s["units"]["PAK"] = unit(
        "31", side="Enemy", type="Weapons Team", steps=1, at_weapon="75mm AT Gun", vof=None, rng="L", spotted=True
    )
    vehicles.queue_at(s, "PAK", "Sherman 1", [], "action")
    del s["units"]["Sherman 1"]
    vehicles.cmd_at(s, ["5"])  # no KeyError: the draw lapses
    assert not vehicles.at36(s)["queue"]
