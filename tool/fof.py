#!/usr/bin/env python3
"""Fields of Fire Deluxe rules engine, command-line entry point. Run without arguments for the command list."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fof.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
