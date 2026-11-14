"""Fixes from Normandy Mission 5 (L163, L166)."""

import pytest
from conftest import fof_subprocess, m6_state, saved_state, unit
from fof import campaign, combat
from fof import grenades  # L556: split from commands


def test_lat_conversion_takes_counter_values(board):
    """L163 [Normandy Unit Breakdown p.47, K12]: a generic Fire Team (S C) hit with A becomes an Assault Team A P."""
    s = board
    s["units"]["Fire Team 1"] = unit("33", side="Enemy", vof="S", rng="C", steps=1, type="Fire Team", target="22")
    prot = []
    combat.reduce_unit(s, "Fire Team 1", "A", prot)
    e = s["units"]["Fire Team 1"]
    assert e["type"] == "Assault Team"
    assert (e["vof_rating"], e["range"]) == ("A", "P")
    assert "Pinned" in e["status"]


def test_lat_conversion_to_paralyzed_stops_fire(board):
    s = board
    s["units"]["Fire Team 1"] = unit("33", side="Enemy", vof="S", rng="C", steps=1, type="Fire Team", target="22")
    combat.reduce_unit(s, "Fire Team 1", "P", [])
    e = s["units"]["Fire Team 1"]
    assert e["type"] == "Paralyzed Team" and e["vof_rating"] is None and e["target"] is None


def test_promoted_steps_old_list_format_blocks_whole_unit():
    """L166: promotions are counted per step; the old list format counts as fully promoted."""
    assert campaign._promoted_steps({"promoted": ["2/1"]}) == {"2/1": 99}
    assert campaign._promoted_steps({"promoted": {"2/1": 2}}) == {"2/1": 2}
    assert campaign._promoted_steps({}) == {}


def test_reconstitution_table_with_green_lat_step():
    """L167 [3.9, 12.2]: squad L L plus one LAT (Green) is L L G, which is Line in table 12.6."""
    assert campaign.experience_from_steps(["Line", "Line", "Green"]) == "Line"
    assert campaign.experience_from_steps(["Veteran", "Veteran", "Line"]) == "Veteran"


def test_enemy_seek_cover_turns_grenade_into_miss(board):
    """L171 [7.10.4]: a grenaded target that moves within its card (here enemy Seek Cover) leaves a Grenade Miss."""
    import types

    from fof import enemy

    s = board
    s["units"]["4/Gp FJ 1"] = unit("33", side="Enemy", vof="A", rng="L", steps=2, grenade=[-4])
    s["cards"]["33"]["cover_max"] = 2
    e = s["units"]["4/Gp FJ 1"]
    ctx = types.SimpleNamespace(e=e, n="4/Gp FJ 1", a="move into or seek cover", o={"--success": "yes"}, prot=[])
    enemy._enemy_seek_cover(s, ctx)
    assert e["grenade"] == []
    assert s["cards"]["33"].get("grenade_miss") is True
    assert e["area"] != "open"


def test_jam_prone_only_weapons_and_ammo_squads():
    """L172 [7.12]: S squads and S weapons teams never jam; A weapons teams and A squads with ammo do."""

    assert not grenades.jam_prone({"type": "Squad", "vof_rating": "S"})
    assert not grenades.jam_prone({"type": "Weapons Team", "vof_rating": "S"})
    assert grenades.jam_prone({"type": "Weapons Team", "vof_rating": "A"})
    assert grenades.jam_prone({"type": "Squad", "vof_rating": "A", "ammo": {"points": 3}})


def test_fire_ammo_skips_rockets_and_at_gun_small_arms():
    """L173 [7.18.1D, Normandy CSR 7]: Concentrate Fire of a rocket team uses no rockets."""
    assert combat.fire_ammo({"type": "Weapons Team", "vof_rating": "S", "ammo": {"type": "RKT", "points": 0}}) is None
    assert combat.fire_ammo({"type": "AT Gun", "vof_rating": "S", "ammo": {"type": "AP", "points": 3}}) is None
    m = {"type": "MG", "points": 2}
    assert combat.fire_ammo({"type": "Weapons Team", "vof_rating": "A", "ammo": m}) is m


def test_rocket_team_with_g_superscript_is_jam_prone():
    """L174, K42 [7.12]: an S G! rocket team (Bazooka) is liable to jamming, also after its rockets ran out."""

    assert grenades.jam_prone({"type": "Weapons Team", "vof_rating": "S", "grenade_ranged": True})
    assert grenades.jam_prone({"type": "Weapons Team", "vof_rating": "S", "rkt_empty": True})


