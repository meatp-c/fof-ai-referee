"""Review 23.10.2026, structure/readability part B (L440-L459): synthetic boards only, no game folder."""

import pytest

from conftest import unit


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    from fof import briefing, state

    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protokoll"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)


def _text(s):
    return s["protokoll"][-1]["text"]


# ---- Struktur 2: bookkeeping removals that are not removals from play


def test_runner_back_to_the_box_is_not_removed_from_play(board):
    """L440: a Runner returning to the CO HQ Assets box is reusable, it does not enter removed_from_play."""
    from fof import comms

    board["zug"] = 2
    board["einheiten"]["Runner 1"] = unit("22", typ="Runner", runner_ziel="1st PLT HQ", unterwegs_seit=1)
    prot = []
    comms.deliver_runner(board, prot)
    assert "Runner 1" not in board["einheiten"]
    assert comms.runner_box(board) == ["Runner 1"]
    assert "removed_from_play" not in board


def test_patrol_reserve_round_trip_keeps_units(board):
    """L440: units set aside for a patrol come back unchanged; they are not removed from play."""
    from fof import campaign

    board["einheiten"]["1/1"] = unit(None)
    board["kommandos"]["1/1"] = {"verfuegbar": 0}
    prot = []
    campaign.patrol_reserve(board, prot)
    assert "1/1" not in board["einheiten"] and "removed_from_play" not in board
    campaign.patrol_reserve_back(board, prot)
    assert board["einheiten"]["1/1"]["karte"] is None and board["kommandos"]["1/1"] == {"verfuegbar": 0}


# ---- Struktur 10: status markers via rules constants


def test_status_marker_constants():
    """L441: one spelling of the status markers; state accessors read them."""
    from fof import rules, state

    assert (rules.PINNED, rules.EXPOSED, rules.ACTIVATED, rules.MOVED_FIRED, rules.FIRE_TEAM_SIDE) == (
        "Pinned",
        "Exposed",
        "Activated",
        "Moved/Fired",
        "Fire Team side",
    )
    e = unit("11", status=[rules.PINNED, rules.FIRE_TEAM_SIDE])
    assert state.pinned(e) and state.fire_team_side(e)


# ---- LOW: 4.2.1a in ACTIONS has no order handler


def test_order_not_implemented_registry():
    """L442: actions of the menu given by their own command are listed; the Violation names that command."""
    from fof import commands, rules

    assert set(rules.ORDER_NOT_IMPLEMENTED) == {"4.2.1a"}
    assert not set(rules.ORDER_NOT_IMPLEMENTED) & set(commands.ORDER_HANDLERS)
    v = rules.order_not_implemented("4.2.1a")
    assert isinstance(v, rules.Violation)
    assert "activate <hq>" in str(v) and "4.2.1a" in str(v) and "Activate a subordinate HQ" in str(v)
    assert str(rules.order_not_implemented("4.2.9z")) == "Action 4.2.9z not implemented yet"


def test_every_menu_action_has_a_handler_or_is_registered():
    """L442: no action of ACTIONS ends silently in cmd_order's fallback."""
    from fof import commands, rules

    by_order_v4 = {"4.2.1f", "4.2.1g", "4.2.1h", "4.2.1j", "4.2.1k"}
    missing = set(rules.ACTIONS) - set(commands.ORDER_HANDLERS) - by_order_v4
    assert missing == set(rules.ORDER_NOT_IMPLEMENTED)


# ---- Struktur 8: English option keys stay accepted in-process


def test_parse_opts_maps_english_keys_but_not_values():
    """L443: in-process callers pass English keys; values are translated only in cli.argv_to_german."""
    from fof import cli, options

    assert options.parse_opts(["--target=21", "--success=ja"]) == {"--ziel": "21", "--erfolg": "ja"}
    assert options.parse_opts(["--ziel=21"]) == options.parse_opts(["--target=21"])
    assert options.parse_opts(["--success=yes"]) == {"--erfolg": "yes"}
    assert cli.argv_to_german(["order", "--success=yes"])[1] == "--erfolg=ja"


# ---- RUF015 / unused arguments


def test_vof_against_takes_the_first_best_entry(board, monkeypatch):
    """L444: next() instead of list(...)[0]: the first entry with the best value names the type."""
    from fof import fire

    entries = [("S", -1, "A", None, None), ("G", -3, "B", None, None), ("H", -3, "C", None, None)]
    monkeypatch.setattr(fire, "vof_entries", lambda s, kid: entries)
    assert fire.vof_against(board, "22", "US") == ("G", -3, ["A", "B", "C"])
    monkeypatch.setattr(fire, "vof_entries", lambda s, kid: [])
    assert fire.vof_against(board, "22", "US") is None


