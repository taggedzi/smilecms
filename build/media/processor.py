"""Generate media derivatives from the media plan."""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable

from PIL import Image

from ..config import Config, DerivativeProfile
from ..content import ContentDocument, MediaReference, MediaVariant
from .models import MediaDerivativeTask, MediaPlan

logger = logging.getLogger(__name__)


def process_media_plan(plan: MediaPlan, config: Config) -> dict[str, list[MediaVariant]]:
    """Execute derivative tasks and return variants keyed by media path."""
    variants: Dict[str, list[MediaVariant]] = defaultdict(list)
    derived_root = config.media_processing.output_dir

    for task in plan.tasks:
        variant = _process_task(task)
        if variant is None:
            continue
        try:
            relative = task.destination.relative_to(derived_root)
            variant.path = relative.as_posix()
        except ValueError:
            # Destination escaped derived root; keep original path.
            variant.path = task.destination.as_posix()
        variants[task.media_path].append(variant)

    return {key: value for key, value in variants.items()}


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


def _process_task(task: MediaDerivativeTask) -> MediaVariant | None:
    source = task.source
    destination = task.destination
    profile = task.profile

    if not source.exists():
        logger.warning("Media source missing: %s", source)
        return None

    destination.parent.mkdir(parents=True, exist_ok=True)

    if _is_image(source):
        return _process_image(source, destination, profile)

    logger.info("Skipping unsupported media type: %s", source)
    return None


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".tiff", ".bmp"}


def _process_image(source: Path, destination: Path, profile: DerivativeProfile) -> MediaVariant | None:
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