def test_set_values_during_play_needs_reason(board):
    """L175: counter values can be corrected during play, but only with --reason."""
    import pytest

    from fof import rules, setup

    s = board
    s["turn"], s["phase"] = 5, "3.7.4"
    s["units"]["2/LMG"] = unit("22", vof="A", rng="L", steps=1, type="Weapons Team")
    if setup.state.in_setup(s):
        pytest.skip("synthetic board counts as setup")
    with pytest.raises(rules.Violation):
        setup.cmd_values(s, ["2/LMG", "ft_vof=A"])


def test_out_of_ammo_unit_is_s_rated_no_jam_no_ammo():
    """L176, K43 [7.18.2]: an A weapons team with an Out of Ammo marker fires S: not liable to jam, no ammo for CF."""

    e = {"type": "Weapons Team", "vof_rating": "A", "out_of_ammo": True, "ammo": {"type": "MG", "points": 0}}
    assert not grenades.jam_prone(e)
    assert combat.fire_ammo(e) is None


def test_last_step_team_inherits_empty_ammo(board, monkeypatch):
    """L177 [7.18.2]: an A squad whose last ammo was fired this turn passes the Out of Ammo state to its last-step Fire Team."""
    from fof import state

    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protocol"].append({"text": text}))
    s = board
    s["phase"] = "3.7.4"
    s["units"]["4/Gp FJ 1"] = unit(
        "33",
        side="Enemy",
        vof="A",
        rng="L",
        steps=2,
        ammo={"type": "MG", "points": 0, "start": 6},
        last_step="Fire Team",
        last_step_values={"vof_rating": "A", "range": "C"},
        ammo_empty=True,
    )
    combat.cmd_hit(s, ["4/Gp FJ 1", "HIT", "C"])  # one step lost, the last step becomes a Fire Team
    teams = [m for m, x in s["units"].items() if x.get("type") == "Fire Team" and x.get("card") == "33"]
    assert "4/Gp FJ 1" not in s["units"] and len(teams) == 1
    team = s["units"][teams[0]]
    assert team["vof_rating"] == "A" and team["ammo"]["points"] == 0
    # L552 (review T4): the squad fired its last ammo this turn (ammo_empty); the Out of Ammo marker comes in 3.8
    assert team.get("ammo_empty") is True and not team.get("out_of_ammo")


def test_marker_summary_point_blank_positions(board):
    """L179 [6.2.1]: outside VOF at the top, better friendly/enemy Point Blank VOF upper right / lower left."""
    from fof import state

    s = board
    s["units"]["US PB"] = unit("33", vof="A", rng="P", steps=1, type="Assault Team", target="33")
    s["units"]["DE PB"] = unit("33", side="Enemy", vof="A", rng="P", steps=1, type="Assault Team", target="33")
    s["units"]["US out"] = unit("23", vof="S", rng="L", steps=3, target="33")
    top, _cf, us, en = state.marker_summary(s)["33"]
    assert top[1] == 0 and us[1] == -1 and en[1] == -1


def test_l183_ncm_rows_per_unit_when_rows_differ(capsys, monkeypatch):
    """L183: two units with the same NCM from different modifiers get their own NCM rows."""
    from fof import combat

    s = {"combat_open": ["A", "B"], "units": {"A": {"card": "31"}, "B": {"card": "31"}}}
    rows = {"A": [("Exposed", -2), ("Woods", 2)], "B": [("Pinned", 1), ("Concentrated Fire", -1)]}
    monkeypatch.setattr(combat, "ncm_groups", lambda s_: [("31", 0, ["A", "B"])])
    monkeypatch.setattr(combat, "_ncm_total", lambda s_, n: (0, 0, rows[n]))
    monkeypatch.setattr(combat.comms, "experience", lambda e: "Line")
    monkeypatch.setattr(combat.state, "steps", lambda e: 1)
    combat.print_next_group(s)
    out = capsys.readouterr().out
    assert "NCM rows A:" in out and "NCM rows B:" in out and "Pinned +1" in out


def test_event_short_input_is_violation(board):
    """L192: 'event no' without card number gives a usage message, no traceback."""
    import pytest
    from fof import events, rules

    board["event_tables"] = {"x": 1}
    board["phase"], board["turn"] = "3.1", 2
    with pytest.raises(rules.Violation):
        events.cmd_event(board, ["no"])


