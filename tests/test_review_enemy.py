"""Review 23.10.2026, enemy/contact/events part (L260-L281): synthetic boards only, no game folder."""

import copy

import pytest

from conftest import unit


@pytest.fixture(autouse=True)
def quiet(monkeypatch, tmp_path):
    from fof import briefing, state

    monkeypatch.setenv("FOF_GAME", str(tmp_path))
    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protocol"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)


def _check_segment(board, type_="offensive"):
    from fof import enemy

    board["type"] = type_
    board["phase"] = enemy.enemy_segments(board)[1]
    return board


def _german(card_id, **extra):
    extra.setdefault("type_name", "German Squad")
    return unit(card_id, side="Enemy", vof="A", **extra)


def _last_text(s):
    return s["protocol"][-1]["text"]


# ---- H1: Leader rows with Rifle Grenade


def test_h1_leader_rifle_grenade_rows_are_reachable(board):
    """L260 (review H1): the guard compared with the untranslated row id 'none'; Z5/Z6 Leader rows never came up."""
    from fof import enemy

    board["campaign"] = {}
    board["enemy_tactic"] = "Hasty"
    board["units"]["US1"] = unit("21")
    board["units"]["G1"] = _german("31", target="21")
    board["units"]["L1"] = unit(
        "31", side="Enemy", vof=None, type="Leader", leader=True, rifle_grenades=2, type_name="German Leader"
    )
    row, col, res = enemy.enemy_row(board, "L1")
    assert row.startswith("Z5 Leader with Rifle Grenade") and res == {"1": "No Action", "2": "Grenade Attack"}
    # under fire without cover: the generic Z6 becomes the Leader's Z6 (K28)
    board["units"]["US1"]["target"] = "31"
    row, _, _ = enemy.enemy_row(board, "L1")
    assert row.startswith("Z6 Leader with Rifle Grenade under fire")
    assert enemy.ROW_NONE == "none"


# ---- H2: segments from the sequence of play


def test_h2_enemy_segments_follow_the_sequence_of_play(board):
    from fof import enemy

    assert enemy.enemy_segments(board) == ("3.4.1", "3.4.2")
    board["type"] = "defensive"
    assert enemy.enemy_segments(board) == ("3.2.1", "3.2.2")


def test_h2_enemy_action_and_check_in_a_defensive_mission(board):
    """L261 (review H2): in a defensive mission enemyaction was refused in 3.2.2 (hard-wired 3.4.2)."""
    from fof import enemy, rules

    _check_segment(board, "defensive")
    board["units"]["G1"] = _german("31", check_open=True)
    enemy.cmd_enemy_action(board, ["G1", "No Action"])
    assert board["units"]["G1"]["check_open"] is False
    board["type"] = "offensive"  # 3.2.2 is no segment of an offensive mission
    with pytest.raises(rules.Violation, match="3.4.2"):
        enemy.cmd_enemy_action(board, ["G1", "No Action"])


def test_h2_event_units_skip_the_check_of_the_defensive_segment(board):
    """L261/L281: units of this turn's Enemy Higher HQ Event make no Activity Check; prepare_enemy_check closes them."""
    from fof import enemy

    _check_segment(board, "defensive")
    board["turn"] = 2
    board["events_done"] = [2, "3.2.1"]
    board["event_units"] = ["G1"]
    board["units"]["G1"] = _german("31")
    board["units"]["G2"] = _german("32")
    prot = []
    enemy.prepare_enemy_check(board, prot)
    assert board["units"]["G1"]["check_open"] is False and board["units"]["G2"]["check_open"] is True
    assert "no Activity Check for G1" in prot[0]


# ---- H3: placement directions by identity


def test_h3_two_equal_package_units_get_their_own_direction(board):
    """L275 (review H3): own.index(u) compared dicts by value; the second equal unit reused the first direction."""
    from fof import contact

    u1 = {"place": "max", "unit": "German Squad", "type_name": "German Squad", "range": "L", "vof_rating": "A"}
    u2 = dict(u1)
    places = []
    contact.contact_choose_places(
        board, [u1, u2], [u1, u2], "12", {}, {}, places, ["22", "21"], [], ["Front", "Left Front"], {}
    )
    assert places == ["22", "21"]


