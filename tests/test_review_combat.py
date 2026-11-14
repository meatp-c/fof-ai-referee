"""Review 23.10.2026, combat/fire/phase/geometry part (L370-L399): synthetic boards only, no game folder."""

import copy

import pytest

from conftest import unit


@pytest.fixture(autouse=True)
def quiet(monkeypatch, tmp_path):
    from fof import briefing, state

    monkeypatch.setenv("FOF_GAME", str(tmp_path))
    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protocol"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)


def _text(s):
    return s["protocol"][-1]["text"]


def _lat(card_id, type_, side="US", **extra):
    from fof import combat, rules

    vof, rng = combat.LAT_VALUES[type_]
    return unit(
        card_id, side=side, vof=vof, rng=rng, steps=1, type=type_, experience=rules.LAT_EXPERIENCE[type_], **extra
    )


# ---- M39: one removal path


def test_m39_lat_casualty_goes_through_remove_from_play(board):
    """L370: a LAT taking C is recorded in removed_from_play; new_name does not hand its name out again."""
    from fof import combat, commands

    board["units"]["Fire Team 1"] = _lat("22", "Fire Team", assets=["Satchel"], cf=1)
    prot = []
    combat.reduce_unit(board, "Fire Team 1", "C", prot)
    assert "Fire Team 1" not in board["units"]
    assert board["removed_from_play"] == ["Fire Team 1"]
    assert board["cards"]["22"]["casualties"] == 1 and board["cards"]["22"]["assets_ground"] == ["Satchel"]
    assert any("Concentrated Fire marker" in p for p in prot) and "Removed from Play" in prot[-1]
    assert commands.new_name(board, "Fire Team") == "Fire Team 2"


def _capture_board(board, guard_status=()):
    board.update(phase="3.5.1", prisoners=0)
    board["units"]["Paralyzed Team 1"] = _lat("22", "Paralyzed Team", side="Enemy", status=["Pinned"])
    board["units"]["Litter Team 1"] = _lat("22", "Litter Team", side="Enemy", carries_casualties=1)
    board["units"]["1/1"] = unit("22", status=list(guard_status))
    return board


def test_m39_prisoners_recorded_and_names_stay_unique(board):
    """L371: captured teams are in removed_from_play; a later Paralyzed Team gets a new name, so the guard's
    guards[].prisoners stay unambiguous; carried casualties leave with the prisoners (no drop on the card)."""
    from fof import combat, commands

    s = _capture_board(board)
    s["campaign"] = {}  # v4: the guard step is noted in guards
    combat.cmd_capture(s, ["Paralyzed Team 1", "1/1"])
    assert "Paralyzed Team 1" not in s["units"] and "Litter Team 1" not in s["units"]
    assert {"Paralyzed Team 1", "Litter Team 1"} <= set(s["removed_from_play"])
    assert s["guards"][0]["prisoners"] == ["Paralyzed Team 1", "Litter Team 1"]
    assert not s["cards"]["22"].get("casualties") and not s["cards"]["22"].get("casualties_enemy")
    assert s["units"]["1/1"]["steps"] == 2 and s["prisoners"] == 2
    assert commands.new_name(s, "Paralyzed Team") == "Paralyzed Team 2"
    assert "Paralyzed Team 1: captured" not in _text(s)  # one line for the group, none per prisoner


def test_m39_enemy_retreat_off_map_returns_package(board):
    """L372: an enemy Paralyzed Team retreating off the map edge leaves via remove_from_play (package back to the pool)."""
    from fof import phase

    board["phase"] = "3.5.2"
    board["packages"] = {"3": {"name": "G3", "in_play": True}}
    board["units"]["Paralyzed Team 1"] = _lat("31", "Paralyzed Team", side="Enemy", package=3)
    board["units"]["1/1"] = unit("21", target="31")
    prot = []
    phase.check_retreat(board, prot)
    assert "Paralyzed Team 1" not in board["units"]
    assert board["removed_from_play"] == ["Paralyzed Team 1"]
    assert board["packages"]["3"]["in_play"] is False
    assert any("retreats off-map" in p and "Removed from Play" in p for p in prot)


# ---- H12: missing arguments


@pytest.mark.parametrize(
    "cmd,args,phase_",
    [
        ("combat.cmd_ncm", [], "3.7.4"),
        ("combat.cmd_capture", ["Paralyzed Team 1"], "3.5.1"),
        ("phase.cmd_retreat", [], "3.5.2"),
        ("combat.cmd_ammo", ["depot", "21"], "3.1"),
        ("combat.cmd_ammo", ["depot", "21", "MG", "vier"], "3.1"),
    ],
)
def test_h12_missing_or_bad_arguments_are_violations(board, cmd, args, phase_):
    """L373: no IndexError/ValueError on missing arguments or non-numbers."""
    import importlib

    from fof import rules

    mod, fn = cmd.split(".")
    board["phase"] = phase_
    with pytest.raises(rules.Violation):
        getattr(importlib.import_module(f"fof.{mod}"), fn)(board, list(args))


