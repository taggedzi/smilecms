"""Generate media derivatives from the media plan."""

from __future__ import annotations

import contextlib
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Set, Any, Union, cast, Callable

import math
from PIL import Image, ImageDraw, ImageFont

from ..config import Config, DerivativeProfile, MediaMetadataEmbedConfig, MediaWatermarkConfig
from ..content import ContentDocument, MediaReference, MediaVariant
from .models import MediaPlan

logger = logging.getLogger(__name__)


@dataclass
class MediaProcessingResult:
    variants: Dict[str, list[MediaVariant]] = field(default_factory=dict)
    processed_tasks: int = 0
    reused_tasks: int = 0
    skipped_tasks: int = 0
    warnings: list[str] = field(default_factory=list)
    missing_sources: list[str] = field(default_factory=list)
    unsupported_media: list[str] = field(default_factory=list)
    copied_assets: int = 0
    reused_assets: int = 0
    pruned_artifacts: int = 0

    def add_task_variant(self, media_path: str, variant: MediaVariant, *, reused: bool = False) -> None:
        self.variants.setdefault(media_path, []).append(variant)
        if reused:
            self.reused_tasks += 1
        else:
            self.processed_tasks += 1

    def add_static_variant(self, media_path: str, variant: MediaVariant, *, reused: bool = False) -> None:
        variants = self.variants.setdefault(media_path, [])
        # Avoid duplicate entries when multiple references share the same asset.
        if any(existing.profile == variant.profile and existing.path == variant.path for existing in variants):
            return
        variants.append(variant)
        if reused:
            self.reused_assets += 1
        else:
            self.copied_assets += 1

    @property
    def processed_assets(self) -> int:
        return len(self.variants)

    @property
    def variants_generated(self) -> int:
        return sum(len(items) for items in self.variants.values())


def process_media_plan(
    plan: MediaPlan,
    config: Config,
    *,
    on_progress: Callable[[str], None] | None = None,
) -> MediaProcessingResult:
    """Execute derivative tasks and return processing details.

    When provided, ``on_progress`` is called with either "derivative" or "asset"
    after handling each corresponding unit of work. This enables callers (e.g.,
    the CLI) to display progress without changing core logic or results.
    """
    result = MediaProcessingResult()
    derived_root = config.media_processing.output_dir
    expected_files: Set[Path] = set()

    for task in plan.tasks:
        source = task.source
        if not source.exists():
            message = f"Media source missing: {source}"
            logger.warning(message)
            result.missing_sources.append(source.as_posix())
            result.skipped_tasks += 1
            if on_progress is not None:
                on_progress("derivative")
            continue

        if not _is_image(source):
            logger.info("Skipping unsupported media type: %s", source)
            result.unsupported_media.append(source.as_posix())
            result.skipped_tasks += 1
            if on_progress is not None:
                on_progress("derivative")
            continue

        destination = task.destination
        destination.parent.mkdir(parents=True, exist_ok=True)

        if _is_cached(source, destination):
            variant = _load_existing_variant(destination, task.profile, derived_root)
            result.add_task_variant(task.media_path, variant, reused=True)
            expected_files.add(destination.resolve())
            if on_progress is not None:
                on_progress("derivative")
            continue

        try:
            variant = _process_image(source, destination, task.profile, config)
        except Exception as exc:
            try:
                bomb_error = getattr(Image, "DecompressionBombError")
            except Exception:
                bomb_error = Exception  # fallback; won't match below if missing
            if isinstance(exc, bomb_error):
                message = f"Oversized image skipped due to limit: {source} ({exc})"
                logger.warning(message)
                result.warnings.append(message)
                result.skipped_tasks += 1
                continue
            raise

        variant.path = _relative_variant_path(destination, derived_root)
        result.add_task_variant(task.media_path, variant)
        expected_files.add(destination.resolve())
        if on_progress is not None:
            on_progress("derivative")

    for rel_path, source in plan.static_assets.items():
        destination = derived_root / rel_path
        if not source.exists():
            message = f"Media source missing: {source}"
            logger.warning(message)
            result.missing_sources.append(source.as_posix())
            if on_progress is not None:
                on_progress("asset")
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if _is_cached(source, destination):
            variant = MediaVariant(
                profile="original",
                path=rel_path,
                width=None,
                height=None,
                format=destination.suffix.lstrip(".").lower() or None,
                quality=None,
            )
            result.add_static_variant(rel_path, variant, reused=True)
        else:
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
        expected_files.add(destination.resolve())
        if on_progress is not None:
            on_progress("asset")

    pruned = _prune_stale_artifacts(derived_root, expected_files)
    if pruned:
        result.pruned_artifacts = pruned

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


