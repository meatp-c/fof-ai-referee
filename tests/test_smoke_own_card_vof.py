"""L462: HC/WP smoke deployed on the firing unit's card: VOF stays on the own card (6.1.2 example 1), not Cease Fire."""

from conftest import unit


def test_pyro_smoke_keeps_vof_on_own_card(board):
    from fof import commands

    s = board
    s["einheiten"]["HMG"] = unit("22", ziel="23")
    s["einheiten"]["German"] = unit("23", side="Feind")
    prot = []
    commands._pyro_smoke(s, "HC Smoke", "22", {"--wert": "2"}, prot)
    e = s["einheiten"]["HMG"]
    assert e["ziel"] == "22" and e.get("_rauch_ziel") == "23", (e, prot)
    assert any("its VOF stays on 22" in p for p in prot), prot
