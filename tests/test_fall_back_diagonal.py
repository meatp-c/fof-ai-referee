"""L473: Fall Back candidates skip a diagonal that crosses a PDF (5.1.2)."""

from conftest import unit


def test_fall_back_skips_diagonal_across_pdf(board):
    from fof import enemy

    s = board
    s["units"]["G"] = unit("21", side="Enemy")
    s["units"]["A"] = unit("22", target="31")  # PDF 22-31 cuts the diagonal 21-32
    s["units"]["X"] = unit("31", side="Enemy")
    cands = enemy.fall_back_candidates(s, s["units"]["G"])
    assert "32" not in cands
