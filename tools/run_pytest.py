"""Wrapper to execute pytest from the project virtual environment if available."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _venv_python(root: Path) -> Path | None:
    scripts_dir = "Scripts" if os.name == "nt" else "bin"
    executable = "python.exe" if os.name == "nt" else "python"
    candidate = root / ".venv" / scripts_dir / executable
    return candidate if candidate.exists() else None


def main(argv: list[str] | None = None) -> int:
    argv = [] if argv is None else argv
    root = Path(__file__).resolve().parents[1]
    venv_executable = _venv_python(root)
    python = str(venv_executable or sys.executable)

    cmd = [python, "-m", "pytest", "-q", *argv]
    return subprocess.call(cmd, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
