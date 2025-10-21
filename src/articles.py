"""Render and write article detail pages."""

from __future__ import annotations

import html
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Set

from markupsafe import Markup

from .config import Config
from .content import ContentDocument, ContentStatus, MediaReference, MediaVariant
from .markdown import render_markdown
from .templates import TemplateAssets
from .themes import ThemeLoader

logger = logging.getLogger(__name__)

MEDIA_SHORTCODE_RE = re.compile(r"\[([^\]]+)\]\((img|image|audio|video):([^)]+)\)")
LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
CODE_RE = re.compile(r"`([^`]+)`")

AVERAGE_READING_SPEED_WPM = 200
DEFAULT_SITE_NAME = "SmileCMS"
DEFAULT_BACK_LABEL = "Back to Home"
MEDIA_BASE_URL = "/media/derived/"

class ArticlePageWriter:
    """Coordinate rendering and writing article pages to disk."""

    def __init__(self, config: Config, assets: TemplateAssets | None = None) -> None:
        self._config = config
        self._output_root = config.output_dir / "posts"
        self._assets = assets or TemplateAssets(config)
        self._renderer = ArticlePageRenderer(self._assets)

    def write(self, documents: Iterable[ContentDocument]) -> list[Path]:
        """Render every published document and write the HTML output."""
        self._output_root.mkdir(parents=True, exist_ok=True)
        existing_dirs: Set[Path] = {path for path in self._output_root.iterdir() if path.is_dir()}
        current_dirs: Set[Path] = set()
        written_paths: list[Path] = []

        for document in documents:
            if document.meta.status is not ContentStatus.PUBLISHED:
                continue

            html_text = self._renderer.render(document)
            destination = self._output_root / document.slug / "index.html"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(html_text, encoding="utf-8")

            current_dirs.add(destination.parent)
            written_paths.append(destination)

        DirectoryPruner.prune(existing_dirs - current_dirs)
        return written_paths


class ArticleBodyRenderer:
    """Transform article markdown body and media references into HTML fragments."""

    def build_reference_map(self, document: ContentDocument) -> dict[str, MediaReference]:
        """Index hero and asset references by their path for quick lookup."""
        mapping: dict[str, MediaReference] = {}
        if document.meta.hero_media:
            mapping[document.meta.hero_media.path] = document.meta.hero_media
        for reference in document.assets:
            mapping[reference.path] = reference
        return mapping

    def render_body(self, body: str, references: dict[str, MediaReference]) -> str:
        """Render the article body and expand media shortcodes."""
        if not body:
            return ""

        def replace(match: re.Match[str]) -> str:
            label, media_type, target = match.groups()
            figure_html = self._render_media_shortcode(
                label.strip(),
                media_type.lower(),
                target.strip(),
                references,
            )
            return f"\n\n{figure_html}\n\n"

        processed = MEDIA_SHORTCODE_RE.sub(replace, body)
        return self._markdown_to_html(processed)

    def hero_context(self, hero: MediaReference | None) -> dict[str, str] | None:
        """Produce template context for the hero media block."""
        if not hero:
            return None
        url = self._select_media_url(hero, "image")
        alt_text = hero.alt_text or hero.title or ""
        return {"url": url, "alt": alt_text or ""}

    def count_words(self, body: str) -> int:
        """Estimate the number of words in the original body content."""
        plain_text = self._extract_plain_text(body)
        return len(plain_text.split()) if plain_text else 0

    def _render_media_shortcode(
        self,
        label: str,
        media_type: str,
        target: str,
        references: dict[str, MediaReference],
    ) -> str:
        reference = references.get(target)
        if reference is None:
            logger.warning("Article media shortcode references missing asset '%s'.", target)
            safe_label = html.escape(label)
            safe_target = html.escape(target)
            return f'<p><em>Missing media: {safe_label} ({safe_target})</em></p>'

        url = self._select_media_url(reference, media_type)
        caption = html.escape(label)

        if media_type in {"img", "image"}:
            alt_text = html.escape(reference.alt_text or caption)
            return (
                '<figure class="article-media article-media--image">'
                f'<img src="{url}" alt="{alt_text}" loading="lazy" />'
                f"<figcaption>{caption}</figcaption>"
                "</figure>"
            )
        if media_type == "audio":
            return (
                '<figure class="article-media article-media--audio">'
                f"<figcaption>{caption}</figcaption>"
                f'<audio controls preload="metadata" src="{url}"></audio>'
                "</figure>"
            )
        if media_type == "video":
            return (
                '<figure class="article-media article-media--video">'
                f'<video controls preload="metadata" src="{url}"></video>'
                f"<figcaption>{caption}</figcaption>"
                "</figure>"
            )

        logger.warning("Unknown media shortcode type '%s'.", media_type)
        safe_target = html.escape(target)
        return f'<p><a href="{safe_target}">{caption}</a></p>'

    def _select_media_url(self, reference: MediaReference, media_type: str) -> str:
        variant = self._select_variant(reference, media_type)
        if variant:
            return f"{MEDIA_BASE_URL}{variant.path.lstrip('/')}"
        return f"{MEDIA_BASE_URL}{reference.path.lstrip('/')}"

    def _select_variant(self, reference: MediaReference, media_type: str) -> MediaVariant | None:
        if not reference.variants:
            return None

        preferred = ("large", "thumb", "original") if media_type in {"img", "image"} else ("original",)
        for profile in preferred:
            for variant in reference.variants:
                if variant.profile == profile:
                    return variant
        return reference.variants[0]

    def _markdown_to_html(self, text: str) -> str:
        return render_markdown(text).strip()

    def _extract_plain_text(self, body: str) -> str:
        text_parts: list[str] = []
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            stripped = IMAGE_RE.sub("", stripped)
            stripped = LINK_RE.sub(r"\1", stripped)
            stripped = CODE_RE.sub(r"\1", stripped)
            stripped = stripped.lstrip("#>*-1234567890. ").strip()
            if stripped:
                text_parts.append(stripped)
        return " ".join(text_parts)


