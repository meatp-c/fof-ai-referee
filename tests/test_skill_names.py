"""L476: every Auto skill that can be bought (rules.SKILL_COST) is usable in an order under the same name."""

import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "tool"))
from fof import commands, rules  # noqa: E402


def test_auto_skill_names_match_the_markers():
    bought = {k for k in rules.SKILL_COST if k.startswith("Auto ")}
    assert bought == set(commands.SKILL_AUTO)
