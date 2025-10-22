"""Utilities for preparing the deployable site bundle."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config


@dataclass
class StagingResult:
    """Summary of staged template and media assets."""

    staged_paths: list[Path] = field(default_factory=list)
    template_paths: list[Path] = field(default_factory=list)
    removed_templates: list[Path] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.staged_paths)


def reset_directory(path: Path) -> None:
    """Remove a directory and recreate it empty."""
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def stage_static_site(
    config: Config,
    *,
    previous_template_paths: set[Path] | None = None,
) -> StagingResult:
    """Copy web assets and media derivatives into the output directory.

    Returns details about staged and removed assets.
    """
    result = StagingResult()

    template_root = config.resolved_templates_dir
    output_root = config.output_dir
    output_root.mkdir(parents=True, exist_ok=True)

    current_template_paths: set[Path] = set()
    if template_root.exists():
        for item in template_root.iterdir():
            destination = output_root / item.name
            if item.is_dir():
                _copytree(item, destination)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, destination)
            result.staged_paths.append(destination)
            result.template_paths.append(destination)
            current_template_paths.add(destination)
    elif previous_template_paths:
        # Template root removed; clean up any previously staged assets.
        for candidate in previous_template_paths:
            if candidate.exists():
                _delete_path(candidate)
                result.removed_templates.append(candidate)

    # Remove stale template assets that no longer exist in the source directory.
    if previous_template_paths:
        for orphan in sorted(previous_template_paths - current_template_paths, key=lambda p: len(p.parts), reverse=True):
            if orphan.exists():
                _delete_path(orphan)
                result.removed_templates.append(orphan)

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
            result.staged_paths.append(derived_destination)
        else:
            result.staged_paths.append(derived_source_abs)

    return result


def _copytree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def _delete_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)
