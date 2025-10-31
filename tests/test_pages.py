from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from src.config import Config
from src.pages import (
    DEFAULT_ERROR_PAGES,
    ErrorPageAction,
    ErrorPageDefinition,
    write_error_pages,
    write_gallery_page,
    write_music_page,
)
from src.templates import TemplateAssets

THEME_SOURCE = Path(__file__).resolve().parent / "fixtures" / "test-theme" / "themes" / "default"


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


def test_write_error_pages_produces_plain_markup(tmp_path: Path) -> None:
    templates_dir = tmp_path / "web" / "dark-theme-1"
    output_dir = tmp_path / "site"
    _copy_default_theme(templates_dir / "themes" / "default")
    _write_site_config(templates_dir / "config" / "site.json")

    config = Config(output_dir=output_dir, templates_dir=templates_dir)
    assets = TemplateAssets(config)

    written_paths = write_error_pages(config, assets)

    assert len(written_paths) == len(DEFAULT_ERROR_PAGES)

    page_404 = next(path for path in written_paths if path.name == "404.html")
    html_404 = page_404.read_text(encoding="utf-8")

    assert "<title>404 Page Not Found | Test Site</title>" in html_404
    assert "<style>" in html_404
    assert 'class="error-card"' in html_404
    assert 'class="site-header"' not in html_404
    assert '<a class="error-link" href="/">Return Home</a>' in html_404
    assert "Check the URL for typos" in html_404
    assert '<link rel="stylesheet"' not in html_404


def test_write_error_pages_supports_custom_paths(tmp_path: Path) -> None:
    templates_dir = tmp_path / "web" / "dark-theme-1"
    output_dir = tmp_path / "site"
    _copy_default_theme(templates_dir / "themes" / "default")
    _write_site_config(templates_dir / "config" / "site.json")

    config = Config(output_dir=output_dir, templates_dir=templates_dir)
    assets = TemplateAssets(config)

    custom_definition = ErrorPageDefinition(
        code=451,
        title="Unavailable for Legal Reasons",
        message="Access to this resource is restricted.",
        suggestions=("Contact support if you believe this is an error.",),
        actions=(ErrorPageAction(label="Contact Support", href="/contact/"),),
        filename="errors/legal/451.html",
    )

    written_paths = write_error_pages(config, assets, definitions=[custom_definition])

    assert written_paths == [output_dir / "errors" / "legal" / "451.html"]
    html = written_paths[0].read_text(encoding="utf-8")
    assert "<title>451 Unavailable for Legal Reasons | Test Site</title>" in html
    assert "Access to this resource is restricted." in html
    assert "Contact support if you believe this is an error." in html
    assert '<a class="error-link" href="/contact/">Contact Support</a>' in html
    assert '<a class="error-link" href="/">Return Home</a>' in html


def test_write_error_pages_rejects_non_relative_paths(tmp_path: Path) -> None:
    templates_dir = tmp_path / "web" / "dark-theme-1"
    output_dir = tmp_path / "site"
    _copy_default_theme(templates_dir / "themes" / "default")
    _write_site_config(templates_dir / "config" / "site.json")

    config = Config(output_dir=output_dir, templates_dir=templates_dir)
    assets = TemplateAssets(config)

    unsafe_definition = ErrorPageDefinition(
        code=418,
        title="I'm a teapot",
        message="Short and stout.",
        filename="../outside.html",
    )

    with pytest.raises(ValueError, match="relative to the site root"):
        write_error_pages(config, assets, definitions=[unsafe_definition])


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
