"""L539-L549, code review 07.11.2026 block C: edge cases (Out-of-Ammo flip, casualties, Litter Teams, contact grenade,
tank Move & Fire, retreat, pre-draw refusals, response Jam, option parsing, jeep, working fields)."""

import pytest

from conftest import _hq_board, card, german, t34, unit
from fof import grenades  # L556: split from commands

# ---- C1 (review C3/E8): the Out-of-Ammo flip


def test_deliberate_flip_to_front_clears_the_ooa_flag(board, monkeypatch):
    from fof import combat, commands

    s = _hq_board(board, monkeypatch)
    mg = s["einheiten"]["MG"] = unit(
        "22",
        vof="A",
        rng="L",
        steps=1,
        typ="Weapons Team",
        platoon="1",
        fire_team_seite=True,
        ft_vof="S",
        munition={"typ": "MG", "punkte": 1},
    )
    combat.ammo_use(s, "MG", mg, 1, "test", [])
    assert mg.get("ooa_flip")
    commands.cmd_order(s, ["1st PLT HQ", "MG", "4.2.3f", "--ooa-flip=ja"])
    assert "ooa_flip" not in mg
    combat.reduce_unit(s, "MG", "F", [])  # HIT-caused flip now
    s["karten"]["22"]["munition"] = {"MG": 2}
    combat.ammo_pick_up(s, mg, "MG", "MG:2", [])
    assert "Fire Team side" in mg["status"]  # resupply does not undo a HIT-caused flip


def test_enemy_rally_does_not_undo_the_ooa_flip(b342):
    from fof import combat, enemy

    s = b342
    s["kampagne"] = {}
    s["einheiten"]["US1"] = unit("12")
    hmg = german(
        "32",
        vof="H",
        typ="Weapons Team",
        steps=1,
        fire_team_seite=True,
        ft_vof="S",
        typname="German HMG",
        munition={"typ": "MG", "punkte": 1, "start": 6},
        spotted=False,
        check_offen=True,
        ziel="12",
    )
    s["einheiten"]["HMG"] = hmg
    combat.ammo_use(s, "HMG", hmg, 1, "test", [])
    enemy.cmd_enemy_action(s, ["HMG", "Rally"])
    assert "Fire Team side" in hmg["status"] and hmg.get("ooa_flip")


# ---- C2 (review E7): Fall Back with Casualty


def test_litter_team_takes_one_casualty_along(b342):
    from fof import combat, enemy

    s = b342
    s["einheiten"]["US1"] = unit("11", ziel="32")
    s["karten"]["32"]["casualties_feind"] = 2
    lt = german("32", typ="Litter Team", vof=None, check_offen=True)
    combat.set_lat_values(lt, "Litter Team")
    s["einheiten"]["LT"] = lt
    enemy.cmd_enemy_action(s, ["LT", "Fall Back with Casualty", "--ziel=42"])
    assert s["karten"]["32"]["casualties_feind"] == 1 and s["karten"]["42"]["casualties_feind"] == 1


# ---- C3 (review E3/E9)


def test_litter_team_does_not_move_towards_a_casualty_under_vof(b342):
    from fof import combat, enemy, rules

    s = b342
    s["einheiten"]["US1"] = unit("12", ziel="22")
    s["karten"]["21"]["casualties_feind"] = 1
    lt = german("32", typ="Litter Team", vof=None, check_offen=True)
    combat.set_lat_values(lt, "Litter Team")
    s["einheiten"]["LT"] = lt
    with pytest.raises(rules.Violation, match="VOF against it"):
        enemy.cmd_enemy_action(s, ["LT", "Move towards closest Casualty", "--ziel=22"])
    assert lt["karte"] == "32"


def test_enemy_seek_cover_on_a_mined_card_asks_for_a_mine_check(b342):
    from fof import enemy

    s = b342
    s["kampagne"] = {}
    s["optionen"] = {"U20_mine_bei_seek_cover": True}
    s["karten"]["32"]["extern"].append(
        {"typ": "Mines", "wert": -4, "quelle": "Mines!", "seite": "Feind", "aktiv": False}
    )
    s["karten"]["32"]["cover"].append({"id": "C1", "typ": "Basic Cover", "wert": 1, "feld": False})
    s["einheiten"]["US1"] = unit("12", ziel="32")
    s["einheiten"]["G1"] = german("32", ziel="12", check_offen=True)
    enemy.cmd_enemy_action(s, ["G1", "Seek Cover"])
    assert s["einheiten"]["G1"]["bereich"] == "C1" and "G1" in s.get("minen_checks", [])


# ---- C4 (review E4): the G! grenade at contact hits the whole stack


