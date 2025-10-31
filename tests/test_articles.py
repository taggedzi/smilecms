from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from src.articles import ArticleBodyRenderer, write_article_pages
from src.config import Config
from src.content import ContentDocument, ContentMeta, ContentStatus, MediaReference

THEME_SOURCE = Path(__file__).resolve().parent / "fixtures" / "test-theme" / "themes" / "default"


def _make_document(slug: str = "sample-post") -> ContentDocument:
    meta = ContentMeta(
        slug=slug,
        title="Sample Post",
        summary="Sample summary",
        tags=["journal", "updates"],
        status=ContentStatus.PUBLISHED,
        published_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    return ContentDocument(
        meta=meta,
        body="First paragraph.\n\nSecond paragraph.",
        source_path=f"{slug}.md",
        assets=[],
    )


def _write_site_config(path: Path) -> None:
    data = {
        "site": {"title": "Test Site", "tagline": "Test Tagline"},
        "navigation": [
            {"label": "Home", "href": "/", "active": True},
            {"label": "Journal", "href": "/journal/"},
        ],
        "footer": {
            "copy": "All rights reserved.",
            "links": [{"label": "Contact", "href": "mailto:hello@example.com"}],
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle)


def _copy_default_theme(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(THEME_SOURCE, destination)


def _expected_asset_prefix(slug: str) -> str:
    depth = slug.count("/") + 2
    return "./" if depth == 0 else "../" * depth


def test_write_article_page_uses_theme_layout(tmp_path: Path) -> None:
    templates_dir = tmp_path / "web" / "dark-theme-1"
    output_dir = tmp_path / "site"
    _copy_default_theme(templates_dir / "themes" / "default")
    _write_site_config(templates_dir / "config" / "site.json")

    config = Config(output_dir=output_dir, templates_dir=templates_dir)
    document = _make_document()

    written = write_article_pages([document], config)

    assert len(written) == 1
    page = written[0].read_text(encoding="utf-8")
    assert "<title>Sample Post - Test Site</title>" in page
    assert 'class="site-header"' in page and "Test Tagline" in page
    assert 'data-site-config="../../config/site.json /site/config/site.json"' in page
    assert 'data-manifest-bases="../../manifests/content /site/manifests/content"' in page
    assert (
        'data-gallery-collections="../../data/gallery/collections.json /site/data/gallery/collections.json"'
        in page
    )
    assert 'aria-current="page"' in page  # journal link marked active
    assert "Back to Journal" in page
    prefix = _expected_asset_prefix(document.meta.slug)
    assert f'href="{prefix}styles/tokens.css"' in page
    assert f'<script type="module" src="{prefix}js/app.js"></script>' in page
    assert "window.__SMILE_DATA__" in page


def test_write_article_page_uses_fallback_theme(tmp_path: Path) -> None:
    templates_dir = tmp_path / "web" / "dark-theme-1"
    output_dir = tmp_path / "site"
    _copy_default_theme(templates_dir / "themes" / "default")
    _write_site_config(templates_dir / "config" / "site.json")

    config = Config(output_dir=output_dir, templates_dir=templates_dir, theme_name="missing-theme")
    document = _make_document("fallback-post")

    written = write_article_pages([document], config)

    assert len(written) == 1
    page = written[0].read_text(encoding="utf-8")
    assert "<title>Sample Post - Test Site</title>" in page
    assert "Back to Journal" in page
    assert 'class="site-header"' in page
    assert 'data-site-config="../../config/site.json /site/config/site.json"' in page
    prefix = _expected_asset_prefix(document.meta.slug)
    assert f'href="{prefix}styles/tokens.css"' in page
    assert f'<script type="module" src="{prefix}js/app.js"></script>' in page


def test_markdown_renderer_supports_extended_markdown() -> None:
    renderer = ArticleBodyRenderer()
    image = MediaReference(path="photos/sunrise.jpg", alt_text="Sunrise")
    audio = MediaReference(path="tracks/song.mp3", title="Song")
    references = {
        "photos/sunrise.jpg": image,
        "tracks/song.mp3": audio,
    }
    body = """# Heading

Paragraph with **bold**, *italic*, and a [link](https://example.com).

> Blockquote

- Item one
- Item two
- [Audio Clip](audio:tracks/song.mp3)

1. Step one
2. Step two

| Column A | Column B |
| -------- | -------- |
| A1       | B1       |

Term
: Definition details

Here is some code:

```python
def hello():
    return "world"
```

Inline `code` and another reference with media: [Gallery Shot](image:photos/sunrise.jpg)
"""

    html = renderer.render_body(body, references)

    assert "<h1>Heading</h1>" in html
    assert "<strong>bold</strong>" in html and "<em>italic</em>" in html
    assert '<a href="https://example.com">' in html
    assert "<blockquote>" in html
    assert "<ul>" in html and "<ol>" in html
    assert "<table>" in html and "<td>A1</td>" in html
    assert "<dl>" in html and "<dt>Term</dt>" in html
    assert '<pre><code class="language-python">' in html
    assert 'class="article-media article-media--audio"' in html
    assert 'class="article-media article-media--image"' in html
