from __future__ import annotations

from pathlib import Path

from src.config import Config, GalleryConfig, MediaProcessingConfig, MusicConfig
from src.content.models import ContentDocument, ContentMeta, ContentStatus, MediaReference
from src.media.audit import audit_media


def _document(
    slug: str, hero: str | None = None, assets: list[str] | None = None
) -> ContentDocument:
    meta = ContentMeta(
        slug=slug,
        title=slug.title(),
        status=ContentStatus.PUBLISHED,
    )
    if hero:
        meta.hero_media = MediaReference(path=hero)
    references = [MediaReference(path=path) for path in assets or []]
    return ContentDocument(
        meta=meta,
        body="",
        source_path=f"{slug}.md",
        assets=references,
    )


def _config(tmp_path: Path) -> Config:
    content_dir = tmp_path / "content"
    article_media_dir = content_dir / "media"
    posts_dir = content_dir / "posts"
    media_dir = tmp_path / "media"
    gallery_dir = media_dir / "image_gallery_raw"
    music_dir = media_dir / "music_collection"
    derived_dir = media_dir / "derived"

    for directory in [article_media_dir, posts_dir, gallery_dir, music_dir, derived_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    return Config(
        content_dir=content_dir,
        article_media_dir=article_media_dir,
        media_dir=media_dir,
        output_dir=tmp_path / "site",
        templates_dir=tmp_path / "web",
        cache_dir=tmp_path / ".cache",
        media_processing=MediaProcessingConfig(
            source_dir=article_media_dir,
            output_dir=derived_dir,
            profiles=[],
        ),
        gallery=GalleryConfig(source_dir=gallery_dir),
        music=MusicConfig(source_dir=music_dir),
    )


def test_audit_media_surfaces_missing_orphan_and_out_of_bounds(tmp_path: Path) -> None:
    config = _config(tmp_path)
    media_root = config.article_media_dir

    used_asset = media_root / "used.jpg"
    used_asset.write_bytes(b"binary")

    orphan_asset = media_root / "orphan.jpg"
    orphan_asset.write_bytes(b"orphan")

    stray_asset = config.content_dir / "posts" / "inline.png"
    stray_asset.write_bytes(b"inline")

    documents = [
        _document("alpha", hero="media/used.jpg", assets=["media/used.jpg"]),
        _document("beta", assets=["media/missing.jpg"]),
        _document("gamma", assets=["static/outside.png"]),
    ]

    result = audit_media(documents, config)

    assert result.total_assets == 2
    assert "media/used.jpg" in result.references

    assert "media/missing.jpg" in result.missing_references
    missing_usage = result.missing_references["media/missing.jpg"]
    assert missing_usage.documents == {"beta"}

    assert "static/outside.png" in result.out_of_bounds_references
    outside_usage = result.out_of_bounds_references["static/outside.png"]
    assert outside_usage.documents == {"gamma"}

    assert "media/orphan.jpg" in result.orphan_files
    assert result.orphan_files["media/orphan.jpg"] == orphan_asset

    stray_sources = {path.resolve() for path in result.stray_files.values()}
    assert stray_asset.resolve() in stray_sources

    assert result.valid_references == 1