def test_contact_grenade_hits_the_whole_stack(b342):
    import copy

    from fof import contact

    s = b342
    s["kampagne"] = {}
    s["karten"]["11"]["pc"] = "A"
    s["karten"]["11"]["cover"].append({"id": "C1", "typ": "Basic Cover", "wert": 1, "feld": False})
    s["einheiten"]["1/1"] = unit("11", bereich="C1")
    s["einheiten"]["1/2"] = unit("11", bereich="C1")
    pk = {
        "name": "G! team",
        "spotted": True,
        "place_vof": True,
        "einheiten": [
            {
                "einheit": "Rifle Grenade Team",
                "typ": "Weapons Team",
                "vof_rating": "G",
                "reichweite": "L",
                "steps": 1,
                "platz": "max",
                "grenade_ranged": True,
            }
        ],
    }
    contact.pc_contact_v4(
        s, "11", "A1", copy.deepcopy(pk), {"--richtung": "Front", "--granate": "ja", "--einheit": "1/1"}
    )
    assert s["einheiten"]["1/1"]["grenade"] and s["einheiten"]["1/2"]["grenade"]


# ---- C5 (review V5/V6): enemy tank Move & Fire


def _big36(b36):
    s = b36
    s["karten"] = {f"{r}{c}": card(r, c) for r in range(1, 6) for c in range(1, 6)}
    s["karten"]["44"]["cc"] = 2
    return s


def sherman(kid):
    return unit(kid, typ="Vehicle", fahrzeug="M4 Sherman 75mm", vof=None, rng=None, steps=2)


def test_no_move_and_fire_without_the_chart_capability(b36):
    from fof import vehicles

    s = _big36(b36)
    s["einheiten"]["SU 1"] = t34("55", fahrzeug="SU-76M")
    s["einheiten"]["Sherman 1"] = sherman("14")
    vehicles.enter_3_6(s, [])
    vehicles.cmd_vehicle(s, ["feind"])
    plan = [x["art"] for x in s["at36"]["aktion"]["plan"]]
    assert "fire" not in plan and "choose" not in plan


def test_move_and_fire_target_choice_comes_after_the_vof(b36):
    from fof import vehicles

    s = _big36(b36)
    s["einheiten"]["T-34 1"] = t34("55")
    s["einheiten"]["Sherman 1"] = sherman("14")
    s["einheiten"]["Sherman 2"] = sherman("41")
    s["einheiten"]["1/1"] = unit("43", ziel="44")
    vehicles.enter_3_6(s, [])
    vehicles.cmd_vehicle(s, ["feind"])
    st = s["at36"]
    assert st["queue"][0]["art"] == "vof" and not st.get("wahl")
    assert [x["art"] for x in st["aktion"]["plan"]][:2] == ["react", "choose"]


# ---- C6 (review V9): retreat through the move path


def test_retreat_leaves_the_grenade_marker_with_the_stack(board, monkeypatch):
    from fof import briefing, phase, rules, state

    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protokoll"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)
    s = board
    s.update(phase="3.5.2", mission="x")
    s["einheiten"]["E1"] = unit("33", side="Feind", ziel="22")
    s["einheiten"]["PT"] = unit("22", typ="Paralyzed Team", steps=1, vof=None, grenade=[-4])
    s["einheiten"]["FT"] = unit("22", typ="Fire Team", steps=1, grenade=[-4], status=[rules.PINNED])
    phase.cmd_retreat(s, ["PT", "12"])
    assert s["einheiten"]["PT"]["karte"] == "12" and not s["einheiten"]["PT"].get("grenade")
    assert s["einheiten"]["FT"]["grenade"] == [-4]


# ---- C7 (review C5): refusals before the draw prompt


def test_infiltrate_within_a_card_without_vof_is_refused_before_the_draw(board, monkeypatch):
    from fof import commands, rules

    s = _hq_board(board, monkeypatch)
    s["einheiten"]["1/1"] = unit("22", platoon="1")
    s["karten"]["22"]["cover"] = [{"id": "C1", "typ": "Basic Cover", "wert": 1, "feld": False}]
    with pytest.raises(rules.Violation, match="requires a VOF"):
        commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.2g", "--area=C1"])


def test_rally_of_an_unpinned_unit_is_refused_before_the_draw(board, monkeypatch):
    from fof import commands, rules

    s = _hq_board(board, monkeypatch)
    s["einheiten"]["1/1"] = unit("22", platoon="1")
    s["einheiten"]["Enemy 1"] = unit("23", side="Feind", vof="A", ziel="22")
    with pytest.raises(rules.Violation, match="not Pinned"):
        commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.3a"])


