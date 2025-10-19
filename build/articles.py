"""Render and write article detail pages."""

from __future__ import annotations

import html
import json
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Set

from .config import Config
from .content import ContentDocument, ContentStatus, MediaReference, MediaVariant
from .markdown import render_markdown

logger = logging.getLogger(__name__)

MEDIA_SHORTCODE_RE = re.compile(r"\[([^\]]+)\]\((img|image|audio|video):([^)]+)\)")
LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
CODE_RE = re.compile(r"`([^`]+)`")

AVERAGE_READING_SPEED_WPM = 200
DEFAULT_SITE_NAME = "SmileCMS"
DEFAULT_BACK_LABEL = "Back to Home"
DEFAULT_THEME = "dark"
MEDIA_BASE_URL = "/media/derived/"

_INLINE_SCRIPT = """<script>
(function () {
  const shell = document.getElementById('app-shell');
  if (shell && shell.dataset.theme) {
    document.documentElement.dataset.theme = shell.dataset.theme;
  }
  const themeToggle = document.querySelector('[data-theme-toggle]');
  if (shell && themeToggle) {
    themeToggle.addEventListener('click', () => {
      const next = shell.dataset.theme === 'dark' ? 'light' : 'dark';
      shell.dataset.theme = next;
      document.documentElement.dataset.theme = next;
      themeToggle.setAttribute('aria-pressed', String(next === 'dark'));
    });
  }
  const navToggle = document.querySelector('.nav-toggle');
  const navMenu = document.getElementById('nav-menu');
  if (navToggle && navMenu) {
    navToggle.addEventListener('click', () => {
      const isOpen = navMenu.dataset.open === 'true';
      const next = isOpen ? 'false' : 'true';
      navMenu.dataset.open = next;
      navToggle.setAttribute('aria-expanded', String(next === 'true'));
    });
  }
})();
</script>"""