@pytest.mark.parametrize("what", ["MG", "MG:x", ":2", "MG:0", "MG:2:3"])
def test_h12_ammo_spec(what):
    """L373: Pick Up / Drop ammo as <type>:<n>; anything else is a Violation."""
    from fof import combat, rules

    with pytest.raises(rules.Violation):
        combat.ammo_spec(what)
    assert combat.ammo_spec("MG:2") == ("MG", 2)


# ---- LOW: guard conditions, hit on vehicles, mortar breakdown


@pytest.mark.parametrize(
    "guard",
    [
        unit("22", status=["Pinned"]),
        unit("22", type="Vehicle", vehicle="M4 Sherman 75mm", vof="H"),
        unit("22", type="HQ", vof=None),
    ],
)
def test_low_guard_must_be_a_valid_captor(board, guard):
    """L374: the guard step must be unpinned infantry with a VOF, like any captor [3.5.1, 8.15]."""
    from fof import combat, rules

    s = _capture_board(board)
    s["units"]["2/1"] = guard
    with pytest.raises(rules.Violation, match="Guard 2/1"):
        combat.cmd_capture(s, ["Paralyzed Team 1", "2/1"])
    assert "Paralyzed Team 1" in s["units"]


def test_low_hit_refuses_vehicles(board):
    """L375: VOF against vehicles is resolved with 'at' in 3.6, not with hit."""
    from fof import combat, rules

    board["phase"] = "3.7.4"
    board["units"]["M4 1"] = unit("22", type="Vehicle", vehicle="M4 Sherman 75mm", vof="H")
    with pytest.raises(rules.Violation, match="vehicle"):
        combat.cmd_hit(board, ["M4 1", "HIT", "F"])


def _mtr_sec(board, steps=3):
    board["campaign"] = {}
    board["setup_units"] = {
        tn: unit(None, type="Weapons Team", vof="S", rng="C", steps=1) for tn in ("1/Mtr", "2/Mtr", "3/Mtr")
    }
    board["units"]["Mtr Sec"] = unit(
        "21",
        type="Weapons Team",
        steps=steps,
        breakdown="mtr_sec",
        mortar=True,
        ammo={"type": "MTR", "points": 3},
        radio=[{"type": "SCR300", "net": "CO"}],
    )
    return board


def test_low_breakdown_step_us_mortar_section(board):
    """L376: one breakdown_step for the hit step (reduce_unit) and the last step (cmd_hit)."""
    from fof import combat

    s = _mtr_sec(board, steps=2)
    prot = []
    assert combat.breakdown_step(s, "Mtr Sec", "F", prot)
    assert s["units"]["1/Mtr"]["status"] == ["Fire Team side", "Pinned"]
    assert s["units"]["1/Mtr"]["ammo"] == {"type": "MTR", "points": 3}
    assert not combat.breakdown_step(s, "Mtr Sec", None, prot)  # still two steps
    s["units"]["Mtr Sec"]["steps"] = 1
    assert combat.breakdown_step(s, "Mtr Sec", None, prot)
    assert "Mtr Sec" not in s["units"] and s["units"]["3/Mtr"]["status"] == ["Pinned"]
    assert s["units"]["3/Mtr"]["radio"] == [{"type": "SCR300", "net": "CO"}]
    assert not combat.breakdown_step(s, "1/Mtr", "F", prot)  # not a section


def test_low_cmd_hit_mortar_section_unchanged(board):
    """L376: HIT F on a 2-step Mortar Section: one step to 1/Mtr (Fire Team side), the last step to 3/Mtr."""
    from fof import combat

    s = _mtr_sec(board, steps=2)
    s["phase"] = "3.7.4"
    s["units"]["Mtr Sec"]["status"] = []
    combat.cmd_hit(s, ["Mtr Sec", "HIT", "F"])
    assert "Mtr Sec" not in s["units"]
    assert {"1/Mtr", "3/Mtr"} <= set(s["units"]) and s["removed_from_play"] == ["Mtr Sec"]


