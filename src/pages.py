"""Render shared site pages (gallery, music) using Jinja templates."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .articles import DEFAULT_SITE_NAME, SiteChromeRenderer
from .config import Config
from .templates import TemplateAssets
from .themes import ThemeLoader


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
