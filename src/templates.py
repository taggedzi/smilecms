"""Shared template utilities used to render site pages with Jinja2."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict

from .config import Config
from .themes import DEFAULT_THEME_NAME, ThemeError, ThemeLoader, build_theme_loader

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TemplateAssets:
    """Load site configuration and theme resources for templated pages."""

    config: Config
    site_config: dict[str, Any]
    theme: ThemeLoader
    data_endpoints: dict[str, Any]
    feed_links: dict[str, str]

    def __init__(self, config: Config) -> None:
        self.config = config
        self.site_config = self._load_site_config()
        self.theme = self._load_theme()
        self.data_endpoints = self._build_data_endpoints()
        self.feed_links = self._build_feed_links()

    def _load_site_config(self) -> dict[str, Any]:
        config_path = self.config.templates_dir / "config" / "site.json"
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

    def _load_theme(self) -> ThemeLoader:
        try:
            return build_theme_loader(
                themes_root=self.config.themes_root,
                active_theme=self.config.theme_name,
                fallback_theme=DEFAULT_THEME_NAME,
            )
        except ThemeError as exc:
            raise ThemeError(f"Unable to load theme '{self.config.theme_name}': {exc}") from exc

    def _build_data_endpoints(self) -> dict[str, Any]:
        """Expose JSON endpoints consumed by client-side scripts."""
        return {
            "site_config": "config/site.json",
            "manifest_bases": "manifests/content",
            "gallery": {
                "collections": "data/gallery/collections.json",
                "manifest": "data/gallery/manifest.json",
                "images": "data/gallery/images.jsonl",
            },
            "music": {
                "tracks": "data/music/tracks.jsonl",
                "manifest": "data/music/manifest.json",
                "summary": "data/music/tracks.json",
            },
        }

    def _build_feed_links(self) -> dict[str, str]:
        return {
            "rss": "/feed.xml",
            "atom": "/atom.xml",
            "json": "/feed.json",
        }

    def make_source_value(self, path: str, *, depth: int) -> str:
        """Return a space-delimited string of relative + absolute sources."""
        normalized = path.lstrip("/")
        prefix = "./" if depth == 0 else "../" * depth
        relative = f"{prefix}{normalized}"
        absolute = f"/site/{normalized}"
        return f"{relative} {absolute}"

    def build_shell_attributes(self, *, depth: int) -> dict[str, str]:
        """Create data-* attribute values for the application shell."""
        attributes: dict[str, str] = {}
        attributes["site-config"] = self.make_source_value(self.data_endpoints["site_config"], depth=depth)
        attributes["manifest-bases"] = self.make_source_value(self.data_endpoints["manifest_bases"], depth=depth)

        gallery_endpoints: Dict[str, str] = self.data_endpoints.get("gallery", {})
        for key, value in gallery_endpoints.items():
            attributes[f"gallery-{key.replace('_', '-')}"] = self.make_source_value(value, depth=depth)

        music_endpoints: Dict[str, str] = self.data_endpoints.get("music", {})
        for key, value in music_endpoints.items():
            attributes[f"music-{key.replace('_', '-')}"] = self.make_source_value(value, depth=depth)

        return attributes

    def make_asset_href(self, path: str, *, depth: int) -> str:
        """Return a relative href/src for assets located under the site root."""
        normalized = path.lstrip("/")
        prefix = "./" if depth == 0 else "../" * depth
        return f"{prefix}{normalized}"
