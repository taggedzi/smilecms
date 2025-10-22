from __future__ import annotations

import json
import shutil
from pathlib import Path

from src.config import Config
from src.pages import write_gallery_page, write_music_page
from src.templates import TemplateAssets

THEME_SOURCE = Path(__file__).resolve().parents[1] / "web" / "dark-theme-1" / "themes" / "default"


def _copy_default_theme(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(THEME_SOURCE, destination)


def _write_site_config(path: Path) -> None:
    data = {
        "site": {"title": "Test Site", "tagline": "Creative Studio"},
        "navigation": [
            {"label": "Home", "href": "/"},
            {"label": "Gallery", "href": "/gallery/"},
            {"label": "Music", "href": "/music/"},
        ],
        "hero": {
            "eyebrow": "Welcome",
            "title": "Explore Everything",
            "subtitle": "Curated collections and soundscapes.",
            "actions": [
                {"label": "View Gallery", "href": "/gallery/"},
                {"label": "Listen More", "href": "/music/"},
            ],
        },
        "sections": [
            {
                "id": "gallery",
                "title": "Featured Galleries",
                "type": "gallery",
                "actions": [{"label": "All Galleries", "href": "/gallery/"}],
            },
            {
                "id": "audio",
                "title": "Listen In",
                "type": "audio",
                "actions": [{"label": "Music Catalog", "href": "/music/"}],
            },
        ],
        "footer": {
            "copy": "All rights reserved.",
            "links": [{"label": "Contact", "href": "mailto:hello@example.com"}],
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle)


def test_write_gallery_page_uses_theme_layout(tmp_path: Path) -> None:
    templates_dir = tmp_path / "web" / "dark-theme-1"
    output_dir = tmp_path / "site"
    _copy_default_theme(templates_dir / "themes" / "default")
    _write_site_config(templates_dir / "config" / "site.json")

    config = Config(output_dir=output_dir, templates_dir=templates_dir)
    assets = TemplateAssets(config)

    page_path = write_gallery_page(config, assets)

    page = page_path.read_text(encoding="utf-8")
    assert "<title>Test Site Gallery</title>" in page
    assert 'class="site-header"' in page and "Creative Studio" in page
    assert 'aria-current="page"' in page  # gallery link active
    assert 'data-site-config="../config/site.json /site/config/site.json"' in page
    assert (
        'data-gallery-collections="../data/gallery/collections.json /site/data/gallery/collections.json"'
        in page
    )
    assert 'href="../styles/gallery.css"' in page
    assert '<script type="module" src="../js/gallery.js"></script>' in page
    assert "window.__SMILE_DATA__" in page


def test_write_music_page_uses_theme_layout(tmp_path: Path) -> None:
    templates_dir = tmp_path / "web" / "dark-theme-1"
    output_dir = tmp_path / "site"
    _copy_default_theme(templates_dir / "themes" / "default")
    _write_site_config(templates_dir / "config" / "site.json")

    config = Config(output_dir=output_dir, templates_dir=templates_dir)
    assets = TemplateAssets(config)

    page_path = write_music_page(config, assets)

    page = page_path.read_text(encoding="utf-8")
    assert "<title>Test Site Music</title>" in page
    assert 'class="site-header"' in page
    assert 'aria-current="page"' in page  # music link active
    assert 'data-music-tracks="../data/music/tracks.jsonl /site/data/music/tracks.jsonl"' in page
    assert 'href="../styles/music.css"' in page
    assert '<script type="module" src="../js/music.js"></script>' in page
    assert "window.__SMILE_DATA__" in page


def test_disabling_music_prunes_navigation_and_data_attributes(tmp_path: Path) -> None:
    templates_dir = tmp_path / "web" / "dark-theme-1"
    output_dir = tmp_path / "site"
    _copy_default_theme(templates_dir / "themes" / "default")
    _write_site_config(templates_dir / "config" / "site.json")

    config = Config(output_dir=output_dir, templates_dir=templates_dir, music={"enabled": False})
    assets = TemplateAssets(config)
    written_config_path = assets.write_site_config(output_dir / "config" / "site.json")

    page_path = write_gallery_page(config, assets)
    page = page_path.read_text(encoding="utf-8")

    assert 'href="/music/' not in page
    assert "js/music.js" not in page
    assert "data-music-tracks" not in page
    assert "music" not in assets.data_endpoints

    shell_attrs = assets.build_shell_attributes(depth=1)
    assert all(not key.startswith("music-") for key in shell_attrs)

    navigation = assets.site_config.get("navigation", [])
    assert isinstance(navigation, list)
    assert all(
        not (isinstance(item, dict) and str(item.get("label") or "").strip().lower() == "music")
        for item in navigation
    )

    hero = assets.site_config.get("hero", {})
    actions = hero.get("actions") if isinstance(hero, dict) else None
    if isinstance(actions, list):
        assert all(
            not (
                isinstance(action, dict)
                and str(action.get("href") or "").strip().rstrip("/").endswith("music")
            )
            for action in actions
        )

    sections = assets.site_config.get("sections", [])
    if isinstance(sections, list):
        assert all(
            not (
                isinstance(section, dict)
                and str(section.get("type") or "").strip().lower() == "audio"
            )
            for section in sections
        )

    written_config = json.loads(written_config_path.read_text(encoding="utf-8"))
    sections_from_file = written_config.get("sections", [])
    if isinstance(sections_from_file, list):
        assert all(
            not (
                isinstance(section, dict)
                and str(section.get("type") or "").strip().lower() == "audio"
            )
            for section in sections_from_file
        )


def test_disabling_gallery_prunes_navigation_and_data_attributes(tmp_path: Path) -> None:
    templates_dir = tmp_path / "web" / "dark-theme-1"
    output_dir = tmp_path / "site"
    _copy_default_theme(templates_dir / "themes" / "default")
    _write_site_config(templates_dir / "config" / "site.json")

    config = Config(output_dir=output_dir, templates_dir=templates_dir, gallery={"enabled": False})
    assets = TemplateAssets(config)
    written_config_path = assets.write_site_config(output_dir / "config" / "site.json")

    assert "gallery" not in assets.data_endpoints

    shell_attrs = assets.build_shell_attributes(depth=1)
    assert all(not key.startswith("gallery-") for key in shell_attrs)

    navigation = assets.site_config.get("navigation", [])
    assert isinstance(navigation, list)
    assert all(
        not (isinstance(item, dict) and str(item.get("label") or "").strip().lower() == "gallery")
        for item in navigation
    )

    hero = assets.site_config.get("hero", {})
    actions = hero.get("actions") if isinstance(hero, dict) else None
    if isinstance(actions, list):
        assert all(
            not (
                isinstance(action, dict)
                and str(action.get("href") or "").strip().rstrip("/").endswith("gallery")
            )
            for action in actions
        )

    sections = assets.site_config.get("sections", [])
    if isinstance(sections, list):
        assert all(
            not (
                isinstance(section, dict)
                and str(section.get("type") or "").strip().lower() == "gallery"
            )
            for section in sections
        )

    written_config = json.loads(written_config_path.read_text(encoding="utf-8"))
    sections_from_file = written_config.get("sections", [])
    if isinstance(sections_from_file, list):
        assert all(
            not (
                isinstance(section, dict)
                and str(section.get("type") or "").strip().lower() == "gallery"
            )
            for section in sections_from_file
        )
