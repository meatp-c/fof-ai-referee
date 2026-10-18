"""Fixes from Normandy Mission 5 (L163, L166)."""

from conftest import unit
from fof import campaign, combat


def test_lat_conversion_takes_counter_values(board):
    """L163 [Normandy Unit Breakdown p.47, K12]: a generic Fire Team (S C) hit with A becomes an Assault Team A P."""
    s = board
    s["einheiten"]["Fire Team 1"] = unit("33", side="Feind", vof="S", rng="C", steps=1, typ="Fire Team", ziel="22")
    prot = []
    combat.reduce_unit(s, "Fire Team 1", "A", prot)
    e = s["einheiten"]["Fire Team 1"]
    assert e["typ"] == "Assault Team"
    assert (e["vof_rating"], e["reichweite"]) == ("A", "P")
    assert "Pinned" in e["status"]


def test_lat_conversion_to_paralyzed_stops_fire(board):
    s = board
    s["einheiten"]["Fire Team 1"] = unit("33", side="Feind", vof="S", rng="C", steps=1, typ="Fire Team", ziel="22")
    combat.reduce_unit(s, "Fire Team 1", "P", [])
    e = s["einheiten"]["Fire Team 1"]
    assert e["typ"] == "Paralyzed Team" and e["vof_rating"] is None and e["ziel"] is None


def test_promoted_steps_old_list_format_blocks_whole_unit():
    """L166: promotions are counted per step; the old list format counts as fully promoted."""
    assert campaign._promoted_steps({"befoerdert": ["2/1"]}) == {"2/1": 99}
    assert campaign._promoted_steps({"befoerdert": {"2/1": 2}}) == {"2/1": 2}
    assert campaign._promoted_steps({}) == {}


def test_reconstitution_table_with_green_lat_step():
    """L167 [3.9, 12.2]: squad L L plus one LAT (Green) is L L G, which is Line in table 12.6."""
    assert campaign.experience_from_steps(["Line", "Line", "Green"]) == "Line"
    assert campaign.experience_from_steps(["Veteran", "Veteran", "Line"]) == "Veteran"