class SiteChromeRenderer:
    """Build context for site-level chrome such as headers, navigation, and footer."""

    def __init__(self, site_config: dict[str, Any]) -> None:
        self._site_config = site_config

    def site_identity(self, fallback: str) -> dict[str, str]:
        site = self._site_config.get("site")
        title = fallback
        tagline = ""
        if isinstance(site, dict):
            candidate = str(site.get("title") or "").strip()
            if candidate:
                title = candidate
            tagline = str(site.get("tagline") or "").strip()
        return {"title": title, "tagline": tagline or title}

    def site_title(self, fallback: str) -> str:
        return self.site_identity(fallback)["title"]

    def navigation(self, current_path: str) -> dict[str, Any]:
        navigation = self._site_config.get("navigation")
        items: list[dict[str, Any]] = []
        any_active = False

        if isinstance(navigation, list):
            for entry in navigation:
                if not isinstance(entry, dict):
                    continue
                label = str(entry.get("label") or "").strip()
                if not label:
                    continue
                raw_href = str(entry.get("href") or "").strip()
                href = self._normalize_nav_href(raw_href)
                active = bool(entry.get("active")) or self._href_matches_current(href, current_path)
                if active:
                    any_active = True
                items.append(
                    {
                        "label": label,
                        "href": href or "/",
                        "active": active,
                    }
                )

        if not items:
            items.append({"label": "Home", "href": "/", "active": True})
            any_active = True

        return {
            "items": items,
            "menu_open": any_active,
        }

    def footer(self) -> dict[str, Any]:
        footer = self._site_config.get("footer")
        copy_text = ""
        links: list[dict[str, Any]] = []
        if isinstance(footer, dict):
            copy_text = str(footer.get("copy") or "").strip()
            raw_links = footer.get("links")
            if isinstance(raw_links, list):
                for entry in raw_links:
                    if not isinstance(entry, dict):
                        continue
                    label = str(entry.get("label") or "").strip()
                    if not label:
                        continue
                    raw_href = str(entry.get("href") or "").strip() or "#"
                    href = self._normalize_nav_href(raw_href)
                    links.append(
                        {
                            "label": label,
                            "href": href or "/",
                            "external": raw_href.startswith("http"),
                        }
                    )

        if not copy_text:
            site_title = self.site_title(DEFAULT_SITE_NAME)
            copy_text = f"Copyright (c) {datetime.today().year} {site_title}."

        return {"copy": copy_text, "links": links}

    def back_link(self, current_path: str) -> dict[str, str]:
        navigation = self._site_config.get("navigation")
        if isinstance(navigation, list):
            for entry in navigation:
                if not isinstance(entry, dict):
                    continue
                label = str(entry.get("label") or "").strip()
                if not label:
                    continue
                label_lower = label.lower()
                raw_href = str(entry.get("href") or "").strip()
                href = self._normalize_nav_href(raw_href)
                if label_lower in {"journal", "articles", "blog"}:
                    return {"href": href or "/", "label": f"Back to {label}"}
            for entry in navigation:
                if not isinstance(entry, dict):
                    continue
                raw_href = str(entry.get("href") or "").strip()
                href = self._normalize_nav_href(raw_href)
                if entry.get("active") or self._href_matches_current(href, current_path):
                    label = str(entry.get("label") or "Home").strip() or "Home"
                    return {"href": href or "/", "label": f"Back to {label}"}
            for entry in navigation:
                if not isinstance(entry, dict):
                    continue
                label = str(entry.get("label") or "").strip()
                if label.lower() == "home":
                    href = self._normalize_nav_href(str(entry.get("href") or "").strip())
                    return {"href": href or "/", "label": f"Back to {label or 'Home'}"}
        return {"href": "/", "label": DEFAULT_BACK_LABEL}

    def _normalize_nav_href(self, value: str) -> str:
        if not value:
            return "/"
        value = value.strip()
        if not value:
            return "/"
        if value.startswith("#"):
            return f"/{value}"
        return value

    def _href_matches_current(self, href: str, current_path: str) -> bool:
        if not href:
            return False
        href_base = href.split("#", 1)[0].rstrip("/") or "/"
        current_base = current_path.split("#", 1)[0].rstrip("/") or "/"
        if href_base == current_base:
            return True
        if current_base.startswith("/posts/") and "journal" in href.lower():
            return True
        return False


