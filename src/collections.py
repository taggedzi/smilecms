"""Load gallery and music collections into content documents."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .config import Config
from .content import (
    ContentDocument,
    ContentMeta,
    ContentStatus,
    ContentType,
    MediaReference,
)
from .gallery import GalleryWorkspace, prepare_workspace
from .gallery.models import GalleryCollectionEntry, GalleryImageEntry

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".tiff", ".bmp"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}


def load_gallery_documents(
    config: Config,
    workspace: GalleryWorkspace | None = None,
) -> list[ContentDocument]:
    """Create content documents for gallery collections supplied by the new pipeline."""
    if workspace is None:
        workspace = prepare_workspace(
            config,
            auto_generate=False,
            run_llm_cleanup=False,
        )

    documents: list[ContentDocument] = []
    for collection in sorted(
        workspace.iter_collections(),
        key=lambda item: (item.metadata.sort_order, item.metadata.title.lower()),
    ):
        meta = collection.metadata
        slug = meta.id.strip().lower()
        title = meta.title
        summary = meta.summary
        description = meta.description or ""
        tags = list(meta.tags)
        if "gallery" not in tags:
            tags.append("gallery")

        hero_entry = _select_gallery_hero(collection)
        hero_reference = _image_to_reference(collection, hero_entry) if hero_entry else None

        assets: list[MediaReference] = []
        for image_entry in collection.images:
            if hero_entry and image_entry.metadata.id == hero_entry.metadata.id:
                continue
            assets.append(_image_to_reference(collection, image_entry))

        content_meta = ContentMeta(
            slug=slug,
            title=title,
            summary=summary,
            tags=tags,
            status=ContentStatus.PUBLISHED,
            content_type=ContentType.GALLERY,
            hero_media=hero_reference,
            published_at=meta.created_at,
            updated_at=meta.updated_at,
        )

        document = ContentDocument(
            meta=content_meta,
            body=description,
            source_path=str(collection.sidecar_path if collection.sidecar_path.exists() else collection.directory),
            assets=assets,
        )
        documents.append(document)

        if hero_reference is None:
            workspace.add_warning(f"Gallery '{slug}' has no hero image defined.")

    return documents


def load_music_documents(config: Config) -> list[ContentDocument]:
    """Create content documents for music tracks."""
    if not config.music.enabled:
        return []
    root = config.music.source_dir
    meta_name = config.music.metadata_filename
    if not root.exists():
        return []

    documents: list[ContentDocument] = []
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        slug = directory.name.strip().lower()
        meta_path = directory / meta_name
        data = _load_yaml(meta_path)

        title = str(data.get("title") or _title_from_slug(slug))
        summary = data.get("summary")
        description = data.get("description") or ""
        tags = _coerce_tags(data.get("tags"))
        if "genre" in data:
            for tag in _coerce_tags(data.get("genre")):
                if tag not in tags:
                    tags.append(tag)
        if "audio" not in tags:
            tags.append("audio")
        status = _parse_status(data.get("status"), default=ContentStatus.PUBLISHED)
        published_at = _parse_datetime(data.get("published_at"))
        updated_at = _parse_datetime(data.get("updated_at"))
        duration = _parse_duration(data.get("duration"))
        asset_meta = data.get("assets") if isinstance(data.get("assets"), dict) else {}

        audio_files = _iter_media_files(directory, AUDIO_EXTENSIONS)
        audio_name = data.get("audio")
        audio_path = _select_primary_file(audio_name, audio_files)
        if audio_path is None:
            logger.warning("Music track '%s' has no audio file; skipping.", slug)
            continue

        audio_rel_path = _media_path("audio", slug, audio_path.name)
        hero_reference = _build_media_reference(
            audio_rel_path,
            data.get("audio_meta", {}),
        )

        download_enabled, download_name = _parse_download_directive(data.get("download"))
        download_meta_entry = data.get("download_meta", {})
        download_path: str | None = None
        if download_enabled:
            selected_name = download_name or audio_path.name
            candidate_path = directory / selected_name
            if not candidate_path.exists():
                logger.warning(
                    "Download asset '%s' declared for track '%s' but file is missing. Falling back to primary audio.",
                    selected_name,
                    slug,
                )
                selected_name = audio_path.name
            download_path = _media_path("audio", slug, selected_name)

        assets: list[MediaReference] = []
        for file_path in directory.iterdir():
            if file_path.name == meta_name or file_path == audio_path:
                continue
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in IMAGE_EXTENSIONS.union(VIDEO_EXTENSIONS):
                continue
            rel_path = _media_path("audio", slug, file_path.name)
            meta_entry = asset_meta.get(file_path.name, {}) if isinstance(asset_meta, dict) else {}
            assets.append(_build_media_reference(rel_path, meta_entry))
        if download_path and download_path != audio_rel_path:
            assets.append(_build_media_reference(download_path, download_meta_entry))

        meta = ContentMeta(
            slug=slug,
            title=title,
            summary=summary,
            tags=tags,
            status=status,
            content_type=ContentType.AUDIO,
            hero_media=hero_reference,
            published_at=published_at,
            updated_at=updated_at,
            duration=duration,
            download_enabled=download_enabled,
            download_path=download_path,
        )

        lyrics_text = _read_lyrics_file(directory)

        document = ContentDocument(
            meta=meta,
            body=description,
            source_path=str(meta_path if meta_path.exists() else directory),
            assets=assets,
            lyrics=lyrics_text,
        )
        documents.append(document)

    return documents


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            logger.warning("Metadata file %s should define a mapping; ignoring.", path)
            return {}
        return data


def _image_to_reference(
    collection: GalleryCollectionEntry,
    image_entry: GalleryImageEntry,
) -> MediaReference:
    metadata = image_entry.metadata
    rel_path = metadata.derived.get("original") or _media_path("gallery", collection.id, metadata.filename)
    reference = MediaReference(
        path=rel_path,
        alt_text=metadata.alt_text,
        title=metadata.title,
        width=metadata.width,
        height=metadata.height,
    )
    return reference


def _select_gallery_hero(collection: GalleryCollectionEntry) -> GalleryImageEntry | None:
    preferred = collection.metadata.hero_image_id or collection.metadata.cover_image_id
    if preferred:
        for image in collection.images:
            if image.metadata.id == preferred:
                return image
    return collection.images[0] if collection.images else None


def _media_path(prefix: str, slug: str, name: str) -> str:
    return f"{prefix}/{slug}/{name}".replace("\\", "/")


def _title_from_slug(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def _coerce_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if isinstance(value, (list, set, tuple)):
        result: list[str] = []
        seen: set[str] = set()
        for item in value:
            tag = str(item)
            if tag not in seen:
                seen.add(tag)
                result.append(tag)
    return result


def _parse_download_directive(value: Any) -> tuple[bool, str | None]:
    if value is None:
        return False, None
    if isinstance(value, bool):
        return value, None
    if isinstance(value, str):
        cleaned = value.strip()
        return (bool(cleaned), cleaned or None)
    if isinstance(value, dict):
        enabled = value.get("enabled", value.get("allow", value.get("allowed", False)))
        try:
            enabled_flag = bool(enabled)
        except Exception:  # pragma: no cover - defensive
            enabled_flag = False
        path_value = value.get("path") or value.get("file") or value.get("name")
        if isinstance(path_value, str):
            path_value = path_value.strip() or None
        else:
            path_value = None
        return enabled_flag, path_value
    return False, None


def _read_lyrics_file(directory: Path) -> str | None:
    lyrics_path = directory / "lyrics.md"
    if not lyrics_path.exists():
        return None
    try:
        return lyrics_path.read_text(encoding="utf-8").strip()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to read lyrics file at %s: %s", lyrics_path, exc)
        return None
    return []


def _parse_status(value: Any, default: ContentStatus) -> ContentStatus:
    if isinstance(value, ContentStatus):
        return value
    if isinstance(value, str):
        try:
            return ContentStatus(value.lower())
        except ValueError:
            logger.warning("Unknown status '%s'; using %s.", value, default.value)
    return default


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        logger.warning("Invalid datetime '%s'; ignoring.", value)
        return None


def _parse_duration(value: Any) -> float | None:
    if value is None:
        return None
    try:
        duration = float(value)
        if duration < 0:
            raise ValueError
        return duration
    except (TypeError, ValueError):
        logger.warning("Invalid duration '%s'; ignoring.", value)
        return None


def _iter_media_files(directory: Path, extensions: set[str]) -> list[Path]:
    files = [
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in extensions
    ]
    return sorted(files, key=lambda path: path.name.lower())


def _select_primary_file(preferred: Any, candidates: list[Path]) -> Path | None:
    if not candidates:
        return None
    if preferred:
        for candidate in candidates:
            if candidate.name == preferred:
                return candidate
        logger.warning("Preferred file '%s' not found; using first available.", preferred)
    return candidates[0]


def _build_media_reference(path: str, meta_entry: Any) -> MediaReference:
    alt_text = None
    title = None
    if isinstance(meta_entry, str):
        alt_text = meta_entry
    elif isinstance(meta_entry, dict):
        alt_text = meta_entry.get("alt_text") or meta_entry.get("alt")
        title = meta_entry.get("title")
    return MediaReference(path=path, alt_text=alt_text, title=title)
