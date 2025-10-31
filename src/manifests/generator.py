"""Utilities for building paginated manifest files."""

from __future__ import annotations

from datetime import datetime, timezone
from math import ceil
from typing import Iterable, Iterator, Optional, Sequence, Tuple

from ..content.models import ContentDocument, ContentMeta
from .models import ManifestItem, ManifestPage

DEFAULT_PAGE_SIZE = 200


class ManifestGenerator:
    """Generate manifest pages from content documents."""

    def __init__(self, *, page_size: int = DEFAULT_PAGE_SIZE) -> None:
        if page_size <= 0:
            raise ValueError("page_size must be positive")
        self.page_size = page_size

    def build_pages(self, documents: Sequence[ContentDocument], prefix: str) -> list[ManifestPage]:
        sorted_docs = sorted(documents, key=lambda doc: _sort_key(doc.meta), reverse=True)
        chunks = list(chunk_documents(sorted_docs, self.page_size))
        total_items = len(documents)
        total_pages = max(len(chunks), 1)

        pages: list[ManifestPage] = []
        for index, chunk in enumerate(chunks, start=1):
            items = [self._to_item(document) for document in chunk]
            page_id = f"{prefix}-{index:03d}"
            pages.append(
                ManifestPage(
                    id=page_id,
                    page=index,
                    total_pages=total_pages,
                    total_items=total_items,
                    items=items,
                )
            )

        if not pages:
            pages.append(
                ManifestPage(
                    id=f"{prefix}-001",
                    page=1,
                    total_pages=1,
                    total_items=0,
                    items=[],
                )
            )

        return pages

    @staticmethod
    def _to_item(document: ContentDocument) -> ManifestItem:
        meta = document.meta
        excerpt, word_count = _summarize(document)
        reading_time = _reading_time_minutes(word_count)
        asset_count = len(document.assets) + (1 if meta.hero_media else 0)
        return ManifestItem(
            slug=meta.slug,
            title=meta.title,
            content_type=meta.content_type,
            summary=meta.summary,
            excerpt=excerpt,
            tags=meta.tags,
            status=meta.status,
            hero_media=meta.hero_media,
            published_at=meta.published_at,
            updated_at=meta.updated_at,
            word_count=word_count,
            reading_time_minutes=reading_time,
            asset_count=asset_count,
            has_media=asset_count > 0,
            duration=meta.duration,
            audio_path=(meta.primary_audio_path if (meta.content_type.value == "audio") else None),
        )


def chunk_documents(documents: Iterable[ContentDocument], page_size: int = DEFAULT_PAGE_SIZE) -> Iterator[list[ContentDocument]]:
    """Yield documents in deterministic page-sized chunks."""
    if page_size <= 0:
        raise ValueError("page_size must be positive")

    batch: list[ContentDocument] = []
    for document in documents:
        batch.append(document)
        if len(batch) >= page_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _sort_key(meta: ContentMeta) -> tuple[datetime, str, str]:
    """Sort primarily by publish/update time, then title, then slug."""
    timestamp = meta.published_at or meta.updated_at
    if timestamp is None:
        timestamp = datetime.min.replace(tzinfo=timezone.utc)
    return (timestamp, meta.title.lower(), meta.slug)


def _summarize(document: ContentDocument) -> Tuple[Optional[str], int]:
    summary = document.meta.summary
    plain = _extract_plain_text(document.body)
    excerpt: str | None
    if summary:
        excerpt = summary
    else:
        excerpt = _truncate(plain, 240) if plain else None
    word_count = len(plain.split()) if plain else 0
    return excerpt, word_count


def _extract_plain_text(body: str) -> str:
    import re

    text_parts: list[str] = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        line = re.sub(r"`([^`]+)`", r"\1", line)
        line = line.lstrip("#>*-1234567890. ").strip()
        text_parts.append(line)
    return " ".join(text_parts)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    truncated = text[:limit].rsplit(" ", 1)[0]
    return f"{truncated}…"


def _reading_time_minutes(word_count: int) -> int:
    if word_count == 0:
        return 0
    return max(1, ceil(word_count / 200))
