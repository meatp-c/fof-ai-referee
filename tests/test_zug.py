"""L470: werkzeuge/zug.py, the one-call probe/book/commit helper (parsing and output filter only; no game folder)."""

import importlib.util
import pathlib

SPEC = importlib.util.spec_from_file_location("zug", pathlib.Path(__file__).resolve().parent.parent / "tool" / "zug.py")
zug = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(zug)


def test_read_commands_skips_comments_and_keeps_quotes():
    cmds = zug.read_commands('# note\nhq "1st PLT HQ"\n\ncard ? 5\n')
    assert cmds == [["hq", "1st PLT HQ"], ["card", "?", "5"]]


def test_shorten_drops_only_allowed_headers():
    out = "ALLOWED [RULE 4.2.2a p.23]\nGI orders 1/3: Move; cost 1\nBoard: 1/3 to 43, Exposed\nCHECKSTAMP OK"
    assert zug.shorten(out, False).splitlines() == [
        "GI orders 1/3: Move; cost 1",
        "Board: 1/3 to 43, Exposed",
        "CHECKSTAMP OK",
    ]
    assert zug.shorten(out, True) == out


def test_parse_args():
    o = zug.parse_args(["--probe", "--msg", "x y"])
    assert o["probe"] and o["msg"] == "x y" and not o["all"]
