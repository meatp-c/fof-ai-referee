"""Review 23.10.2026, combat/fire/phase/geometry part (L370-L399): synthetic boards only, no game folder."""

import copy

import pytest

from conftest import unit


@pytest.fixture(autouse=True)
def quiet(monkeypatch, tmp_path):
    from fof import briefing, state

    monkeypatch.setenv("FOF_PARTIE", str(tmp_path))
    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protokoll"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)


def _text(s):
    return s["protokoll"][-1]["text"]


def _lat(kid, typ, side="US", **extra):
    from fof import combat, rules

    vof, rng = combat.LAT_VALUES[typ]
    return unit(kid, side=side, vof=vof, rng=rng, steps=1, typ=typ, erfahrung=rules.LAT_EXPERIENCE[typ], **extra)


# ---- M39: one removal path


def test_m39_lat_casualty_goes_through_remove_from_play(board):
    """L370: a LAT taking C is recorded in removed_from_play; new_name does not hand its name out again."""
    from fof import combat, commands

    board["einheiten"]["Fire Team 1"] = _lat("22", "Fire Team", assets=["Satchel"], cf=1)
    prot = []
    combat.reduce_unit(board, "Fire Team 1", "C", prot)
    assert "Fire Team 1" not in board["einheiten"]
    assert board["removed_from_play"] == ["Fire Team 1"]
    assert board["karten"]["22"]["casualties"] == 1 and board["karten"]["22"]["assets_boden"] == ["Satchel"]
    assert any("Concentrated Fire marker" in p for p in prot) and "Removed from Play" in prot[-1]
    assert commands.new_name(board, "Fire Team") == "Fire Team 2"


def _capture_board(board, guard_status=()):
    board.update(phase="3.5.1", gefangene=0)
    board["einheiten"]["Paralyzed Team 1"] = _lat("22", "Paralyzed Team", side="Feind", status=["Pinned"])
    board["einheiten"]["Litter Team 1"] = _lat("22", "Litter Team", side="Feind", traegt_casualties=1)
    board["einheiten"]["1/1"] = unit("22", status=list(guard_status))
    return board


def test_m39_prisoners_recorded_and_names_stay_unique(board):
    """L371: captured teams are in removed_from_play; a later Paralyzed Team gets a new name, so the guard's
    wachen[].gefangene stay unambiguous; carried casualties leave with the prisoners (no drop on the card)."""
    from fof import combat, commands

    s = _capture_board(board)
    s["kampagne"] = {}  # v4: the guard step is noted in wachen
    combat.cmd_capture(s, ["Paralyzed Team 1", "1/1"])
    assert "Paralyzed Team 1" not in s["einheiten"] and "Litter Team 1" not in s["einheiten"]
    assert {"Paralyzed Team 1", "Litter Team 1"} <= set(s["removed_from_play"])
    assert s["wachen"][0]["gefangene"] == ["Paralyzed Team 1", "Litter Team 1"]
    assert not s["karten"]["22"].get("casualties") and not s["karten"]["22"].get("casualties_feind")
    assert s["einheiten"]["1/1"]["steps"] == 2 and s["gefangene"] == 2
    assert commands.new_name(s, "Paralyzed Team") == "Paralyzed Team 2"
    assert "Paralyzed Team 1: captured" not in _text(s)  # one line for the group, none per prisoner


def test_m39_enemy_retreat_off_map_returns_package(board):
    """L372: an enemy Paralyzed Team retreating off the map edge leaves via remove_from_play (package back to the pool)."""
    from fof import phase

    board["phase"] = "3.5.2"
    board["pakete"] = {"3": {"name": "G3", "im_spiel": True}}
    board["einheiten"]["Paralyzed Team 1"] = _lat("31", "Paralyzed Team", side="Feind", paket=3)
    board["einheiten"]["1/1"] = unit("21", ziel="31")
    prot = []
    phase.check_retreat(board, prot)
    assert "Paralyzed Team 1" not in board["einheiten"]
    assert board["removed_from_play"] == ["Paralyzed Team 1"]
    assert board["pakete"]["3"]["im_spiel"] is False
    assert any("retreats off-map" in p and "Removed from Play" in p for p in prot)


# ---- H12: missing arguments


