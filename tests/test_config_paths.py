from __future__ import annotations

from pathlib import Path

from src.config import load_config


def _write_project_config(root: Path) -> Path:
    config_text = (
        "project_name: External Project\n"
        "content_dir: content\n"
        "article_media_dir: content/media\n"
        "media_dir: media\n"
        "output_dir: site\n"
        "templates_dir: web\n"
        "cache_dir: .cache\n"
        "media_processing:\n"
        "  source_dir: content/media\n"
        "  output_dir: media/derived\n"
        "gallery:\n"
        "  source_dir: media/image_gallery_raw\n"
        "  metadata_filename: meta.yml\n"
        "music:\n"
        "  source_dir: media/music_collection\n"
        "  metadata_filename: meta.yml\n"
        "feeds:\n"
        "  enabled: true\n"
        "  output_subdir: feeds\n"
    )
    cfg_path = root / "smilecms.yml"
    cfg_path.write_text(config_text, encoding="utf-8")
    return cfg_path


def test_load_config_resolves_paths_relative_to_config_directory(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_project_config(project)

    # Pass a directory path; loader should find smilecms.yml inside it.
    cfg = load_config(project)

    assert cfg.content_dir == (project / "content").resolve()
    assert cfg.article_media_dir == (project / "content" / "media").resolve()
    assert cfg.media_dir == (project / "media").resolve()
    assert cfg.output_dir == (project / "site").resolve()
    assert cfg.templates_dir == (project / "web").resolve()
    assert cfg.cache_dir == (project / ".cache").resolve()

    assert cfg.media_processing.source_dir == (project / "content" / "media").resolve()
    assert cfg.media_processing.output_dir == (project / "media" / "derived").resolve()

    assert cfg.gallery.source_dir == (project / "media" / "image_gallery_raw").resolve()
    assert cfg.music.source_dir == (project / "media" / "music_collection").resolve()

    # feeds.output_subdir remains a relative subpath (joined under output_dir elsewhere)
    assert str(cfg.feeds.output_subdir) == "feeds"
    assert not Path(cfg.feeds.output_subdir).is_absolute()  # type: ignore[arg-type]


def test_load_config_accepts_config_file_path(tmp_path: Path) -> None:
    project = tmp_path / "siteproj"
    project.mkdir()
    config_file = _write_project_config(project)

    cfg = load_config(config_file)
    assert cfg.output_dir == (project / "site").resolve()


def test_load_config_uses_defaults_when_directory_has_no_config(tmp_path: Path) -> None:
    project = tmp_path / "emptyproj"
    project.mkdir()

    cfg = load_config(project)

    # Defaults anchored to the provided directory
    assert cfg.content_dir == (project / "content").resolve()
    assert cfg.article_media_dir == (project / "content" / "media").resolve()
    assert cfg.media_dir == (project / "media").resolve()
    assert cfg.output_dir == (project / "site").resolve()
    assert cfg.templates_dir == (project / "web").resolve()
    assert cfg.cache_dir == (project / ".cache").resolve()