def test_church_tower_also_on_church_on_hill():
    """L195 [RULE 5.2.2B p.36]: a Church card lying on a Hill still gets the Church Tower marker."""
    from fof import commands

    assert commands.upper_story_type({"terrain": "Church on 1 Hill", "op": True}) == "Church Tower"
    assert commands.upper_story_type({"terrain": "Church"}) == "Church Tower"
    assert commands.upper_story_type({"terrain": "Village on 1 Hill", "multistory": True}) == "Upper Story"
    assert commands.upper_story_type({"terrain": "Farm"}) is None


def test_attempt_text_per_unit_list():
    """L197: Platoon Infiltrate lists per unit are shown in English."""
    from fof import commands

    assert commands.attempt_text("yes") == "successful"
    assert commands.attempt_text("1/1:yes,2/1:no") == "1/1 successful, 2/1 failed"


def test_mutual_pdf_gone_entirely_says_remove(board):
    """L198: if a mutual PDF disappears completely, the board line says to remove the marker."""
    import copy

    from fof import state

    old = copy.deepcopy(board)
    old["units"]["A"] = unit("22", target="32")
    old["units"]["B"] = unit("32", side="Enemy", target="22")
    new = copy.deepcopy(old)
    new["units"]["A"]["card"] = "32"
    new["units"]["A"]["target"] = "32"
    new["units"]["B"]["target"] = "32"
    lines = state.marker_changes(old, new)
    assert any("remove the PDF marker" in x for x in lines)
    new2 = copy.deepcopy(old)
    new2["units"]["B"]["target"] = "32"
    assert any("single arrow" in x for x in state.marker_changes(old, new2))


def test_capture_needs_unpinned_infantry_with_vof():
    """L199 [RULE 3.5.1]: vehicles and pinned LATs do not capture; an unpinned Assault Team does."""
    from fof import phase

    assert not phase.can_capture({"type": "Vehicle", "vehicle": "M4 Sherman 75mm", "status": [], "vof_rating": "H"})
    assert not phase.can_capture({"type": "Assault Team", "status": ["Pinned"], "vof_rating": "A"})
    assert not phase.can_capture({"type": "HQ", "status": [], "vof_rating": None})
    assert phase.can_capture({"type": "Assault Team", "status": [], "vof_rating": "A"})
    assert phase.can_capture({"type": "Squad", "status": ["Exposed"], "vof_rating": "S"})


def test_one_way_pdf_gone_says_remove(board):
    """L206: a one-way PDF that disappears is announced for removal."""
    import copy

    from fof import state

    old = copy.deepcopy(board)
    old["units"]["A"] = unit("22", target="32")
    old["units"]["B"] = unit("32", side="Enemy")
    new = copy.deepcopy(old)
    new["units"]["A"]["target"] = None
    assert any("PDF from 22 to 32" in x and "remove" in x for x in state.marker_changes(old, new))


@pytest.mark.game_data
def test_capture_names_markers_leaving_the_board(m6_game, capsys):
    """L209 [RULE 3.5.1, 8.15]: the capture text names the markers that leave with the prisoners (Pinned)."""
    from fof import combat

    s = m6_game(470)
    assert s["phase"] == "3.5.1" and "Paralyzed Team 1" in s["units"]
    combat.cmd_capture(s, ["Paralyzed Team 1", "Assault Team 4"])
    out = capsys.readouterr().out
    assert "with its Pinned marker" in out


def test_initiative_hint_names_star_number():
    """L210 [RULE 3.3.2a/b, 4.1.1]: Initiative uses the small number in the star, not the helmet number."""
    from fof import phase

    s = {
        "co_hq": "CO HQ",
        "units": {"CO HQ": {"type": "HQ"}, "2nd PLT HQ": {"type": "HQ", "level": "PLT"}},
        "commands": {"CO HQ": {"activated": False, "saved": 0}, "2nd PLT HQ": {"activated": False}},
    }
    assert "star number" in phase.segment_note(s, "3.3.2a")
    assert "star number" in phase.segment_note(s, "3.3.2b")


@pytest.mark.game_data
def test_pick_up_without_what_names_items(m6_game, fof_cli):
    """L211 [RULE 5.1.6]: Pick Up without --what is refused and names what lies on the card."""
    s = m6_game(550)
    assert s["phase"] == "3.3.2b" and "Rifle Grenade" in s["cards"]["53"].get("assets_ground", [])
    code, out = fof_cli("order", "3rd PLT HQ", "3/AT", "4.2.2h")
    assert code == 2 and "VIOLATION" in out
    assert "Rifle Grenade" in out and "--what" in out
    assert saved_state()["protocol"][-1]["number"] == s["protocol"][-1]["number"] == 550