@pytest.mark.parametrize(
    "cmd,args,phase_",
    [
        ("combat.cmd_ncm", [], "3.7.4"),
        ("combat.cmd_capture", ["Paralyzed Team 1"], "3.5.1"),
        ("phase.cmd_retreat", [], "3.5.2"),
        ("combat.cmd_ammo", ["lager", "21"], "3.1"),
        ("combat.cmd_ammo", ["lager", "21", "MG", "vier"], "3.1"),
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
        unit("22", typ="Vehicle", fahrzeug="M4 Sherman 75mm", vof="H"),
        unit("22", typ="HQ", vof=None),
    ],
)
def test_low_guard_must_be_a_valid_captor(board, guard):
    """L374: the guard step must be unpinned infantry with a VOF, like any captor [3.5.1, 8.15]."""
    from fof import combat, rules

    s = _capture_board(board)
    s["einheiten"]["2/1"] = guard
    with pytest.raises(rules.Violation, match="Guard 2/1"):
        combat.cmd_capture(s, ["Paralyzed Team 1", "2/1"])
    assert "Paralyzed Team 1" in s["einheiten"]


def test_low_hit_refuses_vehicles(board):
    """L375: VOF against vehicles is resolved with 'at' in 3.6, not with hit."""
    from fof import combat, rules

    board["phase"] = "3.7.4"
    board["einheiten"]["M4 1"] = unit("22", typ="Vehicle", fahrzeug="M4 Sherman 75mm", vof="H")
    with pytest.raises(rules.Violation, match="vehicle"):
        combat.cmd_hit(board, ["M4 1", "HIT", "F"])


def _mtr_sec(board, steps=3):
    board["kampagne"] = {}
    board["aufbau_einheiten"] = {
        tn: unit(None, typ="Weapons Team", vof="S", rng="C", steps=1) for tn in ("1/Mtr", "2/Mtr", "3/Mtr")
    }
    board["einheiten"]["Mtr Sec"] = unit(
        "21",
        typ="Weapons Team",
        steps=steps,
        breakdown="mtr_sec",
        moerser=True,
        munition={"typ": "MTR", "punkte": 3},
        funk=[{"typ": "SCR300", "netz": "CO"}],
    )
    return board


def test_low_breakdown_step_us_mortar_section(board):
    """L376: one breakdown_step for the hit step (reduce_unit) and the last step (cmd_hit)."""
    from fof import combat

    s = _mtr_sec(board, steps=2)
    prot = []
    assert combat.breakdown_step(s, "Mtr Sec", "F", prot)
    assert s["einheiten"]["1/Mtr"]["status"] == ["Fire Team side", "Pinned"]
    assert s["einheiten"]["1/Mtr"]["munition"] == {"typ": "MTR", "punkte": 3}
    assert not combat.breakdown_step(s, "Mtr Sec", None, prot)  # still two steps
    s["einheiten"]["Mtr Sec"]["steps"] = 1
    assert combat.breakdown_step(s, "Mtr Sec", None, prot)
    assert "Mtr Sec" not in s["einheiten"] and s["einheiten"]["3/Mtr"]["status"] == ["Pinned"]
    assert s["einheiten"]["3/Mtr"]["funk"] == [{"typ": "SCR300", "netz": "CO"}]
    assert not combat.breakdown_step(s, "1/Mtr", "F", prot)  # not a section


def test_low_cmd_hit_mortar_section_unchanged(board):
    """L376: HIT F on a 2-step Mortar Section: one step to 1/Mtr (Fire Team side), the last step to 3/Mtr."""
    from fof import combat

    s = _mtr_sec(board, steps=2)
    s["phase"] = "3.7.4"
    s["einheiten"]["Mtr Sec"]["status"] = []
    combat.cmd_hit(s, ["Mtr Sec", "HIT", "F"])
    assert "Mtr Sec" not in s["einheiten"]
    assert {"1/Mtr", "3/Mtr"} <= set(s["einheiten"]) and s["removed_from_play"] == ["Mtr Sec"]


def test_low_breakdown_step_german_section(board):
    """L376: German 81mm section: F/A splits only from the last two steps; the last step becomes 2/81mm Mtr."""
    from fof import combat

    board["mtr_team_de"] = {"1/81mm Mtr": {"vof_rating": "S"}, "2/81mm Mtr": {"vof_rating": "G"}}
    board["einheiten"]["81 Sec"] = unit("31", side="Feind", steps=3, breakdown="mtr_sec_de")
    prot = []
    assert not combat.breakdown_step(board, "81 Sec", "F", prot)  # three steps: generic LAT
    board["einheiten"]["81 Sec"]["steps"] = 2
    assert combat.breakdown_step(board, "81 Sec", "A", prot)
    assert board["einheiten"]["1/81mm Mtr 1"]["status"] == ["Fire Team side", "Pinned"]
    board["einheiten"]["81 Sec"]["steps"] = 1
    assert combat.breakdown_step(board, "81 Sec", None, prot)
    assert "2/81mm Mtr 1" in board["einheiten"] and "81 Sec" not in board["einheiten"]


