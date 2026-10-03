"""Create an isolated development environment without reading private project data."""
from pathlib import Path
import os
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent.parent


def main():
    if sys.version_info < (3, 10):
        raise SystemExit("Python 3.10+ required; Python 3.12 recommended.")

    destination = ROOT / ".venv"
    python = destination / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(destination)

    subprocess.run(
        [str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements.lock")],
        cwd=ROOT,
        check=True,
    )
    subprocess.run([str(python), "-m", "compileall", "-q", "trendee"], cwd=ROOT, check=True)
    subprocess.run(
        [str(python), "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
        check=True,
    )
    print("Code environment ready. Private Wanxi data has not been read.")
    print("Activate the virtualenv, inject runtime data, then run: python -m trendee.cli info")


if __name__ == "__main__":
    main()
