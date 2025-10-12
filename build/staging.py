"""Utilities for preparing the deployable site bundle."""

from __future__ import annotations

import shutil
from pathlib import Path

from .config import Config


def reset_directory(path: Path) -> None:
    """Remove a directory and recreate it empty."""
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def stage_static_site(config: Config) -> list[Path]:
    """Copy web assets and media derivatives into the output directory.

    Returns a list of destination paths that were staged.
    """
    staged: list[Path] = []

    template_root = config.templates_dir
    output_root = config.output_dir
    output_root.mkdir(parents=True, exist_ok=True)

    if template_root.exists():
        for item in template_root.iterdir():
            destination = output_root / item.name
            if item.is_dir():
                _copytree(item, destination)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, destination)
            staged.append(destination)

    derived_source = config.media_processing.output_dir
    if derived_source.exists():
        derived_source_abs = derived_source.resolve()
        output_root_abs = output_root.resolve()
        should_copy = True
        try:
            derived_source_abs.relative_to(output_root_abs)
            should_copy = False
        except ValueError:
            should_copy = True

        if should_copy:
            relative_target = (
                derived_source
                if not derived_source.is_absolute()
                else Path(derived_source.name)
            )
            derived_destination = output_root / relative_target
            derived_destination.parent.mkdir(parents=True, exist_ok=True)
            if derived_destination.exists():
                shutil.rmtree(derived_destination)
            shutil.copytree(derived_source_abs, derived_destination)
            staged.append(derived_destination)
        else:
            staged.append(derived_source_abs)

    return staged


def _copytree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