# ---- phase.py LOW


def test_low_pending_flips_then_one_los_check(board):
    """L377: cease_fire_on_los_loss runs once after all Pending flips; no 'block lifted' message in between."""
    from fof import phase

    board["einheiten"]["1/1"] = unit("31", ziel="11")
    board["einheiten"]["G1"] = unit("11", side="Feind")
    for k in ("21", "31"):  # 21 flips first (card order): the old code saw a half-updated board
        board["karten"][k]["extern"].append({"typ": "Pending", "wert": -2})
    prot = []
    phase.enter_segment(board, "3.7.1", prot)
    e = board["einheiten"]["1/1"]
    assert e["ziel"] == "31" and e["_rauch_ziel"] == "11" and "_vof_sperre" not in e
    assert not any("blocking card" in p for p in prot)
    assert not any("block lifted" in p for p in prot)


# ---- geometry / fire: LOS reason codes, edges, cover


def test_los_detail_codes_and_los_unchanged(board):
    """L378: los_detail gives a reason code; los keeps its (bool, text) result."""
    from fof import geometry

    board["karten"]["21"]["extern"].append({"typ": "Smoke"})
    r = geometry.los_detail(board, "11", "31")
    assert (r.ok, r.code, r.card) == (False, "blocked_between", "21")
    assert geometry.los(board, "11", "31") == (False, r.text)
    assert geometry.los_detail(board, "21", "31").code == "blocked_out"
    assert geometry.los_detail(board, "11", "32").code == "not_straight"
    assert geometry.los(board, "12", "32") == (True, "ok")


def test_missing_recorded_edge_is_not_recorded_not_dark(board):
    """L379: a side missing from the recorded edges gives the 'not recorded' note instead of blocking LOS."""
    from fof import geometry

    board["karten"]["21"]["raender"] = {"links": "dunkel"}  # top/bottom not recorded
    assert geometry.los(board, "11", "31")[0]
    assert any("not recorded" in h for h in board["_hinweise"])
    board["karten"]["21"]["raender"] = {"oben": "dunkel", "unten": "weiss"}
    assert geometry.los_detail(board, "11", "31").code == "dark_edges"
    board["karten"]["21"]["raender"] = {"oben": "weiss", "unten": "weiss"}
    assert geometry.los(board, "11", "31")[0]


def test_cover_of_is_cover_marker(board):
    """L380: one cover lookup; the unknown-card guard applies to both names."""
    from fof import fire, geometry

    assert fire.cover_of(board, unit("22")) is geometry.cover_marker(board, unit("22")) is None
    board["karten"]["22"]["cover"].append({"id": "C1", "typ": "Light Building", "wert": 2})
    e = unit("22", bereich="C1")
    assert fire.cover_of(board, e)["typ"] == "Light Building"
    assert fire.cover_of(board, unit("99", bereich="C1")) is None


def test_cease_fire_on_los_loss_classify_and_apply(board):
    """L381: classify_los_loss names the outcome, apply_los_loss carries it out."""
    from fof import fire

    board["einheiten"]["1/1"] = e = unit("11", ziel="31")
    board["einheiten"]["G1"] = unit("31", side="Feind")
    assert fire.classify_los_loss(board, "1/1", e)[0] == "in_view"
    board["karten"]["21"]["extern"].append({"typ": "Smoke"})
    assert fire.classify_los_loss(board, "1/1", e) == ("blocked_between", "21")
    prot = []
    fire.cease_fire_on_los_loss(board, prot)
    assert e["_vof_sperre"] == "21" and e["ziel"] == "31"
    board["karten"]["21"]["extern"] = []
    board["karten"]["11"]["extern"].append({"typ": "Smoke"})
    fire.cease_fire_on_los_loss(board, prot)
    assert "block lifted" in prot[-2] and e["ziel"] == "11" and e["_rauch_ziel"] == "31"
    board["karten"]["11"]["extern"] = []
    assert fire.classify_los_loss(board, "1/1", e) == ("smoke_lifted", ("31", True))
    fire.cease_fire_on_los_loss(board, prot)
    assert e["ziel"] == "31" and "_rauch_ziel" not in e


