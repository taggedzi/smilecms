"""SmileCMS build package exposing CLI and pipeline interfaces."""

from __future__ import annotations

import tomllib
from importlib.metadata import PackageNotFoundError, version as load_pkg_version
from pathlib import Path
from typing import Any

from .ingest import load_documents

__all__ = ["__version__", "load_documents"]


def _read_local_project_version() -> str:
    """Read the project version from pyproject.toml when the package is uninstalled."""
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        data: dict[str, Any] = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return "0.0.0"

    project = data.get("project")
    if isinstance(project, dict):
        version = project.get("version")
        if isinstance(version, str):
            return version

    return "0.0.0"


try:
    __version__ = load_pkg_version("smilecms")
except PackageNotFoundError:
    __version__ = _read_local_project_version()
