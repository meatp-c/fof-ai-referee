"""L462: HC/WP smoke deployed on the firing unit's card: VOF stays on the own card (6.1.2 example 1), not Cease Fire."""

from conftest import unit
from fof import pyro  # L556: split from commands


def test_pyro_smoke_keeps_vof_on_own_card(board):

    s = board
    s["units"]["HMG"] = unit("22", target="23")
    s["units"]["German"] = unit("23", side="Enemy")
    prot = []
    pyro._pyro_smoke(s, "HC Smoke", "22", {"--value": "2"}, prot)
    e = s["units"]["HMG"]
    assert e["target"] == "22" and e.get("_smoke_target") == "23", (e, prot)
    assert any("its VOF stays on 22" in p for p in prot), prot