def test_reconstitute_squad_without_squad_is_refused_before_the_draw(board, monkeypatch):
    from fof import commands, rules

    s = _hq_board(board, monkeypatch)
    s["einheiten"]["Fire Team 1"] = unit("22", typ="Fire Team", steps=1, platoon="1")
    s["einheiten"]["Fire Team 2"] = unit("22", typ="Fire Team", steps=1, platoon="1")
    s["einheiten"]["Enemy 1"] = unit("23", side="Feind", vof="A", ziel="22")
    with pytest.raises(rules.Violation, match="--squad"):
        commands.cmd_order(s, ["1st PLT HQ", "Fire Team 1", "4.2.3i", "--with=Fire Team 2"])


def test_passenger_cannot_move_under_cover(board, monkeypatch):
    from fof import commands, rules, vehicles

    s = _hq_board(board, monkeypatch)
    s["karten"]["22"]["cover"] = [{"id": "C1", "typ": "Basic Cover", "wert": 1, "feld": False}]
    s["einheiten"]["Jeep"] = vehicles.company_jeep_unit("22")
    s["einheiten"]["1/W/1"] = unit("22", typ="Weapons Team", platoon="1", steps=1, an_bord="Jeep")
    with pytest.raises(rules.Violation, match="on board the Jeep"):
        commands.cmd_order(s, ["1st PLT HQ", "1/W/1", "4.2.2f", "--area=C1"])


# ---- C9 (review K6/K7): option and argument translation


def test_plain_no_is_not_a_yes(board, monkeypatch):
    from fof import commands, rules

    s = _hq_board(board, monkeypatch)
    s["einheiten"]["1/1"] = unit("22", platoon="1", ziel="22")
    s["einheiten"]["Enemy 1"] = unit("22", side="Feind", vof="S", ziel=None)
    with pytest.raises(rules.Violation, match="could infiltrate"):
        commands.cmd_order(s, ["1st PLT HQ", "1/1", "4.2.2a", "--target=32", "--plain=nein"])


def test_free_text_keeps_its_english_words():
    from fof import cli

    out = cli.argv_to_german(["xp", "add", "2", "we", "did", "spend", "a", "promote", "add"])
    assert out == ["xp", "plus", "2", "we", "did", "spend", "a", "promote", "add"]
    assert cli.argv_to_german(["fire", "1/1", "off"])[1:] == ["1/1", "aus"]
    assert cli.argv_to_german(["correct", "status", "1/1", "Pinned", "remove"])[1:] == [
        "status",
        "1/1",
        "Pinned",
        "weg",
    ]


# ---- C10 (review V10): the jeep's experience follows a passenger that changes


def test_jeep_experience_follows_a_flipped_passenger(board):
    from fof import vehicles

    s = board
    s["einheiten"]["Jeep"] = vehicles.company_jeep_unit("21")
    s["einheiten"]["V"] = unit(
        "21", typ="Weapons Team", steps=1, erfahrung="Veteran", an_bord="Jeep", fire_team_seite=True
    )
    vehicles.refresh_jeeps(s)
    assert s["einheiten"]["Jeep"]["erfahrung"] == "Veteran"
    s["einheiten"]["V"]["status"].append("Fire Team side")
    vehicles.refresh_jeeps(s)
    assert s["einheiten"]["Jeep"]["erfahrung"] == "Green"


# ---- C11 (review C10/C11/C12/C13/V15): working fields


def test_indirect_lay_clears_the_direct_lay_working_fields(board, monkeypatch):
    from fof import commands

    s = _hq_board(board, monkeypatch)
    s["einheiten"]["1st PLT HQ"]["karte"] = "12"
    m = s["einheiten"]["Mtr"] = unit(
        "12",
        vof="H",
        rng="C-L",
        steps=2,
        typ="Weapons Team",
        platoon="1",
        moerser=True,
        ziel="12",
        _rauch_ziel="32",
        ziel_offen=["32"],
    )
    s["einheiten"]["Enemy 1"] = unit("32", side="Feind", vof="S", ziel=None)
    commands.cmd_order(s, ["1st PLT HQ", "Mtr", "4.2.4j", "--target=32"])
    assert m.get("indirekt") and "_rauch_ziel" not in m and "ziel_offen" not in m


def test_fire_team_side_is_not_jam_prone():

    assert grenades.jam_prone({"typ": "Weapons Team", "vof_rating": "A", "status": []})
    assert not grenades.jam_prone({"typ": "Weapons Team", "vof_rating": "A", "status": ["Fire Team side"]})