def _process_image(
    source: Path, destination: Path, profile: DerivativeProfile, config: Config
) -> MediaVariant:
    with Image.open(source) as image:
        if "A" in image.getbands():
            image = image.convert("RGBA")
        else:
            image = image.convert("RGB")
        target_size = _calculate_target_size(image.size, profile)
        if target_size and target_size != image.size:
            image = image.resize(target_size, Image.Resampling.LANCZOS)

        # Optional watermark overlay
        wm_config: MediaWatermarkConfig = getattr(
            config.media_processing, "watermark", MediaWatermarkConfig()
        )
        if (
            wm_config.enabled
            and wm_config.text
            and min(image.size) >= max(1, wm_config.min_size)
        ):
            try:
                image = _apply_watermark(image, wm_config)
            except Exception as exc:  # best-effort; don't fail the pipeline
                logger.warning("Watermarking failed for %s: %s", source, exc)

        save_format = _resolve_format(profile.format)
        save_kwargs = _build_save_kwargs(save_format, profile.quality)

        # Optional metadata embedding (JPEG/TIFF EXIF, PNG tEXt)
        embed_config: MediaMetadataEmbedConfig = getattr(
            config.media_processing, "embed_metadata", MediaMetadataEmbedConfig()
        )
        if embed_config.enabled:
            try:
                save_kwargs.update(_prepare_metadata_kwargs(image, save_format, embed_config))
            except Exception as exc:  # best-effort; don't fail the pipeline
                logger.warning("Metadata embed failed for %s: %s", source, exc)

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


def _is_cached(source: Path, destination: Path) -> bool:
    if not destination.exists():
        return False
    try:
        return destination.stat().st_mtime_ns >= source.stat().st_mtime_ns and destination.stat().st_size > 0
    except FileNotFoundError:
        return False


def _load_existing_variant(destination: Path, profile: DerivativeProfile, derived_root: Path) -> MediaVariant:
    width = height = None
    with Image.open(destination) as image:
        width, height = image.size
    return MediaVariant(
        profile=profile.name,
        path=_relative_variant_path(destination, derived_root),
        width=width,
        height=height,
        format=profile.format.lower(),
        quality=profile.quality,
    )


def _relative_variant_path(destination: Path, derived_root: Path) -> str:
    try:
        relative = destination.relative_to(derived_root)
        return relative.as_posix()
    except ValueError:
        return destination.as_posix()


def _prune_stale_artifacts(root: Path, keep: Set[Path]) -> int:
    if not root.exists():
        return 0

    keep_resolved = {path.resolve() for path in keep}
    removed = 0

    for existing in root.rglob("*"):
        existing_resolved = existing.resolve()
        if existing.is_file() and existing_resolved not in keep_resolved:
            with contextlib.suppress(FileNotFoundError):
                existing.unlink()
                removed += 1

    # Clean up empty directories from leaf to root.
    directories = sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    )
    for directory in directories:
        with contextlib.suppress(OSError):
            directory.rmdir()

    return removed


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
    if height is None:
        return None
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


