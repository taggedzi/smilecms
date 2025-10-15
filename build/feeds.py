"""Syndication feed generation helpers for SmileCMS."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import format_datetime as format_rfc2822
from html import escape
from pathlib import Path
from typing import Iterable, Sequence

from .config import Config
from .content.models import ContentStatus
from .manifests import ManifestItem, ManifestPage


@dataclass(slots=True)
class FeedEntry:
    """Normalized feed entry derived from manifest items."""

    slug: str
    title: str
    url: str
    summary: str | None
    tags: list[str]
    published: datetime | None
    updated: datetime | None
    image: str | None
    content_type: str

    @property
    def identifier(self) -> str:
        return self.url


def generate_feeds(config: Config, pages: Sequence[ManifestPage]) -> list[Path]:
    """Generate RSS, Atom, and JSON feeds from manifest pages."""
    settings = config.feeds
    if not settings.enabled:
        return []

    base_url = _normalize_base_url(settings.base_url)
    entries = _collect_entries(pages, limit=settings.limit, base_url=base_url)
    if not entries:
        return []

    metadata = _load_site_metadata(config, base_url)
    updated = entries[0].updated or entries[0].published or datetime.now(timezone.utc)

    feed_root = _resolve_feed_root(config)
    feed_root.mkdir(parents=True, exist_ok=True)

    rss_path = feed_root / "feed.xml"
    atom_path = feed_root / "atom.xml"
    json_path = feed_root / "feed.json"

    relative_base = _feed_relative_base(settings)
    metadata.update(
        {
            "feed_rss": _make_absolute(f"{relative_base}/feed.xml", base_url),
            "feed_atom": _make_absolute(f"{relative_base}/atom.xml", base_url),
            "feed_json": _make_absolute(f"{relative_base}/feed.json", base_url),
        }
    )

    rss_path.write_text(_render_rss(metadata, entries, updated), encoding="utf-8")
    atom_path.write_text(_render_atom(metadata, entries, updated), encoding="utf-8")
    json_path.write_text(_render_json(metadata, entries, updated), encoding="utf-8")

    return [rss_path, atom_path, json_path]


def _collect_entries(
    pages: Iterable[ManifestPage],
    *,
    limit: int,
    base_url: str | None,
) -> list[FeedEntry]:
    collected: list[FeedEntry] = []
    seen_slugs: set[str] = set()

    for page in pages:
        for item in page.items:
            if item.status is not ContentStatus.PUBLISHED:
                continue
            if item.slug in seen_slugs:
                continue

            published = item.published_at or item.updated_at or page.generated_at
            updated = item.updated_at or published
            summary = item.summary or item.excerpt or ""
            tags = list(item.tags or [])
            url = _resolve_item_url(item.slug, base_url)
            image = _resolve_image_url(item, base_url)

            collected.append(
                FeedEntry(
                    slug=item.slug,
                    title=item.title,
                    url=url,
                    summary=summary or None,
                    tags=tags,
                    published=published,
                    updated=updated,
                    image=image,
                    content_type=item.content_type.value,
                )
            )
            seen_slugs.add(item.slug)

    collected.sort(key=lambda entry: _sort_key(entry), reverse=True)
    return collected[:limit]


def _sort_key(entry: FeedEntry) -> datetime:
    candidate = entry.published or entry.updated
    if candidate is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if candidate.tzinfo is None:
        return candidate.replace(tzinfo=timezone.utc)
    return candidate


def _resolve_item_url(slug: str, base_url: str | None) -> str:
    path = f"/posts/{slug.strip('/')}/"
    return _make_absolute(path, base_url)


def _resolve_image_url(item: ManifestItem, base_url: str | None) -> str | None:
    hero = item.hero_media
    if not hero:
        return None

    candidate = None
    if hero.variants:
        for variant in hero.variants:
            if variant.profile == "large":
                candidate = variant.path
                break
        if candidate is None:
            candidate = hero.variants[0].path
    if candidate is None:
        candidate = hero.path

    if not candidate:
        return None
    return _make_absolute(candidate, base_url)


def _load_site_metadata(config: Config, base_url: str | None) -> dict[str, str]:
    settings = config.feeds
    fallback_title = config.project_name
    fallback_description = ""
    site_path = (
        settings.site_config_path
        if settings.site_config_path is not None
        else config.templates_dir / "config" / "site.json"
    )

    data: dict[str, object] = {}
    if site_path.exists():
        try:
            data = json.loads(site_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}

    site_data = data.get("site", {}) if isinstance(data, dict) else {}
    title = str(site_data.get("title") or fallback_title)
    description = str(site_data.get("tagline") or fallback_description)

    navigation = data.get("navigation") if isinstance(data, dict) else None
    home_path = "/"
    if isinstance(navigation, list):
        for entry in navigation:
            if not isinstance(entry, dict):
                continue
            label = str(entry.get("label") or "").strip().lower()
            href = entry.get("href")
            if not href:
                continue
            if label == "home":
                home_path = str(href)
                break
            if home_path == "/":
                home_path = str(href)

    home_url = _make_absolute(home_path, base_url)

    return {
        "title": title,
        "description": description,
        "home_url": home_url,
        "base_url": base_url or "",
    }


def _render_rss(metadata: dict[str, str], entries: Sequence[FeedEntry], updated: datetime) -> str:
    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        "<rss version=\"2.0\">",
        "  <channel>",
        f"    <title>{escape(metadata['title'])}</title>",
        f"    <link>{escape(metadata['home_url'])}</link>",
        f"    <description>{escape(metadata['description'])}</description>",
        f"    <lastBuildDate>{_format_rfc2822(updated)}</lastBuildDate>",
    ]

    for entry in entries:
        parts.extend(
            [
                "    <item>",
                f"      <title>{escape(entry.title)}</title>",
                f"      <link>{escape(entry.url)}</link>",
                f"      <guid>{escape(entry.identifier)}</guid>",
            ]
        )
        if entry.published:
            parts.append(f"      <pubDate>{_format_rfc2822(entry.published)}</pubDate>")
        if entry.summary:
            parts.append(f"      <description>{escape(entry.summary)}</description>")
        for tag in entry.tags:
            parts.append(f"      <category>{escape(tag)}</category>")
        parts.append("    </item>")

    parts.extend(["  </channel>", "</rss>"])
    return "\n".join(parts) + "\n"


def _render_atom(metadata: dict[str, str], entries: Sequence[FeedEntry], updated: datetime) -> str:
    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom">',
        f"  <title>{escape(metadata['title'])}</title>",
        f'  <link href="{escape(metadata["home_url"])}" rel="alternate" />',
    ]

    if metadata.get("feed_atom"):
        parts.append(f'  <link href="{escape(metadata["feed_atom"])}" rel="self" />')

    parts.extend(
        [
            f"  <updated>{_format_iso(updated)}</updated>",
            f"  <id>{escape(metadata['home_url'])}</id>",
        ]
    )

    if metadata.get("description"):
        parts.append(f"  <subtitle>{escape(metadata['description'])}</subtitle>")

    for entry in entries:
        parts.extend(
            [
                "  <entry>",
                f"    <title>{escape(entry.title)}</title>",
                f'    <link href="{escape(entry.url)}" />',
                f"    <id>{escape(entry.identifier)}</id>",
            ]
        )
        if entry.updated:
            parts.append(f"    <updated>{_format_iso(entry.updated)}</updated>")
        if entry.published:
            parts.append(f"    <published>{_format_iso(entry.published)}</published>")
        if entry.summary:
            parts.append(f"    <summary>{escape(entry.summary)}</summary>")
        for tag in entry.tags:
            parts.append(f'    <category term="{escape(tag)}" />')
        parts.append("  </entry>")

    parts.append("</feed>")
    return "\n".join(parts) + "\n"


def _render_json(metadata: dict[str, str], entries: Sequence[FeedEntry], updated: datetime) -> str:
    feed: dict[str, object] = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": metadata["title"],
        "home_page_url": metadata["home_url"],
        "description": metadata["description"],
        "items": [],
    }

    if metadata.get("feed_json"):
        feed["feed_url"] = metadata["feed_json"]
    feed["updated"] = _format_iso(updated)

    items: list[dict[str, object]] = []
    for entry in entries:
        item: dict[str, object] = {
            "id": entry.identifier,
            "url": entry.url,
            "title": entry.title,
        }
        if entry.summary:
            item["summary"] = entry.summary
            item["content_text"] = entry.summary
        if entry.published:
            item["date_published"] = _format_iso(entry.published)
        if entry.updated:
            item["date_modified"] = _format_iso(entry.updated)
        if entry.tags:
            item["tags"] = entry.tags
        if entry.image:
            item["image"] = entry.image
        item["content_type"] = entry.content_type
        items.append(item)

    feed["items"] = items
    return json.dumps(feed, ensure_ascii=False, indent=2) + "\n"


def _format_rfc2822(value: datetime) -> str:
    normalized = value
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=timezone.utc)
    return format_rfc2822(normalized.astimezone(timezone.utc))


def _format_iso(value: datetime) -> str:
    normalized = value
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=timezone.utc)
    return normalized.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_base_url(base_url: str | None) -> str | None:
    if not base_url:
        return None
    text = base_url.strip()
    if not text:
        return None
    return text.rstrip("/")


def _make_absolute(path: str, base_url: str | None) -> str:
    if not path:
        return ""
    if path.startswith("http://") or path.startswith("https://"):
        return path
    normalized = f"/{path.lstrip('/')}"
    if base_url:
        return f"{base_url}{normalized}"
    return normalized


def _resolve_feed_root(config: Config) -> Path:
    subdir = config.feeds.output_subdir
    if subdir is None:
        return config.output_dir
    if subdir.is_absolute():
        return subdir
    return config.output_dir / subdir


def _feed_relative_base(settings) -> str:
    subdir = settings.output_subdir
    if subdir is None:
        return ""
    parts = str(subdir.as_posix()).strip("/")
    if not parts:
        return ""
    return f"/{parts}"
