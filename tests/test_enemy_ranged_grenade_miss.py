"""L513: a failed ranged enemy Grenade Attack (G!) places a Grenade Miss Modifier on the target card (7.10.4)."""

import pytest

from conftest import unit


@pytest.fixture(autouse=True)
def quiet(monkeypatch, tmp_path):
    from fof import briefing, state

    monkeypatch.setenv("FOF_GAME", str(tmp_path))
    monkeypatch.setattr(state, "save_state", lambda s, text, rule=None: s["protocol"].append({"text": text}))
    monkeypatch.setattr(briefing, "print_board", lambda prot, s: None)


def test_failed_ranged_enemy_grenade_places_miss(board):
    from fof import enemy

    board["campaign"] = {}
    board["type"] = "offensive"
    board["phase"] = enemy.enemy_segments(board)[1]
    board["units"]["G1"] = unit("31", side="Enemy", vof="G", type_name="NKPA Mtr Team")
    board["units"]["US1"] = unit("21")
    enemy.cmd_enemy_action(board, ["G1", "Grenade Attack", "--success=no", "--target=21"])
    assert board["cards"]["21"].get("grenade_miss") is True
    assert not board["cards"]["31"].get("grenade_miss")
