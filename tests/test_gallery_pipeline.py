from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from src.config import (
    Config,
    DerivativeProfile,
    GalleryConfig,
    MediaProcessingConfig,
    MusicConfig,
)
from src.gallery import apply_derivatives, export_datasets, prepare_workspace
from src.ingest import load_documents
from src.media import apply_variants_to_documents, collect_media_plan, process_media_plan


def test_gallery_pipeline_generates_sidecars_and_datasets(tmp_path: Path) -> None:
    raw_root = tmp_path / "media" / "image_gallery_raw" / "vacation-trip"
    raw_root.mkdir(parents=True, exist_ok=True)
    image_path = raw_root / "sunset.png"
    Image.new("RGB", (640, 480), color="orange").save(image_path)

    config = Config(
        content_dir=tmp_path / "content",
        output_dir=tmp_path / "site",
        gallery=GalleryConfig(
            source_dir=tmp_path / "media" / "image_gallery_raw",
            metadata_filename="collection.json",
        ),
        media_processing=MediaProcessingConfig(
            source_dir=tmp_path / "media",
            output_dir=tmp_path / "site" / "media" / "derived",
            profiles=[
                DerivativeProfile(name="thumb", width=160, height=160, format="webp", quality=70),
                DerivativeProfile(name="large", width=1024, height=None, format="jpg", quality=85),
            ],
        ),
        music=MusicConfig(source_dir=tmp_path / "music"),
    )

    workspace = prepare_workspace(config)
    assert workspace.collection_count() == 1
    assert workspace.image_count() == 1

    collection_sidecar = raw_root / "collection.json"
    image_sidecar = raw_root / "sunset.json"
    assert collection_sidecar.exists()
    assert image_sidecar.exists()

    with image_sidecar.open("r", encoding="utf-8") as handle:
        image_data = json.load(handle)
    assert image_data["alt_text"]
    assert image_data["derived"]["original"] == "gallery/vacation-trip/sunset.png"

    documents = load_documents(config, gallery_workspace=workspace)
    assert len(documents) == 1
    document = documents[0]
    assert document.meta.slug == "vacation-trip"
    assert document.meta.hero_media is not None
    all_paths = [document.meta.hero_media.path] + [asset.path for asset in document.assets]
    assert any(path.endswith("sunset.png") for path in all_paths)

    media_plan = collect_media_plan(documents, config)
    media_result = process_media_plan(media_plan, config)
    apply_variants_to_documents(documents, media_result.variants)
    updated = apply_derivatives(workspace, media_result, config)
    assert updated == 1

    with image_sidecar.open("r", encoding="utf-8") as handle:
        image_data = json.load(handle)
    assert image_data["derived"]["thumbnail"].startswith("media/derived")
    assert image_data["derived"]["web"].startswith("media/derived")

    export_datasets(workspace, config)
    data_root = config.output_dir / config.gallery.data_subdir
    collections_path = data_root / "collections.json"
    images_path = data_root / "images.jsonl"
    collection_jsonl = data_root / "vacation-trip.jsonl"

    assert collections_path.exists()
    assert images_path.exists()
    assert collection_jsonl.exists()

    with collections_path.open("r", encoding="utf-8") as handle:
        collections_payload = json.load(handle)
    assert collections_payload["collections"][0]["id"] == "vacation-trip"

    lines = collection_jsonl.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["id"] == "sunset"
    assert record["collection_id"] == "vacation-trip"
    assert record["thumbnail"]