def test_multistory_marks_the_new_upper_story(board):
    """L444: the Upper Story marker just placed is found with next() and flagged."""
    from fof import setup

    board["karten"]["22"]["cover"] = [{"id": "C1", "typ": "Light Building", "wert": 2}]
    setup.cmd_multistory(board, ["22"])
    upper = [x for x in board["karten"]["22"]["cover"] if x["typ"] == "Upper Story"]
    assert len(upper) == 1 and upper[0]["feld"] is True and upper[0]["wert"] == 2


def test_unused_arguments_removed():
    """L445: grazing(e) and must_retreat(s, e) no longer take arguments they never read."""
    import inspect

    from fof import fire, phase

    assert list(inspect.signature(fire.grazing).parameters) == ["e"]
    assert list(inspect.signature(phase.must_retreat).parameters) == ["s", "e"]


def test_must_retreat(board):
    """L445: a Paralyzed Team without VOF does not retreat; with VOF it must."""
    from fof import fire, phase, rules

    e = unit("22", typ="Paralyzed Team", steps=1)
    board["einheiten"]["Paralyzed Team 1"] = e
    assert not phase.must_retreat(board, e)
    board["karten"]["22"]["extern"] = [{"typ": "Incoming", "wert": -2}]
    assert fire.vof_against(board, "22", "US")
    assert phase.must_retreat(board, e)
    e["status"].append(rules.EXPOSED)
    assert not phase.must_retreat(board, e)


# ---- Readability: cmd_end_turn and briefing split


def _clean_up_board(board):
    from fof import rules

    board.update(phase="3.8", zug=3, max_zuege=5, kampf_offen=["x"], letzter_versuch="y", impuls_ausgegeben={"a": 1})
    board["kommandos"]["1st PLT HQ"] = {"verfuegbar": 2, "gespart": 1, "aktiviert": True, "fertig": True, "gezogen": 3}
    board["einheiten"]["1/1"] = unit("21", status=[rules.EXPOSED], cf=1, grenade=["G"], grenade_critical=True)
    board["karten"]["22"].update(illum=[{"oben": 1}], grenade_miss=True)
    board["karten"]["22"]["extern"] = [{"typ": "Smoke", "wert": 1}, {"typ": "Indirect", "wert": -2, "quelle": "Mtr"}]
    return board


def test_end_turn_clean_up_and_next_turn(board, capsys):
    """L446: the split cmd_end_turn removes the same markers and starts the next turn."""
    from fof import phase

    s = _clean_up_board(board)
    phase.cmd_end_turn(s, [])
    e = s["einheiten"]["1/1"]
    assert e["status"] == [] and e["cf"] == 0 and e["grenade"] == [] and "grenade_critical" not in e
    c = s["karten"]["22"]
    assert c["illum"] == [] and c["grenade_miss"] is False and c["extern"] == []
    assert s["kommandos"]["1st PLT HQ"] == {"verfuegbar": 0, "gespart": 1, "aktiviert": False, "fertig": False}
    assert s["kampf_offen"] == [] and s["letzter_versuch"] is None and s["impuls_ausgegeben"] == {}
    assert s["zug"] == 4 and s["phase"] == "3.1"
    text = _text(s)
    assert text.startswith("Clean Up; turn 4 begins; ")
    assert text.index("1/1: remove Exposed") < text.index("22: remove Illumination") < text.index("Command markers")
    assert "Turn 4 begins with phase 3.1" in capsys.readouterr().out


def test_end_turn_last_turn_ends_the_mission(board, capsys):
    """L446: end_of_mission saves the mission end and the turn counter stays."""
    from fof import phase

    s = _clean_up_board(board)
    s["zug"] = 5
    phase.cmd_end_turn(s, [])
    assert s["zug"] == 5 and s["phase"] == "3.8"
    assert _text(s).startswith("Turn 5 ended: end of mission reached; ")
    assert "End of mission: last turn played." in capsys.readouterr().out


def test_end_turn_outside_3_8_is_refused(board):
    from fof import phase, rules

    with pytest.raises(rules.Violation, match="only in phase 3.8"):
        phase.cmd_end_turn(board, [])


def test_briefing_uses_card_line(board):
    """L447: the board section of the briefing is made of card_line, the totals of board_totals."""
    from fof import briefing

    board.update(mission="Test", max_zuege=5, aktivitaet=None, removed_from_play=["Fire Team 1"], evakuiert=2)
    board["karten"]["22"].update(cc=1, pc="P1")
    board["einheiten"]["1/1"] = unit("22")
    txt = briefing.briefing(board, errors=[])
    line = briefing.card_line(board, "22", board["karten"]["22"])
    assert line.startswith("- 22 Open Fields (+1) [PC P1]: 1/1")
    assert line in txt.split("\n")
    assert briefing.board_totals(board) == ["- Evacuated casualties: 2", "- Removed from Play: Fire Team 1"]
    assert "## Campaign" not in txt
