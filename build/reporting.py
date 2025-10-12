"""Build reporting helpers for SmileCMS."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, Field

from .content import ContentDocument, ContentStatus
from .manifests import ManifestPage
from .media.processor import MediaProcessingResult
from .media.models import MediaPlan


class DocumentStats(BaseModel):
    total: int
    published: int
    drafts: int
    archived: int


class ManifestStats(BaseModel):
    pages: int
    items: int


class MediaStats(BaseModel):
    tasks_planned: int
    tasks_processed: int
    tasks_skipped: int
    assets_planned: int
    assets_processed: int
    assets_copied: int
    variants_generated: int
    warnings: list[str] = Field(default_factory=list)
    missing_sources: list[str] = Field(default_factory=list)
    unsupported_media: list[str] = Field(default_factory=list)


class BuildReport(BaseModel):
    project: str
    generated_at: datetime
    duration_seconds: float
    documents: DocumentStats
    manifests: ManifestStats
    media: MediaStats
    warnings: list[str] = Field(default_factory=list)


def build_document_stats(documents: Iterable[ContentDocument]) -> DocumentStats:
    total = 0
    published = drafts = archived = 0
    for document in documents:
        total += 1
        status = document.status
        if status is ContentStatus.PUBLISHED:
            published += 1
        elif status is ContentStatus.DRAFT:
            drafts += 1
        elif status is ContentStatus.ARCHIVED:
            archived += 1
    return DocumentStats(
        total=total,
        published=published,
        drafts=drafts,
        archived=archived,
    )


def build_manifest_stats(pages: Iterable[ManifestPage]) -> ManifestStats:
    pages_list = list(pages)
    total_items = sum(len(page.items) for page in pages_list)
    return ManifestStats(pages=len(pages_list), items=total_items)


def build_media_stats(plan: MediaPlan, result: MediaProcessingResult) -> MediaStats:
    return MediaStats(
        tasks_planned=len(plan.tasks),
        tasks_processed=result.processed_tasks,
        tasks_skipped=result.skipped_tasks,
        assets_planned=plan.asset_count,
        assets_processed=result.processed_assets,
        assets_copied=result.copied_assets,
        variants_generated=result.variants_generated,
        warnings=list(result.warnings),
        missing_sources=list(result.missing_sources),
        unsupported_media=list(result.unsupported_media),
    )


def assemble_report(
    *,
    project: str,
    duration_seconds: float,
    documents: DocumentStats,
    manifests: ManifestStats,
    media: MediaStats,
) -> BuildReport:
    warnings: list[str] = []
    for message in media.warnings:
        warnings.append(message)
    for path in media.missing_sources:
        warnings.append(f"Missing media source: {path}")
    for path in media.unsupported_media:
        warnings.append(f"Unsupported media type: {path}")

    return BuildReport(
        project=project,
        generated_at=datetime.now(timezone.utc),
        duration_seconds=duration_seconds,
        documents=documents,
        manifests=manifests,
        media=media,
        warnings=warnings,
    )


def write_report(report: BuildReport, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "build-report.json"
    with target.open("w", encoding="utf-8") as handle:
        json.dump(report.model_dump(mode="json"), handle, ensure_ascii=False, indent=2)
    return target
