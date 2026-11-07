"""L553, code review 07.11.2026 D4 (T5): paths that had no test (snapshots, argument translation, CSR 1/2 switches,
phone hub, staging radio LOS, runner, reconstitution of a removed unit, drop/radio damage, radio overview)."""

import json

import pytest

from conftest import unit


@pytest.fixture
def stub(monkeypatch):
    from fof import briefing, state

    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protokoll"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)


def test_snapshot_write_failure_says_so(monkeypatch, capsys):
    from fof import state

    def fail(path, text):
        raise OSError("disk full (test)")

    monkeypatch.setattr(state, "write_atomic", fail)
    state.save_snapshot(5, "{}")
    assert "snapshot verlauf/5.json not written" in capsys.readouterr().out


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

    out = cli.argv_to_german(["terrain", "22", "Woods", "--edges=top-green,left-white,corner,bottom-dark"])
    assert out[-1] == "--raender=oben-gruen,links-weiss,diagonal,unten-gruen"


def _mortar_state():
    sec = unit("11", typ="Weapons Team", steps=3, vof="H", platoon="1", funk=[{"typ": "SCR536", "netz": "CO TAC"}])
    team = unit(None, typ="Weapons Team", steps=1, vof="G", moerser=True)
    return {
        "einheiten": {"Mtr Sec": sec},
        "reserve_einheiten": {"1/Mtr": team, "2/Mtr": dict(team), "3/Mtr": dict(team)},
        "aufbau_einheiten": {"Mtr Sec": dict(sec, funk=[])},
    }


def test_mortar_teams_and_back_to_the_section():
    from fof import setup

    s = _mortar_state()
    prot = []
    setup.setup_mortar(s, "CO HQ", {}, {"--moerser": "teams"}, prot)
    assert "Mtr Sec" not in s["einheiten"] and {"1/Mtr", "2/Mtr", "3/Mtr"} <= set(s["einheiten"])
    assert s["mtr_sec_funk_frei"] == [{"typ": "SCR536", "netz": "CO TAC"}]
    setup.setup_mortar(s, "CO HQ", {}, {"--moerser": "sektion"}, prot)
    assert set(s["einheiten"]) == {"Mtr Sec"} and s["einheiten"]["Mtr Sec"]["karte"] == "11"
    assert s["einheiten"]["Mtr Sec"]["funk"] == [{"typ": "SCR536", "netz": "CO TAC"}] and "mtr_sec_funk_frei" not in s


def test_co_tac_from_phone_back_to_radio():
    from fof import setup

    s = {
        "co_hq": "CO HQ",
        "telefon_leitungen": 4,
        "einheiten": {"CO HQ": unit("11", funk=[{"typ": "SCR536", "netz": "CO TAC"}])},
        "funk_frei": [{"typ": "SCR536", "netz": "CO TAC"}],
    }
    setup.setup_net(s, "CO HQ", s["einheiten"]["CO HQ"], {"--netz": "telefon"}, [])
    assert s["einheiten"]["CO HQ"]["funk"][0]["typ"] == "EE8" and s["funk_frei"][0]["typ"] == "EE8"
    s["einheiten"]["CO HQ"]["leitungen"] = 2
    setup.setup_net(s, "CO HQ", s["einheiten"]["CO HQ"], {"--netz": "funk"}, [])
    assert s["einheiten"]["CO HQ"]["funk"][0]["typ"] == "SCR536" and s["funk_frei"][0]["typ"] == "SCR536"
    assert "leitungen" not in s["einheiten"]["CO HQ"] and "leitungen_pool" not in s


def test_phone_link_through_the_hub(board):
    from fof import comms

    s = board
    s.update(co_hq="CO HQ", co_tac_mittel="telefon", funk_aktiv=True)
    ee8 = [{"typ": "EE8", "netz": "CO TAC"}]
    s["einheiten"]["CO HQ"] = unit("23", typ="HQ", ebene="CO", funk=list(ee8))
    s["einheiten"]["1st PLT HQ"] = unit("21", typ="HQ", ebene="PLT", funk=list(ee8))
    s["einheiten"]["2nd PLT HQ"] = unit("23", typ="HQ", ebene="PLT", funk=list(ee8))
    ok, why = comms.phone_link(s, "1st PLT HQ", "2nd PLT HQ")
    assert not ok and "via the hub CO HQ" in why and "no unbroken line chain" in why
    s["karten"]["22"]["leitungen"] = [{"cut": False}]
    ok, why = comms.phone_link(s, "1st PLT HQ", "2nd PLT HQ")
    assert ok and "via the hub CO HQ" in why


