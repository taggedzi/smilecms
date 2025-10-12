"""Generate media derivatives from the media plan."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable

from PIL import Image

from ..config import Config, DerivativeProfile
from ..content import ContentDocument, MediaReference, MediaVariant
from .models import MediaPlan

logger = logging.getLogger(__name__)


@dataclass
class MediaProcessingResult:
    variants: Dict[str, list[MediaVariant]] = field(default_factory=dict)
    processed_tasks: int = 0
    skipped_tasks: int = 0
    warnings: list[str] = field(default_factory=list)
    missing_sources: list[str] = field(default_factory=list)
    unsupported_media: list[str] = field(default_factory=list)
    copied_assets: int = 0

    def add_task_variant(self, media_path: str, variant: MediaVariant) -> None:
        self.variants.setdefault(media_path, []).append(variant)
        self.processed_tasks += 1

    def add_static_variant(self, media_path: str, variant: MediaVariant) -> None:
        variants = self.variants.setdefault(media_path, [])
        # Avoid duplicate entries when multiple references share the same asset.
        if any(existing.profile == variant.profile and existing.path == variant.path for existing in variants):
            return
        variants.append(variant)
        self.copied_assets += 1

    @property
    def processed_assets(self) -> int:
        return len(self.variants)

    @property
    def variants_generated(self) -> int:
        return sum(len(items) for items in self.variants.values())


def process_media_plan(plan: MediaPlan, config: Config) -> MediaProcessingResult:
    """Execute derivative tasks and return processing details."""
    result = MediaProcessingResult()
    derived_root = config.media_processing.output_dir

    for task in plan.tasks:
        source = task.source
        if not source.exists():
            message = f"Media source missing: {source}"
            logger.warning(message)
            result.missing_sources.append(source.as_posix())
            result.skipped_tasks += 1
            continue

        if not _is_image(source):
            logger.info("Skipping unsupported media type: %s", source)
            result.unsupported_media.append(source.as_posix())
            result.skipped_tasks += 1
            continue

        destination = task.destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        variant = _process_image(source, destination, task.profile)
        try:
            relative = destination.relative_to(derived_root)
            variant.path = relative.as_posix()
        except ValueError:
            variant.path = destination.as_posix()
        result.add_task_variant(task.media_path, variant)

    for rel_path in plan.static_assets:
        source = config.media_processing.source_dir / rel_path
        destination = derived_root / rel_path
        if not source.exists():
            message = f"Media source missing: {source}"
            logger.warning(message)
            result.missing_sources.append(source.as_posix())
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        variant = MediaVariant(
            profile="original",
            path=rel_path,
            width=None,
            height=None,
            format=destination.suffix.lstrip(".").lower() or None,
            quality=None,
        )
        result.add_static_variant(rel_path, variant)

    return result


def apply_variants_to_documents(
    documents: Iterable[ContentDocument], variants: dict[str, list[MediaVariant]]
) -> None:
    """Attach generated variants back to media references."""
    for document in documents:
        if document.meta.hero_media:
            _apply_to_reference(document.meta.hero_media, variants)
        for reference in document.assets:
            _apply_to_reference(reference, variants)


def _apply_to_reference(reference: MediaReference, variants: dict[str, list[MediaVariant]]) -> None:
    reference.variants = [variant.model_copy() for variant in variants.get(reference.path, [])]


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".tiff", ".bmp"}


def _process_image(source: Path, destination: Path, profile: DerivativeProfile) -> MediaVariant:
    with Image.open(source) as image:
        if "A" in image.getbands():
            image = image.convert("RGBA")
        else:
            image = image.convert("RGB")
        target_size = _calculate_target_size(image.size, profile)
        if target_size and target_size != image.size:
            image = image.resize(target_size, Image.Resampling.LANCZOS)

        save_format = _resolve_format(profile.format)
        save_kwargs = _build_save_kwargs(save_format, profile.quality)

        if save_format == "JPEG" and image.mode != "RGB":
            image = image.convert("RGB")

        image.save(destination, format=save_format, **save_kwargs)
        width, height = image.size

    return MediaVariant(
        profile=profile.name,
        path=destination.as_posix(),
        width=width,
        height=height,
        format=profile.format.lower(),
        quality=profile.quality,
    )


def _calculate_target_size(size: tuple[int, int], profile: DerivativeProfile) -> tuple[int, int] | None:
    orig_width, orig_height = size
    width = profile.width
    height = profile.height

    if width is None and height is None:
        return None

    if width is not None and height is not None:
        scale = min(width / orig_width, height / orig_height, 1.0)
        return int(orig_width * scale), int(orig_height * scale)

    if width is not None:
        scale = min(width / orig_width, 1.0)
        return int(orig_width * scale), int(orig_height * scale)

    # height specified
    scale = min(height / orig_height, 1.0)
    return int(orig_width * scale), int(orig_height * scale)


def _resolve_format(fmt: str) -> str:
    mapping = {
        "jpg": "JPEG",
        "jpeg": "JPEG",
        "png": "PNG",
        "webp": "WEBP",
        "gif": "GIF",
        "bmp": "BMP",
        "tiff": "TIFF",
    }
    return mapping.get(fmt.lower(), fmt.upper())


def _build_save_kwargs(fmt: str, quality: int) -> dict[str, int | bool]:
    kwargs: dict[str, int | bool] = {}
    if fmt in {"JPEG", "WEBP"}:
        kwargs["quality"] = quality
    if fmt == "JPEG":
        kwargs["optimize"] = True
        kwargs["progressive"] = True
    return kwargs
