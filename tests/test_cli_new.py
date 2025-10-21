from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from typer.testing import CliRunner

from src.cli import app


def _write_default_config(path: Path) -> None:
    path.write_text(
        (
            "project_name: Test Project\n"
            "gallery:\n"
            '  metadata_filename: "meta.yml"\n'
            "music:\n"
            '  metadata_filename: "meta.yml"\n'
        ),
        encoding="utf-8",
    )


def test_new_post_scaffolds_recommended_front_matter() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _write_default_config(Path("smilecms.yml"))
        result = runner.invoke(app, ["new", "post", "my-first-post", "--title", "My First Post"])
        assert result.exit_code == 0, result.output

        post_path = Path("content/posts/my-first-post.md")
        assert post_path.exists()
        content = post_path.read_text(encoding="utf-8")
        assert 'title: "My First Post"' in content
        assert "slug: my-first-post" in content
        assert "status: published" in content
        assert "Markdown body starts here." in content
        assert re.search(r"published_at: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", content)
        assert re.search(r"updated_at: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", content)
        assert 'hero_media:\n  path: "media/hero-image.jpg"' in content

        asset_dir = Path("content/media/my-first-post")
        assert asset_dir.is_dir()
        assert (asset_dir / ".gitkeep").exists()


def test_new_gallery_creates_meta_sidecar() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _write_default_config(Path("smilecms.yml"))
        result = runner.invoke(app, ["new", "gallery", "painted-sunsets"])
        assert result.exit_code == 0, result.output

        meta_path = Path("media/image_gallery_raw/painted-sunsets/meta.yml")
        assert meta_path.exists()
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        assert payload["id"] == "painted-sunsets"
        assert payload["title"] == "Painted Sunsets"
        assert payload["tags"] == []
        assert payload["summary"] is None
        assert payload["description"] is None
        assert payload["cover_image_id"] is None
        assert payload["hero_image_id"] is None
        assert payload["version"] == 1
        assert payload["created_at"].endswith("Z")
        assert payload["updated_at"].endswith("Z")

        keep_path = meta_path.parent / ".gitkeep"
        assert keep_path.exists()


def test_new_track_scaffolds_music_directory() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _write_default_config(Path("smilecms.yml"))
        result = runner.invoke(app, ["new", "track", "evening-jam"])
        assert result.exit_code == 0, result.output

        meta_path = Path("media/music_collection/evening-jam/meta.yml")
        assert meta_path.exists()
        data = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
        assert data["title"] == "Evening Jam"
        assert data["audio"] == "evening-jam.mp3"
        assert data["download"] is True
        assert data["audio_meta"]["mime_type"] == "audio/mpeg"
        assert data["status"] == "published"
        assert data["tags"] == []
        published_at = data["published_at"]
        if isinstance(published_at, str):
            assert published_at.endswith("Z")
        else:
            assert getattr(published_at, "tzinfo", None) is not None

        lyrics_path = Path("media/music_collection/evening-jam/lyrics.md")
        assert lyrics_path.exists()
        lyrics_text = lyrics_path.read_text(encoding="utf-8")
        assert "Write lyrics here" in lyrics_text


def test_new_command_aborts_when_target_exists() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _write_default_config(Path("smilecms.yml"))
        first = runner.invoke(app, ["new", "post", "duplicate-post"])
        assert first.exit_code == 0, first.output

        second = runner.invoke(app, ["new", "post", "duplicate-post"])
        assert second.exit_code != 0
        assert "Cannot scaffold" in second.output
