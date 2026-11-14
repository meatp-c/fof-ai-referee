"""L555 (review E6/S8): the annotated module boundaries (state, rules, options, comms) pass mypy. Skipped where mypy is
not installed (pip install mypy)."""

import pathlib

import pytest

mypy_api = pytest.importorskip("mypy.api")

ANNOTATED = ("state.py", "rules.py", "options.py", "comms.py")


def test_annotated_modules_pass_mypy():
    root = pathlib.Path(__file__).resolve().parents[1]
    pkg = root / "tool" / "fof"
    out, err, code = mypy_api.run(
        ["--ignore-missing-imports", "--follow-imports=silent", "--python-version", "3.10"]
        + [str(pkg / f) for f in ANNOTATED]
    )
    assert code == 0, out + err
