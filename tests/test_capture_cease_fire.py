"""L468: after a capture the captors' fire on that card ceases when no target is left (6.3.3)."""

from conftest import unit


def test_capture_ends_point_blank_fire(board, monkeypatch):
    from fof import combat

    s = board
    s["phase"] = "3.5.1"
    s["einheiten"]["PT"] = unit("22", side="Feind", steps=1)
    s["einheiten"]["PT"]["typ"] = "Paralyzed Team"
    s["einheiten"]["A"] = unit("22", ziel="22")
    s["einheiten"]["B"] = unit("22", ziel="22")
    monkeypatch.setattr(combat.campaign, "book_xp", lambda *a, **k: None)
    monkeypatch.setattr(combat.state, "save_state", lambda *a, **k: None)
    monkeypatch.setattr(combat.briefing, "print_board", lambda *a, **k: None)
    combat.cmd_capture(s, ["PT", "B"])
    assert s["einheiten"]["A"]["ziel"] is None
