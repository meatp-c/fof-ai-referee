"""L531-, code review 07.11.2026 block B: game results that matter for Naktong M1 (enemy tanks, bunkers, retreat)."""

import pytest

from conftest import _hq_board, bazooka, german, t34, unit


# ---- B1 (review V3): after a plan-based enemy tank action the US side acts next


def test_us_acts_after_an_enemy_tank_action(b36):
    from fof import rules, vehicles

    s = b36
    s["einheiten"]["T-34 1"] = t34("33")
    s["einheiten"]["T-34 2"] = t34("31")
    s["einheiten"]["Bazooka"] = bazooka("11", status=[rules.ACTIVATED])
    s["einheiten"]["Sherman 1"] = unit(
        "11", typ="Vehicle", fahrzeug="M4 Sherman 75mm", vof=None, rng=None, steps=2, status=[rules.ACTIVATED]
    )
    vehicles.enter_3_6(s, [])
    vehicles.cmd_vehicle(s, ["fertig", "Bazooka"])
    vehicles.cmd_vehicle(s, ["feind", "--einheit=T-34 1"])
    vehicles.cmd_at(s, ["9"])  # Missed
    assert s["at36"]["reaktion_offen"]["schuetzen"] == ["Sherman 1"]  # B2: the shot opens a Reaction Fire window
    vehicles.cmd_vehicle(s, ["reaktion", "pass"])  # the tank action ends
    assert s["at36"]["naechste"] == "US"
    vehicles.cmd_vehicle(s, ["bewegen", "Sherman 1", "12"])  # no "It is the enemy's turn"


# ---- B2 (review V1/V7): US Reaction Fire window holds the enemy tank on the card of its move


def test_reaction_window_stops_the_tank_and_keeps_it_moving(b36):
    from fof import rules, vehicles

    s = b36
    s["karten"]["31"]["cc"] = 2  # the tank drives 33, 22, 31 toward the better card
    s["einheiten"]["T-34 1"] = t34("33")
    s["einheiten"]["Bazooka"] = bazooka("22")
    s["karten"]["22"]["cc"] = 0
    vehicles.enter_3_6(s, [])
    vehicles.cmd_vehicle(s, ["feind"])
    e = s["einheiten"]["T-34 1"]
    w = s["at36"].get("reaktion_offen")
    assert w and w["ziel"] == "T-34 1" and w["schuetzen"] == ["Bazooka"]
    stop = e["karte"]
    assert e.get("in_bewegung")
    with pytest.raises(rules.Violation, match="First decide on Reaction Fire"):
        vehicles.lock(s)
    vehicles.cmd_vehicle(s, ["reaktion", "Bazooka", "T-34 1"])
    item = s["at36"]["queue"][0]
    assert ("Target is moving", 1) in [tuple(z) for z in item["zeilen"]]
    assert e["karte"] == stop and "reaktion_offen" not in s["at36"]


def test_react_pass_closes_the_window_and_the_plan_runs_on(b36):
    from fof import vehicles

    s = b36
    s["karten"]["32"]["cc"] = 2
    s["einheiten"]["T-34 1"] = t34("33")
    s["einheiten"]["Bazooka"] = bazooka("22")
    vehicles.enter_3_6(s, [])
    vehicles.cmd_vehicle(s, ["feind"])
    assert s["at36"].get("reaktion_offen")
    vehicles.cmd_vehicle(s, ["reaktion", "pass"])
    assert "reaktion_offen" not in s["at36"] and s["at36"].get("aktion") is None
    assert vehicles.moved_fired(s["einheiten"]["T-34 1"])


def test_no_reaction_fire_without_an_open_window(b36):
    from fof import rules, vehicles

    s = b36
    s.pop("sonderregeln")
    s["einheiten"]["T-34 1"] = t34("33")
    s["einheiten"]["Bazooka"] = bazooka("22")
    vehicles.enter_3_6(s, [])
    with pytest.raises(rules.Violation, match="No Reaction Fire window"):
        vehicles.cmd_vehicle(s, ["reaktion", "Bazooka", "T-34 1"])
    assert not s["at36"]["queue"]


# ---- B3 (review V2): the tank's Concentrate Fire is bookable with a target


@pytest.mark.parametrize("opt", ["--ziel=Bazooka 1", "--einheit=Bazooka 1"])
def test_tank_concentrate_fire_with_a_target(b36, opt):
    from fof import vehicles

    s = b36
    s["einheiten"]["T-34 1"] = t34("33", vof="H", rng="V", ziel="22")
    s["einheiten"]["Bazooka 1"] = bazooka("22", vof="S")
    s["einheiten"]["Bazooka 2"] = bazooka("22", vof="S")
    vehicles.cmd_vehicle(s, ["feind", "--erfolg=ja", opt])
    assert s["einheiten"]["Bazooka 1"].get("cf") and not s["einheiten"]["Bazooka 2"].get("cf")


