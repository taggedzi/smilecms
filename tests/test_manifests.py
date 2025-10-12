from datetime import datetime, timezone
from pathlib import Path

from build.content.models import ContentDocument, ContentMeta, ContentStatus, MediaReference
from build.manifests import ManifestGenerator, chunk_documents, write_manifest_pages


def _document(
    slug: str,
    *,
    title: str,
    body: str | None = None,
    summary: str | None = None,
    published: datetime | None = None,
    updated: datetime | None = None,
    assets: list[MediaReference] | None = None,
) -> ContentDocument:
    meta = ContentMeta(
        slug=slug,
        title=title,
        tags=[],
        status=ContentStatus.PUBLISHED,
        summary=summary,
        published_at=published,
        updated_at=updated,
    )
    return ContentDocument(
        meta=meta,
        body=body or "Sample body text for SmileCMS manifest testing.",
        source_path=f"{slug}.md",
        assets=assets or [],
    )


def test_chunk_documents_respects_page_size() -> None:
    docs = [_document(f"post-{i}", title=f"Post {i}") for i in range(5)]
    chunks = list(chunk_documents(docs, page_size=2))

    assert len(chunks) == 3
    assert all(len(chunk) <= 2 for chunk in chunks)
    assert [doc.slug for doc in chunks[0]] == ["post-0", "post-1"]


def test_manifest_generator_orders_by_newest_first() -> None:
    tz = timezone.utc
    docs = [
        _document(
            "old",
            title="Old",
            body="Old content body.",
            published=datetime(2022, 1, 1, tzinfo=tz),
        ),
        _document(
            "new",
            title="New",
            body="New content body with more text to estimate reading time.",
            published=datetime(2024, 1, 1, tzinfo=tz),
        ),
        _document(
            "updated",
            title="Updated",
            body="Updated document body that should appear after new when published is missing.",
            published=None,
            updated=datetime(2023, 6, 1, tzinfo=tz),
        ),
    ]
    generator = ManifestGenerator(page_size=2)
    pages = generator.build_pages(docs, prefix="posts")

    assert len(pages) == 2
    first_page = pages[0]
    assert first_page.id == "posts-001"
    assert [item.slug for item in first_page.items] == ["new", "updated"]
    assert pages[1].items[0].slug == "old"
    first_item = first_page.items[0]
    assert first_item.word_count > 0
    assert first_item.reading_time_minutes >= 1
    assert first_item.excerpt is not None


def test_manifest_writer_serializes_json(tmp_path: Path) -> None:
    generator = ManifestGenerator(page_size=2)
    docs = [
        _document(
            "single",
            title="Single",
            body="This document includes an image reference.",
            published=datetime.now(timezone.utc),
            assets=[MediaReference(path="images/sample.jpg")],
        )
    ]
    pages = generator.build_pages(docs, prefix="posts")

    manifest_dir = tmp_path / "site" / "manifests"
    written = write_manifest_pages(pages, manifest_dir)

    assert len(written) == 1
    path = written[0]
    assert path.exists()
    data = path.read_text(encoding="utf-8")
    assert '"slug": "single"' in data
    assert '"asset_count": 1' in data
    assert '"has_media": true' in data
