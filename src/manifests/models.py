"""Pydantic models describing manifest structures."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from ..content.models import ContentStatus, ContentType, MediaReference


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class ManifestItem(BaseModel):
    """Slim document representation for client consumption."""

    slug: str = Field(...)
    title: str = Field(...)
    content_type: ContentType = Field(default=ContentType.ARTICLE)
    summary: Optional[str] = Field(default=None)
    excerpt: Optional[str] = Field(default=None)
    tags: list[str] = Field(default_factory=list)
    status: ContentStatus = Field(default=ContentStatus.DRAFT)
    hero_media: Optional[MediaReference] = Field(default=None)
    published_at: Optional[datetime] = Field(default=None)
    updated_at: Optional[datetime] = Field(default=None)
    word_count: int = Field(default=0, ge=0)
    reading_time_minutes: int = Field(default=0, ge=0)
    asset_count: int = Field(default=0, ge=0)
    has_media: bool = Field(default=False)
    duration: Optional[float] = Field(default=None, ge=0)
    audio_path: Optional[str] = Field(default=None, description="Primary audio asset path for audio items.")


class ManifestPage(BaseModel):
    """Chunked payload distributed to the front-end."""

    id: str = Field(description="Stable identifier for the page (e.g., 'posts-001').")
    page: int = Field(ge=1)
    total_pages: int = Field(ge=1)
    total_items: int = Field(ge=0)
    items: list[ManifestItem] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utc_now)
