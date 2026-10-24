"""Review 23.10.2026, enemy/contact/events part (L260-L281): synthetic boards only, no game folder."""

import copy

import pytest

from conftest import unit


@pytest.fixture(autouse=True)
def quiet(monkeypatch, tmp_path):
    from fof import briefing, state

    monkeypatch.setenv("FOF_PARTIE", str(tmp_path))
    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protokoll"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)


def _check_segment(board, typ="offensiv"):
    from fof import enemy

    board["typ"] = typ
    board["phase"] = enemy.enemy_segments(board)[1]
    return board


def _german(kid, **extra):
    extra.setdefault("typname", "German Squad")
    return unit(kid, side="Feind", vof="A", **extra)


def _last_text(s):
    return s["protokoll"][-1]["text"]


# ---- H1: Leader rows with Rifle Grenade


def test_h1_leader_rifle_grenade_rows_are_reachable(board):
    """L260 (review H1): the guard compared with the untranslated row id 'keine'; Z5/Z6 Leader rows never came up."""
    from fof import enemy

    board["kampagne"] = {}
    board["feind_taktik"] = "Hasty"
    board["einheiten"]["US1"] = unit("21")
    board["einheiten"]["G1"] = _german("31", ziel="21")
    board["einheiten"]["L1"] = unit(
        "31", side="Feind", vof=None, typ="Leader", leader=True, rifle_grenades=2, typname="German Leader"
    )
    row, col, res = enemy.enemy_row(board, "L1")
    assert row.startswith("Z5 Leader with Rifle Grenade") and res == {"1": "No Action", "2": "Grenade Attack"}
    # under fire without cover: the generic Z6 becomes the Leader's Z6 (K28)
    board["einheiten"]["US1"]["ziel"] = "31"
    row, _, _ = enemy.enemy_row(board, "L1")
    assert row.startswith("Z6 Leader with Rifle Grenade under fire")
    assert enemy.ROW_NONE == "none"


# ---- H2: segments from the sequence of play


def test_h2_enemy_segments_follow_the_sequence_of_play(board):
    from fof import enemy

    assert enemy.enemy_segments(board) == ("3.4.1", "3.4.2")
    board["typ"] = "defensiv"
    assert enemy.enemy_segments(board) == ("3.2.1", "3.2.2")


def test_h2_enemy_action_and_check_in_a_defensive_mission(board):
    """L261 (review H2): in a defensive mission enemyaction was refused in 3.2.2 (hard-wired 3.4.2)."""
    from fof import enemy, rules

    _check_segment(board, "defensiv")
    board["einheiten"]["G1"] = _german("31", check_offen=True)
    enemy.cmd_enemy_action(board, ["G1", "No Action"])
    assert board["einheiten"]["G1"]["check_offen"] is False
    board["typ"] = "offensiv"  # 3.2.2 is no segment of an offensive mission
    with pytest.raises(rules.Violation, match="3.4.2"):
        enemy.cmd_enemy_action(board, ["G1", "No Action"])


def test_h2_event_units_skip_the_check_of_the_defensive_segment(board):
    """L261/L281: units of this turn's Enemy Higher HQ Event make no Activity Check; prepare_enemy_check closes them."""
    from fof import enemy

    _check_segment(board, "defensiv")
    board["zug"] = 2
    board["ereignis_erledigt"] = [2, "3.2.1"]
    board["ereignis_einheiten"] = ["G1"]
    board["einheiten"]["G1"] = _german("31")
    board["einheiten"]["G2"] = _german("32")
    prot = []
    enemy.prepare_enemy_check(board, prot)
    assert board["einheiten"]["G1"]["check_offen"] is False and board["einheiten"]["G2"]["check_offen"] is True
    assert "no Activity Check for G1" in prot[0]


# ---- H3: placement directions by identity


