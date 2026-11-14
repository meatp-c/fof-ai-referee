"""L465: vehicle Spot checks LOS like the infantry Spot (Incoming/smoke on the own card blocks LOS out, 5.4)."""

import pytest
from conftest import unit


def test_vehicle_spot_refused_out_of_incoming(board, monkeypatch):
    from fof import rules, vehicles

    s = board
    tank = unit("22", vof="H", rng="V", steps=2)
    tank.update(vehicle="M10 TD 76mm", type="Vehicle", status=["Activated"])
    s["units"]["TD"] = tank
    s["units"]["Spotter"] = unit("33", side="Enemy", spotted=False)
    s["cards"]["22"].setdefault("external", []).append({"type": "Incoming", "value": -3, "side": "Enemy"})
    monkeypatch.setattr(vehicles, "start_action", lambda s_, n: ({"action": {"plan": []}}, s_["units"][n]))
    with pytest.raises(rules.Violation, match="No LOS from 22 to 33"):
        vehicles.vehicle_spot(s, ["TD"], {"--target": "33"})
