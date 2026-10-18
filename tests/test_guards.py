"""Guard steps (8.15 p.69) are noted with their Experience Level and listed as returning between missions (L126)."""

from fof import campaign


def test_guards_returning_lists_guards_and_replacement_limit():
    s = {
        "wachen": [
            {"einheit": "1/AT", "erfahrung": "Veteran", "karte": "44", "zug": 10, "gefangene": ["Litter Team 5"]}
        ],
        "us_casualties_gesamt": 3,
        "us_gefangen": 0,
    }
    prot = []
    campaign.guards_returning(s, prot)
    assert "1/AT 1 step Veteran" in prot[0]
    assert "8.15" in prot[0]
    assert "3 this mission" in prot[1] and "12.4" in prot[1]


def test_guards_returning_without_guards():
    prot = []
    campaign.guards_returning({"us_casualties_gesamt": 2, "us_gefangen": 1}, prot)
    assert len(prot) == 1 and "3 this mission" in prot[0]
