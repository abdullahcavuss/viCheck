"""How to run pylabview's readRSRC in a child process.

From source:   python -m pylabview.readRSRC ...
Frozen (exe):  viCheck.exe --pylabview ...   (the launcher dispatches this flag to readRSRC.main)

pylabview runs in its own process so a crash or hang on a damaged VI can never take the app down.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# git submodule: https://github.com/abdullahcavuss/pylabview (the package is third_party/pylabview/pylabview)
THIRD_PARTY = os.path.join(os.path.dirname(HERE), "third_party", "pylabview")
FROZEN = bool(getattr(sys, "frozen", False))


def readrsrc_cmd(args):
    """Returns (cmd, env) for running readRSRC with the given arguments.

    --tolerant (added in our pylabview fork): files with inconsistent data are still read, with warnings,
    instead of failing completely - viCheck only reads VIs, it never re-creates them."""
    args = ["--tolerant"] + list(args)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    if FROZEN:
        return [sys.executable, "--pylabview"] + list(args), env
    env["PYTHONPATH"] = THIRD_PARTY + os.pathsep + env.get("PYTHONPATH", "")
    return [sys.executable, "-W", "ignore", "-m", "pylabview.readRSRC"] + list(args), env


def no_window_flags():
    """On Windows, never flash a console window for the child process."""
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    return {}


def run_readrsrc_inprocess(argv):
    """Entry point used by the frozen exe for `--pylabview ...`."""
    import io
    import warnings
    warnings.simplefilter("ignore")
    # a windowed exe may have no stdout/stderr; readRSRC prints a lot
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if THIRD_PARTY not in sys.path:
        sys.path.insert(0, THIRD_PARTY)
    from pylabview import readRSRC
    sys.argv = ["readRSRC"] + list(argv)
    try:
        readRSRC.main()
    except SystemExit as e:
        return int(e.code or 0) if isinstance(e.code, int) else 1
    except Exception as e:
        sys.stderr.write("Error: %s\n" % e)
        return 10
    return 0
