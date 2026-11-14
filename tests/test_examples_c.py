"""Worked examples of the rulebook (Series Rules 3rd Ed.), part C: 7.2.2 to 7.2.4, 8.3/8.4, 12.4, 12.6.
Each test rebuilds the situation of the example on the synthetic board and checks the result of the tool
against the example. Line numbers refer to rulebook.txt. Row 1 is the row nearest to the player,
"forward" is row +1; column +1 is to the right."""

import copy

import pytest
from conftest import card, unit

from fof import briefing, campaign, combat, commands, comms, contact, fire, rules, state


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protocol"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)


def tripod_mg(card_id, **extra):
    return unit(card_id, vof="A", rng="V", type="Weapons Team", steps=1, tripod=True, **extra)


# ---------------------------------------------------------------- 7.2.3 Overhead Fire


def test_overhead_fire_example_1_mg_on_level_2_fires_over_level_1_at_level_3(board):
    """[RULE 7.2.3 p.52, 7.2.1 p.51] Line 5517, Overhead Fire Example 1: a tripod MG at elevation 2, a friendly
    unit adjacent at elevation 1, an enemy at Long Range at elevation 3. The MG opens fire on the enemy,
    no VOF marker lies on the friendly card in between.
    Tool since L147 (15.10.2026)."""
    s = board
    s["cards"]["11"]["elevation"] = 2
    s["cards"]["12"]["elevation"] = 1
    s["cards"]["13"]["elevation"] = 3
    s["units"]["MG"] = tripod_mg("11")
    s["units"]["1/1"] = unit("12")
    s["units"]["Enemy 1"] = unit("13", side="Enemy")
    assert fire.overhead_possible(s, "11", "12", "13") is True
    fire.open_fire(s, [])
    assert s["units"]["MG"]["target"] == "13"
    assert fire.effective_fire_target(s, "MG") == "13"
    assert fire.vof_against(s, "13", "Enemy")[:2] == ("A", -1)
    v12 = fire.vof_against(s, "12", "US")  # L552 (review T4): the enemy itself fires at 12, so there is a VOF
    assert v12 is not None and "MG" not in v12[2]  # no VOF of the MG on the card it fires over


def test_overhead_fire_example_2_mg_on_level_1_fires_over_level_1_at_hill_level_2(board):
    """[RULE 7.2.3 p.52, 7.2.1 p.51] Line 5533, Overhead Fire Example 2: tripod MG at elevation 1, friendly unit
    adjacent also at elevation 1, enemy at Long Range on a hill at elevation 2. The MG can fire at the enemy,
    no VOF lies on the friendly card.
    Tool since L147 (15.10.2026)."""
    s = board
    s["cards"]["13"]["elevation"] = 2
    s["units"]["MG"] = tripod_mg("11")
    s["units"]["1/1"] = unit("12")
    s["units"]["Enemy 1"] = unit("13", side="Enemy")
    assert fire.overhead_possible(s, "11", "12", "13") is True
    fire.open_fire(s, [])
    assert s["units"]["MG"]["target"] == "13"
    assert fire.effective_fire_target(s, "MG") == "13"
    assert fire.vof_against(s, "13", "Enemy")[:2] == ("A", -1)
    v12 = fire.vof_against(s, "12", "US")
    assert (
        v12 is None or "MG" not in v12[2]
    )  # L552: no VOF on 12 at all is the expected case here (no enemy fires at 12)
    assert fire.effective_fire_target(s, "MG") != "12"


# ---------------------------------------------------------------- 7.2.2 / 7.2.4 Grazing Fire and FPL (diagram 7.2.5)