def _apply_watermark(image: Image.Image, wm: MediaWatermarkConfig) -> Image.Image:
    width, height = image.size
    base_mode = image.mode

    if base_mode != "RGBA":
        base = image.convert("RGBA")
    else:
        base = image

    shorter = max(1, min(width, height))
    font_size = max(1, int(shorter * wm.font_size_ratio))
    # Ensure consistent type across code paths for mypy
    font: Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]
    if wm.font_path:
        try:
            font = ImageFont.truetype(str(wm.font_path), font_size)
        except Exception:
            font = ImageFont.load_default()
    else:
        # load_default doesn't scale; still usable as fallback
        font = ImageFont.load_default()

    # Create a large transparent canvas to allow rotation without clipping, then crop
    diag = int(math.hypot(width, height)) * 2
    overlay = Image.new("RGBA", (diag, diag), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    text = wm.text
    # Measure text
    try:
        bbox = draw.textbbox((0, 0), text, font=cast(ImageFont.ImageFont, font))
        text_w = max(1, bbox[2] - bbox[0])
        text_h = max(1, bbox[3] - bbox[1])
    except Exception:
        text_w = max(1, font_size * max(1, len(text)))
        text_h = max(1, font_size)

    step_x = int(text_w * (1.0 + wm.spacing_ratio))
    step_y = int(text_h * (1.0 + wm.spacing_ratio))

    color_rgb = _parse_hex_rgb(wm.color)
    fill = (color_rgb[0], color_rgb[1], color_rgb[2], wm.opacity)

    # Tile text across overlay
    for y in range(-step_y, diag + step_y, step_y):
        # offset every other row for a nice pattern
        x_offset = 0 if ((y // step_y) % 2 == 0) else step_x // 2
        for x in range(-step_x, diag + step_x, step_x):
            draw.text((x + x_offset, y), text, font=cast(ImageFont.ImageFont, font), fill=fill)

    # Rotate and crop the overlay back to image size
    rotated = overlay.rotate(wm.angle, resample=Image.Resampling.BICUBIC, expand=True)
    cx, cy = rotated.size[0] // 2, rotated.size[1] // 2
    left = cx - (width // 2)
    top = cy - (height // 2)
    wm_cropped = rotated.crop((left, top, left + width, top + height))

    composed = Image.alpha_composite(base, wm_cropped)
    if base_mode != "RGBA":
        return composed.convert(base_mode)
    return composed


def _parse_hex_rgb(value: str) -> tuple[int, int, int]:
    text = (value or "").strip()
    if text.startswith("#"):
        text = text[1:]
    if len(text) == 3:
        r, g, b = [int(c * 2, 16) for c in text]
    elif len(text) >= 6:
        r = int(text[0:2], 16)
        g = int(text[2:4], 16)
        b = int(text[4:6], 16)
    else:
        r, g, b = (255, 255, 255)
    return (r, g, b)


def _prepare_metadata_kwargs(
    image: Image.Image, fmt: str, meta: MediaMetadataEmbedConfig
) -> dict[str, Any]:
    # Only embed when values exist
    has_values = any([meta.artist, meta.copyright, meta.license, meta.url])
    if not has_values:
        return {}

    fmt = fmt.upper()
    if fmt in {"JPEG", "TIFF"}:
        try:
            exif = image.getexif()
        except Exception:
            exif = None
        if exif is None:
            return {}
        # EXIF tag ids
        TAG_ImageDescription = 0x010E
        TAG_Artist = 0x013B
        TAG_Copyright = 0x8298

        description_parts: list[str] = []
        if meta.license:
            description_parts.append(f"License: {meta.license}")
        if meta.url:
            description_parts.append(f"URL: {meta.url}")
        description = "; ".join(description_parts) if description_parts else None

        if meta.artist:
            exif[TAG_Artist] = str(meta.artist)
        if meta.copyright:
            exif[TAG_Copyright] = str(meta.copyright)
        if description:
            exif[TAG_ImageDescription] = description

        try:
            return {"exif": exif.tobytes()}
        except Exception:
            return {}

    if fmt == "PNG":
        try:
            from PIL.PngImagePlugin import PngInfo

            pnginfo = PngInfo()
            if meta.artist:
                pnginfo.add_text("Author", str(meta.artist))
            if meta.copyright:
                pnginfo.add_text("Copyright", str(meta.copyright))
            if meta.license:
                pnginfo.add_text("License", str(meta.license))
            if meta.url:
                pnginfo.add_text("URL", str(meta.url))
            return {"pnginfo": pnginfo}
        except Exception:
            return {}

    # Other formats: skip to avoid errors
    return {}
