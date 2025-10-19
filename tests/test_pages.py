from __future__ import annotations

import json
import shutil
from pathlib import Path

from build.config import Config
from build.pages import write_gallery_page, write_music_page
from build.templates import TemplateAssets

THEME_SOURCE = Path(__file__).resolve().parents[1] / "web" / "themes" / "default"


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
        "footer": {
            "copy": "All rights reserved.",
            "links": [{"label": "Contact", "href": "mailto:hello@example.com"}],
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle)


def test_write_gallery_page_uses_theme_layout(tmp_path: Path) -> None:
    templates_dir = tmp_path / "web"
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
    templates_dir = tmp_path / "web"
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
