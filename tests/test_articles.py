from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from build.articles import write_article_pages
from build.config import Config
from build.content import ContentDocument, ContentMeta, ContentStatus


def _make_document(slug: str = "sample-post") -> ContentDocument:
    meta = ContentMeta(
        slug=slug,
        title="Sample Post",
        summary="Sample summary",
        tags=["journal", "updates"],
        status=ContentStatus.PUBLISHED,
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
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


def _write_base_template(path: Path) -> None:
    template = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>SmileCMS</title>
    <link rel="stylesheet" href="./styles/tokens.css" />
  </head>
  <body>
    <a class="skip-link" href="#main">Skip to content</a>
    <div id="app-shell" class="app-shell" data-theme="dark">
      <header class="site-header" id="site-header" aria-live="polite"></header>
      <nav class="site-nav" id="site-nav" aria-label="Primary"></nav>
      <main id="main" class="site-main" tabindex="-1">
        <section class="loading-state"></section>
      </main>
      <footer class="site-footer" id="site-footer"></footer>
    </div>
    <div id="template-host" hidden></div>
    <script type="module" src="./js/app.js"></script>
  </body>
</html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(template, encoding="utf-8")


def test_write_article_page_uses_base_template(tmp_path: Path) -> None:
    templates_dir = tmp_path / "web"
    output_dir = tmp_path / "site"
    _write_base_template(templates_dir / "index.html")
    _write_site_config(templates_dir / "config" / "site.json")

    config = Config(output_dir=output_dir, templates_dir=templates_dir)
    document = _make_document()

    written = write_article_pages([document], config)

    assert len(written) == 1
    page = written[0].read_text(encoding="utf-8")
    assert '<title>Sample Post - Test Site</title>' in page
    assert 'class="site-header"' in page and "Test Tagline" in page
    assert 'class="nav-list"' in page and 'data-open="true"' in page
    assert "Back to Journal" in page
    assert 'href="/styles/tokens.css"' in page
    assert "./styles" not in page
    assert "js/app.js" not in page
    assert "template-host" not in page
    assert 'aria-current="page"' in page  # journal link marked active


def test_write_article_page_falls_back_without_base(tmp_path: Path) -> None:
    templates_dir = tmp_path / "web"
    output_dir = tmp_path / "site"
    _write_site_config(templates_dir / "config" / "site.json")

    config = Config(output_dir=output_dir, templates_dir=templates_dir)
    document = _make_document("fallback-post")

    written = write_article_pages([document], config)

    assert len(written) == 1
    page = written[0].read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in page
    assert "Back to Journal" in page
    assert "site-header" in page and "Test Tagline" in page
    assert 'href="/styles/base.css"' in page
    assert "/js/app.js" not in page