class ArticleMainRenderer:
    """Prepare context rendered inside the `<main>` article block."""

    def __init__(self, chrome: SiteChromeRenderer, body_renderer: ArticleBodyRenderer) -> None:
        self._chrome = chrome
        self._body_renderer = body_renderer

    def build_context(
        self,
        document: ContentDocument,
        *,
        body_html: str,
        hero: dict[str, str] | None,
        back_link: dict[str, str],
        site_title: str,
    ) -> dict[str, Any]:
        meta = document.meta
        summary = str(meta.summary or "").strip()
        word_count = self._body_renderer.count_words(document.body)
        reading_time = self._reading_time(word_count)
        date_str = self._format_datetime(meta.published_at) or self._format_datetime(meta.updated_at)

        meta_items: list[str] = []
        if date_str:
            meta_items.append(date_str)
        if reading_time:
            meta_items.append(f"{reading_time} min read")

        tags = [tag.strip() for tag in meta.tags if tag and tag.strip()]
        footer_copy = f"Copyright (c) {datetime.today().year} {site_title} - Return home"

        return {
            "summary": summary,
            "meta_items": meta_items,
            "tags": tags,
            "hero": hero,
            "body_html": Markup(body_html) if body_html else Markup(""),
            "back": {
                "href": back_link["href"],
                "label": back_link["label"],
            },
            "footer": {
                "href": "/",
                "copy": footer_copy,
            },
        }

    @staticmethod
    def _format_datetime(value: datetime | None) -> str | None:
        if not value:
            return None
        try:
            return value.strftime("%b %d, %Y")
        except Exception:
            logger.warning("Unable to format datetime value %r", value)
            return None

    @staticmethod
    def _reading_time(word_count: int) -> int | None:
        if word_count <= 0:
            return None
        return max(1, round(word_count / AVERAGE_READING_SPEED_WPM))


