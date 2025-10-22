"""Render shared site pages (gallery, music, and static error responses)."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from textwrap import dedent, indent
from typing import Iterable, Sequence

from .articles import DEFAULT_SITE_NAME, SiteChromeRenderer
from .config import Config
from .templates import TemplateAssets
from .themes import ThemeLoader


@dataclass(frozen=True, slots=True)
class ErrorPageAction:
    """Link surfaced on an error page to help visitors recover."""

    label: str
    href: str


@dataclass(frozen=True, slots=True)
class ErrorPageDefinition:
    """Structured metadata describing a rendered error page."""

    code: int
    title: str
    message: str
    description: str | None = None
    suggestions: Sequence[str] = ()
    actions: Sequence[ErrorPageAction] = ()
    filename: str | None = None

    def output_filename(self) -> str:
        """Generate the filename used for the rendered error page."""
        if self.filename:
            return self.filename
        return f"{self.code}.html"


DEFAULT_ERROR_PAGES: tuple[ErrorPageDefinition, ...] = (
    ErrorPageDefinition(
        code=403,
        title="Forbidden",
        message="You don't have permission to access this page.",
        suggestions=(
            "Make sure you're signed in with the right account if access is restricted.",
            "Return to the home page and try navigating from there.",
        ),
    ),
    ErrorPageDefinition(
        code=404,
        title="Page Not Found",
        message="We couldn't find the page you were looking for.",
        suggestions=(
            "Check the URL for typos or outdated links.",
            "Head back to the home page to browse the latest content.",
        ),
    ),
    ErrorPageDefinition(
        code=500,
        title="Something Went Wrong",
        message="An unexpected error occurred while processing your request.",
        suggestions=(
            "Refresh the page to try again.",
            "If the problem continues, let us know so we can investigate.",
        ),
    ),
    ErrorPageDefinition(
        code=503,
        title="Temporarily Unavailable",
        message="We're performing maintenance right now. Please check back soon.",
        suggestions=(
            "Try reloading after a few minutes.",
            "Follow our social channels for real-time updates.",
        ),
    ),
)


ERROR_PAGE_STYLE = dedent(
    """
    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 2.5rem 1.5rem;
      background: linear-gradient(135deg, #0f172a, #1e293b);
      color: #0b1120;
      font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
    }

    .error-container {
      width: min(42rem, 100%);
    }

    .error-card {
      background: rgba(255, 255, 255, 0.96);
      border-radius: 18px;
      padding: clamp(2rem, 5vw, 3rem);
      box-shadow: 0 30px 60px rgba(15, 23, 42, 0.25);
      display: grid;
      gap: 1.25rem;
      text-align: center;
    }

    .error-code {
      font-size: clamp(3rem, 12vw, 6rem);
      font-weight: 700;
      letter-spacing: 0.08em;
      margin: 0;
      color: #1d4ed8;
    }

    .error-message,
    .error-description {
      margin: 0;
      color: rgba(15, 17, 32, 0.82);
    }

    .error-suggestions {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 0.5rem;
      text-align: left;
      color: rgba(15, 17, 32, 0.78);
    }

    .error-suggestions li {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 0.75rem;
      align-items: flex-start;
    }

    .error-suggestions li::before {
      content: "•";
      color: #1d4ed8;
      font-weight: 700;
      font-size: 1rem;
      line-height: 1.5;
    }

    .error-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      justify-content: center;
    }

    .error-link {
      display: inline-block;
      padding: 0.75rem 1.5rem;
      border-radius: 999px;
      text-decoration: none;
      font-weight: 600;
      color: #0b1120;
      background: #bfdbfe;
      transition: transform 0.18s ease, box-shadow 0.18s ease;
      box-shadow: 0 12px 24px rgba(59, 130, 246, 0.25);
    }

    .error-link:hover,
    .error-link:focus-visible {
      transform: translateY(-2px);
      box-shadow: 0 18px 36px rgba(59, 130, 246, 0.35);
      outline: none;
    }

    @media (prefers-color-scheme: dark) {
      body {
        background: radial-gradient(circle at top, #1e3a8a, #020617);
        color: #e2e8f0;
      }

      .error-card {
        background: rgba(15, 23, 42, 0.9);
        color: #e2e8f0;
      }

      .error-message,
      .error-description,
      .error-suggestions {
        color: rgba(226, 232, 240, 0.86);
      }

      .error-link {
        color: #0b1120;
        background: #60a5fa;
      }
    }

    @media (max-width: 640px) {
      body {
        padding: 2rem 1rem;
      }

      .error-card {
        padding: clamp(1.75rem, 7vw, 2.25rem);
      }

      .error-suggestions li {
        grid-template-columns: auto 1fr;
      }
    }
    """
).strip()


def write_gallery_page(config: Config, assets: TemplateAssets | None = None) -> Path:
    """Render the gallery index page into the site output directory."""
    resources = assets or TemplateAssets(config)
    renderer = _GalleryPageRenderer(resources)
    html = renderer.render()
    destination = config.output_dir / "gallery" / "index.html"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html, encoding="utf-8")
    return destination


def write_music_page(config: Config, assets: TemplateAssets | None = None) -> Path:
    """Render the music catalog page into the site output directory."""
    resources = assets or TemplateAssets(config)
    renderer = _MusicPageRenderer(resources)
    html = renderer.render()
    destination = config.output_dir / "music" / "index.html"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html, encoding="utf-8")
    return destination


def write_error_pages(
    config: Config,
    assets: TemplateAssets | None = None,
    *,
    definitions: Sequence[ErrorPageDefinition] | None = None,
) -> list[Path]:
    """Render lightweight, self-contained error pages into the site output directory."""
    resources = assets or TemplateAssets(config)
    renderer = _PlainErrorPageRenderer(resources)
    specs = tuple(definitions) if definitions is not None else DEFAULT_ERROR_PAGES

    written: list[Path] = []
    for definition in specs:
        filename = Path(definition.output_filename())
        if filename.is_absolute() or ".." in filename.parts:
            msg = f"Error page filename '{filename}' must be relative to the site root."
            raise ValueError(msg)
        html = renderer.render(definition)
        destination = config.output_dir / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(html, encoding="utf-8")
        written.append(destination)
    return written


class _BasePageRenderer:
    """Common helpers shared by static page renderers."""

    def __init__(self, assets: TemplateAssets) -> None:
        self._assets = assets
        self._chrome = SiteChromeRenderer(assets.site_config)

    @property
    def theme(self) -> ThemeLoader:
        return self._assets.theme

    def _relative_prefix(self, depth: int) -> str:
        return "./" if depth == 0 else "../" * depth

    def _base_context(
        self,
        *,
        depth: int,
        current_path: str,
        page_title: str,
        page_slug: str,
        body_class: str,
        styles: Iterable[str],
        scripts: Iterable[dict[str, str]],
    ) -> dict[str, object]:
        site_identity = self._chrome.site_identity(DEFAULT_SITE_NAME)
        navigation = self._chrome.navigation(current_path=current_path)
        footer = self._chrome.footer()
        shell_attributes = self._assets.build_shell_attributes(depth=depth)

        return {
            "site": site_identity,
            "navigation": navigation,
            "footer": footer,
            "shell": {
                "theme": self.theme.manifest.default_shell_theme,
                "data_attributes": shell_attributes,
            },
            "page": {
                "title": page_title,
                "slug": page_slug,
                "body_class": body_class,
                "styles": list(styles),
                "scripts": list(scripts),
                "relative_root": self._relative_prefix(depth),
            },
            "assets": self._assets.build_theme_assets(depth=depth),
            "feeds": self._assets.feed_links,
        }


class _GalleryPageRenderer(_BasePageRenderer):
    """Render the gallery landing page."""

    def render(self) -> str:
        depth = 1  # gallery/index.html
        styles = [self._assets.make_asset_href("styles/gallery.css", depth=depth)]
        scripts = [
            {
                "src": self._assets.make_asset_href("js/gallery.js", depth=depth),
                "type": "module",
            }
        ]
        context = self._base_context(
            depth=depth,
            current_path="/gallery/",
            page_title=f"{self._chrome.site_identity(DEFAULT_SITE_NAME)['title']} Gallery",
            page_slug="gallery",
            body_class="gallery-page",
            styles=styles,
            scripts=scripts,
        )
        context["gallery"] = {
            "loading_message": "Loading gallery collections...",
        }
        return str(self.theme.render_page("gallery", context))


class _MusicPageRenderer(_BasePageRenderer):
    """Render the music landing page."""

    def render(self) -> str:
        depth = 1  # music/index.html
        styles = [self._assets.make_asset_href("styles/music.css", depth=depth)]
        scripts = [
            {
                "src": self._assets.make_asset_href("js/music.js", depth=depth),
                "type": "module",
            }
        ]
        context = self._base_context(
            depth=depth,
            current_path="/music/",
            page_title=f"{self._chrome.site_identity(DEFAULT_SITE_NAME)['title']} Music",
            page_slug="music",
            body_class="music-page",
            styles=styles,
            scripts=scripts,
        )
        context["music"] = {
            "loading_message": "Loading music catalog...",
        }
        return str(self.theme.render_page("music", context))


class _PlainErrorPageRenderer:
    """Render a self-contained HTML document for an error response."""

    def __init__(self, assets: TemplateAssets) -> None:
        self._assets = assets

    def render(self, definition: ErrorPageDefinition) -> str:
        site_title = self._site_title()
        page_title = f"{definition.code} {definition.title} | {site_title}"
        actions = self._ensure_home_link(list(definition.actions))
        css_block = indent(ERROR_PAGE_STYLE, "    ")

        lines: list[str] = [
            "<!DOCTYPE html>",
            '<html lang="en">',
            "  <head>",
            '    <meta charset="utf-8" />',
            '    <meta name="viewport" content="width=device-width, initial-scale=1" />',
            f"    <title>{escape(page_title)}</title>",
            "    <style>",
        ]
        lines.extend(css_block.splitlines())
        lines.append("    </style>")
        lines.append("  </head>")
        lines.append("  <body>")
        lines.append('    <main class="error-container" role="main">')
        lines.append('      <article class="error-card" aria-labelledby="error-title">')
        lines.append(f'        <p class="error-code" aria-hidden="true">{definition.code}</p>')
        lines.append(f'        <h1 id="error-title">{escape(definition.title)}</h1>')
        lines.append(f'        <p class="error-message">{escape(definition.message)}</p>')

        if definition.description:
            lines.append(f'        <p class="error-description">{escape(definition.description)}</p>')

        if definition.suggestions:
            lines.append('        <ul class="error-suggestions">')
            for suggestion in definition.suggestions:
                lines.append(f'          <li>{escape(suggestion)}</li>')
            lines.append("        </ul>")

        if actions:
            lines.append('        <nav class="error-actions" aria-label="Helpful links">')
            for action in actions:
                label = escape(action.label)
                href = escape(action.href, quote=True)
                lines.append(f'          <a class="error-link" href="{href}">{label}</a>')
            lines.append("        </nav>")

        lines.append("      </article>")
        lines.append("    </main>")
        lines.append("  </body>")
        lines.append("</html>")
        return "\n".join(lines) + "\n"

    def _site_title(self) -> str:
        site_meta = self._assets.site_config.get("site")
        if isinstance(site_meta, dict):
            raw_title = site_meta.get("title")
            if isinstance(raw_title, str) and raw_title.strip():
                return raw_title.strip()
        return DEFAULT_SITE_NAME

    @staticmethod
    def _ensure_home_link(actions: list[ErrorPageAction]) -> list[ErrorPageAction]:
        if not actions:
            return [ErrorPageAction(label="Return Home", href="/")]
        if not any(_PlainErrorPageRenderer._is_home_link(action.href) for action in actions):
            actions.insert(0, ErrorPageAction(label="Return Home", href="/"))
        return actions

    @staticmethod
    def _is_home_link(href: str) -> bool:
        normalized = href.strip()
        if not normalized:
            return True
        normalized = normalized.lower()
        return normalized in {"/", "./", "index.html", "./index.html"}