# ---- move_enemy (M19, M21, M22, M26)


def test_move_enemy_leaves_deep_bunker_takes_best_cover_and_expires_grenade(board):
    """L264 (review M19, M21, M26): one move path; the Deep Bunker id of the old card no longer blocks fire."""
    from fof import enemy, fire

    board["campaign"] = {}
    board["cards"]["31"]["cover"] = [{"id": "C1", "type": "Deep Bunker", "value": 3}]
    board["cards"]["21"]["cover"] = [
        {"id": "C1", "type": "Basic Cover", "value": 1},
        {"id": "C2", "type": "Foxholes", "value": 2},
    ]
    board["cards"]["21"]["external"] = [{"type": "Mines", "value": -1}]
    g = _german("31", area="C1", deep_bunker="C1", grenade=[-4], ammo={"type": "MG", "points": 9, "start": 6})
    board["units"]["G1"] = g
    prot = []
    chosen = enemy.move_enemy(board, "G1", "21", prot, how="infiltrates", exposed=False)
    assert chosen["id"] == "C2" and g["area"] == "C2" and g["card"] == "21"
    assert "deep_bunker" not in g and fire.can_fire(g)
    assert g["grenade"] == [] and board["cards"]["31"]["grenade_miss"]  # M21: also for infiltration
    assert "Exposed" not in g["status"]
    assert "G1" in board["mine_checks"]


def test_move_enemy_fixed_cover_to_fixed_cover_is_not_exposed(board):
    """[RULE 5.1.2 p.32] trench to trench on adjacent cards: not Exposed (now for every enemy move)."""
    from fof import enemy, rules

    ft = rules.FIXED_COVER[0]
    board["cards"]["31"]["cover"] = [{"id": "C1", "type": ft, "value": 2}]
    board["cards"]["21"]["cover"] = [{"id": "C1", "type": ft, "value": 2}]
    board["units"]["G1"] = _german("31", area="C1")
    enemy.move_enemy(board, "G1", "21", [])
    assert "Exposed" not in board["units"]["G1"]["status"]
    board["units"]["G2"] = _german("32")
    enemy.move_enemy(board, "G2", "22", [], cover=False)
    assert "Exposed" in board["units"]["G2"]["status"] and board["units"]["G2"]["area"] == "open"


def test_m26_seek_cover_takes_the_highest_free_marker(board):
    from fof import enemy

    _check_segment(board)
    board["cards"]["31"]["cover"] = [
        {"id": "C1", "type": "Basic Cover", "value": 1},
        {"id": "C2", "type": "Foxholes", "value": 2},
    ]
    board["units"]["G1"] = _german("31")
    enemy.cmd_enemy_action(board, ["G1", "Move into or Seek Cover"])
    assert board["units"]["G1"]["area"] == "C2"


def test_contact_enemy_card_correction_uses_the_move_path(board):
    """L264 (review M19): 'enemy <unit> card=..' left deep_bunker behind."""
    from fof import contact

    board["cards"]["31"]["cover"] = [{"id": "C1", "type": "Deep Bunker", "value": 3}]
    board["units"]["G1"] = _german("31", area="C1", deep_bunker="C1")
    contact.cmd_enemy(board, ["G1", "card=21"])
    g = board["units"]["G1"]
    assert g["card"] == "21" and g["area"] == "open" and "deep_bunker" not in g and "Exposed" in g["status"]


