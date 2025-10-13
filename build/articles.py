"""Render and write article detail pages."""

from __future__ import annotations

import html
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .config import Config
from .content import ContentDocument, ContentStatus, MediaReference, MediaVariant

logger = logging.getLogger(__name__)

MEDIA_SHORTCODE_RE = re.compile(r"\[([^\]]+)\]\((img|image|audio|video):([^)]+)\)")
LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
CODE_RE = re.compile(r"`([^`]+)`")


def write_article_pages(documents: Iterable[ContentDocument], config: Config) -> list[Path]:
    """Render published articles into static HTML pages."""
    output_root = config.output_dir / "posts"
    written: list[Path] = []

    for document in documents:
        if document.meta.status is not ContentStatus.PUBLISHED:
            continue

        reference_map = _build_reference_map(document)
        body_html = _render_body(document.body, reference_map)
        hero_html = _render_hero(document.meta.hero_media, reference_map)

        html_text = _render_document_html(document, body_html, hero_html)
        destination = output_root / document.slug / "index.html"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(html_text, encoding="utf-8")
        written.append(destination)

    return written


def _build_reference_map(document: ContentDocument) -> dict[str, MediaReference]:
    mapping: dict[str, MediaReference] = {}
    if document.meta.hero_media:
        mapping[document.meta.hero_media.path] = document.meta.hero_media
    for reference in document.assets:
        mapping[reference.path] = reference
    return mapping


def _render_body(body: str, references: dict[str, MediaReference]) -> str:
    if not body:
        return ""

    def replace(match: re.Match[str]) -> str:
        label, media_type, target = match.groups()
        target = target.strip()
        figure_html = _render_media_shortcode(label.strip(), media_type.lower(), target, references)
        return f"\n\n{figure_html}\n\n"

    processed = MEDIA_SHORTCODE_RE.sub(replace, body)
    return _markdown_to_html(processed)


def _render_media_shortcode(
    label: str, media_type: str, target: str, references: dict[str, MediaReference]
) -> str:
    reference = references.get(target)
    if reference is None:
        logger.warning("Article media shortcode references missing asset '%s'.", target)
        safe_label = html.escape(label)
        safe_target = html.escape(target)
        return f'<p><em>Missing media: {safe_label} ({safe_target})</em></p>'

    url = _select_media_url(reference, media_type)
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


def _select_media_url(reference: MediaReference, media_type: str) -> str:
    variant = _select_variant(reference, media_type)
    if variant:
        return f"/media/derived/{variant.path.lstrip('/')}"
    return f"/media/derived/{reference.path.lstrip('/')}"


def _select_variant(reference: MediaReference, media_type: str) -> MediaVariant | None:
    if not reference.variants:
        return None

    if media_type in {"img", "image"}:
        preferred = ("large", "thumb", "original")
    else:
        preferred = ("original",)

    for profile in preferred:
        for variant in reference.variants:
            if variant.profile == profile:
                return variant
    return reference.variants[0]


def _render_hero(hero: MediaReference | None, references: dict[str, MediaReference]) -> str:
    if not hero:
        return ""
    url = _select_media_url(hero, "image")
    alt_text = html.escape(hero.alt_text or hero.title or "")
    return (
        '<figure class="article-hero">'
        f'<img src="{url}" alt="{alt_text}" loading="lazy" />'
        "</figure>"
    )


def _render_document_html(
    document: ContentDocument, body_html: str, hero_html: str
) -> str:
    meta = document.meta
    date_str = _format_datetime(meta.published_at) or _format_datetime(meta.updated_at)
    summary_html = f"<p>{html.escape(meta.summary)}</p>" if meta.summary else ""
    word_count = _count_words(document.body)
    reading_time = _reading_time(word_count)

    tag_markup = "".join(
        f'<li><span class="pill pill--light">#{html.escape(tag)}</span></li>'
        for tag in meta.tags
    )

    date_markup = f"<span>{date_str}</span>" if date_str else ""
    reading_markup = f"<span>{reading_time} min read</span>" if reading_time else ""
    tags_markup = f'<ul class="article-card__tags">{tag_markup}</ul>' if tag_markup else ""

    template = f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{html.escape(meta.title)} - {html.escape(meta.slug)}</title>
    <link rel="stylesheet" href="/styles/tokens.css" />
    <link rel="stylesheet" href="/styles/base.css" />
    <link rel="stylesheet" href="/styles/layout.css" />
    <link rel="stylesheet" href="/styles/typography.css" />
    <link rel="stylesheet" href="/styles/components.css" />
  </head>
  <body>
    <a class="skip-link" href="#article">Skip to article</a>
    <div class="article-shell">
      <header class="article-header">
        <nav class="article-nav">
          <a class="article-nav__back" href="/">Back to Home</a>
        </nav>
      </header>
      <main id="article" class="article-content">
        <article class="article-card">
          <header class="article-card__header">
            <h1>{html.escape(meta.title)}</h1>
            {summary_html}
            <div class="article-card__meta">
              {date_markup}
              {reading_markup}
            </div>
            {tags_markup}
          </header>
          {hero_html}
          <div class="article-card__body">
            {body_html}
          </div>
        </article>
      </main>
      <footer class="article-footer">
        <a href="/">Copyright (c) {datetime.today().year} SmileCMS - Return home</a>
      </footer>
    </div>
  </body>
</html>
"""
    return template


def _format_datetime(value: datetime | None) -> str | None:
    if not value:
        return None
    try:
        return value.strftime("%b %d, %Y")
    except Exception:
        logger.warning("Unable to format datetime value %r", value)
        return None


def _count_words(body: str) -> int:
    plain = _extract_plain_text(body)
    return len(plain.split()) if plain else 0


def _extract_plain_text(body: str) -> str:
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


def _reading_time(word_count: int) -> int | None:
    if word_count <= 0:
        return None
    return max(1, round(word_count / 200))


def _markdown_to_html(text: str) -> str:
    lines = text.splitlines()
    html_parts: list[str] = []
    in_list = False
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if paragraph_lines:
            combined = " ".join(paragraph_lines).strip()
            if combined:
                html_parts.append(f"<p>{html.escape(combined)}</p>")
            paragraph_lines = []

    for raw_line in lines:
        stripped = raw_line.strip()

        if not stripped:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            flush_paragraph()
            continue

        if stripped.startswith("<figure"):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            flush_paragraph()
            html_parts.append(stripped)
            continue

        if stripped.startswith("### "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            flush_paragraph()
            html_parts.append(f"<h3>{html.escape(stripped[4:].strip())}</h3>")
            continue

        if stripped.startswith("## "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            flush_paragraph()
            html_parts.append(f"<h2>{html.escape(stripped[3:].strip())}</h2>")
            continue

        if stripped.startswith("# "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            flush_paragraph()
            html_parts.append(f"<h1>{html.escape(stripped[2:].strip())}</h1>")
            continue

        if stripped.startswith("- ") or stripped.startswith("* "):
            flush_paragraph()
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            item_content = html.escape(stripped[2:].strip())
            html_parts.append(f"<li>{item_content}</li>")
            continue

        if in_list:
            html_parts.append("</ul>")
            in_list = False

        paragraph_lines.append(stripped)

    if in_list:
        html_parts.append("</ul>")
    flush_paragraph()

    return "\n".join(html_parts)
