"""L570: a unit on its Fire Team side fires with ft_vof although its front has no VOF (enemy Spotter after an F/A hit,
8.10 'They only flip to their Fire-Team side as a result of a combat Hit (F or A)'; US HQ on its Fire Team side)."""

from conftest import unit

from fof import fire


def test_spotter_on_its_fire_team_side_opens_fire(board):
    s = board
    s["units"]["Spotter"] = unit("22", side="Enemy", vof=None, type="Spotter", steps=1)
    s["units"]["Spotter"].update(spotter=True, ft_vof="S", ft_range="C", fire_team_side=True)
    s["units"]["1/1"] = unit("23")
    assert not fire.can_fire(s["units"]["Spotter"])  # front side: no VOF, it calls for fire instead
    s["units"]["Spotter"]["status"].append("Fire Team side")
    assert fire.can_fire(s["units"]["Spotter"])
    prot = []
    fire.open_fire(s, prot)
    assert s["units"]["Spotter"]["target"] == "23", prot
