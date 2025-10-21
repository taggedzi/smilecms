import json
from pathlib import Path

from src.content.models import ContentDocument, ContentMeta, ContentStatus
from src.manifests.models import ManifestItem, ManifestPage
from src.media.models import MediaPlan
from src.media.processor import MediaProcessingResult
from src.reporting import (
    assemble_report,
    build_document_stats,
    build_manifest_stats,
    build_media_stats,
    write_report,
)


def _doc(slug: str, status: ContentStatus) -> ContentDocument:
    meta = ContentMeta(slug=slug, title=slug.title(), status=status)
    return ContentDocument(meta=meta, body="Body", source_path=f"{slug}.md")


def test_build_document_stats_counts_statuses() -> None:
    documents = [
        _doc("a", ContentStatus.PUBLISHED),
        _doc("b", ContentStatus.DRAFT),
        _doc("c", ContentStatus.PUBLISHED),
        _doc("d", ContentStatus.ARCHIVED),
    ]
    stats = build_document_stats(documents)
    assert stats.total == 4
    assert stats.published == 2
    assert stats.drafts == 1
    assert stats.archived == 1


def test_build_manifest_stats_counts_items() -> None:
    page = ManifestPage(
        id="content-001",
        page=1,
        total_pages=1,
        total_items=2,
        items=[
            ManifestItem(slug="a", title="A"),
            ManifestItem(slug="b", title="B"),
        ],
    )
    stats = build_manifest_stats([page])
    assert stats.pages == 1
    assert stats.items == 2


def test_write_report_writes_json(tmp_path: Path) -> None:
    documents = build_document_stats([_doc("a", ContentStatus.PUBLISHED)])
    manifests = build_manifest_stats(
        [
            ManifestPage(
                id="content-001",
                page=1,
                total_pages=1,
                total_items=1,
                items=[ManifestItem(slug="a", title="A")],
            )
        ]
    )
    media_plan = MediaPlan()
    media_result = MediaProcessingResult()
    media_stats = build_media_stats(media_plan, media_result)
    report = assemble_report(
        project="SmileCMS",
        duration_seconds=0.5,
        documents=documents,
        manifests=manifests,
        media=media_stats,
    )

    path = write_report(report, tmp_path)
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["project"] == "SmileCMS"
    assert data["documents"]["total"] == 1
    assert data["media"]["assets_copied"] == 0
