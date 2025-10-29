from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest
from PIL import Image

from src.config import Config, DerivativeProfile, GalleryConfig, MediaProcessingConfig
from src.content.models import ContentDocument, ContentMeta, ContentStatus, MediaReference
from src.media import collect_media_plan, process_media_plan
from src.gallery.metadata import _image_dimensions, _extract_captured_at


def _doc(slug: str, media_paths: list[str]) -> ContentDocument:
    meta = ContentMeta(
        slug=slug,
        title=slug.title(),
        status=ContentStatus.PUBLISHED,
    )
    assets = [MediaReference(path=p) for p in media_paths]
    return ContentDocument(meta=meta, body="Body", source_path=f"{slug}.md", assets=assets)


def _bombing_open(target: Path, real_open: Callable[..., Any]) -> Callable[..., Any]:
    BombError = getattr(Image, "DecompressionBombError")

    def _raise_on_target(path: Any, *args: Any, **kwargs: Any) -> Any:
        # Pillow may be passed either a str, Path, or file object
        candidate = Path(path) if isinstance(path, (str, Path)) else None
        if candidate and candidate.resolve() == target.resolve():
            raise BombError("simulated decompression bomb for test")
        return real_open(path, *args, **kwargs)

    return _raise_on_target


def test_process_media_plan_skips_oversized_images(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw_dir = tmp_path / "raw"
    derived_dir = tmp_path / "derived"
    (raw_dir / "gallery").mkdir(parents=True, exist_ok=True)

    # Create a small real image; we'll simulate bomb error via monkeypatch
    source_path = raw_dir / "gallery" / "huge.png"
    Image.new("RGB", (32, 32), color="red").save(source_path)

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

    document = _doc("alpha", ["gallery/huge.png"])

    # Patch Image.open to raise DecompressionBombError for this specific file
    real_open = Image.open
    monkeypatch.setattr(Image, "open", _bombing_open(source_path, real_open))

    plan = collect_media_plan([document], config)
    result = process_media_plan(plan, config)

    assert result.skipped_tasks == 2  # two profiles skipped
    assert any("Oversized image skipped" in w for w in result.warnings)
    # No variants generated for the asset
    assert "gallery/huge.png" not in result.variants or not result.variants.get("gallery/huge.png")


def test_gallery_metadata_handles_oversized_images(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Create a placeholder file; patch Image.open to raise bomb error
    img_path = tmp_path / "bomb.png"
    Image.new("RGB", (8, 8), color="blue").save(img_path)

    real_open = Image.open
    monkeypatch.setattr(Image, "open", _bombing_open(img_path, real_open))

    w, h = _image_dimensions(img_path)
    assert w is None and h is None

    captured = _extract_captured_at(img_path)
    assert captured is None