# ---- efficiency: fire map cache


def _grazing_board(board):
    board["karten"].update(
        {f"{r}{c}": dict(board["karten"]["11"], reihe=r, spalte=c) for r in (4, 5) for c in (1, 2, 3)}
    )
    for k, c in board["karten"].items():
        board["karten"][k] = copy.deepcopy(c)
    board["einheiten"]["HMG"] = unit("11", vof="H", rng="V", steps=1, tripod=True, ziel="31")
    board["einheiten"]["1/1"] = unit("12", ziel="32", status=["Pinned"])
    board["einheiten"]["G1"] = unit("31", side="Feind", ziel="11")
    board["einheiten"]["G2"] = unit("32", side="Feind", ziel="32", nur_pdf=True, vof="G")
    board["karten"]["33"]["extern"].append({"typ": "Incoming", "wert": -2, "quelle": "FM"})
    return board


def test_fire_cache_gives_identical_results(board):
    """L382: inside fire.cached(s) vof_entries, pdfs_to, crossfire and marker_summary equal the uncached values."""
    from fof import fire, state

    s = _grazing_board(board)
    assert len(fire.grazing_cards(s, "HMG")) > 1
    plain = {k: (fire.vof_entries(s, k), fire.pdfs_to(s, k, "Feind"), fire.pdfs_to(s, k, "US")) for k in s["karten"]}
    summary, activity = state.marker_summary(s), fire.expected_activity(s)
    with fire.cached(s):
        with fire.cached(s):  # nested blocks share the map
            assert {
                k: (fire.vof_entries(s, k), fire.pdfs_to(s, k, "Feind"), fire.pdfs_to(s, k, "US")) for k in s["karten"]
            } == plain
        assert id(s) in fire._FIRE_MAPS
        assert state.marker_summary(s) == summary and fire.expected_activity(s) == activity
    assert id(s) not in fire._FIRE_MAPS  # released: later changes are seen again
    s["einheiten"]["HMG"]["ziel"] = None
    assert fire.vof_entries(s, "21") != plain["21"][0]


def test_ncm_rows_cached_equal(board):
    """L382: NCM rows and groups (now inside cached blocks) are unchanged."""
    from fof import combat, fire, rules

    s = _grazing_board(board)
    s["phase"] = "3.7.3"
    s["kampf_offen"] = ["G1", "G2"]
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

    board.update(
        kampagne={}, phase="3.7.4", zug=2, aufstellung_fertig=True, sniper_offen={"G1": "1/1"}, kampf_offen=["1/1"]
    )
    ids = [p for p, _ in state.sop(board)]
    with pytest.raises(rules.Violation, match="Sniper target G1"):
        phase.check_next_phase(board, ["weiter"], ids, [])
    board.pop("sniper_offen")
    with pytest.raises(rules.Violation, match="Combat Effects still open"):
        phase.check_next_phase(board, ["weiter"], ids, [])
    board["kampf_offen"] = []
    assert phase.check_next_phase(board, ["weiter"], ids, []) == ids[ids.index("3.7.4") + 1]


def test_leave_checks_company_only_with_a_company(board):
    """L383: the CO HQ checks of 3.3.1b/3.3.2a/3.3.2b need a company (no co_hq key otherwise)."""
    from fof import phase, state

    ids = [p for p, _ in state.sop(board)]
    for ph in ("3.3.1b", "3.3.2a", "3.3.2b"):
        board["phase"] = ph
        phase.check_next_phase(board, ["weiter"], ids, [])


def test_enter_hook_for_the_defensive_check_segment(board, monkeypatch):
    """L384: the enemy check hook follows the SOP (3.2.2 in defensive missions, 3.4.2 otherwise)."""
    from fof import enemy, phase

    calls = []
    monkeypatch.setattr(enemy, "prepare_enemy_check", lambda s, prot: calls.append(s["typ"]))
    board["typ"] = "defensiv"
    phase.enter_segment(board, "3.2.2", [])
    phase.enter_segment(board, "3.4.2", [])
    board["typ"] = "offensiv"
    phase.enter_segment(board, "3.4.2", [])
    assert calls == ["defensiv", "offensiv"]