def test_radio_los_from_the_staging_area(board):
    from fof import comms

    s = board
    for k in ("11", "12", "13"):
        s["karten"][k]["staging"] = True
    assert comms.radio_los(s, "11", "12")[0]
    assert comms.radio_los(s, "11", "21")[0]
    ok, why = comms.radio_los(s, "11", "31")
    assert not ok and "only to adjacent cards of row 1" in why


def test_runner_finds_its_hq_gone(board):
    from fof import comms

    s = board
    s["zug"] = 3
    s["kommandos"]["1st PLT HQ"] = {"verfuegbar": 0, "gespart": 0, "aktiviert": False, "fertig": False}
    s["einheiten"]["1st PLT HQ"] = unit("23", typ="HQ", ebene="PLT", steps=1)
    s["einheiten"]["Runner 1"] = unit("22", typ="Runner", steps=1, runner_ziel="1st PLT HQ", unterwegs_seit=2)
    prot = []
    comms.deliver_runner(s, prot)
    assert "no longer on 22" in prot[0] and not s["kommandos"]["1st PLT HQ"]["aktiviert"]
    assert "Runner 1" not in s["einheiten"] and s["runner_box"] == ["Runner 1"]


def test_reconstitute_a_unit_removed_from_play(board, stub):
    from fof import campaign

    s = board
    s.update(kampagne={"versuch": 1}, missionsende=True, removed_from_play=["1/1"])
    s["aufbau_einheiten"] = {"1/1": unit("11", steps=3, platoon="1")}
    s["einheiten"]["LT1"] = unit("21", typ="Fire Team", steps=1)
    s["einheiten"]["LT2"] = unit("21", typ="Fire Team", steps=1)
    campaign.cmd_reconstitute(s, ["1/1", "--from=LT1,LT2"])
    e = s["einheiten"]["1/1"]
    assert e["steps"] == 2 and e["karte"] == "21" and "1/1" not in s["removed_from_play"]
    assert "LT1" not in s["einheiten"] and "LT2" not in s["einheiten"]


def test_drop_a_casualty_and_a_radio(board, stub):
    from fof import setup

    s = board
    s["einheiten"]["LT"] = unit(
        "22", typ="Litter Team", steps=1, traegt_casualties=1, funk=[{"typ": "SCR536", "netz": "CO TAC"}]
    )
    setup.cmd_drop(s, ["LT", "Casualty"])
    assert s["karten"]["22"]["casualties"] == 1 and s["einheiten"]["LT"]["traegt_casualties"] == 0
    setup.cmd_drop(s, ["LT", "SCR536"])
    assert s["einheiten"]["LT"]["funk"] == []
    assert s["karten"]["22"]["assets"] == [{"typ": "SCR536", "netz": "CO TAC", "schaden_offen": False}]


@pytest.mark.parametrize("result", ["zerstoert", "heil"])
def test_radio_damage_draw(board, stub, result):
    from fof import setup

    s = board
    s["karten"]["22"]["assets"] = [{"typ": "SCR536", "netz": "CO TAC", "schaden_offen": True}]
    setup.cmd_radio(s, ["schaden", "22", "SCR536", result])
    if result == "zerstoert":
        assert s["karten"]["22"]["assets"] == [] and s["funk_zerstoert"] == ["SCR536 CO TAC"]
    else:
        assert s["karten"]["22"]["assets"][0]["schaden_offen"] is False


def test_radio_overview_lists_bn_and_co_tac_links(board):
    from fof import briefing

    s = board
    s.update(co_hq="CO HQ", funk_aktiv=True)
    s["einheiten"]["CO HQ"] = unit(
        "22", typ="HQ", ebene="CO", funk=[{"typ": "SCR300", "netz": "BN TAC"}, {"typ": "SCR536", "netz": "CO TAC"}]
    )
    s["einheiten"]["1st PLT HQ"] = unit("21", typ="HQ", ebene="PLT", funk=[{"typ": "SCR536", "netz": "CO TAC"}])
    s["einheiten"]["Arty FO"] = unit("23", typ="FO", funk=[{"typ": "SCR610", "netz": "Arty FD"}])
    out = briefing.radio_overview(s)
    assert out[0].startswith("BN HQ (off-map) with CO HQ: yes")
    assert any(x.startswith("CO HQ with 1st PLT HQ: yes") for x in out)
    assert "Arty FO: FD radio Arty FD" in out
