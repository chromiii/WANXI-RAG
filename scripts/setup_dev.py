"""Bootstrap a local development environment without reading private project data."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent.parent


def run(python: Path, *args: str) -> None:
    subprocess.run([str(python), *args], cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create the WANXI-RAG virtual environment and validate the codebase."
    )
    parser.add_argument(
        "--with-ml",
        action="store_true",
        help="Install sentence-transformers/torch dependencies required for full local RAG retrieval.",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Create/install the environment without running the unit test suite.",
    )
    args = parser.parse_args()

    if sys.version_info < (3, 10):
        raise SystemExit("Python 3.10+ required; Python 3.12 recommended.")

    destination = ROOT / ".venv"
    python = destination / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    if not python.exists():
        print(f"Creating virtual environment: {destination}")
        venv.EnvBuilder(with_pip=True).create(destination)

    print("Installing base runtime dependencies...")
    run(python, "-m", "pip", "install", "--upgrade", "pip")
    run(python, "-m", "pip", "install", "-r", str(ROOT / "requirements.lock"))

    if args.with_ml:
        print("Installing local embedding/reranker dependencies...")
        run(python, "-m", "pip", "install", "-r", str(ROOT / "requirements-ml.txt"))

    print("Compiling package...")
    run(python, "-m", "compileall", "-q", "trendee")

    if not args.skip_tests:
        print("Running code-only tests...")
        run(python, "-m", "unittest", "discover", "-s", "tests", "-v")

    print()
    print("Environment ready. No private Wanxi data or API key was read.")
    if args.with_ml:
        print("Full local retrieval dependencies are installed.")
    else:
        print("For the full RAG demo, rerun with --with-ml or install requirements-ml.txt.")
    if os.name == "nt":
        print(r"Activate: .\.venv\Scripts\Activate.ps1")
    else:
        print("Activate: source .venv/bin/activate")
    print("Next: copy .env.example to .env, provide the authorized PDF, then follow docs/INSTALL.md.")


if __name__ == "__main__":
    main()