class ArticlePageWriter:
    """Coordinate rendering and writing article pages to disk."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._output_root = config.output_dir / "posts"
        self._assets = TemplateAssets(config)
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


class TemplateAssets:
    """Load template data shared across article rendering."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self.base_template = self._load_base_template()
        self.site_config = self._load_site_config()

    def _load_base_template(self) -> str | None:
        base_path = self._config.templates_dir / "index.html"
        if not base_path.exists():
            logger.warning(
                "Base template not found at %s; using standalone article layout.",
                base_path,
            )
            return None
        try:
            return base_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Unable to read base template %s: %s", base_path, exc)
            return None

    def _load_site_config(self) -> dict[str, Any]:
        config_path = self._config.templates_dir / "config" / "site.json"
        if not config_path.exists():
            logger.warning("Site configuration not found at %s; using defaults.", config_path)
            return {}
        try:
            with config_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
                if isinstance(data, dict):
                    return data
                logger.warning(
                    "Site configuration %s does not define an object root; ignoring.",
                    config_path,
                )
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load site configuration %s: %s", config_path, exc)
        return {}


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

    def render_hero(self, hero: MediaReference | None) -> str:
        """Render the hero media block if a hero is present."""
        if not hero:
            return ""
        url = self._select_media_url(hero, "image")
        alt_text = html.escape(hero.alt_text or hero.title or "")
        return (
            '<figure class="article-hero">'
            f'<img src="{url}" alt="{alt_text}" loading="lazy" />'
            "</figure>"
        )

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
    """Render site-level chrome such as headers, navigation, and footer."""

    def __init__(self, site_config: dict[str, Any]) -> None:
        self._site_config = site_config

    def site_title(self, fallback: str) -> str:
        """Return the configured site title or a provided fallback value."""
        site = self._site_config.get("site")
        if isinstance(site, dict):
            title = str(site.get("title") or "").strip()
            if title:
                return title
        return fallback

    def header(self) -> str:
        """Render the site header block including branding and theme toggle."""
        site = self._site_config.get("site")
        fallback_title = DEFAULT_SITE_NAME
        title = fallback_title
        tagline = ""
        if isinstance(site, dict):
            title = str(site.get("title") or fallback_title)
            tagline = str(site.get("tagline") or "").strip()

        title_html = html.escape(title)
        tagline_html = html.escape(tagline or title)

        parts = [
            '<div class="site-brand">',
            f'  <span class="pill">{tagline_html}</span>',
            f'  <h1 class="headline-2">{title_html}</h1>',
            "</div>",
            '<div class="site-actions">',
            '  <button class="button button--secondary" data-theme-toggle aria-pressed="false">',
            "    Toggle theme",
            "  </button>",
            "</div>",
        ]
        return "\n".join(parts)

    def navigation(self, current_path: str) -> str:
        """Render primary navigation markup, marking the active path when found."""
        navigation = self._site_config.get("navigation")
        items_markup: list[str] = []
        any_active = False

        if isinstance(navigation, list):
            for entry in navigation:
                if not isinstance(entry, dict):
                    continue
                label = str(entry.get("label") or "").strip()
                if not label:
                    continue
                href_raw = str(entry.get("href") or "").strip()
                href = self._normalize_nav_href(href_raw)
                active = bool(entry.get("active")) or self._href_matches_current(href, current_path)
                if active:
                    any_active = True
                aria_current = ' aria-current="page"' if active else ""
                label_html = html.escape(label)
                href_html = html.escape(href or "/")
                items_markup.append(
                    "\n".join(
                        [
                            '    <li role="none">',
                            f'      <a class="nav-link" role="menuitem" href="{href_html}"{aria_current}>{label_html}</a>',
                            "    </li>",
                        ]
                    )
                )

        if not items_markup:
            items_markup.append(
                "\n".join(
                    [
                        '    <li role="none">',
                        '      <a class="nav-link" role="menuitem" href="/">Home</a>',
                        "    </li>",
                    ]
                )
            )
            any_active = True

        data_open = "true" if any_active else "false"
        parts = [
            '<button class="nav-toggle" aria-expanded="false" aria-controls="nav-menu">',
            '  <span class="nav-toggle__label">Menu</span>',
            '  <span class="nav-toggle__icon" aria-hidden="true"></span>',
            "</button>",
            f'<ul class="nav-list" id="nav-menu" role="menubar" data-open="{data_open}">',
            *items_markup,
            "</ul>",
        ]
        return "\n".join(parts)

    def footer(self) -> str:
        """Render footer copy along with optional external links."""
        footer = self._site_config.get("footer")
        copy_text = ""
        links: list[dict[str, Any]] = []
        if isinstance(footer, dict):
            copy_text = str(footer.get("copy") or "").strip()
            raw_links = footer.get("links")
            if isinstance(raw_links, list):
                links = [entry for entry in raw_links if isinstance(entry, dict)]

        if not copy_text:
            site_title = self.site_title(DEFAULT_SITE_NAME)
            copy_text = f"Copyright (c) {datetime.today().year} {site_title}."

        copy_html = html.escape(copy_text)

        link_lines: list[str] = []
        for entry in links:
            label = str(entry.get("label") or "").strip()
            if not label:
                continue
            href = str(entry.get("href") or "").strip() or "#"
            href_html = html.escape(self._normalize_nav_href(href))
            label_html = html.escape(label)
            attrs = ""
            if href.startswith("http"):
                attrs = ' target="_blank" rel="noreferrer noopener"'
            link_lines.append(f'    <a class="site-footer__link" href="{href_html}"{attrs}>{label_html}</a>')

        parts = [f'  <p class="site-footer__copy">{copy_html}</p>']
        if link_lines:
            parts.append('  <div class="site-footer__links">')
            parts.extend(link_lines)
            parts.append("  </div>")
        return "\n".join(parts)

    def back_link(self) -> tuple[str, str]:
        """Determine the most relevant 'back' destination for article pages."""
        navigation = self._site_config.get("navigation")
        if isinstance(navigation, list):
            for entry in navigation:
                if not isinstance(entry, dict):
                    continue
                label = str(entry.get("label") or "").strip()
                if not label:
                    continue
                label_lower = label.lower()
                if label_lower in {"journal", "articles", "blog"}:
                    href = self._normalize_nav_href(str(entry.get("href") or "").strip())
                    return (href or "/"), f"Back to {label}"
            for entry in navigation:
                if not isinstance(entry, dict):
                    continue
                if entry.get("active"):
                    label = str(entry.get("label") or "Home").strip() or "Home"
                    href = self._normalize_nav_href(str(entry.get("href") or "").strip())
                    return (href or "/"), f"Back to {label}"
            for entry in navigation:
                if not isinstance(entry, dict):
                    continue
                label = str(entry.get("label") or "").strip()
                if label.lower() == "home":
                    href = self._normalize_nav_href(str(entry.get("href") or "").strip())
                    return (href or "/"), f"Back to {label or 'Home'}"
        return "/", DEFAULT_BACK_LABEL

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
    """Produce the `<main>` article block, including metadata and back links."""

    def __init__(self, chrome: SiteChromeRenderer, body_renderer: ArticleBodyRenderer) -> None:
        self._chrome = chrome
        self._body_renderer = body_renderer

    def render(
        self,
        document: ContentDocument,
        body_html: str,
        hero_html: str,
        back_href: str,
        back_label: str,
    ) -> str:
        meta = document.meta
        date_str = self._format_datetime(meta.published_at) or self._format_datetime(meta.updated_at)
        summary_html = f"<p>{html.escape(meta.summary)}</p>" if meta.summary else ""
        word_count = self._body_renderer.count_words(document.body)
        reading_time = self._reading_time(word_count)

        meta_items: list[str] = []
        if date_str:
            meta_items.append(f"<span>{html.escape(date_str)}</span>")
        if reading_time:
            meta_items.append(f"<span>{reading_time} min read</span>")

        tag_items: list[str] = [
            f'<li><span class="pill pill--light">#{html.escape(tag)}</span></li>'
            for tag in meta.tags
        ]

        body_lines = [
            f"          {line}" if line else "          "
            for line in body_html.strip().splitlines()
        ] if body_html.strip() else []

        hero_line = f"        {hero_html}" if hero_html else ""

        back_label_text = back_label or "Back"
        lines: list[str] = [
            '<main id="main" class="article-main" tabindex="-1">',
            '  <div class="article-shell">',
            '    <header class="article-header">',
            '      <nav class="article-nav">',
            f'        <a class="article-nav__back" href="{html.escape(back_href)}">{html.escape(back_label_text)}</a>',
            "      </nav>",
            "    </header>",
            '    <section id="article" class="article-content" aria-labelledby="article-title">',
            '      <article class="article-card">',
            '        <header class="article-card__header">',
            f'          <h1 id="article-title">{html.escape(meta.title)}</h1>',
        ]

        if summary_html:
            lines.append(f"          {summary_html}")

        if meta_items:
            lines.append('          <div class="article-card__meta">')
            for item in meta_items:
                lines.append(f"            {item}")
            lines.append("          </div>")

        if tag_items:
            lines.append('          <ul class="article-card__tags">')
            for tag_item in tag_items:
                lines.append(f"            {tag_item}")
            lines.append("          </ul>")

        lines.append("        </header>")

        if hero_line:
            lines.append(hero_line)

        lines.append('        <div class="article-card__body">')
        if body_lines:
            lines.extend(body_lines)
        lines.append("        </div>")
        lines.append("      </article>")
        lines.append("    </section>")
        lines.append('    <footer class="article-footer">')
        footer_copy = f"Copyright (c) {datetime.today().year} {DEFAULT_SITE_NAME} - Return home"
        lines.append(f'      <a href="/">{html.escape(footer_copy)}</a>')
        lines.append("    </footer>")
        lines.append("  </div>")
        lines.append("</main>")
        return "\n".join(lines)

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
    """Compose the final HTML page from rendered fragments."""

    def __init__(
        self,
        assets: TemplateAssets,
        chrome: SiteChromeRenderer,
        main_renderer: ArticleMainRenderer,
    ) -> None:
        self._assets = assets
        self._chrome = chrome
        self._main_renderer = main_renderer

    def compose(self, document: ContentDocument, body_html: str, hero_html: str) -> str:
        """Assemble the final HTML page for a document using available assets."""
        back_href, back_label = self._chrome.back_link()
        if self._assets.base_template:
            return self._render_with_base_template(
                document,
                body_html,
                hero_html,
                back_href=back_href,
                back_label=back_label,
            )
        return self._render_standalone_document(
            document,
            body_html,
            hero_html,
            back_href=back_href,
            back_label=back_label,
        )

    def _render_with_base_template(
        self,
        document: ContentDocument,
        body_html: str,
        hero_html: str,
        *,
        back_href: str,
        back_label: str,
    ) -> str:
        assert self._assets.base_template is not None
        meta = document.meta
        site_title = self._chrome.site_title(meta.slug)
        page_title = f"{html.escape(meta.title)} - {html.escape(site_title)}"

        header_block = self._indent_block(self._chrome.header(), 8)
        nav_block = self._indent_block(
            self._chrome.navigation(current_path=f"/posts/{document.slug}/"),
            8,
        )
        footer_block = self._indent_block(self._chrome.footer(), 8)
        main_block = self._indent_html(
            self._main_renderer.render(
                document,
                body_html,
                hero_html,
                back_href=back_href,
                back_label=back_label,
            ),
            6,
        )

        html_text = self._assets.base_template
        html_text = self._inject_inline_script(html_text)
        html_text = self._strip_template_host(html_text)
        html_text = self._replace_title(html_text, page_title)
        html_text = self._replace_tag_contents(html_text, "header", "site-header", header_block)
        html_text = self._replace_tag_contents(html_text, "nav", "site-nav", nav_block)
        html_text = self._replace_main_section(html_text, main_block)
        html_text = self._replace_tag_contents(html_text, "footer", "site-footer", footer_block)
        html_text = self._normalize_asset_paths(html_text)
        html_text = self._ensure_shell_theme(html_text)
        return html_text

    def _render_standalone_document(
        self,
        document: ContentDocument,
        body_html: str,
        hero_html: str,
        *,
        back_href: str,
        back_label: str,
    ) -> str:
        meta = document.meta
        site_title = self._chrome.site_title(DEFAULT_SITE_NAME) or DEFAULT_SITE_NAME
        page_title = f"{html.escape(meta.title)} - {html.escape(site_title)}"

        header_block = self._indent_block(self._chrome.header(), 8, trailing_newline=False)
        nav_block = self._indent_block(
            self._chrome.navigation(current_path=f"/posts/{document.slug}/"),
            8,
            trailing_newline=False,
        )
        main_block = self._indent_block(
            self._main_renderer.render(
                document,
                body_html,
                hero_html,
                back_href=back_href,
                back_label=back_label,
            ),
            6,
            leading_newline=False,
            trailing_newline=False,
        )
        footer_block = self._indent_block(self._chrome.footer(), 8, trailing_newline=False)

        template_lines = [
            "<!DOCTYPE html>",
            '<html lang="en">',
            "  <head>",
            '    <meta charset="utf-8" />',
            '    <meta name="viewport" content="width=device-width, initial-scale=1" />',
            '    <meta name="color-scheme" content="dark light" />',
            f"    <title>{page_title}</title>",
            '    <link rel="stylesheet" href="/styles/tokens.css" />',
            '    <link rel="stylesheet" href="/styles/base.css" />',
            '    <link rel="stylesheet" href="/styles/layout.css" />',
            '    <link rel="stylesheet" href="/styles/typography.css" />',
            '    <link rel="stylesheet" href="/styles/components.css" />',
            "  </head>",
            "  <body>",
            '    <a class="skip-link" href="#main">Skip to content</a>',
            f'    <div id="app-shell" class="app-shell" data-theme="{DEFAULT_THEME}">',
            '      <header class="site-header" id="site-header" aria-live="polite">',
            f"{header_block}",
            "      </header>",
            '      <nav class="site-nav" id="site-nav" aria-label="Primary">',
            f"{nav_block}",
            "      </nav>",
            f"{main_block}",
            '      <footer class="site-footer" id="site-footer">',
            f"{footer_block}",
            "      </footer>",
            "    </div>",
            f"{self._indent_block(_INLINE_SCRIPT, 4, leading_newline=False, trailing_newline=False)}",
            "  </body>",
            "</html>",
        ]
        html_text = "\n".join(template_lines)
        html_text = self._normalize_asset_paths(html_text)
        html_text = self._ensure_shell_theme(html_text)
        return html_text

    def _replace_tag_contents(self, source: str, tag: str, element_id: str, replacement: str) -> str:
        pattern = re.compile(
            rf'(<{tag}\b[^>]*\bid="{element_id}"[^>]*>)(.*?)(</{tag}>)',
            re.IGNORECASE | re.DOTALL,
        )

        def _repl(match: re.Match[str]) -> str:
            return f"{match.group(1)}{replacement}{match.group(3)}"

        return pattern.sub(_repl, source, count=1)

    def _replace_main_section(self, source: str, replacement: str) -> str:
        pattern = re.compile(
            r'<main\b[^>]*id="main"[^>]*>.*?</main>',
            re.IGNORECASE | re.DOTALL,
        )
        return pattern.sub(replacement, source, count=1)

    def _replace_title(self, source: str, title: str) -> str:
        pattern = re.compile(r"<title>.*?</title>", re.IGNORECASE | re.DOTALL)
        replacement = f"<title>{title}</title>"
        updated, count = pattern.subn(replacement, source, count=1)
        if count == 0:
            return replacement + source
        return updated

    def _normalize_asset_paths(self, html_text: str) -> str:
        html_text = html_text.replace('href="./styles/', 'href="/styles/')
        html_text = html_text.replace('href="../styles/', 'href="/styles/')
        html_text = html_text.replace('src="./js/', 'src="/js/')
        html_text = html_text.replace('src="../js/', 'src="/js/')
        return html_text

    def _strip_template_host(self, html_text: str) -> str:
        pattern = re.compile(r'\s*<div id="template-host"[^>]*></div>\s*', re.IGNORECASE)
        return pattern.sub("\n", html_text, count=1)

    def _inject_inline_script(self, html_text: str) -> str:
        pattern = re.compile(
            r'(?P<indent>\s*)<script[^>]+src="\.?/js/app\.js"[^>]*></script>',
            re.IGNORECASE,
        )

        def repl(match: re.Match[str]) -> str:
            indent = match.group("indent")
            script_lines = _INLINE_SCRIPT.strip().splitlines()
            indented = "\n".join(f"{indent}{line}" for line in script_lines)
            return indented

        updated, count = pattern.subn(repl, html_text, count=1)
        if count:
            return updated

        fallback_indent = "    "
        script_lines = _INLINE_SCRIPT.strip().splitlines()
        indented_script = "\n".join(f"{fallback_indent}{line}" for line in script_lines)
        return updated.replace("</body>", f"{indented_script}\n  </body>", 1)

    def _ensure_shell_theme(self, html_text: str) -> str:
        if 'data-theme="' in html_text:
            return html_text
        return html_text.replace(
            '<div id="app-shell" class="app-shell"',
            f'<div id="app-shell" class="app-shell" data-theme="{DEFAULT_THEME}"',
            1,
        )

    def _indent_html(self, content: str, spaces: int) -> str:
        if not content:
            return ""
        prefix = " " * spaces
        stripped = content.strip("\n")
        lines = stripped.splitlines()
        return "\n".join(f"{prefix}{line}" if line else prefix for line in lines)

    def _indent_block(
        self,
        content: str,
        spaces: int,
        *,
        leading_newline: bool = True,
        trailing_newline: bool = True,
    ) -> str:
        if not content:
            return ""
        body = self._indent_html(content, spaces)
        if leading_newline:
            body = "\n" + body
        if trailing_newline:
            body = body + "\n"
        return body


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
        hero_html = self._body_renderer.render_hero(document.meta.hero_media)
        return self._composer.compose(document, body_html, hero_html)


def write_article_pages(documents: Iterable[ContentDocument], config: Config) -> list[Path]:
    """
    Render published articles into static HTML pages.

    Args:
        documents: An iterable of content documents to be rendered.
        config: Build configuration containing template and output directories.

    Returns:
        A list of paths to the written HTML files.
    """
    writer = ArticlePageWriter(config)
    return writer.write(documents)

