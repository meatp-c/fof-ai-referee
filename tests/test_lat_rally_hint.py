"""L463: 4.2.3a on an unpinned generic LAT names the upgrade action."""

import pytest
from conftest import unit


def test_rally_paralyzed_team_names_convert_action(board):
    from fof import comms, rules

    s = board
    s["einheiten"]["PT"] = unit("22", steps=1)
    s["einheiten"]["PT"]["typ"] = "Paralyzed Team"
    with pytest.raises(rules.Violation, match="4.2.3b"):
        comms.action_allowed(s["einheiten"]["PT"], "PT", "4.2.3a")