def test_grazing_fire_lays_vof_along_all_cards_same_level_or_one_slope(board):
    """[RULE 7.2.2 p.51, 7.2.4 p.53, diagram 7.2.5] Line 5627: Grazing Fire (and FPL) place VOF on all cards in
    range at the same elevation in a straight line; uphill or downhill, but not both. Given a choice (downhill or
    straight across a valley) the MG aims at the nearest enemy along the PDF. FPL is not built in the tool;
    only Grazing Fire with a tripod MG is checked."""
    s = board
    s["units"]["MG"] = tripod_mg("11", target="12")
    s["units"]["Enemy 1"] = unit("12", side="Enemy")
    s["units"]["Enemy 2"] = unit("13", side="Enemy")
    # a) straight line, all at the same elevation: VOF on 12 and 13
    assert fire.grazing_cards(s, "MG") == ["12", "13"]
    assert fire.vof_against(s, "13", "Enemy")[:2] == ("A", -1)
    # b) all uphill 1-2-3: VOF on 12 and 13
    s["cards"]["12"]["elevation"], s["cards"]["13"]["elevation"] = 2, 3
    assert fire.grazing_cards(s, "MG") == ["12", "13"]
    # c) all downhill 3-2-1: VOF on 12 and 13
    s["cards"]["11"]["elevation"], s["cards"]["12"]["elevation"], s["cards"]["13"]["elevation"] = 3, 2, 1
    assert fire.grazing_cards(s, "MG") == ["12", "13"]
    # d) level, then uphill 1-1-2: VOF only on 12, not both
    s["cards"]["11"]["elevation"], s["cards"]["12"]["elevation"], s["cards"]["13"]["elevation"] = 1, 1, 2
    assert fire.grazing_cards(s, "MG") == ["12"]
    assert fire.vof_against(s, "13", "Enemy") is None
    # e) valley 2-1-2: downhill and uphill again is not possible, the MG aims at the nearest enemy (12), 13 stays free
    s["cards"]["11"]["elevation"], s["cards"]["12"]["elevation"], s["cards"]["13"]["elevation"] = 2, 1, 2
    s["units"]["MG"]["target"] = None
    fire.open_fire(s, [])
    assert s["units"]["MG"]["target"] == "12"
    assert fire.effective_fire_target(s, "MG") == "12"
    assert fire.vof_against(s, "12", "Enemy")[:2] == ("A", -1)
    assert fire.vof_against(s, "13", "Enemy") is None


# ---------------------------------------------------------------- 8.3 / 8.4 Paketplatzierung


def _package_example_1_board(board):
    """Trigger on 11 (elevation 1), enemy CCF Rifle Squad on 22 (elevation 1) in a firefight with the trigger,
    Rocky Hill 33 (elevation 3) front right at Long Range, helper card 44 behind it (LOS hidden by the hill)."""
    s = board
    s["cards"]["44"] = card(4, 4)
    s["cards"]["33"].update(terrain="Rocky Hill", elevation=3)
    s["cards"]["11"]["pc"] = "A"
    # trigger: in the example the 1/75mm RCL (H, capable of overhead fire); rebuilt here as an infantry Weapons Team with VOF H
    s["units"]["RCL"] = unit("11", vof="H", rng="V", type="Weapons Team", steps=1, target="22")
    s["units"]["CCF Rifle Squad"] = unit("22", side="Enemy", target="11")
    return s


def _package(name, **unit_fields):
    return {"name": name, "spotted": False, "units": [dict(unit_fields, unit=name, place="max", steps=1)]}


