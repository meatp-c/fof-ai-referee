"""L513: a failed ranged enemy Grenade Attack (G!) places a Grenade Miss Modifier on the target card (7.10.4)."""

import pytest

from conftest import unit


@pytest.fixture(autouse=True)
def quiet(monkeypatch, tmp_path):
    from fof import briefing, state

    monkeypatch.setenv("FOF_PARTIE", str(tmp_path))
    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protokoll"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)


def test_failed_ranged_enemy_grenade_places_miss(board):
    from fof import enemy

    board["kampagne"] = {}
    board["typ"] = "offensiv"
    board["phase"] = enemy.enemy_segments(board)[1]
    board["einheiten"]["G1"] = unit("31", side="Feind", vof="G", typname="NKPA Mtr Team")
    board["einheiten"]["US1"] = unit("21")
    enemy.cmd_enemy_action(board, ["G1", "Grenade Attack", "--erfolg=nein", "--ziel=21"])
    assert board["karten"]["21"].get("grenade_miss") is True
    assert not board["karten"]["31"].get("grenade_miss")