def test_h3_two_equal_package_units_get_their_own_direction(board):
    """L275 (review H3): own.index(u) compared dicts by value; the second equal unit reused the first direction."""
    from fof import contact

    u1 = {"platz": "max", "einheit": "German Squad", "typname": "German Squad", "reichweite": "L", "vof_rating": "A"}
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

    board["kampagne"] = {}
    board["karten"]["31"]["cover"] = [{"id": "C1", "typ": "Deep Bunker", "wert": 3}]
    board["karten"]["21"]["cover"] = [
        {"id": "C1", "typ": "Basic Cover", "wert": 1},
        {"id": "C2", "typ": "Foxholes", "wert": 2},
    ]
    board["karten"]["21"]["extern"] = [{"typ": "Mines", "wert": -1}]
    g = _german("31", bereich="C1", deep_bunker="C1", grenade=[-4], munition={"typ": "MG", "punkte": 9, "start": 6})
    board["einheiten"]["G1"] = g
    prot = []
    chosen = enemy.move_enemy(board, "G1", "21", prot, how="infiltrates", exposed=False)
    assert chosen["id"] == "C2" and g["bereich"] == "C2" and g["karte"] == "21"
    assert "deep_bunker" not in g and fire.can_fire(g)
    assert g["grenade"] == [] and board["karten"]["31"]["grenade_miss"]  # M21: also for infiltration
    assert "Exposed" not in g["status"]
    assert "G1" in board["minen_checks"]


def test_move_enemy_fixed_cover_to_fixed_cover_is_not_exposed(board):
    """[RULE 5.1.2 p.32] trench to trench on adjacent cards: not Exposed (now for every enemy move)."""
    from fof import enemy, rules

    ft = rules.FIXED_COVER[0]
    board["karten"]["31"]["cover"] = [{"id": "C1", "typ": ft, "wert": 2}]
    board["karten"]["21"]["cover"] = [{"id": "C1", "typ": ft, "wert": 2}]
    board["einheiten"]["G1"] = _german("31", bereich="C1")
    enemy.move_enemy(board, "G1", "21", [])
    assert "Exposed" not in board["einheiten"]["G1"]["status"]
    board["einheiten"]["G2"] = _german("32")
    enemy.move_enemy(board, "G2", "22", [], cover=False)
    assert "Exposed" in board["einheiten"]["G2"]["status"] and board["einheiten"]["G2"]["bereich"] == "offen"


def test_m26_seek_cover_takes_the_highest_free_marker(board):
    from fof import enemy

    _check_segment(board)
    board["karten"]["31"]["cover"] = [
        {"id": "C1", "typ": "Basic Cover", "wert": 1},
        {"id": "C2", "typ": "Foxholes", "wert": 2},
    ]
    board["einheiten"]["G1"] = _german("31")
    enemy.cmd_enemy_action(board, ["G1", "Move into or Seek Cover"])
    assert board["einheiten"]["G1"]["bereich"] == "C2"


def test_contact_enemy_card_correction_uses_the_move_path(board):
    """L264 (review M19): 'enemy <unit> card=..' left deep_bunker behind."""
    from fof import contact

    board["karten"]["31"]["cover"] = [{"id": "C1", "typ": "Deep Bunker", "wert": 3}]
    board["einheiten"]["G1"] = _german("31", bereich="C1", deep_bunker="C1")
    contact.cmd_enemy(board, ["G1", "karte=21"])
    g = board["einheiten"]["G1"]
    assert g["karte"] == "21" and g["bereich"] == "offen" and "deep_bunker" not in g and "Exposed" in g["status"]


