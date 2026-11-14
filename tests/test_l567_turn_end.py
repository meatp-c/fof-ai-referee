"""L567: terrain catalog source in English (old German source text translated on load); the terrain hint names the
English option names."""

import pytest

from fof import migrate, rules, setup


def test_catalog_source_of_an_older_game_is_translated():
    old = {"terrain_catalog": {"Rocky": {"source": "beim Aufdecken vom Brett abgelesen (L482)", "cc": 1}}}
    new = migrate.state(old)
    assert new["terrain_catalog"]["Rocky"]["source"] == "read from the card on the board when revealed (L482)"


def test_unknown_terrain_names_the_english_options(board):
    board["terrain_catalog"] = {}
    with pytest.raises(rules.Violation, match="--new-type=yes") as err:
        setup.set_terrain(board, "22", "Rocky", {})
    assert "--vehicles=normal|slow|no" in str(err.value)
    setup.set_terrain(board, "22", "Rocky", {"--new-type": "yes", "--cc": "1", "--cover_max": "2", "--cover_draw": "2"})
    assert board["terrain_catalog"]["Rocky"]["source"] == "read from the card on the board when revealed (L482)"