def test_m22_event_fall_back_like_the_activity_check(board):
    """L278 (review M22): restricted movers stay under VOF, map edge gives a protocol line, Deep Bunker is left."""
    from fof import events

    board["campaign"] = {}
    board["cards"]["22"]["cover"] = [{"id": "C1", "type": "Deep Bunker", "value": 3}]
    board["units"]["G1"] = _german("22", area="C1", deep_bunker="C1")
    board["units"]["LT"] = unit("21", side="Enemy", vof=None, type="Litter Team")
    board["units"]["G3"] = _german("33")
    board["cards"]["31"]["external"] = [{"type": "Incoming", "value": -3, "source": "Mortar"}]
    board["options"]["U18_fall_back_edge_offmap"] = False  # reading b: the unit stays at the map edge
    prot = []
    events.enemy_event(board, {"id": "fall_back", "text": "Fall Back"}, {}, prot)
    g1 = board["units"]["G1"]
    assert g1["card"] == "32" and "deep_bunker" not in g1
    assert board["units"]["LT"]["card"] == "21" and any("no Fall Back possible" in x for x in prot)
    assert board["units"]["G3"]["card"] == "33" and any("G3: no card behind 33" in x for x in prot)
    assert set(board["event_units"]) == {"G1", "LT", "G3"}


# ---- M20, M23, M25, M27, M28, M11


def test_m20_deep_bunker_exit_with_a_target_tie(board):
    """L273 (review M20): leaving the Deep Bunker with two equal targets asks for --target instead of 'not firing'."""
    from fof import enemy, rules

    _check_segment(board)
    board["cards"]["32"]["cover"] = [{"id": "C1", "type": "Deep Bunker", "value": 3}]
    board["units"]["G1"] = _german("32", area="C1", deep_bunker="C1")
    board["units"]["US1"] = unit("21")
    board["units"]["US2"] = unit("23")
    args = ["G1", "Grenade Attack (or Concentrate Fire)", "--success=no"]
    with pytest.raises(rules.Violation, match="--target"):
        enemy.cmd_enemy_action(copy.deepcopy(board), args)  # a Violation saves nothing: the CLI reloads the state
    enemy.cmd_enemy_action(board, args + ["--target=23"])
    g = board["units"]["G1"]
    assert g["target"] == "23" and g["area"] == "open" and "deep_bunker" not in g


def test_m23_advance_without_a_card_ahead_is_a_violation(board):
    from fof import enemy, rules

    _check_segment(board)
    del board["cards"]["21"]
    board["units"]["G1"] = _german("31", check_open=True)
    with pytest.raises(rules.Violation, match="card 21"):
        enemy.cmd_enemy_action(board, ["G1", "Advance Straight Ahead"])
    assert board["units"]["G1"]["check_open"] is True


def test_m25_auto_command_for_a_spotter_is_executable(board):
    from fof import cli, enemy, options

    board["campaign"] = {}
    board["units"]["US1"] = unit("21")
    board["units"]["SP"] = unit("31", side="Enemy", vof=None, type="Spotter", spotter=True, missions=1)
    row, col, res = enemy.enemy_row(board, "SP")
    assert col == "Auto" and res == {"Auto": "Call for Fire"}
    cmd = enemy.auto_command(board, "SP", res["Auto"])
    assert cmd.startswith('fof.py enemyaction "SP" "Call for Fire" --target=21')
    argv = cli.normalize_argv(["enemyaction", "SP", "Call for Fire", "--target=21", "--success=yes"])
    assert options.parse_opts(argv[3:]) == {"--target": "21", "--success": "yes"}


def test_m27_m11_enemy_grenade_default_and_target_check(board):
    """L274 (review M27): default Grenade VOF -4; L265 (review M11): --unit must be an opponent on the attacked card."""
    from fof import enemy, rules

    _check_segment(board)
    board["units"]["G1"] = _german("21")
    board["units"]["G2"] = _german("21", type_name="German MG")
    board["units"]["US1"] = unit("21")
    board["units"]["US2"] = unit("22")
    for bad in ("G2", "US2"):
        with pytest.raises(rules.Violation):
            enemy.cmd_enemy_action(board, ["G1", "Grenade Attack", "--success=yes", f"--einheit={bad}"])
    enemy.cmd_enemy_action(board, ["G1", "Grenade Attack", "--success=yes", "--unit=US1"])
    assert board["units"]["US1"]["grenade"] == [rules.GRENADE_VOF_DEFAULT] == [-4]


