import json
from datetime import UTC, datetime
from pathlib import Path

from src.config import Config, FeedConfig
from src.content.models import ContentStatus, ContentType, MediaReference, MediaVariant
from src.feeds import generate_feeds
from src.manifests.models import ManifestItem, ManifestPage


def _manifest_item(slug: str) -> ManifestItem:
    return ManifestItem(
        slug=slug,
        title=slug.replace("-", " ").title(),
        content_type=ContentType.ARTICLE,
        summary="Short summary.",
        excerpt="Short summary.",
        tags=["updates"],
        status=ContentStatus.PUBLISHED,
        hero_media=MediaReference(
            path="media/example.jpg",
            variants=[
                MediaVariant(profile="thumb", path="thumb/media/example.jpg"),
                MediaVariant(profile="large", path="large/media/example.jpg"),
            ],
        ),
        published_at=datetime(2024, 1, 1, tzinfo=UTC),
        updated_at=datetime(2024, 1, 2, tzinfo=UTC),
        word_count=120,
        reading_time_minutes=1,
        asset_count=1,
        has_media=True,
    )


def test_generate_feeds_writes_all_formats(tmp_path: Path) -> None:
    template_dir = tmp_path / "web" / "dark-theme-1"
    (template_dir / "config").mkdir(parents=True)
    (template_dir / "config" / "site.json").write_text(
        json.dumps(
            {
                "site": {
                    "title": "SmileCMS Studio",
                    "tagline": "Art, essays, and ambient soundscapes.",
                },
                "navigation": [{"label": "Home", "href": "/"}],
            }
        ),
        encoding="utf-8",
    )

    output_dir = tmp_path / "site"
    config = Config(
        project_name="SmileCMS Studio",
        templates_dir=template_dir,
        output_dir=output_dir,
        feeds=FeedConfig(base_url="https://example.com", limit=5),
    )

    page = ManifestPage(
        id="content-001",
        page=1,
        total_pages=1,
        total_items=1,
        items=[_manifest_item("hello-world")],
    )

    paths = generate_feeds(config, [page])
    names = {path.name for path in paths}
    assert names == {"feed.xml", "atom.xml", "feed.json"}

    rss = (output_dir / "feed.xml").read_text(encoding="utf-8")
    assert "<title>Hello World</title>" in rss
    assert "https://example.com/posts/hello-world/" in rss

    atom = (output_dir / "atom.xml").read_text(encoding="utf-8")
    assert "<entry>" in atom

    feed_json = json.loads((output_dir / "feed.json").read_text(encoding="utf-8"))
    assert feed_json["items"][0]["id"] == "https://example.com/posts/hello-world/"
    assert feed_json["items"][0]["image"] == "https://example.com/large/media/example.jpg"


def test_generate_feeds_respects_disabled(tmp_path: Path) -> None:
    template_dir = tmp_path / "web" / "dark-theme-1"
    (template_dir / "config").mkdir(parents=True)
    (template_dir / "config" / "site.json").write_text("{}", encoding="utf-8")

    output_dir = tmp_path / "site"
    config = Config(
        project_name="SmileCMS Studio",
        templates_dir=template_dir,
        output_dir=output_dir,
        feeds=FeedConfig(enabled=False),
    )

    page = ManifestPage(
        id="content-001",
        page=1,
        total_pages=1,
        total_items=0,
        items=[_manifest_item("ignored")],
    )

    paths = generate_feeds(config, [page])
    assert paths == []
    assert not (output_dir / "feed.xml").exists()