def test_gi_usage_and_hint():
    """L212 [RULE 3.3.2d]: gi without the star number is a Violation, and the segment names the star number."""
    import pytest

    from fof import commands, phase, rules

    with pytest.raises(rules.Violation):
        commands.cmd_gi({"phase": "3.3.2d"}, [])
    s = {"co_hq": "CO HQ", "units": {"CO HQ": {"type": "HQ"}}, "commands": {"CO HQ": {"activated": True}}}
    assert "star" in phase.segment_note(s, "3.3.2d")


@pytest.mark.game_data
def test_pinned_enemy_fall_back_avoids_vof_cards():
    """L213/E90 [RULE 4.2.5, 8.6.1C] reading B: a Pinned/Litter enemy falls back only onto cards without VOF."""
    from fof import enemy

    s = m6_state(563)
    assert s["units"]["Litter Team 1"]["card"] == "53"
    assert enemy.fall_back_candidates(s, s["units"]["Litter Team 1"]) == ["62"]


def test_enemy_counter_number_reused_after_removal():
    """L215 [Glossary 'Removed from Play', E88]: enemy counters return to the mix, so the lowest number is reused."""
    from fof import commands

    s = {"units": {}, "removed_from_play": ["German LMG 1", "1/3"]}
    assert commands.new_name(s, "German LMG", reuse_removed=True) == "German LMG 1"
    assert commands.new_name(s, "German LMG") == "German LMG 2"


@pytest.mark.game_data
def test_grenade_weapon_choice_bazooka_or_rifle_grenade(m6_game, fof_cli):
    """L216 [RULE 7.6, 7.10]: a Bazooka team with a picked-up Rifle Grenade must choose the weapon."""
    s = m6_game(622)
    assert "Rifle Grenade" in s["units"]["3/AT"]["assets"]
    base = ["order", "3rd PLT HQ", "3/AT", "4.2.4d", "--target=62", "--success=no"]
    code, out = fof_cli(*base)
    assert code == 2 and "VIOLATION" in out and "--weapon=rifle|own" in out
    code, out = fof_cli(*base, "--weapon=rifle")
    assert code == 0 and "VIOLATION" not in out
    e = saved_state()["units"]["3/AT"]
    assert "Rifle Grenade" not in e["assets"] and e["ammo"]["points"] == 1


@pytest.mark.game_data
def test_cease_fire_recipient_need_not_fire(m6_game):
    """L217 [RULE 4.2.4k]: Cease Fire reaches all occupants of the card; the Recipient itself need not be firing.
    Runs the real entry point (fof.py) in a subprocess, the other CLI tests run in-process."""
    s = m6_game(625)
    assert s["units"]["3rd PLT HQ"]["card"] == "43"
    r = fof_subprocess("order", "3rd PLT HQ", "3rd PLT HQ", "4.2.4k")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "VIOLATION" not in r.stdout and "Traceback" not in r.stderr
    assert "all firing units on 43 cease fire" in r.stdout
    assert saved_state()["protocol"][-1]["number"] == 626


@pytest.mark.game_data
def test_second_unit_joins_existing_pdf(m6_game, fof_cli):
    """L218 [RULE 6.3.5]: units never place an extra PDF if they can fire along the card's current PDF."""
    s = m6_game(675)
    assert s["units"]["Fire Team 3"].get("target_open")
    code, out = fof_cli("fire", "5/Gp FJ 1", "63")
    assert code == 0 and "VIOLATION" not in out
    e = saved_state()["units"]["Fire Team 3"]
    assert e["target"] == "63" and not e.get("target_open")


@pytest.mark.game_data
def test_enemy_seek_cover_in_village_uses_building_table(m6_game, fof_cli):
    """L219 [Normandy CSR 8]: enemy Seek Cover on a Village card draws on the building table."""
    s = m6_game(726)
    assert s["units"]["Fire Team 3"]["card"] == "74" and not s["cards"]["74"].get("cover")
    base = ["enemyaction", "Fire Team 3", "Move into or Seek Cover", "--success=yes"]
    code, out = fof_cli(*base)
    assert code == 2 and "VIOLATION" in out and "--building" in out
    code, out = fof_cli(*base, "--building=2")
    assert code == 0 and "VIOLATION" not in out
    c = saved_state()["cards"]["74"]["cover"]
    assert c and c[0]["type"] == "Strong Building"


def test_reconstitute_without_args_is_a_violation():
    """L220: 'reconstitute' without arguments gives the usage, not a traceback."""
    import pytest

    from fof import campaign, rules

    with pytest.raises(rules.Violation):
        campaign.cmd_reconstitute({"phase": "3.8", "turn": 10, "max_turns": 10, "units": {}}, [])