def test_m11_contact_grenade_target_must_be_an_opponent(board):
    from fof import enemy, rules

    board["units"]["G1"] = _german("31")
    with pytest.raises(rules.Violation, match="own side"):
        enemy.grenade_target_check(board, "31", "G1", board["units"]["G1"])


def test_m28_z7_compares_directions(board):
    """L263 (review M28): two PDFs from the same direction are not 'another direction'."""
    from fof import enemy

    for r in (1, 2, 3):
        board["cards"][f"{r}4"] = dict(board["cards"]["11"], row=r, column=4)
    board["units"]["G1"] = _german("12", target="13")
    board["units"]["US1"] = unit("14", target="12")  # east, two cards away, own PDF goes east too
    assert not enemy.fire_from_other_direction(board, "12", "13")
    board["units"]["US2"] = unit("32", target="12")
    assert enemy.fire_from_other_direction(board, "12", "13")


# ---- H12: argument checks


def test_h12_missing_or_bad_arguments_are_violations(board):
    from fof import contact, enemy, events, rules

    board["units"]["US1"] = unit("21")
    calls = [
        (enemy.cmd_enemy_action, []),
        (enemy.cmd_sniper, ["S"]),
        (contact.cmd_pc, ["clear"]),
        (contact.cmd_pc, ["contact", "21"]),
        (contact.cmd_external, ["21"]),
        (contact.cmd_external, ["21", "Incoming", "x"]),
        (contact.cmd_enemy, []),
        (contact.cmd_mine, ["US1"]),
        (contact.cmd_pc_campaign, ["reveal", "21"]),
    ]
    for fn, args in calls:
        with pytest.raises(rules.Violation):
            fn(board, args)
    with pytest.raises(rules.Violation, match="whole number"):
        contact.building_cover(board, "21", "x", None)
    board.update(turn=2, phase="3.1", event_tables={"friendly": [], "enemy": []})
    with pytest.raises(rules.Violation, match="whole number"):
        events.cmd_event(board, ["5", "yes", "x"])


# ---- LOW


def test_low_immobile_at_gun_may_seek_cover_but_not_move(board):
    """L270: 'move' also matched 'Move into or Seek Cover'."""
    from fof import enemy, rules

    _check_segment(board)
    board["cards"]["31"]["cover"] = [{"id": "C1", "type": "Basic Cover", "value": 1}]
    board["units"]["PAK"] = _german("31", immobile=True)
    with pytest.raises(rules.Violation, match="immobile"):
        enemy.cmd_enemy_action(board, ["PAK", "Move towards closest Casualty", "--target=21"])
    enemy.cmd_enemy_action(board, ["PAK", "Move into or Seek Cover"])
    assert board["units"]["PAK"]["area"] == "C1"


def test_low_text_with_both_grenade_and_concentrate(board):
    """L272: only the chart result 'Grenade Attack (or Concentrate Fire)' may name both; it resolves by situation."""
    from fof import enemy, rules

    _check_segment(board)
    board["units"]["G1"] = _german("31", target="21")
    board["units"]["US1"] = unit("21")
    with pytest.raises(rules.Violation, match="names both"):
        enemy.cmd_enemy_action(board, ["G1", "Grenade Concentrate", "--success=no"])
    with pytest.raises(rules.Violation, match="Concentrate Fire: draw"):
        enemy.cmd_enemy_action(board, ["G1", "Grenade Attack (or Concentrate Fire)"])


def test_low_trading_fire_with_mine_hit_and_no_mines_marker(board):
    """L266: vof_against(...)[1] was None[1] when only a mine hit made the unit 'under fire'."""
    from fof import enemy

    board["cards"]["31"]["cover"] = [{"id": "C1", "type": "Basic Cover", "value": 1}]
    board["units"]["G1"] = _german("31", target="21", mine_hit=True, concentrated=True, area="C1")
    board["units"]["US1"] = unit("21")
    row, _, _ = enemy.enemy_row(board, "G1")
    assert row.startswith("Z10")


