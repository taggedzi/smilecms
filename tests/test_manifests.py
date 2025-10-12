from datetime import datetime, timezone
from pathlib import Path

from build.content.models import ContentDocument, ContentMeta, ContentStatus
from build.manifests import ManifestGenerator, chunk_documents, write_manifest_pages


def _document(slug: str, *, title: str, published: datetime | None = None, updated: datetime | None = None) -> ContentDocument:
    meta = ContentMeta(
        slug=slug,
        title=title,
        tags=[],
        status=ContentStatus.PUBLISHED,
        published_at=published,
        updated_at=updated,
    )
    return ContentDocument(meta=meta, body="Body", source_path=f"{slug}.md")


def test_chunk_documents_respects_page_size() -> None:
    docs = [_document(f"post-{i}", title=f"Post {i}") for i in range(5)]
    chunks = list(chunk_documents(docs, page_size=2))

    assert len(chunks) == 3
    assert all(len(chunk) <= 2 for chunk in chunks)
    assert [doc.slug for doc in chunks[0]] == ["post-0", "post-1"]


def test_manifest_generator_orders_by_newest_first() -> None:
    tz = timezone.utc
    docs = [
        _document("old", title="Old", published=datetime(2022, 1, 1, tzinfo=tz)),
        _document("new", title="New", published=datetime(2024, 1, 1, tzinfo=tz)),
        _document("updated", title="Updated", published=None, updated=datetime(2023, 6, 1, tzinfo=tz)),
    ]
    generator = ManifestGenerator(page_size=2)
    pages = generator.build_pages(docs, prefix="posts")

    assert len(pages) == 2
    first_page = pages[0]
    assert first_page.id == "posts-001"
    assert [item.slug for item in first_page.items] == ["new", "updated"]
    assert pages[1].items[0].slug == "old"


def test_manifest_writer_serializes_json(tmp_path: Path) -> None:
    generator = ManifestGenerator(page_size=2)
    docs = [_document("single", title="Single", published=datetime.now(timezone.utc))]
    pages = generator.build_pages(docs, prefix="posts")

    manifest_dir = tmp_path / "site" / "manifests"
    written = write_manifest_pages(pages, manifest_dir)

    assert len(written) == 1
    path = written[0]
    assert path.exists()
    data = path.read_text(encoding="utf-8")
    assert '"slug": "single"' in data
