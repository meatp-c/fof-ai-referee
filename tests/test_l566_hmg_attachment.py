"""L566: an HMG team attached to a rifle platoon stays under its HMG PLT HQ as well (Naktong S.17: the HMG PLT HQ
commands itself and all HMG teams, also when they are attached to other platoons)."""

import pytest

from fof import comms, rules, setup


def _hq(platoon):
    return {"side": "US", "type": "HQ", "level": "PLT", "platoon": platoon, "card": None, "status": [], "steps": 1}


def _units(board):
    board["units"].update(
        {
            "1st PLT HQ": _hq("1"),
            "2nd PLT HQ": _hq("2"),
            "HMG PLT HQ": dict(_hq("HMG"), attachment=True),
            "1/1 HMG": {
                "side": "US",
                "type": "Weapons Team",
                "platoon": "HMG",
                "attachment": True,
                "attached_to": [],
                "status": [],
            },
            "1/75mm RCL": {
                "side": "US",
                "type": "Weapons Team",
                "platoon": None,
                "attachment": True,
                "attached_to": [],
                "status": [],
            },
        }
    )
    return board["units"]


def test_attached_hmg_team_answers_to_both_hqs(board):
    u, prot = _units(board), []
    setup.assign_platoon(board, "1/1 HMG", u["1/1 HMG"], "1", prot)
    assert u["1/1 HMG"]["platoon"] == "HMG" and u["1/1 HMG"]["attached_to"] == ["1st PLT HQ"]
    assert "HMG PLT HQ keeps command" in prot[-1]
    assert comms.chain_of_command(board, "HMG PLT HQ", "1/1 HMG")
    assert comms.chain_of_command(board, "1st PLT HQ", "1/1 HMG")
    with pytest.raises(rules.Violation):
        comms.chain_of_command(board, "2nd PLT HQ", "1/1 HMG")
    setup.assign_platoon(board, "1/1 HMG", u["1/1 HMG"], "none", prot)  # detached again: HMG PLT HQ only
    assert u["1/1 HMG"]["platoon"] == "HMG" and u["1/1 HMG"]["attached_to"] == []


def test_company_attachment_still_moves_to_the_platoon(board):
    u, prot = _units(board), []
    setup.assign_platoon(board, "1/75mm RCL", u["1/75mm RCL"], "1", prot)
    assert u["1/75mm RCL"]["platoon"] == "1" and u["1/75mm RCL"]["attached_to"] == ["1st PLT HQ"]
    setup.assign_platoon(board, "1/75mm RCL", u["1/75mm RCL"], "none", prot)
    assert u["1/75mm RCL"]["platoon"] is None and u["1/75mm RCL"]["attached_to"] == []