def test_low_breakdown_step_german_section(board):
    """L376: German 81mm section: F/A splits only from the last two steps; the last step becomes 2/81mm Mtr."""
    from fof import combat

    board["mtr_team_de"] = {"1/81mm Mtr": {"vof_rating": "S"}, "2/81mm Mtr": {"vof_rating": "G"}}
    board["units"]["81 Sec"] = unit("31", side="Enemy", steps=3, breakdown="mtr_sec_de")
    prot = []
    assert not combat.breakdown_step(board, "81 Sec", "F", prot)  # three steps: generic LAT
    board["units"]["81 Sec"]["steps"] = 2
    assert combat.breakdown_step(board, "81 Sec", "A", prot)
    assert board["units"]["1/81mm Mtr 1"]["status"] == ["Fire Team side", "Pinned"]
    board["units"]["81 Sec"]["steps"] = 1
    assert combat.breakdown_step(board, "81 Sec", None, prot)
    assert "2/81mm Mtr 1" in board["units"] and "81 Sec" not in board["units"]


# ---- phase.py LOW


def test_low_pending_flips_then_one_los_check(board):
    """L377: cease_fire_on_los_loss runs once after all Pending flips; no 'block lifted' message in between."""
    from fof import phase

    board["units"]["1/1"] = unit("31", target="11")
    board["units"]["G1"] = unit("11", side="Enemy")
    for k in ("21", "31"):  # 21 flips first (card order): the old code saw a half-updated board
        board["cards"][k]["external"].append({"type": "Pending", "value": -2})
    prot = []
    phase.enter_segment(board, "3.7.1", prot)
    e = board["units"]["1/1"]
    assert e["target"] == "31" and e["_smoke_target"] == "11" and "_vof_blocked" not in e
    assert not any("blocking card" in p for p in prot)
    assert not any("block lifted" in p for p in prot)


# ---- geometry / fire: LOS reason codes, edges, cover


def test_los_detail_codes_and_los_unchanged(board):
    """L378: los_detail gives a reason code; los keeps its (bool, text) result."""
    from fof import geometry

    board["cards"]["21"]["external"].append({"type": "Smoke"})
    r = geometry.los_detail(board, "11", "31")
    assert (r.ok, r.code, r.card) == (False, "blocked_between", "21")
    assert geometry.los(board, "11", "31") == (False, r.text)
    assert geometry.los_detail(board, "21", "31").code == "blocked_out"
    assert geometry.los_detail(board, "11", "32").code == "not_straight"
    assert geometry.los(board, "12", "32") == (True, "ok")


def test_missing_recorded_edge_is_not_recorded_not_dark(board):
    """L379: a side missing from the recorded edges gives the 'not recorded' note instead of blocking LOS."""
    from fof import geometry

    board["cards"]["21"]["edges"] = {"left": "dunkel"}  # top/bottom not recorded
    assert geometry.los(board, "11", "31")[0]
    assert any("not recorded" in h for h in board["_hints"])
    board["cards"]["21"]["edges"] = {"top": "dunkel", "bottom": "white"}
    assert geometry.los_detail(board, "11", "31").code == "dark_edges"
    board["cards"]["21"]["edges"] = {"top": "white", "bottom": "white"}
    assert geometry.los(board, "11", "31")[0]


def test_cover_of_is_cover_marker(board):
    """L380: one cover lookup; the unknown-card guard applies to both names."""
    from fof import fire, geometry

    assert fire.cover_of(board, unit("22")) is geometry.cover_marker(board, unit("22")) is None
    board["cards"]["22"]["cover"].append({"id": "C1", "type": "Light Building", "value": 2})
    e = unit("22", area="C1")
    assert fire.cover_of(board, e)["type"] == "Light Building"
    assert fire.cover_of(board, unit("99", area="C1")) is None


def test_cease_fire_on_los_loss_classify_and_apply(board):
    """L381: classify_los_loss names the outcome, apply_los_loss carries it out."""
    from fof import fire

    board["units"]["1/1"] = e = unit("11", target="31")
    board["units"]["G1"] = unit("31", side="Enemy")
    assert fire.classify_los_loss(board, "1/1", e)[0] == "in_view"
    board["cards"]["21"]["external"].append({"type": "Smoke"})
    assert fire.classify_los_loss(board, "1/1", e) == ("blocked_between", "21")
    prot = []
    fire.cease_fire_on_los_loss(board, prot)
    assert e["_vof_blocked"] == "21" and e["target"] == "31"
    board["cards"]["21"]["external"] = []
    board["cards"]["11"]["external"].append({"type": "Smoke"})
    fire.cease_fire_on_los_loss(board, prot)
    assert "block lifted" in prot[-2] and e["target"] == "11" and e["_smoke_target"] == "31"
    board["cards"]["11"]["external"] = []
    assert fire.classify_los_loss(board, "1/1", e) == ("smoke_lifted", ("31", True))
    fire.cease_fire_on_los_loss(board, prot)
    assert e["target"] == "31" and "_smoke_target" not in e


# ---- efficiency: fire map cache