def test_point_blank_shift_clears_old_working_fields(board):
    from fof import fire

    e = unit("22", ziel="33", _vof_sperre="32", _reichweite_vof="32", konzentriert=True)
    fire.set_target(e, "22")
    assert e["ziel"] == "22" and not {"_vof_sperre", "_reichweite_vof", "konzentriert"} & set(e)


# ---- C12 (review E10/E12/E13/E15/K10)


def test_enemy_correction_accepts_the_english_words(b342):
    from fof import contact

    s = b342
    s["kampagne"] = {}
    s["einheiten"]["US1"] = unit("11")
    s["einheiten"]["G1"] = german("31")
    contact.cmd_enemy(s, ["G1", "card=32"])
    assert s["einheiten"]["G1"]["karte"] == "32"
    contact.cmd_enemy(s, ["G1", "remove"])
    assert "G1" not in s["einheiten"]
    s["karten"]["22"]["extern"].append({"typ": "Smoke", "wert": 1, "quelle": "x"})
    contact.cmd_external(s, ["22", "remove"])
    assert s["karten"]["22"]["extern"] == []


def test_second_face_up_pc_marker_applies_8_2_3_and_a_hidden_one_is_promoted(b342):
    from fof import contact, state

    s = b342
    s["aktivitaet"] = "No Contact"
    s["karten"]["23"]["pc"] = "B"
    contact.cmd_pc_v4(s, ["setzen", "23", "A"])
    assert s["karten"]["23"]["pc"] == "A" and "pc2" not in s["karten"]["23"]
    s["karten"]["13"]["pc"] = "A"
    contact.cmd_pc_v4(s, ["setzen", "13", "?"])
    state.clear_pc(s["karten"]["13"])
    assert s["karten"]["13"]["pc"] == "?" and "pc2" not in s["karten"]["13"]


def test_enemy_infiltration_must_step_towards_the_closest_opponent(b342):
    from fof import enemy, rules

    s = b342
    s["einheiten"]["US1"] = unit("11", ziel="31")
    s["einheiten"]["G1"] = german("31", ziel="11", check_offen=True)
    with pytest.raises(rules.Violation, match="does not bring G1 closer"):
        enemy.cmd_enemy_action(s, ["G1", "Infiltrate towards closest opposing unit", "--ziel=41", "--erfolg=ja"])


def test_drop_ammo_names_the_types(board, monkeypatch):
    from fof import rules, setup

    s = _hq_board(board, monkeypatch, phase="3.3.1b")
    s["einheiten"]["MG"] = unit("22", typ="Weapons Team", steps=1, munition={"typ": "MG", "punkte": 4})
    with pytest.raises(rules.Violation, match="MG\\|MTR\\|RKT\\|RCL"):
        setup.cmd_drop(s, ["MG", "AMMO:1"])


# ---- C13 small findings (review V12, V16, K9, K12, K14, E11)


def test_enemy_litter_team_at_its_edge_retreats_off_the_map_with_its_casualty(board):
    from fof import combat, phase

    s = board
    s.update(phase="3.5.1", mission="x")
    s["einheiten"]["US1"] = unit("21", ziel="31")
    s["karten"]["31"]["casualties_feind"] = 1
    lt = unit("31", side="Feind", typ="Litter Team", steps=1, vof=None)
    combat.set_lat_values(lt, "Litter Team")
    s["einheiten"]["LT"] = lt
    phase.check_retreat(s, [])
    assert "LT" not in s["einheiten"] and s["karten"]["31"]["casualties_feind"] == 0


def test_enemy_tank_route_needs_recorded_trafficability(b36):
    from fof import rules, vehicles

    s = b36
    s["terrain_katalog"] = {}
    s["karten"]["32"]["cc"] = 2
    s["einheiten"]["T-34 1"] = t34("33")
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
    data["protokoll"] = data["protokoll"][:1]  # as if an old file had been reused under this number
    snap.write_text(json.dumps(data), encoding="utf-8")
    code, out = fof_cli("undo", "2")
    assert code == 2 and "holds the state after entry 1" in out


def test_this_turn_only_needs_a_weather_value(board, monkeypatch):
    from fof import rules, setup

    s = _hq_board(board, monkeypatch, phase="3.1")
    s["wetter_nur_zug"] = True
    with pytest.raises(rules.Violation, match="needs a weather value"):
        setup.cmd_visibility(s, ["0", "--nur_zug=ja"])
    setup.cmd_visibility(s, ["0", "1"])
    assert "wetter_nur_zug" not in s


def test_extend_refuses_ambiguous_card_ids(board, monkeypatch):
    from fof import rules, setup

    s = _hq_board(board, monkeypatch)
    with pytest.raises(rules.Violation, match="not unique"):
        setup.cmd_extend(s, ["2", "10", "Woods"])
