from __future__ import annotations

from pathlib import Path

from build.config import Config, DerivativeProfile, MediaProcessingConfig
from build.content.models import ContentDocument, ContentMeta, ContentStatus, MediaReference
from build.media import collect_media_plan


def _doc(slug: str, media_paths: list[str], hero_path: str | None = None) -> ContentDocument:
    meta = ContentMeta(
        slug=slug,
        title=slug.title(),
        status=ContentStatus.PUBLISHED,
    )
    if hero_path:
        meta.hero_media = MediaReference(path=hero_path)
    assets = [MediaReference(path=path) for path in media_paths]
    return ContentDocument(meta=meta, body="Body text", source_path=f"{slug}.md", assets=assets)


def test_collect_media_plan_deduplicates_assets(tmp_path: Path) -> None:
    media_config = MediaProcessingConfig(
        source_dir=tmp_path / "raw",
        output_dir=tmp_path / "derived",
        profiles=[
            DerivativeProfile(name="thumb", width=160, height=160, format="webp", quality=70),
            DerivativeProfile(name="large", width=1920, format="jpg", quality=85),
        ],
    )
    config = Config(media_processing=media_config)

    docs = [
        _doc("alpha", ["gallery/photo.jpg"]),
        _doc("beta", ["gallery/photo.jpg", "gallery/diagram.png"], hero_path="gallery/diagram.png"),
    ]

    plan = collect_media_plan(docs, config)

    assert len(plan.tasks) == 4  # two profiles per asset
    thumb_tasks = [task for task in plan.tasks if task.profile.name == "thumb"]
    assert len(thumb_tasks) == 2
    photo_task = next(task for task in plan.tasks if task.media_path == "gallery/photo.jpg" and task.profile.name == "thumb")
    assert photo_task.source == media_config.source_dir / "gallery/photo.jpg"
    assert photo_task.destination == media_config.output_dir / "thumb" / "gallery" / "photo.webp"
    assert photo_task.documents == {"alpha", "beta"}
    assert "asset" in photo_task.roles
    hero_task = next(task for task in plan.tasks if task.media_path == "gallery/diagram.png" and task.profile.name == "thumb")
    assert hero_task.roles == {"asset", "hero"}


def test_collect_media_plan_handles_empty_profiles(tmp_path: Path) -> None:
    media_config = MediaProcessingConfig(
        source_dir=tmp_path / "raw",
        output_dir=tmp_path / "derived",
        profiles=[],
    )
    config = Config(media_processing=media_config)
    docs = [_doc("alpha", ["gallery/photo.jpg"])]

    plan = collect_media_plan(docs, config)
    assert plan.tasks == []