def test_package_example_1_overhead_capable_hmg_placed_behind_its_own_blocking_squad(board, quiet):
    """[RULE 8.4.3 p.63/64, 7.2.1 p.51, 7.2.3 p.52, 8.2.4 p.62] Line 6813, Example 1: the 1/75mm RCL triggers an
    A contact. Package: HMG, Unspotted, to the right at Max LOS (Rocky Hill, elevation 3). Ordinarily nothing could go
    to the right, because the (enemy) CCF Rifle Squad blocks the line; but the HMG can use Overhead Fire, is placed on
    the hill and fires over the squad at the RCL. PC marker removed, Unspotted marker with the HMG. The RCL (also
    capable of overhead fire) could later fire at the spotted HMG with Shift Fire. Rebuild: RCL as an infantry team
    with VOF H, direction "Right" = Right Front (diagonal).
    Tool since L147/L151 (15.10.2026)."""
    s = _package_example_1_board(board)
    control = copy.deepcopy(s)
    assert fire.overhead_possible(s, "33", "22", "11") is True
    pk = _package("HMG", type="Weapons Team", range="V", vof_rating="A", tripod=True)
    contact.pc_contact_campaign(s, "11", "A1", pk, {"--direction": "Right"})
    hmg = s["units"]["HMG 1"]
    assert hmg["card"] == "33" and hmg["spotted"] is False
    assert hmg["target"] == "11" and fire.effective_fire_target(s, "HMG 1") == "11"
    assert fire.vof_against(s, "22", "Enemy") == ("H", -3, ["RCL"])  # only the RCL fire, no VOF of the HMG
    assert "HMG 1" in fire.vof_against(s, "11", "US")[2]
    assert s["cards"]["11"]["pc"] is None
    assert s["units"]["RCL"]["target"] == "22"  # HMG Unspotted: no return fire, the RCL stays on the squad
    # later: HMG spotted, Shift Fire of the RCL (H, overhead across card 22 of the same height at elevation 3)
    hmg["spotted"] = True
    assert fire.overhead_possible(s, "11", "22", "33") is True
    s["units"]["RCL"]["target"] = "33"
    assert fire.effective_fire_target(s, "RCL") == "33"
    assert fire.vof_against(s, "33", "Enemy")[:2] == ("H", -3)
    # counter check "Ordinarily": an LMG without Overhead Fire cannot be placed to the right
    pk2 = _package("LMG", type="Weapons Team", range="L", vof_rating="A")
    with pytest.raises(rules.Violation):
        contact.pc_contact_campaign(control, "11", "A1", pk2, {"--direction": "Right"})


def test_package_example_2_spotter_at_very_long_range_on_the_hill_with_us_units(board, quiet):
    """[RULE 8.4.3 p.63/64, 8.4.1 p.63] Line 6847, Example 2: 1/LMG enters a Woods and triggers a B contact:
    Incoming Artillery with a Spotter in Foxholes, to the left at Max LOS. The hill far left sees the Woods at
    Very Long Range (3 cards); the Spotter sits there Unspotted in the Foxhole and calls artillery onto the Woods,
    while the US units "in the same area" keep firing down the hill into the Marsh at a German Litter Team.
    Reading: the same card as the Spotter; a Spotter sets no PDF, the ban on friendly units on the placement card
    applies only to units with a PDF. Direction "Left" = Left Front (diagonal), the hill as card 40.
    Tool since L151 (15.10.2026)."""
    s = board
    s["cards"]["13"]["terrain"] = "Woods"
    s["cards"]["13"]["pc"] = "B"
    s["cards"]["40"] = card(4, 0, elevation=3, terrain="Hill")
    s["cards"]["41"] = card(4, 1, terrain="Marsh")
    s["units"]["1/LMG"] = unit("13", vof="A", type="Weapons Team", steps=1)
    s["units"]["1/2"] = unit("40", target="41")
    s["units"]["2/2"] = unit("40", target="41")
    s["units"]["German Litter Team"] = unit("41", side="Enemy", vof=None, type="Litter Team", steps=1)
    pk = {
        "name": "Incoming Artillery with Spotter",
        "spotted": False,
        "marker": [{"type": "Incoming", "value": -3}],
        "units": [
            {
                "unit": "Spotter",
                "type": "Spotter",
                "spotter": True,
                "place": "max_los",
                "cover": "Foxhole",
                "cover_value": 1,
                "steps": 1,
            }
        ],
    }
    contact.pc_contact_campaign(s, "13", "B1", pk, {"--direction": "Left"})
    sp = s["units"]["Spotter 1"]
    assert sp["card"] == "40" and sp["spotted"] is False
    foxhole = [c for c in s["cards"]["40"]["cover"] if c["id"] == sp["area"]]
    assert foxhole and foxhole[0]["type"] == "Foxhole"
    assert any(x["type"] == "Incoming" and x["value"] == -3 for x in s["cards"]["13"]["external"])
    assert s["cards"]["13"]["pc"] is None
    # L568: the enemy Target marker of the spotter is announced as a board change, not only booked
    assert s["enemy_target"]["Spotter"] == "13"
    assert "Place the enemy Target marker (Spotter) on 13" in s["protocol"][-1]["text"]
    for n in ("1/2", "2/2"):  # the US units keep firing into the Marsh
        assert s["units"][n]["target"] == "41"


# ---------------------------------------------------------------- 12.4 Replacements (Normandy)


