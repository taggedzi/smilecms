"""Export datasets that drive the front-end music catalog."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Tuple

from ..config import Config
from ..content import (
    ContentDocument,
    ContentStatus,
    ContentType,
    MediaReference,
    MediaVariant,
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}


@dataclass
class MusicExportResult:
    """Details about the exported music catalog."""

    tracks: int = 0
    written: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def export_music_catalog(documents: Iterable[ContentDocument], config: Config) -> MusicExportResult:
    """Write JSON datasets describing published audio tracks."""

    published_tracks = [
        document
        for document in documents
        if document.meta.content_type is ContentType.AUDIO and document.meta.status is ContentStatus.PUBLISHED
    ]

    data_root = config.output_dir / config.music.data_subdir
    data_root.mkdir(parents=True, exist_ok=True)

    generated_at = datetime.now(tz=timezone.utc).isoformat()
    warnings: list[str] = []
    records = []

    for document in published_tracks:
        record, record_warnings = _build_track_record(document)
        if record is None:
            warnings.extend(record_warnings or [])
            continue
        warnings.extend(record_warnings or [])
        records.append(record)

    jsonl_path = data_root / "tracks.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")

    summary_path = data_root / "tracks.json"
    summary_payload = {
        "version": 1,
        "generated_at": generated_at,
        "tracks": len(records),
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    manifest_path = data_root / "manifest.json"
    manifest_payload = {
        "version": 1,
        "generated_at": generated_at,
        "tracks": len(records),
        "warnings": warnings,
    }
    manifest_path.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")

    return MusicExportResult(
        tracks=len(records),
        written=[jsonl_path, summary_path, manifest_path],
        warnings=warnings,
    )


def _build_track_record(document: ContentDocument) -> Tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    meta = document.meta

    # Determine the actual audio source for this track. For audio content we
    # prefer the explicit primary_audio_path recorded during ingestion. This
    # path points at the processed media namespace (e.g. "audio/<slug>/<file>.mp3").
    audio_path = (meta.primary_audio_path or "").strip() if meta.primary_audio_path else None
    audio_mime: str | None = None

    if not audio_path:
        # Backward-compatibility: older content may have used hero_media to point
        # at the audio asset. This is not ideal (hero is for visual cover art),
        # but keep this fallback to avoid hard failures.
        audio_ref = meta.hero_media
        if audio_ref is None or not (audio_ref.path or "").strip():
            warnings.append(
                f"Track '{meta.slug}' is missing a primary audio reference; skipping."
            )
            return None, warnings
        variant = _select_variant(audio_ref, ("download", "original", "web"))
        audio_path = (variant.path if variant else audio_ref.path) or None
        audio_mime = audio_ref.mime_type

    if not audio_path:
        warnings.append(f"Track '{meta.slug}' has an empty audio path; skipping.")
        return None, warnings

    cover_ref = _select_cover_reference(document)
    cover_payload = _serialize_media_reference(cover_ref) if cover_ref else None

    extras = []
    for reference in document.assets:
        if cover_ref and reference.path == cover_ref.path:
            continue
        if _is_download_reference(reference, meta.download_path):
            continue
        ref_type = _classify_asset(reference)
        if ref_type is None:
            continue
        extras.append(
            {
                "type": ref_type,
                "media": _serialize_media_reference(reference),
            }
        )

    download_path = None
    download_filename = None
    if meta.download_enabled:
        # Prefer the explicit download file when provided; otherwise fall back
        # to the primary audio.
        if meta.download_path:
            # Attempt to locate a matching reference for variant selection; if
            # we don't find one, trust the provided path as-is.
            download_ref = _find_reference(document, meta.download_path)
            if download_ref:
                download_variant = _select_variant(download_ref, ("download", "original", "web"))
                download_path = (download_variant.path if download_variant else download_ref.path) or None
            else:
                download_path = meta.download_path
        else:
            download_path = audio_path
        if download_path:
            download_filename = Path(download_path).name

    lyrics_text = document.lyrics or ""

    search_chunks = [
        meta.title or "",
        meta.summary or "",
        document.body or "",
        " ".join(meta.tags or []),
        lyrics_text,
    ]
    search_text = " ".join(chunk for chunk in search_chunks if chunk).lower()

    record = {
        "id": meta.slug,
        "slug": meta.slug,
        "title": meta.title,
        "summary": meta.summary,
        "description": document.body,
        "tags": meta.tags,
        "duration": meta.duration,
        "published_at": meta.published_at.isoformat() if meta.published_at else None,
        "updated_at": meta.updated_at.isoformat() if meta.updated_at else None,
        "audio": {
            "src": audio_path,
            "mime_type": audio_mime,
        },
        "download": {
            "enabled": bool(meta.download_enabled and download_path),
            "src": download_path,
            "filename": download_filename,
        },
        "cover": cover_payload,
        "extras": extras,
        "lyrics": lyrics_text or None,
        "search": search_text,
    }

    return record, warnings


def _select_cover_reference(document: ContentDocument) -> MediaReference | None:
    for reference in document.assets:
        suffix = Path(reference.path).suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            return reference
    return None


def _find_reference(document: ContentDocument, path: str) -> MediaReference | None:
    normalized = path.replace("\\", "/")
    if document.meta.hero_media and document.meta.hero_media.path == normalized:
        return document.meta.hero_media
    for reference in document.assets:
        if reference.path == normalized:
            return reference
    return None


def _is_download_reference(reference: MediaReference, download_path: str | None) -> bool:
    if not download_path:
        return False
    return reference.path == download_path


def _classify_asset(reference: MediaReference) -> str | None:
    suffix = Path(reference.path).suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    return None


def _serialize_media_reference(reference: MediaReference | None) -> dict[str, Any] | None:
    if reference is None:
        return None
    variants = {variant.profile: variant.path for variant in reference.variants}
    return {
        "path": reference.path,
        "alt": reference.alt_text,
        "title": reference.title,
        "variants": variants,
        "mime_type": reference.mime_type,
        "width": reference.width,
        "height": reference.height,
        "duration": reference.duration,
    }


def _select_variant(reference: MediaReference, preferred: Tuple[str, ...]) -> MediaVariant | None:
    if not reference.variants:
        return None
    for profile in preferred:
        for variant in reference.variants:
            if variant.profile == profile:
                return variant
    return reference.variants[0]
