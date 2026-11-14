"""L553, code review 07.11.2026 D4 (T5): paths that had no test (snapshots, argument translation, CSR 1/2 switches,
phone hub, staging radio LOS, runner, reconstitution of a removed unit, drop/radio damage, radio overview)."""

import json

import pytest

from conftest import unit


@pytest.fixture
def stub(monkeypatch):
    from fof import briefing, state

    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protocol"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)


def test_snapshot_write_failure_says_so(monkeypatch, capsys):
    from fof import state

    def fail(path, text):
        raise OSError("disk full (test)")

    monkeypatch.setattr(state, "write_atomic", fail)
    state.save_snapshot(5, "{}")
    assert "snapshot history/5.json not written" in capsys.readouterr().out


def test_snapshot_reuses_the_oldest_file_and_holds_the_new_state(tmp_path):
    from fof import state

    d = tmp_path / state.HISTORY_DIR
    d.mkdir()
    (d / "1.json").write_text('{"old": true}', encoding="utf-8")
    state.save_snapshot(state.HISTORY_KEEP + 2, '{"new": true}')
    assert not (d / "1.json").exists()
    assert json.loads((d / f"{state.HISTORY_KEEP + 2}.json").read_text(encoding="utf-8")) == {"new": True}


def test_edges_translation_beyond_white():
    from fof import cli

    out = cli.normalize_argv(["terrain", "22", "Woods", "--edges=top-green,left-white,corner,bottom-dark"])
    assert out[-1] == "--edges=top-green,left-white,diagonal,bottom-green"


def _mortar_state():
    sec = unit("11", type="Weapons Team", steps=3, vof="H", platoon="1", radio=[{"type": "SCR536", "net": "CO TAC"}])
    team = unit(None, type="Weapons Team", steps=1, vof="G", mortar=True)
    return {
        "units": {"Mtr Sec": sec},
        "reserve_units": {"1/Mtr": team, "2/Mtr": dict(team), "3/Mtr": dict(team)},
        "setup_units": {"Mtr Sec": dict(sec, radio=[])},
    }


def test_mortar_teams_and_back_to_the_section():
    from fof import setup

    s = _mortar_state()
    prot = []
    setup.setup_mortar(s, "CO HQ", {}, {"--mortar": "teams"}, prot)
    assert "Mtr Sec" not in s["units"] and {"1/Mtr", "2/Mtr", "3/Mtr"} <= set(s["units"])
    assert s["mtr_sec_radio_free"] == [{"type": "SCR536", "net": "CO TAC"}]
    setup.setup_mortar(s, "CO HQ", {}, {"--mortar": "section"}, prot)
    assert set(s["units"]) == {"Mtr Sec"} and s["units"]["Mtr Sec"]["card"] == "11"
    assert s["units"]["Mtr Sec"]["radio"] == [{"type": "SCR536", "net": "CO TAC"}] and "mtr_sec_radio_free" not in s


def test_co_tac_from_phone_back_to_radio():
    from fof import setup

    s = {
        "co_hq": "CO HQ",
        "phone_lines": 4,
        "units": {"CO HQ": unit("11", radio=[{"type": "SCR536", "net": "CO TAC"}])},
        "radio_free": [{"type": "SCR536", "net": "CO TAC"}],
    }
    setup.setup_net(s, "CO HQ", s["units"]["CO HQ"], {"--net": "phone"}, [])
    assert s["units"]["CO HQ"]["radio"][0]["type"] == "EE8" and s["radio_free"][0]["type"] == "EE8"
    s["units"]["CO HQ"]["lines"] = 2
    setup.setup_net(s, "CO HQ", s["units"]["CO HQ"], {"--net": "radio"}, [])
    assert s["units"]["CO HQ"]["radio"][0]["type"] == "SCR536" and s["radio_free"][0]["type"] == "SCR536"
    assert "lines" not in s["units"]["CO HQ"] and "lines_pool" not in s


def test_phone_link_through_the_hub(board):
    from fof import comms

    s = board
    s.update(co_hq="CO HQ", co_tac_medium="phone", radio_active=True)
    ee8 = [{"type": "EE8", "net": "CO TAC"}]
    s["units"]["CO HQ"] = unit("23", type="HQ", level="CO", radio=list(ee8))
    s["units"]["1st PLT HQ"] = unit("21", type="HQ", level="PLT", radio=list(ee8))
    s["units"]["2nd PLT HQ"] = unit("23", type="HQ", level="PLT", radio=list(ee8))
    ok, why = comms.phone_link(s, "1st PLT HQ", "2nd PLT HQ")
    assert not ok and "via the hub CO HQ" in why and "no unbroken line chain" in why
    s["cards"]["22"]["lines"] = [{"cut": False}]
    ok, why = comms.phone_link(s, "1st PLT HQ", "2nd PLT HQ")
    assert ok and "via the hub CO HQ" in why


