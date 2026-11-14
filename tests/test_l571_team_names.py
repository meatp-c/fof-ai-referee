"""L571: with 'names lat card' the generic team counters are called by counter type and card (AT 45, FT 33, P 55,
L 42; enemy teams with the enemy prefix) and are renamed when their type or card changes."""

from conftest import saved_state, unit

from fof import naming


def lat(card_id, typ="Assault Team", side="US", **kw):
    return unit(card_id, side=side, type=typ, steps=1, **kw)


def test_without_the_option_the_numbered_names_stay(board):
    board["units"]["Assault Team 3"] = lat("22")
    assert naming.relabel(board) == []
    assert "Assault Team 3" in board["units"]


def test_team_is_named_by_type_and_card_and_references_follow(board):
    s = board
    s["lat_names"] = "card"
    s["units"]["Assault Team 3"] = lat("22")
    s["units"]["1/1"] = unit("21", attached_to=["Assault Team 3"])
    s["units"]["Enemy"] = unit("23", side="Enemy", target_unit="Assault Team 3")
    s["commands"]["Assault Team 3"] = {"saved": 0}
    s["protocol"].append({"text": "Assault Team 3"})
    lines = naming.relabel(s)
    assert lines == ["Assault Team 3 is now called AT 22 (counter type and card)"]
    assert "AT 22" in s["units"] and "Assault Team 3" not in s["units"]
    assert s["units"]["1/1"]["attached_to"] == ["AT 22"]
    assert s["units"]["Enemy"]["target_unit"] == "AT 22"
    assert "AT 22" in s["commands"]
    assert s["protocol"][0]["text"] == "Assault Team 3"  # the log keeps the name of the time


def test_rename_on_card_change_and_on_type_change_with_enemy_prefix(board):
    s = board
    s.update(lat_names="card", enemy_prefix="NKPA")
    s["units"]["AT 22"] = lat("23")
    s["units"]["NKPA FT 31"] = lat("31", "Paralyzed Team", side="Enemy")
    lines = naming.relabel(s)
    assert set(s["units"]) == {"AT 23", "NKPA P 31"}, lines
    assert naming.relabel(s) == []  # stable once the names fit


def test_second_team_of_a_type_on_a_card_gets_a_letter_and_keeps_it(board):
    s = board
    s["lat_names"] = "card"
    s["units"]["AT 22"] = lat("22")
    s["units"]["Assault Team 9"] = lat("22")
    naming.relabel(s)
    assert set(s["units"]) == {"AT 22", "AT 22b"}
    del s["units"]["AT 22"]
    assert naming.relabel(s) == []  # 'AT 22b' still fits card 22, no churn


def test_names_command_renames_on_the_next_save(cli_game, fof_cli):
    cli_game(units={"Assault Team 1": lat("22"), "1/1": unit("21")})
    code, out = fof_cli("names", "lat", "card")
    assert code == 0, out
    assert "Assault Team 1 is now called AT 22" in out
    s = saved_state()
    assert "AT 22" in s["units"] and s["lat_names"] == "card"
    assert "now called AT 22" in s["protocol"][-1]["text"]
    code, out = fof_cli("names", "lat", "numbered")
    assert code == 0 and "lat_names" not in saved_state()