# ---- B4-B6: enemy units leaving a Bunker / Deep Bunker, cover capacity (review E1, E6, E2)


def test_unit_out_of_its_bunker_fires_point_blank_and_shifts(b342):
    from fof import enemy, fire

    s = b342
    s["karten"]["32"]["cover"].append({"id": "C1", "typ": "Bunker", "wert": 3, "feld": True, "richtung": [-1, 0]})
    s["einheiten"]["US1"] = unit("22", ziel="32")
    s["einheiten"]["HMG"] = german(
        "32",
        vof="H",
        bereich="C1",
        kein_point_blank=True,
        bunker_richtung="22",
        typ="Weapons Team",
        ziel="22",
        check_offen=True,
    )
    enemy.cmd_enemy_action(s, ["HMG", "Fall Back", "--ziel=41"])
    e = s["einheiten"]["HMG"]
    assert e["karte"] == "41" and "kein_point_blank" not in e and "bunker_richtung" not in e
    s["einheiten"]["US2"] = unit("41")
    e["ziel"] = None
    fire.open_fire(s, [], only=["HMG"])
    assert e["ziel"] == "41"


def test_deep_bunker_unit_gets_no_target_at_placement_and_fires_when_it_leaves(b342):
    import copy

    from fof import contact, enemy, fire, state

    s = b342
    s["kampagne"] = {}
    s["karten"]["11"]["pc"] = "A"
    s["einheiten"]["1/1"] = unit("11")
    pk = {
        "name": "Deep Bunker MG",
        "spotted": True,
        "place_vof": True,
        "einheiten": [
            {
                "einheit": "German HMG",
                "typ": "Weapons Team",
                "vof_rating": "H",
                "reichweite": "L",
                "steps": 1,
                "platz": "max",
                "cover": "Deep Bunker",
                "cover_wert": 3,
            }
        ],
    }
    contact.pc_contact_v4(s, "11", "A1", copy.deepcopy(pk), {"--richtung": "Front"})
    e = s["einheiten"]["German HMG 1"]
    assert e.get("deep_bunker") and e["ziel"] is None and not fire.is_firing(e)
    assert (e["karte"], "11") not in state.pdf_pairs(s)  # no PDF from the bunker (the US fire at it is fine)
    s["einheiten"]["1/1"]["karte"] = "22"
    e["check_offen"] = True
    enemy.cmd_enemy_action(s, ["German HMG 1", "Grenade Attack (or Concentrate Fire)", "--erfolg=ja", "--einheit=1/1"])
    assert "deep_bunker" not in e and e["ziel"] == "22"


def test_fall_back_skips_a_full_foxhole(b342):
    from fof import enemy

    s = b342
    s["karten"]["42"]["cover"].append({"id": "C1", "typ": "Foxholes", "wert": 1, "feld": True, "kapazitaet": 1})
    s["einheiten"]["US1"] = unit("11", ziel="31")
    s["einheiten"]["G2"] = german("42", bereich="C1", steps=1, typ="Weapons Team")
    s["einheiten"]["G1"] = german("31", steps=3, ziel="11", check_offen=True)
    enemy.cmd_enemy_action(s, ["G1", "Fall Back", "--ziel=42"])
    assert s["einheiten"]["G1"]["karte"] == "42" and s["einheiten"]["G1"]["bereich"] == "offen"
    assert s["einheiten"]["G2"]["bereich"] == "C1"


# ---- B7 (review C1): infiltration after the own Point Blank fire


def test_infiltrate_after_own_point_blank_fire(board, monkeypatch):
    from fof import commands, rules

    s = _hq_board(board, monkeypatch)
    s["einheiten"]["1/1"] = unit("22", platoon="1", ziel="22")
    s["einheiten"]["Enemy 1"] = unit("22", side="Feind", vof="S", ziel=None)
    assert commands.infiltrate_possible(s, s["einheiten"]["1/1"], "32")
    with pytest.raises(rules.Violation, match="could infiltrate"):
        commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.2a", "--target=32"])
    commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.2c", "--target=32", "--success=ja"])
    assert s["einheiten"]["1/1"]["karte"] == "32"


# ---- B8 (review V4): a lifted Incoming gives the unit under it its old target back in 3.7.1


