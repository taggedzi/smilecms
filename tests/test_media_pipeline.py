from __future__ import annotations

from pathlib import Path

from PIL import Image

from build.config import (
    Config,
    DerivativeProfile,
    GalleryConfig,
    MediaProcessingConfig,
)
from build.content.models import ContentDocument, ContentMeta, ContentStatus, MediaReference
from build.media import apply_variants_to_documents, collect_media_plan, process_media_plan


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
    config = Config(
        media_processing=media_config,
        gallery=GalleryConfig(source_dir=media_config.source_dir / "gallery"),
    )

    docs = [
        _doc("alpha", ["gallery/photo.jpg"]),
        _doc("beta", ["gallery/photo.jpg", "gallery/diagram.png"], hero_path="gallery/diagram.png"),
    ]

    plan = collect_media_plan(docs, config)

    assert len(plan.tasks) == 4  # two profiles per asset
    assert plan.static_assets == {}
    thumb_tasks = [task for task in plan.tasks if task.profile.name == "thumb"]
    assert len(thumb_tasks) == 2
    photo_task = next(
        task
        for task in plan.tasks
        if task.media_path == "gallery/photo.jpg" and task.profile.name == "thumb"
    )
    assert photo_task.source == media_config.source_dir / "gallery/photo.jpg"
    assert photo_task.destination == media_config.output_dir / "thumb" / "gallery" / "photo.webp"
    assert photo_task.documents == {"alpha", "beta"}
    assert "asset" in photo_task.roles
    hero_task = next(
        task
        for task in plan.tasks
        if task.media_path == "gallery/diagram.png" and task.profile.name == "thumb"
    )
    assert hero_task.roles == {"asset", "hero"}


def test_collect_media_plan_handles_empty_profiles(tmp_path: Path) -> None:
    media_config = MediaProcessingConfig(
        source_dir=tmp_path / "raw",
        output_dir=tmp_path / "derived",
        profiles=[],
    )
    config = Config(
        media_processing=media_config,
        gallery=GalleryConfig(source_dir=media_config.source_dir / "gallery"),
    )
    docs = [_doc("alpha", ["gallery/photo.jpg"])]

    plan = collect_media_plan(docs, config)
    assert plan.tasks == []


def test_process_media_plan_generates_variants(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    derived_dir = tmp_path / "derived"
    (raw_dir / "gallery").mkdir(parents=True, exist_ok=True)

    image_path = raw_dir / "gallery" / "photo.png"
    Image.new("RGB", (800, 600), color="blue").save(image_path)

    media_config = MediaProcessingConfig(
        source_dir=raw_dir,
        output_dir=derived_dir,
        profiles=[
            DerivativeProfile(name="thumb", width=160, height=160, format="webp", quality=70),
            DerivativeProfile(name="large", width=1920, format="jpg", quality=85),
        ],
    )
    config = Config(
        media_processing=media_config,
        gallery=GalleryConfig(source_dir=media_config.source_dir / "gallery"),
    )

    docs = [_doc("alpha", ["gallery/photo.png"], hero_path="gallery/photo.png")]

    plan = collect_media_plan(docs, config)
    result = process_media_plan(plan, config)
    apply_variants_to_documents(docs, result.variants)

    thumb_path = derived_dir / "thumb" / "gallery" / "photo.webp"
    large_path = derived_dir / "large" / "gallery" / "photo.jpg"
    assert thumb_path.exists()
    assert large_path.exists()

    assert result.processed_tasks == 2
    assert result.processed_assets == 1
    assert result.variants_generated == 2
    assert result.copied_assets == 0

    asset = docs[0].assets[0]
    hero = docs[0].meta.hero_media
    assert asset.variants
    assert hero and hero.variants
    variant_paths = {variant.path for variant in asset.variants}
    assert "thumb/gallery/photo.webp" in variant_paths
    assert "large/gallery/photo.jpg" in variant_paths
    for variant in asset.variants:
        if variant.profile == "thumb":
            assert variant.width is not None
            assert variant.width <= 160
            assert variant.height is not None
            assert variant.height <= 160


def test_process_media_plan_copies_static_assets(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    derived_dir = tmp_path / "derived"
    (raw_dir / "gallery").mkdir(parents=True, exist_ok=True)

    audio_path = raw_dir / "gallery" / "song.mp3"
    audio_path.write_bytes(b"ID3test data")

    media_config = MediaProcessingConfig(
        source_dir=raw_dir,
        output_dir=derived_dir,
        profiles=[
            DerivativeProfile(name="thumb", width=160, height=160, format="webp", quality=70),
        ],
    )
    config = Config(
        media_processing=media_config,
        gallery=GalleryConfig(source_dir=media_config.source_dir / "gallery"),
    )

    docs = [_doc("alpha", ["gallery/song.mp3"], hero_path="gallery/song.mp3")]

    plan = collect_media_plan(docs, config)
    assert len(plan.tasks) == 0
    assert plan.static_assets == {"gallery/song.mp3": raw_dir / "gallery" / "song.mp3"}

    result = process_media_plan(plan, config)
    apply_variants_to_documents(docs, result.variants)

    copied_path = derived_dir / "gallery" / "song.mp3"
    assert copied_path.exists()
    assert plan.asset_count == 1
    assert result.copied_assets == 1
    assert result.processed_tasks == 0
    assert result.processed_assets == 1
    assert result.variants_generated == 1

    hero = docs[0].meta.hero_media
    assert hero is not None
    assert hero.variants
    assert hero.variants[0].profile == "original"
    assert hero.variants[0].path == "gallery/song.mp3"
