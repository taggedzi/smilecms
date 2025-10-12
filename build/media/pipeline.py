"""Collect derivative generation tasks."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Iterable, Iterator, Tuple, Literal

from ..config import Config, DerivativeProfile
from ..content import ContentDocument, MediaReference
from .models import MediaDerivativeTask, MediaPlan

logger = logging.getLogger(__name__)

MediaRole = Literal["hero", "asset"]
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".tiff", ".bmp"}


def collect_media_plan(documents: Iterable[ContentDocument], config: Config) -> MediaPlan:
    plan = MediaPlan()
    profiles = config.media_processing.profiles
    output_root = config.media_processing.output_dir
    seen: Dict[Tuple[str, str], MediaDerivativeTask] = {}

    for document in documents:
        for role, reference in _iter_references(document):
            rel_path = _normalize_media_path(reference.path)
            reference.path = rel_path
            source_path = _resolve_source_path(rel_path, config)
            if source_path is None:
                logger.warning(
                    "Unable to resolve media source for '%s' referenced by '%s'.",
                    rel_path,
                    document.slug,
                )
                continue

            if _is_image_extension(rel_path) and profiles:
                for profile in profiles:
                    key = (rel_path, profile.name)
                    task = seen.get(key)
                    if task is None:
                        task = MediaDerivativeTask(
                            source=source_path,
                            destination=_destination_path(output_root, rel_path, profile),
                            profile=profile,
                            media_path=rel_path,
                        )
                        plan.add_task(task)
                        seen[key] = task
                    task.add_document(document.slug)
                    task.add_role(role)  # type: ignore[arg-type]
            else:
                plan.add_static_asset(rel_path, source_path)

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


def _normalize_media_path(path: str) -> str:
    normalized = path.replace("\\", "/").lstrip("/")
    return normalized


def _is_image_extension(path: str) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTENSIONS


def _resolve_source_path(rel_path: str, config: Config) -> Path | None:
    parts = Path(rel_path).parts
    if not parts:
        return None
    prefix, remainder = parts[0], parts[1:]
    for mount_prefix, base_dir in config.media_mounts:
        if prefix == mount_prefix:
            return base_dir.joinpath(*remainder)
    # Fallback to legacy location under media_processing source dir.
    return config.media_processing.source_dir / Path(rel_path)
