"""Domain models for gallery ingestion and publication."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _default_tags() -> list[str]:
    return []


def _default_options() -> dict[str, Any]:
    return {}


def _default_manual_overrides() -> dict[str, Any]:
    return {}


def _default_notes() -> list[str]:
    return []


def _default_derived() -> dict[str, str | None]:
    return {
        "original": None,
        "thumbnail": None,
        "web": None,
    }


def _default_tag_scores() -> dict[str, float]:
    return {}


class GalleryCollectionMetadata(BaseModel):
    """Collection-level metadata stored next to raw assets."""

    model_config = ConfigDict(extra="allow")

    version: int = Field(default=1, description="Schema version for collection metadata.")
    id: str = Field(description="Unique identifier, typically the folder name.")
    title: str = Field(description="Display title for the collection.")
    summary: str | None = Field(
        default=None, description="One or two sentence overview for listing views."
    )
    description: str | None = Field(
        default=None, description="Long-form description displayed on detail pages."
    )
    tags: list[str] = Field(default_factory=_default_tags, description="Collection level tags.")
    sort_order: int = Field(
        default=0, description="Manual ordering hint. Lower numbers sort first."
    )
    created_at: datetime | None = Field(
        default=None, description="When the collection was first created."
    )
    updated_at: datetime | None = Field(
        default=None, description="Last time the collection metadata changed."
    )
    cover_image_id: str | None = Field(
        default=None,
        description="Preferred image id to use as thumbnail or hero. Falls back to first asset.",
    )
    hero_image_id: str | None = Field(
        default=None,
        description="Optional image id to feature on landing pages when different from cover.",
    )
    options: dict[str, Any] = Field(
        default_factory=_default_options,
        description="Theme hooks allowing sites to opt into alternate layouts.",
    )

    @field_validator("id", mode="before")
    @classmethod
    def _normalize_id(cls, value: Any) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError("Collection id cannot be empty.")
        return text

    @field_validator("title", mode="before")
    @classmethod
    def _normalize_title(cls, value: Any) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError("Collection title cannot be empty.")
        return text

    @field_validator("tags", mode="before")
    @classmethod
    def _coerce_tags(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, (list, tuple, set)):
            result: list[str] = []
            seen: set[str] = set()
            for item in value:
                tag = str(item).strip()
                if tag and tag not in seen:
                    seen.add(tag)
                    result.append(tag)
            return result
        return []

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _parse_datetime(cls, value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError as exc:
            raise ValueError(f"Could not parse datetime: {value}") from exc
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class GalleryImageMetadata(BaseModel):
    """Image-level metadata persisted as JSON sidecars."""

    model_config = ConfigDict(extra="allow")

    version: int = Field(default=1, description="Schema version for image metadata.")
    id: str = Field(description="Unique identifier scoped to the collection (typically the stem).")
    collection_id: str = Field(description="Collection identifier.")
    filename: str = Field(description="Filename of the raw asset.")
    title: str = Field(description="Display title.")
    alt_text: str = Field(description="Cleaned alt text used for accessibility.")
    description: str | None = Field(
        default=None, description="Cleaned description for captions or detail views."
    )
    caption: str | None = Field(
        default=None, description="Optional shorter caption (cleaned)."
    )
    tags: list[str] = Field(
        default_factory=_default_tags,
        description="Cleaned tag list used for search/filter.",
    )
    alt_raw: str | None = Field(
        default=None, description="Original generated alt text before cleaning."
    )
    description_raw: str | None = Field(
        default=None, description="Original generated description before cleaning."
    )
    caption_raw: str | None = Field(
        default=None, description="Original generated caption before cleaning."
    )
    tags_raw: list[str] = Field(
        default_factory=_default_tags,
        description="Original generated tags before cleaning.",
    )
    tag_scores: dict[str, float] = Field(
        default_factory=_default_tag_scores,
        description="Raw probability scores from the ML tagging model.",
    )
    rating: str | None = Field(
        default=None, description="Highest-rated classification label reported by the tagger."
    )
    width: int | None = Field(default=None, ge=1, description="Pixel width of the source asset.")
    height: int | None = Field(
        default=None, ge=1, description="Pixel height of the source asset."
    )
    filesize: int | None = Field(
        default=None, ge=0, description="Size of the source file in bytes."
    )
    hash: str | None = Field(
        default=None, description="SHA256 checksum of the source asset for change detection."
    )
    created_at: datetime | None = Field(
        default=None, description="Filesystem created timestamp (UTC)."
    )
    captured_at: datetime | None = Field(
        default=None, description="Timestamp sourced from EXIF metadata when available."
    )
    modified_at: datetime | None = Field(
        default=None, description="Filesystem modified timestamp (UTC)."
    )
    ai_confidence: float | None = Field(
        default=None, description="Confidence score returned by the ML tagging model."
    )
    ml_model_signature: str | None = Field(
        default=None,
        description="Identifier describing the ML models used for the last tagging pass.",
    )
    ml_source_hash: str | None = Field(
        default=None,
        description="Checksum of the source asset when ML metadata was produced.",
    )
    ml_generated_at: datetime | None = Field(
        default=None, description="Timestamp when ML metadata was last generated."
    )
    llm_revision: int = Field(
        default=0, ge=0, description="Incremented whenever the LLM cleanup modifies content."
    )
    llm_updated_at: datetime | None = Field(
        default=None, description="Last time the LLM cleanup stage ran."
    )
    manual_overrides: dict[str, Any] = Field(
        default_factory=_default_manual_overrides,
        description="Fields explicitly edited by humans that should remain sticky.",
    )
    derived: dict[str, str | None] = Field(
        default_factory=_default_derived,
        description="Paths to generated derivatives (relative to site root).",
    )
    notes: list[str] = Field(
        default_factory=_default_notes,
        description="Warnings and info about automated processing steps.",
    )
    last_generated_at: datetime | None = Field(
        default=None, description="Timestamp of the last metadata generation run."
    )

    @field_validator("id", mode="before")
    @classmethod
    def _normalize_id(cls, value: Any) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError("Image id cannot be empty.")
        return text

    @field_validator("collection_id", mode="before")
    @classmethod
    def _normalize_collection(cls, value: Any) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError("collection_id cannot be empty.")
        return text

    @field_validator("filename", mode="before")
    @classmethod
    def _normalize_filename(cls, value: Any) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError("filename cannot be empty.")
        return text

    @field_validator(
        "alt_text",
        "alt_raw",
        "description",
        "description_raw",
        "caption",
        "caption_raw",
        mode="before",
    )
    @classmethod
    def _normalize_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("tags", "tags_raw", mode="before")
    @classmethod
    def _coerce_tags(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, (list, tuple, set)):
            result: list[str] = []
            seen: set[str] = set()
            for item in value:
                tag = str(item).strip()
                if tag and tag not in seen:
                    seen.add(tag)
                    result.append(tag)
            return result
        return []

    @field_validator(
        "created_at",
        "captured_at",
        "modified_at",
        "llm_updated_at",
        "last_generated_at",
        "ml_generated_at",
        mode="before",
    )
    @classmethod
    def _parse_datetime(cls, value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError as exc:
            raise ValueError(f"Could not parse datetime: {value}") from exc
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class GalleryImageRecord(BaseModel):
    """Flattened record exported to JSONL for the front-end."""

    version: int = Field(default=1)
    id: str
    collection_id: str
    title: str
    alt: str
    caption: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=_default_tags)
    captured_at: datetime | None = None
    created_at: datetime | None = None
    rating: str | None = None
    ai_confidence: float | None = None
    width: int | None = None
    height: int | None = None
    src: str | None = None
    thumbnail: str | None = None
    original: str | None = None
    download: str | None = None
    llm_revision: int = 0
    metadata_path: str | None = None
    checksum: str | None = None

    @classmethod
    def from_metadata(
        cls,
        metadata: GalleryImageMetadata,
        metadata_path: Path,
        base_download_path: str,
    ) -> "GalleryImageRecord":
        derived = metadata.derived or {}
        return cls(
            id=metadata.id,
            collection_id=metadata.collection_id,
            title=metadata.title,
            alt=metadata.alt_text,
            caption=metadata.caption,
            description=metadata.description,
            tags=list(metadata.tags),
            rating=metadata.rating,
            ai_confidence=metadata.ai_confidence,
            captured_at=metadata.captured_at,
            created_at=metadata.created_at,
            width=metadata.width,
            height=metadata.height,
            src=derived.get("web"),
            thumbnail=derived.get("thumbnail"),
            original=derived.get("original"),
            download=derived.get("download", derived.get("original", base_download_path)),
            llm_revision=metadata.llm_revision,
            metadata_path=str(metadata_path.as_posix()),
            checksum=metadata.hash,
        )


@dataclass(slots=True)
class GalleryImageEntry:
    """In-memory representation of a gallery image asset and metadata."""

    collection_id: str
    source_path: Path
    sidecar_path: Path
    metadata: GalleryImageMetadata
    raw_payload: dict[str, Any]
    changed: bool = False
    warnings: list[str] = field(default_factory=list)

    def mark_changed(self) -> None:
        self.changed = True


@dataclass(slots=True)
class GalleryCollectionEntry:
    """In-memory representation of a gallery collection directory."""

    id: str
    directory: Path
    sidecar_path: Path
    metadata: GalleryCollectionMetadata
    raw_payload: dict[str, Any]
    images: list[GalleryImageEntry] = field(default_factory=list)
    changed: bool = False
    warnings: list[str] = field(default_factory=list)

    def mark_changed(self) -> None:
        self.changed = True

    @property
    def cover_image(self) -> GalleryImageEntry | None:
        if not self.images:
            return None
        target = self.metadata.cover_image_id or self.metadata.hero_image_id
        if target:
            for image in self.images:
                if image.metadata.id == target:
                    return image
        return self.images[0]


@dataclass(slots=True)
class GalleryWorkspace:
    """Aggregate state used across pipeline stages."""

    root: Path
    collections: dict[str, GalleryCollectionEntry] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    collection_writes: list[Path] = field(default_factory=list)
    image_writes: list[Path] = field(default_factory=list)
    data_writes: list[Path] = field(default_factory=list)

    def iter_collections(self) -> Iterable[GalleryCollectionEntry]:
        return self.collections.values()

    def iter_images(self) -> Iterable[GalleryImageEntry]:
        for collection in self.collections.values():
            yield from collection.images

    def add_collection(self, entry: GalleryCollectionEntry) -> None:
        self.collections[entry.id] = entry

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def image_count(self) -> int:
        return sum(len(collection.images) for collection in self.collections.values())

    def collection_count(self) -> int:
        return len(self.collections)

    def record_collection_write(self, path: Path) -> None:
        self.collection_writes.append(path)

    def record_image_write(self, path: Path) -> None:
        self.image_writes.append(path)

    def record_data_write(self, path: Path) -> None:
        self.data_writes.append(path)