def test_m22_event_fall_back_like_the_activity_check(board):
    """L278 (review M22): restricted movers stay under VOF, map edge gives a protocol line, Deep Bunker is left."""
    from fof import events

    board["kampagne"] = {}
    board["karten"]["22"]["cover"] = [{"id": "C1", "typ": "Deep Bunker", "wert": 3}]
    board["einheiten"]["G1"] = _german("22", bereich="C1", deep_bunker="C1")
    board["einheiten"]["LT"] = unit("21", side="Feind", vof=None, typ="Litter Team")
    board["einheiten"]["G3"] = _german("33")
    board["karten"]["31"]["extern"] = [{"typ": "Incoming", "wert": -3, "quelle": "Mortar"}]
    board["optionen"]["U18_fall_back_rand_offmap"] = False  # reading b: the unit stays at the map edge
    prot = []
    events.enemy_event(board, {"id": "fall_back", "text": "Fall Back"}, {}, prot)
    g1 = board["einheiten"]["G1"]
    assert g1["karte"] == "32" and "deep_bunker" not in g1
    assert board["einheiten"]["LT"]["karte"] == "21" and any("no Fall Back possible" in x for x in prot)
    assert board["einheiten"]["G3"]["karte"] == "33" and any("G3: no card behind 33" in x for x in prot)
    assert set(board["ereignis_einheiten"]) == {"G1", "LT", "G3"}


# ---- M20, M23, M25, M27, M28, M11


def test_m20_deep_bunker_exit_with_a_target_tie(board):
    """L273 (review M20): leaving the Deep Bunker with two equal targets asks for --target instead of 'not firing'."""
    from fof import enemy, rules

    _check_segment(board)
    board["karten"]["32"]["cover"] = [{"id": "C1", "typ": "Deep Bunker", "wert": 3}]
    board["einheiten"]["G1"] = _german("32", bereich="C1", deep_bunker="C1")
    board["einheiten"]["US1"] = unit("21")
    board["einheiten"]["US2"] = unit("23")
    args = ["G1", "Grenade Attack (or Concentrate Fire)", "--erfolg=nein"]
    with pytest.raises(rules.Violation, match="--target"):
        enemy.cmd_enemy_action(copy.deepcopy(board), args)  # a Violation saves nothing: the CLI reloads the state
    enemy.cmd_enemy_action(board, args + ["--ziel=23"])
    g = board["einheiten"]["G1"]
    assert g["ziel"] == "23" and g["bereich"] == "offen" and "deep_bunker" not in g


def test_m23_advance_without_a_card_ahead_is_a_violation(board):
    from fof import enemy, rules

    _check_segment(board)
    del board["karten"]["21"]
    board["einheiten"]["G1"] = _german("31", check_offen=True)
    with pytest.raises(rules.Violation, match="card 21"):
        enemy.cmd_enemy_action(board, ["G1", "Advance Straight Ahead"])
    assert board["einheiten"]["G1"]["check_offen"] is True


def test_m25_auto_command_for_a_spotter_is_executable(board):
    from fof import cli, enemy, options

    board["kampagne"] = {}
    board["einheiten"]["US1"] = unit("21")
    board["einheiten"]["SP"] = unit("31", side="Feind", vof=None, typ="Spotter", spotter=True, missionen=1)
    row, col, res = enemy.enemy_row(board, "SP")
    assert col == "Auto" and res == {"Auto": "Call for Fire"}
    cmd = enemy.auto_command(board, "SP", res["Auto"])
    assert cmd.startswith('fof.py enemyaction "SP" "Call for Fire" --target=21')
    argv = cli.argv_to_german(["enemyaction", "SP", "Call for Fire", "--target=21", "--success=yes"])
    assert options.parse_opts(argv[3:]) == {"--ziel": "21", "--erfolg": "ja"}