def test_normandy_replacements_six_green_plus_two_veteran_for_ten_casualties(board, quiet):
    """[RULE 12.4 p.81/82] Line 8566: Normandy, six replacement steps per mission; ten casualty steps in the mission
    give six Green and two Veteran replacements (1 per 4 casualties, rounded down), the company starts two steps
    below strength."""
    s = board
    s.update(
        campaign={"attempt": 1, "attempts_max": 2, "xp_table": {}, "replacement_green": 6, "veteran_per_casualties": 4},
        objective_rules={"secure": [], "clear_rows": []},
        us_casualties_total=10,
        co_hq="CO HQ",
    )
    s["units"]["CO HQ"] = unit("11", vof=None, type="HQ", level="CO", steps=1)
    prot = []
    campaign.campaign_mission_end(s, prot)
    text = "\n".join(prot)
    assert s["mission_end"] is True
    assert "replacements 6 Green plus 2 Veteran" in text
    assert "10 casualty steps" in text
    assert 10 - (6 + 2) == 2  # two steps below strength (the example's arithmetic; the tool does not name them)


# ---------------------------------------------------------------- 12.6 Multi-Step Unit Experience Levels

# rows of table 12.6 as far as the examples show them (steps as a list, result).
EXPERIENCE_TABLE_12_6 = [
    (["Line", "Line", "Green", "Green"], "Green"),
    (["Line", "Line", "Line", "Green"], "Line"),
    (["Veteran", "Veteran", "Green"], "Line"),
    (["Veteran", "Veteran", "Line"], "Veteran"),
    (["Line", "Line", "Green"], "Line"),
]


def _unit_experience_function():
    """Looks for a function in the tool that derives the unit level from the step levels per 12.6."""
    names = (
        "unit_experience",
        "multi_step_experience",
        "experience_from_steps",
        "combined_experience",
        "erfahrung_einheit",
        "stufe_aus_steps",
    )
    for mod in (campaign, comms, rules, combat, commands):
        for name in names:
            f = getattr(mod, name, None)
            if callable(f):
                return f
    return None


def test_multi_step_experience_line_squad_with_two_green_lats(board, quiet):
    """[RULE 12.6 p.82, 12.2 p.81, 12.3 p.81] Line 8665: Line squad 2/3 (4 steps) lost two steps; two LATs (Green)
    fill it up. Without a promotion the unit is Green (L+L+G+G); one Experience Point raises a Green step to
    Line, the whole unit is then Line (L+L+L+G). Plus the other rows of the example (3 steps: V+V+G = Line,
    V+V+L = Veteran, L+L+G = Line).
    Tool since L152 (15.10.2026): campaign.experience_from_steps, applied in cmd_reconstitute."""
    s = board
    s.update(
        reattempt_setup=True,
        campaign={"attempt": 2, "attempts_max": 2},
        setup_units={"2/3": dict(unit("11", platoon="3"), steps=4)},
        xp=[{"turn": 1, "attempt": 1, "points": 1, "reason": "test"}],
    )
    s["units"]["2/3"] = unit("11", platoon="3", steps=2)
    s["units"]["Fire Team 1"] = unit("11", vof="S", rng="C", type="Fire Team", steps=1, experience="Green")
    s["units"]["Fire Team 2"] = unit("11", vof="S", rng="C", type="Fire Team", steps=1, experience="Green")
    campaign.cmd_reconstitute(s, ["2/3", "--from=Fire Team 1,Fire Team 2"])
    squad = s["units"]["2/3"]
    assert squad["steps"] == 4
    f = _unit_experience_function()
    if f is None:
        pytest.fail(
            "MISSING: no function for table 12.6 (unit level from step levels); "
            f"cmd_reconstitute leaves 2/3 at {squad['experience']} instead of Green (L+L+G+G)"
        )
    for steps, expected in EXPERIENCE_TABLE_12_6:
        assert f(steps) == expected, f"{'+'.join(x[0] for x in steps)} muss {expected} ergeben"
    assert squad["experience"] == "Green"
    campaign.cmd_xp_promote(s, ["2/3", "--from=Green", "--steps=1"])
    assert squad["experience"] == "Line"