def test_low_unknown_event_id_is_a_violation_and_displacing_events_book(board):
    """L277: unknown ids fell through and counted as resolved; Cannon/Mortar Displacing did nothing."""
    from fof import events, rules

    for fn in (events.friendly_event, events.enemy_event):
        with pytest.raises(rules.Violation, match="not implemented"):
            fn(board, {"id": "no_such_event", "text": "x"}, {}, [])
    events.friendly_event(board, {"id": "cannon_displacing", "group": "Regimental Cannon Co"}, {}, [])
    assert board["fm_blocked"] == {"turn": 1, "group": "Regimental Cannon Co"}


def test_low_counter_attack_bookkeeping_extends(board):
    from fof import events

    board["enemy_tactic"] = "Hasty"
    assert events.start_counter_attack(board, {"turns": 3}) == 3
    board["turn"] = 2
    assert events.start_counter_attack(board, {"turns": 3, "tactic": "Assault"}) == 4
    assert board["counterattack"] == {"tactic_before": "Hasty", "until_turn": 4} and board["enemy_tactic"] == "Assault"


def test_low_point_blank_shift_on_contact_ceases_the_old_fire(board):
    """L280: the v4 shift kept 'concentrated' (and the other fire fields) of the old PDF."""
    from fof import contact

    board["units"]["US1"] = unit("21", target="31", concentrated=True, _smoke_target="31")
    board["units"]["G1"] = _german("21", target="21")
    contact.contact_tail(board, ["G1"], [])
    us = board["units"]["US1"]
    assert us["target"] == "21" and "concentrated" not in us and "_smoke_target" not in us


# ---- structure: the activity chart as data


def test_chart_rows_are_consistent():
    """Structure 4 (L282): every row table names chart rows; each R# column has results covering exactly 1..N."""
    from fof import enemy

    tables = (enemy.CAMPAIGN_ROWS, enemy.LAT_ROWS, enemy.DEFENSIVE_ROWS, enemy.SPECIAL_ROWS, enemy.OFFENSIVE_ROWS)
    keys = {k for rows in tables for k, _ in rows if k}
    assert keys == set(enemy.CHART)

    def covered(column, result):
        if column == "Auto":
            return set(result) == {"Auto"}
        hits = []
        for band in result:
            lo, _, hi = band.partition("-")
            hits += range(int(lo), int(hi or lo) + 1)
        return sorted(hits) == list(range(1, int(column) + 1))

    for key, row in enemy.CHART.items():
        assert len(row.columns) == len(row.results), key
        for column, result in zip(row.columns, row.results):
            assert covered(column, result), key
        if row.with_leader:
            assert covered(*row.with_leader), key


def test_chart_row_ids_and_tactic_columns(board):
    from fof import enemy

    board["units"]["US1"] = unit("21")
    board["units"]["G1"] = _german("21")
    for tactic, column in (("Delay", "5"), ("Hasty", "4"), ("Deliberate", "3")):
        board["enemy_tactic"] = tactic
        row, col, _ = enemy.enemy_row(board, "G1")
        assert row == "Z1 opponent on card, without cover" and col == column
    board["enemy_tactic"] = "Overrun"
    row, col, res = enemy.enemy_row(board, "G1")
    assert row.startswith("O1 ") and row.endswith("[Enemy Offensive Activity Check Hierarchy, Overrun]") and col == "6"
    board["units"]["G1"]["status"] = ["Pinned"]
    board["units"]["L1"] = unit("21", side="Enemy", vof=None, type="Leader", leader=True)
    row, col, res = enemy.enemy_row(board, "G1")
    assert row == "P1 Pinned, opponent on card, without cover (With Leader, 8.9)" and col == "4"