def test_m27_m11_enemy_grenade_default_and_target_check(board):
    """L274 (review M27): default Grenade VOF -4; L265 (review M11): --unit must be an opponent on the attacked card."""
    from fof import enemy, rules

    _check_segment(board)
    board["einheiten"]["G1"] = _german("21")
    board["einheiten"]["G2"] = _german("21", typname="German MG")
    board["einheiten"]["US1"] = unit("21")
    board["einheiten"]["US2"] = unit("22")
    for bad in ("G2", "US2"):
        with pytest.raises(rules.Violation):
            enemy.cmd_enemy_action(board, ["G1", "Grenade Attack", "--erfolg=ja", f"--einheit={bad}"])
    enemy.cmd_enemy_action(board, ["G1", "Grenade Attack", "--erfolg=ja", "--einheit=US1"])
    assert board["einheiten"]["US1"]["grenade"] == [rules.GRENADE_VOF_DEFAULT] == [-4]


def test_m11_contact_grenade_target_must_be_an_opponent(board):
    from fof import enemy, rules

    board["einheiten"]["G1"] = _german("31")
    with pytest.raises(rules.Violation, match="own side"):
        enemy.grenade_target_check(board, "31", "G1", board["einheiten"]["G1"])


def test_m28_z7_compares_directions(board):
    """L263 (review M28): two PDFs from the same direction are not 'another direction'."""
    from fof import enemy

    for r in (1, 2, 3):
        board["karten"][f"{r}4"] = dict(board["karten"]["11"], reihe=r, spalte=4)
    board["einheiten"]["G1"] = _german("12", ziel="13")
    board["einheiten"]["US1"] = unit("14", ziel="12")  # east, two cards away, own PDF goes east too
    assert not enemy.fire_from_other_direction(board, "12", "13")
    board["einheiten"]["US2"] = unit("32", ziel="12")
    assert enemy.fire_from_other_direction(board, "12", "13")


# ---- H12: argument checks


def test_h12_missing_or_bad_arguments_are_violations(board):
    from fof import contact, enemy, events, rules

    board["einheiten"]["US1"] = unit("21")
    calls = [
        (enemy.cmd_enemy_action, []),
        (enemy.cmd_sniper, ["S"]),
        (contact.cmd_pc, ["frei"]),
        (contact.cmd_pc, ["kontakt", "21"]),
        (contact.cmd_external, ["21"]),
        (contact.cmd_external, ["21", "Incoming", "x"]),
        (contact.cmd_enemy, []),
        (contact.cmd_mine, ["US1"]),
        (contact.cmd_pc_v4, ["aufdecken", "21"]),
    ]
    for fn, args in calls:
        with pytest.raises(rules.Violation):
            fn(board, args)
    with pytest.raises(rules.Violation, match="whole number"):
        contact.building_cover(board, "21", {}, "x", None)
    board.update(zug=2, phase="3.1", ereignistabellen={"freund": [], "feind": []})
    with pytest.raises(rules.Violation, match="whole number"):
        events.cmd_event(board, ["5", "ja", "x"])


# ---- LOW


def test_low_immobile_at_gun_may_seek_cover_but_not_move(board):
    """L270: 'move' also matched 'Move into or Seek Cover'."""
    from fof import enemy, rules

    _check_segment(board)
    board["karten"]["31"]["cover"] = [{"id": "C1", "typ": "Basic Cover", "wert": 1}]
    board["einheiten"]["PAK"] = _german("31", unbeweglich=True)
    with pytest.raises(rules.Violation, match="immobile"):
        enemy.cmd_enemy_action(board, ["PAK", "Move towards closest Casualty", "--ziel=21"])
    enemy.cmd_enemy_action(board, ["PAK", "Move into or Seek Cover"])
    assert board["einheiten"]["PAK"]["bereich"] == "C1"


def test_low_text_with_both_grenade_and_concentrate(board):
    """L272: only the chart result 'Grenade Attack (or Concentrate Fire)' may name both; it resolves by situation."""
    from fof import enemy, rules

    _check_segment(board)
    board["einheiten"]["G1"] = _german("31", ziel="21")
    board["einheiten"]["US1"] = unit("21")
    with pytest.raises(rules.Violation, match="names both"):
        enemy.cmd_enemy_action(board, ["G1", "Grenade Concentrate", "--erfolg=nein"])
    with pytest.raises(rules.Violation, match="Concentrate Fire: draw"):
        enemy.cmd_enemy_action(board, ["G1", "Grenade Attack (or Concentrate Fire)"])


