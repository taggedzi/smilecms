"""Collect derivative generation tasks."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Iterator, Tuple, Literal

from ..config import Config, DerivativeProfile
from ..content import ContentDocument, MediaReference
from .models import MediaDerivativeTask, MediaPlan

MediaRole = Literal["hero", "asset"]


def collect_media_plan(documents: Iterable[ContentDocument], config: Config) -> MediaPlan:
    plan = MediaPlan()
    profiles = config.media_processing.profiles
    if not profiles:
        return plan

    source_root = config.media_processing.source_dir
    output_root = config.media_processing.output_dir
    seen: Dict[Tuple[str, str], MediaDerivativeTask] = {}

    for document in documents:
        for role, reference in _iter_references(document):
            rel_path = reference.path
            for profile in profiles:
                key = (rel_path, profile.name)
                task = seen.get(key)
                if task is None:
                    task = MediaDerivativeTask(
                        source=source_root / rel_path,
                        destination=_destination_path(output_root, rel_path, profile),
                        profile=profile,
                        media_path=rel_path,
                    )
                    plan.add_task(task)
                    seen[key] = task
                task.add_document(document.slug)
                task.add_role(role)  # type: ignore[arg-type]

    return plan


def _iter_references(document: ContentDocument) -> Iterator[tuple[MediaRole, MediaReference]]:
    if document.meta.hero_media:
        yield "hero", document.meta.hero_media
    for asset in document.assets:
        yield "asset", asset


def _destination_path(output_root: Path, rel_path: str, profile: DerivativeProfile) -> Path:
    original = Path(rel_path)
    stem = original.stem
    suffix = profile.format
    parent = output_root / profile.name / original.parent
    return parent / f"{stem}.{suffix}"
