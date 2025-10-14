"""Gallery build pipeline orchestration."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable

from ..config import Config
from ..media.processor import MediaProcessingResult
from .inference import TaggingSession, ml_timestamp
from .llm import clean_metadata
from .metadata import generate_collection_defaults, generate_image_metadata
from .models import (
    GalleryCollectionEntry,
    GalleryCollectionMetadata,
    GalleryImageEntry,
    GalleryImageMetadata,
    GalleryImageRecord,
    GalleryWorkspace,
)
from .utils import read_json, title_from_stem, write_json

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".tiff", ".bmp"}


def prepare_workspace(
    config: Config,
    *,
    auto_generate: bool = True,
    run_llm_cleanup: bool | None = None,
) -> GalleryWorkspace:
    """Discover gallery collections and ensure sidecars exist."""
    root = config.gallery.source_dir
    workspace = GalleryWorkspace(root=root)
    if not root.exists():
        logger.info("Gallery source directory %s does not exist; skipping.", root)
        return workspace

    run_llm = config.gallery.llm_enabled if run_llm_cleanup is None else run_llm_cleanup
    tagging_session: TaggingSession | None = None
    if auto_generate and config.gallery.tagging_enabled:
        candidate = TaggingSession(config)
        if candidate.available:
            tagging_session = candidate
        else:
            reason = candidate.failure_reason or "ML tagging unavailable."
            workspace.add_warning(f"Gallery tagging skipped: {reason}")

    now = datetime.now(tz=timezone.utc)

    for collection_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        try:
            collection = _load_collection(collection_dir, config)
        except ValueError as exc:
            workspace.add_error(f"Failed to load collection at {collection_dir}: {exc}")
            continue

        workspace.add_collection(collection)

        if auto_generate:
            if generate_collection_defaults(collection, now):
                collection.mark_changed()
            for image_entry in collection.images:
                if generate_image_metadata(image_entry, collection, now):
                    image_entry.mark_changed()
            if tagging_session is not None:
                for image_entry in collection.images:
                    try:
                        if _apply_tagging(image_entry, tagging_session, workspace, now):
                            image_entry.mark_changed()
                    except Exception as exc:  # pragma: no cover - defensive logging
                        message = f"Failed to annotate {image_entry.source_path.name}: {exc}"
                        logger.warning(message)
                        workspace.add_warning(message)
                        image_entry.warnings.append(message)
            if run_llm:
                for image_entry in collection.images:
                    if clean_metadata(image_entry, now):
                        image_entry.mark_changed()

    if auto_generate:
        persist_workspace(workspace)

    return workspace


def persist_workspace(workspace: GalleryWorkspace) -> None:
    """Write any mutated sidecars back to disk."""
    for collection in workspace.iter_collections():
        payload = collection.metadata.model_dump(mode="json", exclude_none=False)
        if payload != collection.raw_payload or collection.changed:
            write_json(collection.sidecar_path, payload)
            collection.raw_payload = payload
            collection.changed = False
            workspace.record_collection_write(collection.sidecar_path)

    for image in workspace.iter_images():
        payload = image.metadata.model_dump(mode="json", exclude_none=False)
        if payload != image.raw_payload or image.changed:
            write_json(image.sidecar_path, payload)
            image.raw_payload = payload
            image.changed = False
            workspace.record_image_write(image.sidecar_path)


def apply_derivatives(
    workspace: GalleryWorkspace,
    media_result: MediaProcessingResult,
    config: Config,
) -> int:
    """Attach derivative paths from media processing to image metadata."""
    updated = 0
    variant_map = media_result.variants

    for image in workspace.iter_images():
        key = f"gallery/{image.collection_id}/{image.metadata.filename}"
        variants = variant_map.get(key, [])
        if not variants:
            continue
        derived = dict(image.metadata.derived or {})
        original = derived.get("original") or key
        derived["original"] = original

        changed = False
        for role, profile in config.gallery.profile_map.items():
            variant = next((item for item in variants if item.profile == profile), None)
            if variant is None:
                continue
            path = _resolve_variant_path(config, variant.path)
            if derived.get(role) != path:
                derived[role] = path
                changed = True

        if "download" not in derived or derived["download"] is None:
            derived["download"] = derived.get("original")
            changed = True

        if changed:
            image.metadata.derived = derived
            image.mark_changed()
            updated += 1

    if updated:
        persist_workspace(workspace)

    return updated


def export_datasets(workspace: GalleryWorkspace, config: Config) -> None:
    """Write JSON and JSONL datasets consumed by the gallery front-end."""
    data_root = config.output_dir / config.gallery.data_subdir
    data_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=timezone.utc).isoformat()

    collections_payload: dict[str, object] = {
        "version": 1,
        "generated_at": timestamp,
        "collections": [],
    }
    manifest_payload: dict[str, object] = {
        "version": 1,
        "generated_at": timestamp,
        "collections": workspace.collection_count(),
        "images": workspace.image_count(),
        "warnings": workspace.warnings,
        "errors": workspace.errors,
    }

    global_jsonl_path = data_root / "images.jsonl"
    with global_jsonl_path.open("w", encoding="utf-8") as global_handle:
        for collection in sorted(workspace.iter_collections(), key=lambda item: item.metadata.sort_order):
            collection_entry = _collection_to_payload(collection, data_root)
            collections_payload["collections"].append(collection_entry)

            lines, path = _write_collection_jsonl(collection, data_root, timestamp)
            for line in lines:
                global_handle.write(line)
                global_handle.write("\n")
            workspace.record_data_write(path)

    workspace.record_data_write(global_jsonl_path)

    collections_path = data_root / "collections.json"
    write_json(collections_path, collections_payload)  # type: ignore[arg-type]
    workspace.record_data_write(collections_path)

    manifest_path = data_root / "manifest.json"
    write_json(manifest_path, manifest_payload)  # type: ignore[arg-type]
    workspace.record_data_write(manifest_path)


def _load_collection(directory: Path, config: Config) -> GalleryCollectionEntry:
    collection_id = directory.name
    sidecar_path = directory / config.gallery.metadata_filename
    raw_payload: dict[str, object]
    try:
        raw_payload = read_json(sidecar_path)
    except ValueError as exc:
        logger.warning("Invalid collection metadata at %s: %s", sidecar_path, exc)
        raw_payload = {}

    payload = dict(raw_payload)
    payload.setdefault("id", payload.get("slug") or collection_id)
    payload.setdefault("title", payload.get("title") or title_from_stem(collection_id))

    metadata = GalleryCollectionMetadata(**payload)
    entry = GalleryCollectionEntry(
        id=metadata.id,
        directory=directory,
        sidecar_path=sidecar_path,
        metadata=metadata,
        raw_payload=raw_payload,
    )

    image_entries = []
    for image_path in _iter_images(directory):
        try:
            image_entry = _load_image(image_path, entry, config)
        except ValueError as exc:
            entry.warnings.append(f"Failed to load image metadata for {image_path.name}: {exc}")
            continue
        image_entries.append(image_entry)

    entry.images = sorted(image_entries, key=lambda item: item.metadata.filename.lower())
    return entry


def _load_image(path: Path, collection: GalleryCollectionEntry, config: Config) -> GalleryImageEntry:
    stem = path.stem
    sidecar_path = path.with_suffix(config.gallery.image_sidecar_extension)

    raw_payload: dict[str, object]
    try:
        raw_payload = read_json(sidecar_path)
    except ValueError as exc:
        logger.warning("Invalid image sidecar at %s: %s", sidecar_path, exc)
        raw_payload = {}

    payload = dict(raw_payload)
    payload.setdefault("id", payload.get("id") or stem)
    payload.setdefault("collection_id", payload.get("collection_id") or collection.id)
    payload.setdefault("filename", payload.get("filename") or path.name)
    default_title = title_from_stem(stem)
    payload.setdefault("title", payload.get("title") or default_title)

    alt_fallback = (
        payload.get("alt_text")
        or payload.get("alt")
        or payload.get("title")
        or default_title
    )
    payload.setdefault("alt_text", alt_fallback or default_title)

    metadata = GalleryImageMetadata(**payload)
    return GalleryImageEntry(
        collection_id=metadata.collection_id,
        source_path=path,
        sidecar_path=sidecar_path,
        metadata=metadata,
        raw_payload=raw_payload,
    )


def _iter_images(directory: Path) -> Iterable[Path]:
    for path in directory.iterdir():
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            yield path


def _resolve_variant_path(config: Config, relative_path: str) -> str:
    """Convert a variant path into a web-consumable posix path."""
    derived_root = config.media_processing.output_dir
    variant = PurePosixPath(relative_path.lstrip("/"))

    if not derived_root.is_absolute():
        base = PurePosixPath(derived_root.as_posix().lstrip("./"))
        return str(base / variant)

    combined = (derived_root / Path(relative_path)).resolve()
    try:
        relative = combined.relative_to(config.output_dir.resolve())
        return relative.as_posix()
    except ValueError:
        return PurePosixPath(combined.as_posix()).as_posix()


def _collection_to_payload(collection: GalleryCollectionEntry, data_root: Path) -> dict[str, object]:
    cover_entry = collection.cover_image
    cover_payload: dict[str, object] | None = None
    if cover_entry:
        metadata = cover_entry.metadata
        cover_payload = {
            "id": metadata.id,
            "title": metadata.title,
            "alt": metadata.alt_text,
            "thumbnail": metadata.derived.get("thumbnail"),
            "src": metadata.derived.get("web"),
        }

    return {
        "id": collection.metadata.id,
        "title": collection.metadata.title,
        "summary": collection.metadata.summary,
        "description": collection.metadata.description,
        "tags": collection.metadata.tags,
        "sort_order": collection.metadata.sort_order,
        "image_count": len(collection.images),
        "data_path": _collection_jsonl_path(collection, data_root).relative_to(data_root).as_posix(),
        "cover": cover_payload,
        "options": collection.metadata.options,
    }


def _write_collection_jsonl(
    collection: GalleryCollectionEntry,
    data_root: Path,
    timestamp: str,
) -> tuple[list[str], Path]:
    path = _collection_jsonl_path(collection, data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    with path.open("w", encoding="utf-8") as handle:
        for image in collection.images:
            record = GalleryImageRecord.from_metadata(
                image.metadata,
                image.sidecar_path,
                base_download_path=image.metadata.derived.get("original") or "",
            )
            payload = record.model_dump(mode="json", exclude_none=True)
            payload.setdefault("generated_at", timestamp)
            line = json.dumps(payload, ensure_ascii=False)
            handle.write(line)
            handle.write("\n")
            lines.append(line)
    return lines, path


def _collection_jsonl_path(collection: GalleryCollectionEntry, data_root: Path) -> Path:
    filename = f"{collection.id}.jsonl"
    return data_root / filename


def _apply_tagging(
    image_entry: GalleryImageEntry,
    session: TaggingSession,
    workspace: GalleryWorkspace,
    now: datetime,
) -> bool:
    """Apply ML-generated annotations to an image metadata payload."""
    annotation = session.annotate(image_entry.source_path)
    if annotation is None:
        return False

    metadata = image_entry.metadata
    manual = metadata.manual_overrides or {}
    source_hash = metadata.hash

    def _has_placeholder_tags() -> bool:
        candidates = list(metadata.tags or []) + list(metadata.tags_raw or [])
        candidates.extend((metadata.tag_scores or {}).keys())
        return any(str(tag).upper().startswith("LABEL_") for tag in candidates)

    if (
        metadata.ml_source_hash
        and metadata.ml_model_signature
        and session.model_signature
        and source_hash
        and metadata.ml_source_hash == source_hash
        and metadata.ml_model_signature == session.model_signature
        and not _has_placeholder_tags()
    ):
        return False

    changed = False

    def _set_text(field: str, value: str | None, allow_manual: bool = True) -> None:
        nonlocal changed
        if value is None:
            return
        if allow_manual and manual.get(field):
            return
        current = getattr(metadata, field)
        if current != value:
            setattr(metadata, field, value)
            changed = True

    _set_text("alt_raw", annotation.alt_text)
    _set_text("alt_text", annotation.alt_text, allow_manual=False)
    _set_text("description_raw", annotation.caption)
    _set_text("description", annotation.caption)
    _set_text("caption_raw", annotation.caption)
    _set_text("caption", annotation.caption)

    if annotation.tags:
        tags = list(annotation.tags)
        if not manual.get("tags_raw") and metadata.tags_raw != tags:
            metadata.tags_raw = tags
            changed = True
        if not manual.get("tags") and metadata.tags != tags:
            metadata.tags = tags
            changed = True

    scores = dict(annotation.tag_scores)
    if metadata.tag_scores != scores:
        metadata.tag_scores = scores
        changed = True

    if annotation.rating:
        current_rating = getattr(metadata, "rating", None)
        if current_rating != annotation.rating:
            metadata.rating = annotation.rating
            changed = True
        if annotation.rating != "rating:safe":
            note = f"Image flagged as {annotation.rating}"
            if note not in metadata.notes:
                metadata.notes.append(note)
                changed = True
            workspace.add_warning(
                f"{metadata.collection_id}/{metadata.filename} flagged as {annotation.rating}"
            )

    if metadata.ai_confidence != annotation.confidence:
        metadata.ai_confidence = annotation.confidence
        changed = True

    if source_hash and metadata.ml_source_hash != source_hash:
        metadata.ml_source_hash = source_hash
        changed = True

    if session.model_signature and metadata.ml_model_signature != session.model_signature:
        metadata.ml_model_signature = session.model_signature
        changed = True

    timestamp = ml_timestamp()
    metadata.ml_generated_at = timestamp
    changed = True
    if metadata.last_generated_at != now:
        metadata.last_generated_at = now
        changed = True

    image_entry.metadata = metadata
    return changed
