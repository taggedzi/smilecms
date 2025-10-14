"""Metadata generation for gallery assets."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from PIL import Image, ExifTags

from .models import GalleryCollectionEntry, GalleryImageEntry
from .utils import hash_file, title_from_stem

logger = logging.getLogger(__name__)

EXIF_DATETIME_KEYS = {
    "DateTimeOriginal",
    "DateTimeDigitized",
    "DateTime",
}


def generate_collection_defaults(entry: GalleryCollectionEntry, now: datetime) -> bool:
    """Ensure core collection metadata fields exist."""
    metadata = entry.metadata
    changed = False

    if not metadata.title:
        metadata.title = title_from_stem(entry.id)
        changed = True

    if metadata.created_at is None:
        metadata.created_at = now
        changed = True

    if changed:
        metadata.updated_at = now
    elif metadata.updated_at is None:
        metadata.updated_at = now
        changed = True

    entry.metadata = metadata
    return changed


def generate_image_metadata(
    entry: GalleryImageEntry,
    collection: GalleryCollectionEntry,
    now: datetime,
) -> bool:
    """Populate missing metadata for a single gallery image."""
    metadata = entry.metadata
    source_path = entry.source_path
    changed = False

    if metadata.collection_id != collection.id:
        metadata.collection_id = collection.id
        changed = True

    filename = source_path.name
    if metadata.filename != filename:
        metadata.filename = filename
        changed = True

    stem = Path(filename).stem
    auto_title = title_from_stem(stem)
    if not metadata.title:
        metadata.title = auto_title
        changed = True

    if metadata.alt_raw is None:
        metadata.alt_raw = auto_title
        changed = True
    if metadata.alt_text is None:
        metadata.alt_text = metadata.alt_raw
        changed = True

    if metadata.description_raw is None:
        description = f"{metadata.alt_raw} from {collection.metadata.title}"
        metadata.description_raw = description
        changed = True
    if metadata.description is None:
        metadata.description = metadata.description_raw
        changed = True

    if metadata.caption_raw is None:
        metadata.caption_raw = metadata.description_raw
        changed = True
    if metadata.caption is None:
        metadata.caption = metadata.caption_raw
        changed = True

    generated_tags = _generate_tags(stem, collection.metadata.tags)
    if not metadata.tags_raw:
        metadata.tags_raw = generated_tags
        changed = True
    if not metadata.tags:
        metadata.tags = list(dict.fromkeys(metadata.tags_raw))
        changed = True

    if metadata.derived.get("original") is None:
        metadata.derived["original"] = f"gallery/{collection.id}/{filename}"
        changed = True

    stat = source_path.stat()
    filesize = int(stat.st_size)
    if metadata.filesize != filesize:
        metadata.filesize = filesize
        changed = True

    created = _safe_datetime(stat.st_ctime)
    modified = _safe_datetime(stat.st_mtime)
    if metadata.created_at is None:
        metadata.created_at = created
        changed = True
    if metadata.modified_at != modified:
        metadata.modified_at = modified
        changed = True

    digest = hash_file(source_path)
    if metadata.hash != digest:
        metadata.hash = digest
        changed = True

    width, height = _image_dimensions(source_path)
    if width and height:
        if metadata.width != width:
            metadata.width = width
            changed = True
        if metadata.height != height:
            metadata.height = height
            changed = True

    captured = _extract_captured_at(source_path)
    if captured is not None and metadata.captured_at != captured:
        metadata.captured_at = captured
        changed = True

    metadata.last_generated_at = now
    entry.metadata = metadata
    return changed


def _generate_tags(stem: str, collection_tags: Iterable[str]) -> list[str]:
    tokens = []
    for chunk in stem.replace("_", " ").split():
        chunk = chunk.strip().lower()
        if not chunk or chunk.isdigit():
            continue
        tokens.append(chunk)

    combined = list(dict.fromkeys([*collection_tags, *tokens]))
    return combined


def _safe_datetime(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def _image_dimensions(path: Path) -> tuple[int | None, int | None]:
    try:
        with Image.open(path) as image:
            return image.size
    except (OSError, FileNotFoundError) as exc:
        logger.warning("Unable to determine dimensions for %s: %s", path, exc)
        return None, None


def _extract_captured_at(path: Path) -> datetime | None:
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            if not exif:
                return None
            reverse_tags = {ExifTags.TAGS.get(key, str(key)): value for key, value in exif.items()}
            for key in EXIF_DATETIME_KEYS:
                raw_value = reverse_tags.get(key)
                if raw_value:
                    try:
                        return _parse_exif_timestamp(raw_value)
                    except ValueError:
                        continue
    except (OSError, FileNotFoundError) as exc:
        logger.debug("Skipping EXIF extraction for %s: %s", path, exc)
    return None


def _parse_exif_timestamp(value: str) -> datetime:
    """Parse EXIF datetime format YYYY:MM:DD HH:MM:SS."""
    text = str(value).strip()
    if not text:
        raise ValueError("Empty EXIF timestamp")
    try:
        parsed = datetime.strptime(text, "%Y:%m:%d %H:%M:%S")
        return parsed.replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError(f"Unable to parse EXIF timestamp '{value}'") from exc
