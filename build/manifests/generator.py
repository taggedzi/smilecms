"""Utilities for building paginated manifest files."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Iterator, Sequence

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
            items = [self._to_item(document.meta) for document in chunk]
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
    def _to_item(meta: ContentMeta) -> ManifestItem:
        return ManifestItem(
            slug=meta.slug,
            title=meta.title,
            summary=meta.summary,
            tags=meta.tags,
            status=meta.status,
            hero_media=meta.hero_media,
            published_at=meta.published_at,
            updated_at=meta.updated_at,
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
