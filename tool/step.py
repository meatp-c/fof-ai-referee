#!/usr/bin/env python3
"""One call per game step: probe in a scratch copy, book for real only if every command is legal, then git commit.

Usage (commands on stdin, one fof command line per line; '#' lines are ignored):
    python3 tool/step.py [--probe] [--all] [--msg "commit text"] [--game <folder>] <<'EOF'
    hq "1st PLT HQ"
    card ? 5
    order "1st PLT HQ" 2/1 4.2.2c --target=32 --success=yes
    EOF

  --probe   only the scratch run, nothing is booked or committed
  --all     print every output line (default: all but the ALLOWED header lines)
  --msg     commit message (default: "<game> T<turn>: <first command>")
  --game    game folder (default: the one named in .current_game)

Exit code 0 booked (or probe ok), 2 a VIOLATION in the probe (nothing booked), 1 other error.
replaces the probe/book/commit/lock-cleanup sequence of three to four separate calls. named step.py (until
 it had a German name); the German option name and the file names of earlier releases are still accepted.
the verdict comes from fof.py's exit code (0 legal, 2 VIOLATION, anything else an error such as a traceback or
'No game state'), not from the word VIOLATION in the text: informational lines, help texts and notes may contain it.
"""

import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent  # same root as fof.state.ROOT: the folder above tool/
FOF = HERE / "fof.py"
sys.path.insert(0, str(HERE))
from fof import migrate  # noqa: E402  (file names of earlier releases)

ATTRIBUTION = os.environ.get("FOF_COMMIT_TRAILER", "")


def parse_args(argv):
    opts = {"probe": False, "all": False, "msg": None, "game": None}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--probe", "--all"):
            opts[a[2:]] = True
        elif migrate.OPTION_WORDS.get(a, a) in ("--msg", "--game") and i + 1 < len(argv):
            opts[migrate.OPTION_WORDS.get(a, a)[2:]] = argv[i + 1]
            i += 1
        else:
            raise SystemExit(f"unknown argument {a}")
        i += 1
    return opts


def read_commands(text):
    cmds = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            cmds.append(shlex.split(line))
    return cmds


def run(cmd, game_dir):
    """Run one fof command against game_dir; returns (exit code, output)."""
    env = dict(os.environ, FOF_GAME=str(game_dir), PYTHONUTF8="1")
    # drop the variable name of earlier releases, never FOF_GAME itself (without it the probe would run
    # against the real game from .current_game and every step would be booked twice)
    env.pop(migrate.ENV["FOF_GAME"], None)
    p = subprocess.run(
        [sys.executable, str(FOF), *cmd], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8"
    )
    return p.returncode, (p.stdout + p.stderr).rstrip("\n")


def verdict(rc, out):
    """'ok', 'violation' (exit 2, cli.main) or 'error' (any other exit code, or a traceback in the output)."""
    if rc == 2:
        return "violation"
    if rc != 0 or "Traceback (most recent call last)" in out:
        return "error"
    return "ok"


def shorten(out, show_all):
    """Default: everything except the ALLOWED headers (the order line below them names action and cost)."""
    if show_all:
        return out
    return "\n".join(ln for ln in out.splitlines() if not ln.startswith("ALLOWED"))


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")


def clear_locks():
    """The VM sandbox cannot delete in the connected folder: move git's leftover lock files aside (never under refs)."""
    gitdir = ROOT / ".git"
    for lk in list(gitdir.glob("*.lock")) + [gitdir / "objects" / "maintenance.lock"]:
        if lk.exists():
            try:
                lk.rename(gitdir / f"stale-{lk.name}-{os.getpid()}-{abs(hash(str(lk)))}")
            except OSError:
                pass


def commit(game, msg):
    clear_locks()
    paths = [p for p in (game, "data", "normandy", HERE.name, "tests", "export_en") if (ROOT / p).exists()]
    if not git("--no-optional-locks", "status", "--porcelain", "--", *paths).stdout.strip():
        return "git: nothing to commit"  # a step that changed nothing leaves no lock file behind
    git("add", "-A", *paths)
    body = msg + (f"\n\n{ATTRIBUTION}" if ATTRIBUTION else "")
    r = git("commit", "-q", "-m", body)
    clear_locks()
    if r.returncode != 0 and "nothing to commit" not in (r.stdout + r.stderr):
        return "git: " + (r.stderr.strip().splitlines() or ["commit failed"])[-1]
    h = git("log", "--oneline", "-1").stdout.strip()
    return f"git: {h}" if r.returncode == 0 else "git: nothing to commit"


def turn_of(game_dir):
    try:
        s = json.loads((game_dir / "game_state.json").read_text(encoding="utf-8"))
        return migrate.state(s).get("turn")  # a game not yet saved since still has German keys
    except (OSError, ValueError):
        return None


def main():
    opts = parse_args(sys.argv[1:])
    cmds = read_commands(sys.stdin.read())
    if not cmds:
        raise SystemExit("no commands on stdin")
    game = opts["game"] or migrate.path(ROOT, ".current_game").read_text(encoding="utf-8").strip()
    real = ROOT / game
    migrate.adopt(real)  # game_state.json and history/ instead of the names of an earlier release
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="fofstep_"))
    try:
        probe = scratch / pathlib.Path(game).name  # an absolute --game must not resolve to the real folder
        # undo needs the snapshots, so the probe copies history only then
        needs_history = any(
            c and c[0] in ("undo", *[g for g, e in migrate.COMMANDS_DE.items() if e == "undo"]) for c in cmds
        )
        shutil.copytree(real, probe, ignore=None if needs_history else shutil.ignore_patterns("history"))
        (probe / "history").mkdir(exist_ok=True)
        for c in cmds:
            rc, out = run(c, probe)
            v = verdict(rc, out)
            if v != "ok":
                why = "probe" if v == "violation" else f"probe, error exit {rc}"
                print(f"PROBE {' '.join(c)}\n{shorten(out, opts['all'])}\nNOT BOOKED ({why})")
                sys.exit(2 if v == "violation" else 1)
            if opts["probe"]:
                print(f"PROBE {' '.join(c)}\n{shorten(out, opts['all'])}")
        if opts["probe"]:
            return
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        if scratch.exists():
            print(f"NOTE: scratch folder {scratch} could not be removed")
    for i, c in enumerate(cmds):
        rc, out = run(c, real)
        print(f"> {' '.join(c)}\n{shorten(out, opts['all'])}")
        if verdict(rc, out) != "ok":  # should not happen after a clean probe; stop and report
            done = f"commands 1-{i} are booked but not committed" if i else "nothing was booked"
            print(
                f"STOPPED: {'violation' if rc == 2 else f'error exit {rc}'} in the real run of command {i + 1}; {done}"
            )
            sys.exit(1)
    msg = opts["msg"] or f"{game} T{turn_of(real)}: {' '.join(cmds[0])}"
    print(commit(game, msg))


if __name__ == "__main__":
    main()