def test_low_trading_fire_with_mine_hit_and_no_mines_marker(board):
    """L266: vof_against(...)[1] was None[1] when only a mine hit made the unit 'under fire'."""
    from fof import enemy

    board["karten"]["31"]["cover"] = [{"id": "C1", "typ": "Basic Cover", "wert": 1}]
    board["einheiten"]["G1"] = _german("31", ziel="21", mine_hit=True, konzentriert=True, bereich="C1")
    board["einheiten"]["US1"] = unit("21")
    row, _, _ = enemy.enemy_row(board, "G1")
    assert row.startswith("Z10")


def test_low_unknown_event_id_is_a_violation_and_displacing_events_book(board):
    """L277: unknown ids fell through and counted as resolved; Cannon/Mortar Displacing did nothing."""
    from fof import events, rules

    for fn in (events.friendly_event, events.enemy_event):
        with pytest.raises(rules.Violation, match="not implemented"):
            fn(board, {"id": "no_such_event", "text": "x"}, {}, [])
    events.friendly_event(board, {"id": "cannon_displacing", "gruppe": "Regimental Cannon Co"}, {}, [])
    assert board["fm_gesperrt"] == {"zug": 1, "gruppe": "Regimental Cannon Co"}


def test_low_counter_attack_bookkeeping_extends(board):
    from fof import events

    board["feind_taktik"] = "Hasty"
    assert events.start_counter_attack(board, {"zuege": 3}) == 3
    board["zug"] = 2
    assert events.start_counter_attack(board, {"zuege": 3, "taktik": "Assault"}) == 4
    assert board["gegenangriff"] == {"taktik_vorher": "Hasty", "bis_zug": 4} and board["feind_taktik"] == "Assault"


def test_low_point_blank_shift_on_contact_ceases_the_old_fire(board):
    """L280: the v4 shift kept 'konzentriert' (and the other fire fields) of the old PDF."""
    from fof import contact

    board["einheiten"]["US1"] = unit("21", ziel="31", konzentriert=True, _rauch_ziel="31")
    board["einheiten"]["G1"] = _german("21", ziel="21")
    contact.contact_tail(board, ["G1"], [])
    us = board["einheiten"]["US1"]
    assert us["ziel"] == "21" and "konzentriert" not in us and "_rauch_ziel" not in us


# ---- structure: the activity chart as data


def test_chart_rows_are_consistent():
    """Structure 4 (L282): every row table names chart rows; each R# column has results covering exactly 1..N."""
    from fof import enemy

    tables = (enemy.V4_ROWS, enemy.LAT_ROWS, enemy.DEFENSIVE_ROWS, enemy.SPECIAL_ROWS, enemy.OFFENSIVE_ROWS)
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

    board["einheiten"]["US1"] = unit("21")
    board["einheiten"]["G1"] = _german("21")
    for tactic, column in (("Delay", "5"), ("Hasty", "4"), ("Deliberate", "3")):
        board["feind_taktik"] = tactic
        row, col, _ = enemy.enemy_row(board, "G1")
        assert row == "Z1 opponent on card, without cover" and col == column
    board["feind_taktik"] = "Overrun"
    row, col, res = enemy.enemy_row(board, "G1")
    assert row.startswith("O1 ") and row.endswith("[Enemy Offensive Activity Check Hierarchy, Overrun]") and col == "6"
    board["einheiten"]["G1"]["status"] = ["Pinned"]
    board["einheiten"]["L1"] = unit("21", side="Feind", vof=None, typ="Leader", leader=True)
    row, col, res = enemy.enemy_row(board, "G1")
    assert row == "P1 Pinned, opponent on card, without cover (With Leader, 8.9)" and col == "4"