def _grazing_board(board):
    board["cards"].update({f"{r}{c}": dict(board["cards"]["11"], row=r, column=c) for r in (4, 5) for c in (1, 2, 3)})
    for k, c in board["cards"].items():
        board["cards"][k] = copy.deepcopy(c)
    board["units"]["HMG"] = unit("11", vof="H", rng="V", steps=1, tripod=True, target="31")
    board["units"]["1/1"] = unit("12", target="32", status=["Pinned"])
    board["units"]["G1"] = unit("31", side="Enemy", target="11")
    board["units"]["G2"] = unit("32", side="Enemy", target="32", pdf_only=True, vof="G")
    board["cards"]["33"]["external"].append({"type": "Incoming", "value": -2, "source": "FM"})
    return board


def test_fire_cache_gives_identical_results(board):
    """L382: inside fire.cached(s) vof_entries, pdfs_to, crossfire and marker_summary equal the uncached values."""
    from fof import fire, state

    s = _grazing_board(board)
    assert len(fire.grazing_cards(s, "HMG")) > 1
    plain = {k: (fire.vof_entries(s, k), fire.pdfs_to(s, k, "Enemy"), fire.pdfs_to(s, k, "US")) for k in s["cards"]}
    summary, activity = state.marker_summary(s), fire.expected_activity(s)
    with fire.cached(s):
        with fire.cached(s):  # nested blocks share the map
            assert {
                k: (fire.vof_entries(s, k), fire.pdfs_to(s, k, "Enemy"), fire.pdfs_to(s, k, "US")) for k in s["cards"]
            } == plain
        assert id(s) in fire._FIRE_MAPS
        assert state.marker_summary(s) == summary and fire.expected_activity(s) == activity
    assert id(s) not in fire._FIRE_MAPS  # released: later changes are seen again
    s["units"]["HMG"]["target"] = None
    assert fire.vof_entries(s, "21") != plain["21"][0]


def test_ncm_rows_cached_equal(board):
    """L382: NCM rows and groups (now inside cached blocks) are unchanged."""
    from fof import combat, fire, rules

    s = _grazing_board(board)
    s["phase"] = "3.7.3"
    s["combat_open"] = ["G1", "G2"]
    with fire.cached(s):
        cached_rows = combat.ncm_rows(s, "G1")
    assert not fire._FIRE_MAPS
    fire._FIRE_MAPS[id(s)] = {}  # an empty map would hide all fire: proves ncm_rows uses an open cache
    try:
        with pytest.raises(rules.Violation, match="No VOF"):
            combat.ncm_rows(s, "G1")
    finally:
        fire._FIRE_MAPS.clear()
    assert combat.ncm_rows(s, "G1") == cached_rows
    groups = combat.ncm_groups(s)
    assert [g[0] for g in groups] == ["31", "32"] and not fire._FIRE_MAPS


# ---- structure: segment tables


def test_leave_checks_keep_their_order(board):
    """L383: LEAVE_CHECKS run in the order of the former if-chain (sniper/line checks before open Combat Effects)."""
    from fof import phase, rules, state

    board.update(campaign={}, phase="3.7.4", turn=2, setup_done=True, sniper_open={"G1": "1/1"}, combat_open=["1/1"])
    ids = [p for p, _ in state.sop(board)]
    with pytest.raises(rules.Violation, match="Sniper target G1"):
        phase.check_next_phase(board, ["next"], ids, [])
    board.pop("sniper_open")
    with pytest.raises(rules.Violation, match="Combat Effects still open"):
        phase.check_next_phase(board, ["next"], ids, [])
    board["combat_open"] = []
    assert phase.check_next_phase(board, ["next"], ids, []) == ids[ids.index("3.7.4") + 1]


def test_leave_checks_company_only_with_a_company(board):
    """L383: the CO HQ checks of 3.3.1b/3.3.2a/3.3.2b need a company (no co_hq key otherwise)."""
    from fof import phase, state

    ids = [p for p, _ in state.sop(board)]
    for ph in ("3.3.1b", "3.3.2a", "3.3.2b"):
        board["phase"] = ph
        phase.check_next_phase(board, ["next"], ids, [])


def test_enter_hook_for_the_defensive_check_segment(board, monkeypatch):
    """L384: the enemy check hook follows the SOP (3.2.2 in defensive missions, 3.4.2 otherwise)."""
    from fof import enemy, phase

    calls = []
    monkeypatch.setattr(enemy, "prepare_enemy_check", lambda s, prot: calls.append(s["type"]))
    board["type"] = "defensive"
    phase.enter_segment(board, "3.2.2", [])
    phase.enter_segment(board, "3.4.2", [])
    board["type"] = "offensive"
    phase.enter_segment(board, "3.4.2", [])
    assert calls == ["defensive", "offensive"]
