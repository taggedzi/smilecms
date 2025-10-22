"""Shared template utilities used to render site pages with Jinja2."""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
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
                    return self._apply_feature_toggles(data)
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
        endpoints: dict[str, Any] = {
            "site_config": "config/site.json",
            "manifest_bases": "manifests/content",
        }
        if self.config.gallery.enabled:
            endpoints["gallery"] = {
                "collections": "data/gallery/collections.json",
                "manifest": "data/gallery/manifest.json",
                "images": "data/gallery/images.jsonl",
            }
        if self.config.music.enabled:
            endpoints["music"] = {
                "tracks": "data/music/tracks.jsonl",
                "manifest": "data/music/manifest.json",
                "summary": "data/music/tracks.json",
            }
        return endpoints

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

    def _apply_feature_toggles(self, site_config: dict[str, Any]) -> dict[str, Any]:
        """Prune site configuration elements when features are disabled."""
        sanitized = deepcopy(site_config)
        if not self.config.gallery.enabled:
            self._prune_feature_config(
                sanitized,
                target_slug="gallery",
                section_types=("gallery",),
                section_ids=("gallery",),
            )
        if not self.config.music.enabled:
            self._prune_feature_config(
                sanitized,
                target_slug="music",
                section_types=("audio",),
                section_ids=("audio", "music"),
            )
        return sanitized

    def _prune_feature_config(
        self,
        site_config: dict[str, Any],
        *,
        target_slug: str,
        section_types: tuple[str, ...],
        section_ids: tuple[str, ...],
    ) -> None:
        """Remove navigation, hero actions, and sections tied to a disabled feature."""
        target_href = self._normalize_internal_href(target_slug)

        def _targets_feature(entry: Any) -> bool:
            if not isinstance(entry, dict):
                return False
            raw_href = str(entry.get("href") or "").strip()
            if not raw_href:
                return False
            if "://" in raw_href or raw_href.startswith(("mailto:", "#")):
                return False
            normalized = self._normalize_internal_href(raw_href)
            return normalized == target_href

        navigation = site_config.get("navigation")
        if isinstance(navigation, list):
            site_config["navigation"] = [entry for entry in navigation if not _targets_feature(entry)]

        hero = site_config.get("hero")
        if isinstance(hero, dict):
            actions = hero.get("actions")
            if isinstance(actions, list):
                hero["actions"] = [entry for entry in actions if not _targets_feature(entry)]

        sections = site_config.get("sections")
        if isinstance(sections, list):
            pruned_sections: list[Any] = []
            for section in sections:
                if not isinstance(section, dict):
                    pruned_sections.append(section)
                    continue
                section_type = str(section.get("type") or "").strip().lower()
                section_id = str(section.get("id") or "").strip().lower()
                if section_type in section_types or section_id in section_ids:
                    continue
                actions = section.get("actions")
                if isinstance(actions, list):
                    section["actions"] = [entry for entry in actions if not _targets_feature(entry)]
                pruned_sections.append(section)
            site_config["sections"] = pruned_sections

    @staticmethod
    def _normalize_internal_href(value: str) -> str:
        """Normalize relative hrefs for feature matching."""
        text = value.strip()
        if not text:
            return "/"
        if "://" in text or text.startswith(("mailto:", "#")):
            return text
        normalized = text
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        if not normalized.endswith("/"):
            normalized = f"{normalized}/"
        return normalized

    def make_asset_href(self, path: str, *, depth: int) -> str:
        """Return a relative href/src for assets located under the site root."""
        if path.startswith(("http://", "https://", "//")):
            return path
        normalized = path.lstrip("/")
        prefix = "./" if depth == 0 else "../" * depth
        return f"{prefix}{normalized}"

    def build_theme_assets(self, *, depth: int) -> dict[str, Any]:
        """Resolve theme asset paths relative to the rendered page depth."""
        bundle = self.theme.assets.to_template_dict()
        styles: list[str] = []
        for href in bundle.get("styles", []):
            styles.append(self.make_asset_href(href, depth=depth))

        scripts: list[dict[str, Any]] = []
        for script in bundle.get("scripts", []):
            src = script.get("src", "")
            normalized = dict(script)
            normalized["src"] = self.make_asset_href(src, depth=depth) if src else src
            scripts.append(normalized)

        return {
            "styles": styles,
            "scripts": scripts,
        }

    def write_site_config(self, destination: Path | None = None) -> Path:
        """Persist the sanitized site configuration for runtime hydration."""
        target = destination or (self.config.output_dir / "config" / "site.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(self.site_config, indent=2)
        target.write_text(serialized, encoding="utf-8")
        return target
