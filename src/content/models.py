"""Typed representations of SmileCMS content documents."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


class ContentStatus(str, Enum):
    """Publication state for a document."""

    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ContentType(str, Enum):
    """High-level type/category for a document."""

    ARTICLE = "article"
    GALLERY = "gallery"
    AUDIO = "audio"
    VIDEO = "video"
    OTHER = "other"


class MediaVariant(BaseModel):
    """Represents a generated derivative of a media asset."""

    profile: str = Field(description="Derivative profile name, e.g. 'thumb'.")
    path: str = Field(description="Relative path to the generated asset.")
    width: Optional[int] = Field(default=None, ge=1)
    height: Optional[int] = Field(default=None, ge=1)
    format: Optional[str] = Field(default=None)
    quality: Optional[int] = Field(default=None, ge=1, le=100)

    @field_validator("path")
    def _strip_leading_slash(cls, value: str) -> str:
        return value.lstrip("/")


class MediaReference(BaseModel):
    """Reference to a media asset associated with a document."""

    path: str = Field(description="Relative path to the media asset.")
    alt_text: Optional[str] = Field(default=None, description="Accessibility description.")
    title: Optional[str] = Field(default=None, description="Human-readable label.")
    mime_type: Optional[str] = Field(default=None, description="Detected MIME type.")
    width: Optional[int] = Field(default=None, description="Pixel width, if image/video.")
    height: Optional[int] = Field(default=None, description="Pixel height, if image/video.")
    duration: Optional[float] = Field(
        default=None, description="Duration in seconds for time-based media."
    )
    variants: list[MediaVariant] = Field(default_factory=list, description="Derived variants.")

    @field_validator("path")
    def _strip_leading_slash(cls, value: str) -> str:
        return value.lstrip("/")


class ContentMeta(BaseModel):
    """Front-matter metadata for a document."""

    slug: str = Field(description="URL-friendly identifier.")
    title: str = Field(description="Display title.")
    summary: Optional[str] = Field(default=None, description="Short summary.")
    tags: list[str] = Field(default_factory=list, description="Free-form tags.")
    status: ContentStatus = Field(default=ContentStatus.DRAFT)
    content_type: ContentType = Field(default=ContentType.ARTICLE)
    hero_media: Optional[MediaReference] = Field(
        default=None, description="Primary media asset for the document."
    )
    canonical_url: Optional[HttpUrl] = Field(
        default=None, description="External canonical reference if applicable."
    )
    published_at: Optional[datetime] = Field(
        default=None, description="Original publish timestamp."
    )
    updated_at: Optional[datetime] = Field(
        default=None, description="Last modification timestamp."
    )
    duration: Optional[float] = Field(
        default=None, description="Duration in seconds for audio/video items.", ge=0
    )
    download_enabled: Optional[bool] = Field(
        default=None,
        description="Whether a direct download link should be exposed for this item.",
    )
    download_path: Optional[str] = Field(
        default=None,
        description="Relative path (within media mounts) to the downloadable asset.",
    )
    primary_audio_path: Optional[str] = Field(
        default=None,
        description="Relative path to the primary audio asset for audio items.",
    )

    @field_validator("slug")
    def _normalize_slug(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("slug cannot be empty")
        return cleaned

    @field_validator("published_at", "updated_at")
    def _ensure_timezone(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @field_validator("download_path")
    def _normalize_download_path(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip()


class ContentDocument(BaseModel):
    """Full representation of a content item."""

    meta: ContentMeta = Field(description="Front-matter metadata.")
    body: str = Field(description="Raw markdown body.")
    source_path: str = Field(description="Path to the source file.")
    assets: list[MediaReference] = Field(default_factory=list, description="Linked media assets.")
    lyrics: Optional[str] = Field(default=None, description="Optional lyrics associated with the document.")

    @property
    def slug(self) -> str:
        return self.meta.slug

    @property
    def status(self) -> ContentStatus:
        return self.meta.status