def test_incoming_removed_in_3_7_1_restores_the_old_target(board):
    from fof import fire, phase

    s = board
    s.update(zug=2, phase="3.7.1", mission="x")
    s["einheiten"]["1/1"] = unit("11")
    s["einheiten"]["E1"] = unit("22", side="Feind", steps=2)
    fire.open_fire(s, [])
    s["karten"]["11"]["extern"].append({"typ": "Incoming", "wert": -3, "quelle": "FM"})
    fire.cease_fire_on_los_loss(s, [])
    assert s["einheiten"]["1/1"]["ziel"] == "11" and s["einheiten"]["1/1"]["_rauch_ziel"] == "22"
    phase._enter_3_7_1(s, [])
    assert s["einheiten"]["1/1"]["ziel"] == "22" and fire.vof_against(s, "22", "Feind") is not None


# ---- B9 (review C2/C9): reconstitute a PLT HQ from the active Staff; only PLT HQs


def test_staff_handing_over_its_own_step_ends_its_impulse(board, monkeypatch):
    from fof import commands

    s = _hq_board(board, monkeypatch, phase="3.3.1c")
    s["kommandos"]["1st Sgt"] = {"verfuegbar": 3, "gespart": 1, "aktiviert": True, "fertig": False}
    s["einheiten"]["1st Sgt"] = unit("22", vof=None, typ="Staff", steps=1)
    del s["einheiten"]["1st PLT HQ"]
    s["aktiver_hq"] = "1st Sgt"
    s["removed_from_play"] = ["1st PLT HQ"]
    s["rfp_daten"] = {"1st PLT HQ": {"ebene": "PLT", "platoon": "1", "ft_vof": "S"}}
    commands.cmd_order(s, ["1st Sgt", "1st Sgt", "4.2.1d", "--hq=1st PLT HQ"])
    assert "1st PLT HQ" in s["einheiten"] and "1st Sgt" not in s["einheiten"]
    assert s["aktiver_hq"] is None and s["kommandos"]["1st Sgt"]["fertig"]


def test_the_co_hq_is_not_reconstituted_by_4_2_1d(board, monkeypatch):
    from fof import commands, rules

    s = _hq_board(board, monkeypatch, phase="3.3.1c")
    s["kommandos"]["1st Sgt"] = {"verfuegbar": 3, "gespart": 0, "aktiviert": True, "fertig": False}
    s["einheiten"]["1st Sgt"] = unit("22", vof=None, typ="Staff", steps=1)
    s["aktiver_hq"] = "1st Sgt"
    s["removed_from_play"] = ["CO HQ"]
    s["rfp_daten"] = {"CO HQ": {"ebene": "CO", "platoon": None, "ft_vof": "S"}}
    with pytest.raises(rules.Violation, match="not a PLT HQ"):
        commands.cmd_order(s, ["1st Sgt", "1st Sgt", "4.2.1d", "--hq=CO HQ"])


# ---- B10 (review E5/V8): a removed counter leaves no pending check behind


def test_removed_enemy_leaves_no_pending_mine_check(b342):
    from fof import contact, enemy

    s = b342
    s["kampagne"] = {}
    s["karten"]["42"]["extern"].append(
        {"typ": "Mines", "wert": -4, "quelle": "Mines!", "seite": "Feind", "aktiv": False}
    )
    s["einheiten"]["US1"] = unit("11", ziel="31")
    s["einheiten"]["G1"] = german("31", ziel="11", check_offen=True)
    enemy.cmd_enemy_action(s, ["G1", "Fall Back", "--ziel=42"])
    assert s["minen_checks"] == ["G1"]
    contact.cmd_enemy(s, ["G1", "weg"])
    assert s["minen_checks"] == [] and "G1" not in s.get("minen_check_info", {})
    contact.mine_lock(s)  # no longer blocks


def test_at_draw_against_a_removed_target_lapses(b36):
    from fof import vehicles

    s = b36
    s.pop("sonderregeln")
    s["einheiten"]["Sherman 1"] = unit("11", typ="Vehicle", fahrzeug="M4 Sherman 75mm", vof=None, rng=None, steps=2)
    s["einheiten"]["PAK"] = unit(
        "31", side="Feind", typ="Weapons Team", steps=1, at_waffe="75mm AT Gun", vof=None, rng="L", spotted=True
    )
    vehicles.queue_at(s, "PAK", "Sherman 1", [], "action")
    del s["einheiten"]["Sherman 1"]
    vehicles.cmd_at(s, ["5"])  # no KeyError: the draw lapses
    assert not vehicles.at36(s)["queue"]