class TemplateComposer:
    """Compose the final HTML page using the active Jinja theme."""

    def __init__(
        self,
        assets: TemplateAssets,
        chrome: SiteChromeRenderer,
        main_renderer: ArticleMainRenderer,
    ) -> None:
        self._assets = assets
        self._chrome = chrome
        self._main_renderer = main_renderer

    @property
    def theme(self) -> ThemeLoader:
        return self._assets.theme

    def compose(self, document: ContentDocument, body_html: str, hero: dict[str, str] | None) -> str:
        meta = document.meta
        current_path = f"/posts/{document.slug}/"
        depth = self._document_depth(document)

        site_identity = self._chrome.site_identity(DEFAULT_SITE_NAME)
        navigation = self._chrome.navigation(current_path=current_path)
        footer = self._chrome.footer()
        back_link = self._chrome.back_link(current_path=current_path)

        article_context = self._main_renderer.build_context(
            document,
            body_html=body_html,
            hero=hero,
            back_link=back_link,
            site_title=site_identity["title"],
        )

        shell_attributes = self._assets.build_shell_attributes(depth=depth)

        context = {
            "site": site_identity,
            "navigation": navigation,
            "footer": footer,
            "shell": {
                "theme": self.theme.manifest.default_shell_theme,
                "data_attributes": shell_attributes,
            },
            "page": {
                "title": f"{meta.title} - {site_identity['title']}",
                "slug": meta.slug,
                "body_class": "article-page",
                "styles": [],
                "scripts": [],
                "relative_root": self._relative_prefix(depth),
            },
            "document": {
                "title": meta.title,
                "slug": meta.slug,
            },
            "article": article_context,
            "assets": self.theme.assets.to_template_dict(),
            "feeds": self._assets.feed_links,
        }
        return self.theme.render_page("article", context)

    @staticmethod
    def _document_depth(document: ContentDocument) -> int:
        """Compute directory depth from site root for the rendered document."""
        return document.slug.count("/") + 2

    @staticmethod
    def _relative_prefix(depth: int) -> str:
        return "./" if depth == 0 else "../" * depth


class DirectoryPruner:
    """Remove stale article directories after rendering."""

    @staticmethod
    def prune(stale_dirs: Iterable[Path]) -> None:
        """Remove directories not touched during the current build."""
        for directory in sorted(stale_dirs, key=lambda item: len(item.parts), reverse=True):
            if directory.exists():
                shutil.rmtree(directory, ignore_errors=True)


class ArticlePageRenderer:
    """Render a single ContentDocument into its final HTML page."""

    def __init__(self, assets: TemplateAssets) -> None:
        self._assets = assets
        self._body_renderer = ArticleBodyRenderer()
        self._chrome = SiteChromeRenderer(assets.site_config)
        self._main_renderer = ArticleMainRenderer(self._chrome, self._body_renderer)
        self._composer = TemplateComposer(assets, self._chrome, self._main_renderer)

    def render(self, document: ContentDocument) -> str:
        """Render the provided document into final HTML."""
        references = self._body_renderer.build_reference_map(document)
        body_html = self._body_renderer.render_body(document.body, references)
        hero = self._body_renderer.hero_context(document.meta.hero_media)
        return self._composer.compose(document, body_html, hero)


def write_article_pages(
    documents: Iterable[ContentDocument],
    config: Config,
    *,
    assets: TemplateAssets | None = None,
) -> list[Path]:
    """
    Render published articles into static HTML pages.

    Args:
        documents: An iterable of content documents to be rendered.
        config: Build configuration containing template and output directories.

    Returns:
        A list of paths to the written HTML files.
    """
    writer = ArticlePageWriter(config, assets=assets)
    return writer.write(documents)