def test_radio_los_from_the_staging_area(board):
    from fof import comms

    s = board
    for k in ("11", "12", "13"):
        s["cards"][k]["staging"] = True
    assert comms.radio_los(s, "11", "12")[0]
    assert comms.radio_los(s, "11", "21")[0]
    ok, why = comms.radio_los(s, "11", "31")
    assert not ok and "only to adjacent cards of row 1" in why


def test_runner_finds_its_hq_gone(board):
    from fof import comms

    s = board
    s["turn"] = 3
    s["commands"]["1st PLT HQ"] = {"available": 0, "saved": 0, "activated": False, "done": False}
    s["units"]["1st PLT HQ"] = unit("23", type="HQ", level="PLT", steps=1)
    s["units"]["Runner 1"] = unit("22", type="Runner", steps=1, runner_target="1st PLT HQ", en_route_since=2)
    prot = []
    comms.deliver_runner(s, prot)
    assert "no longer on 22" in prot[0] and not s["commands"]["1st PLT HQ"]["activated"]
    assert "Runner 1" not in s["units"] and s["runner_box"] == ["Runner 1"]


def test_reconstitute_a_unit_removed_from_play(board, stub):
    from fof import campaign

    s = board
    s.update(campaign={"attempt": 1}, mission_end=True, removed_from_play=["1/1"])
    s["setup_units"] = {"1/1": unit("11", steps=3, platoon="1")}
    s["units"]["LT1"] = unit("21", type="Fire Team", steps=1)
    s["units"]["LT2"] = unit("21", type="Fire Team", steps=1)
    campaign.cmd_reconstitute(s, ["1/1", "--from=LT1,LT2"])
    e = s["units"]["1/1"]
    assert e["steps"] == 2 and e["card"] == "21" and "1/1" not in s["removed_from_play"]
    assert "LT1" not in s["units"] and "LT2" not in s["units"]


def test_drop_a_casualty_and_a_radio(board, stub):
    from fof import setup

    s = board
    s["units"]["LT"] = unit(
        "22", type="Litter Team", steps=1, carries_casualties=1, radio=[{"type": "SCR536", "net": "CO TAC"}]
    )
    setup.cmd_drop(s, ["LT", "Casualty"])
    assert s["cards"]["22"]["casualties"] == 1 and s["units"]["LT"]["carries_casualties"] == 0
    setup.cmd_drop(s, ["LT", "SCR536"])
    assert s["units"]["LT"]["radio"] == []
    assert s["cards"]["22"]["assets"] == [{"type": "SCR536", "net": "CO TAC", "damage_open": False}]


@pytest.mark.parametrize("result", ["destroyed", "intact"])
def test_radio_damage_draw(board, stub, result):
    from fof import setup

    s = board
    s["cards"]["22"]["assets"] = [{"type": "SCR536", "net": "CO TAC", "damage_open": True}]
    setup.cmd_radio(s, ["damage", "22", "SCR536", result])
    if result == "destroyed":
        assert s["cards"]["22"]["assets"] == [] and s["radio_destroyed"] == ["SCR536 CO TAC"]
    else:
        assert s["cards"]["22"]["assets"][0]["damage_open"] is False


def test_radio_overview_lists_bn_and_co_tac_links(board):
    from fof import briefing

    s = board
    s.update(co_hq="CO HQ", radio_active=True)
    s["units"]["CO HQ"] = unit(
        "22", type="HQ", level="CO", radio=[{"type": "SCR300", "net": "BN TAC"}, {"type": "SCR536", "net": "CO TAC"}]
    )
    s["units"]["1st PLT HQ"] = unit("21", type="HQ", level="PLT", radio=[{"type": "SCR536", "net": "CO TAC"}])
    s["units"]["Arty FO"] = unit("23", type="FO", radio=[{"type": "SCR610", "net": "Arty FD"}])
    out = briefing.radio_overview(s)
    assert out[0].startswith("BN HQ (off-map) with CO HQ: yes")
    assert any(x.startswith("CO HQ with 1st PLT HQ: yes") for x in out)
    assert "Arty FO: FD radio Arty FD" in out
