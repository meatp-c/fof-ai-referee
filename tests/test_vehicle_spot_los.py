"""L465: vehicle Spot checks LOS like the infantry Spot (Incoming/smoke on the own card blocks LOS out, 5.4)."""

import pytest
from conftest import unit


def test_vehicle_spot_refused_out_of_incoming(board, monkeypatch):
    from fof import rules, vehicles

    s = board
    tank = unit("22", vof="H", rng="V", steps=2)
    tank.update(fahrzeug="M10 TD 76mm", typ="Vehicle", status=["Activated"])
    s["einheiten"]["TD"] = tank
    s["einheiten"]["Spotter"] = unit("33", side="Feind", spotted=False)
    s["karten"]["22"].setdefault("extern", []).append({"typ": "Incoming", "wert": -3, "seite": "Feind"})
    monkeypatch.setattr(vehicles, "start_action", lambda s_, n, kind: ({"aktion": {"plan": []}}, s_["einheiten"][n]))
    with pytest.raises(rules.Violation, match="No LOS from 22 to 33"):
        vehicles.vehicle_spot(s, ["TD"], {"--ziel": "33"})
