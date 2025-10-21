"""Theme loading and rendering utilities for SmileCMS."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterable, Sequence

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape
from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "theme.json"
DEFAULT_THEME_NAME = "default"


class ThemeError(RuntimeError):
    """Raised when a theme cannot be loaded or validated."""


class ScriptAsset(BaseModel):
    """Script asset definition that can be injected into templates."""

    model_config = ConfigDict(populate_by_name=True)

    src: str = Field(...)
    type: str | None = Field(default=None)
    defer: bool = Field(default=False)
    async_: bool = Field(default=False, alias="async")
    integrity: str | None = Field(default=None)
    crossorigin: str | None = Field(default=None)

    def to_template_dict(self) -> dict[str, Any]:
        return {
            "src": self.src,
            "type": self.type,
            "defer": self.defer,
            "async": self.async_,
            "integrity": self.integrity,
            "crossorigin": self.crossorigin,
        }


class ThemeAssets(BaseModel):
    """Static assets associated with a theme."""

    styles: list[str] = Field(default_factory=list)
    scripts: list[ScriptAsset] = Field(default_factory=list)

    def merge_with(self, fallback: "ThemeAssets | None") -> "ThemeAssets":
        if fallback is None:
            return ThemeAssets(styles=list(self.styles), scripts=list(self.scripts))
        styles = list(self.styles) if self.styles else list(fallback.styles)
        scripts = list(self.scripts) if self.scripts else list(fallback.scripts)
        return ThemeAssets(styles=styles, scripts=scripts)

    def to_template_dict(self) -> dict[str, Any]:
        return {
            "styles": list(self.styles),
            "scripts": [script.to_template_dict() for script in self.scripts],
        }


class ThemeManifest(BaseModel):
    """Structured representation of the theme.json manifest."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(default="Unnamed Theme")
    version: str | None = Field(default=None)
    entrypoints: dict[str, str] = Field(default_factory=dict)
    partials: dict[str, str] = Field(default_factory=dict)
    assets: ThemeAssets = Field(default_factory=ThemeAssets)
    default_shell_theme: str = Field(default="dark")

    def merge_with(self, fallback: "ThemeManifest | None") -> "ThemeManifest":
        if fallback is None:
            return self
        data = {
            "name": self.name or fallback.name,
            "version": self.version or fallback.version,
            "entrypoints": {**fallback.entrypoints, **self.entrypoints},
            "partials": {**fallback.partials, **self.partials},
            "assets": self.assets.merge_with(fallback.assets),
            "default_shell_theme": self.default_shell_theme or fallback.default_shell_theme,
        }
        return ThemeManifest(**data)

    def to_template_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "entrypoints": dict(self.entrypoints),
            "partials": dict(self.partials),
            "default_shell_theme": self.default_shell_theme,
        }


class ThemeLoader:
    """Load theme manifests and associated Jinja environments."""

    def __init__(
        self,
        *,
        themes_root: Path,
        active_theme: str = DEFAULT_THEME_NAME,
        fallback_theme: str = DEFAULT_THEME_NAME,
    ) -> None:
        self._themes_root = themes_root
        self._active_theme = active_theme or DEFAULT_THEME_NAME
        self._fallback_theme = fallback_theme or DEFAULT_THEME_NAME
        self._environment: Environment | None = None
        self._manifest: ThemeManifest | None = None
        self._load()

    @property
    def manifest(self) -> ThemeManifest:
        assert self._manifest is not None  # pragma: no cover - construction guarantees
        return self._manifest

    @property
    def assets(self) -> ThemeAssets:
        return self.manifest.assets

    @property
    def environment(self) -> Environment:
        assert self._environment is not None  # pragma: no cover - construction guarantees
        return self._environment

    @property
    def themes_root(self) -> Path:
        return self._themes_root

    @property
    def active_theme(self) -> str:
        return self._active_theme

    def render_page(self, key: str, context: dict[str, Any]) -> str:
        template_path = self.manifest.entrypoints.get(key)
        if not template_path:
            raise ThemeError(f"Theme '{self._active_theme}' does not define an entrypoint named '{key}'.")
        template = self.environment.get_template(template_path)
        rendered = template.render(**context)
        if not isinstance(rendered, str):  # pragma: no cover - defensive typing check
            raise ThemeError(
                f"Template '{template_path}' for theme '{self._active_theme}' rendered non-string output."
            )
        return rendered

    def ensure_templates(self, template_keys: Sequence[str]) -> None:
        for key in template_keys:
            if not key:
                continue
            template_path = self.manifest.entrypoints.get(key, key)
            try:
                self.environment.get_template(template_path)
            except TemplateNotFound as exc:
                raise ThemeError(
                    f"Required template '{template_path}' not found while loading theme '{self._active_theme}'."
                ) from exc

    def _load(self) -> None:
        themes_root = self._themes_root
        if not themes_root.exists():
            raise ThemeError(f"Themes root '{themes_root}' does not exist.")

        fallback_manifest = self._load_manifest(self._fallback_theme)
        active_manifest = (
            fallback_manifest if self._active_theme == self._fallback_theme else self._load_manifest(self._active_theme)
        )

        if active_manifest is None and fallback_manifest is None:
            raise ThemeError(
                f"Neither active theme '{self._active_theme}' nor fallback '{self._fallback_theme}' could be loaded."
            )

        merged_manifest: ThemeManifest
        if active_manifest is None:
            logger.warning(
                "Active theme '%s' not available. Falling back to '%s'.",
                self._active_theme,
                self._fallback_theme,
            )
            assert fallback_manifest is not None
            merged_manifest = fallback_manifest
            search_paths = [self._theme_dir(self._fallback_theme)]
        else:
            merged_manifest = active_manifest.merge_with(
                fallback_manifest if fallback_manifest is not active_manifest else None
            )
            search_paths = [self._theme_dir(self._active_theme)]
            if (
                fallback_manifest is not None
                and self._fallback_theme != self._active_theme
                and self._theme_dir(self._fallback_theme) not in search_paths
            ):
                search_paths.append(self._theme_dir(self._fallback_theme))

        existing_paths = [path for path in search_paths if path.exists()]
        if not existing_paths:
            raise ThemeError(
                f"No template directories could be resolved for theme '{self._active_theme}' "
                f"(fallback '{self._fallback_theme}')."
            )

        loader = FileSystemLoader([str(path) for path in existing_paths])
        environment = Environment(
            loader=loader,
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        environment.globals["theme"] = merged_manifest.to_template_dict()

        self._environment = environment
        self._manifest = merged_manifest

        required_templates = [
            template
            for template in (
                merged_manifest.entrypoints.get("base"),
                merged_manifest.entrypoints.get("article"),
            )
            if template
        ]
        self.ensure_templates(required_templates)

    def _load_manifest(self, theme_name: str) -> ThemeManifest | None:
        theme_dir = self._theme_dir(theme_name)
        manifest_path = theme_dir / MANIFEST_FILENAME
        if not manifest_path.exists():
            logger.debug("Theme manifest not found at %s", manifest_path)
            return None
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ThemeError(f"Failed to load theme manifest at {manifest_path}: {exc}") from exc
        try:
            return ThemeManifest.model_validate(data)
        except ValidationError as exc:
            raise ThemeError(f"Theme manifest validation failed for {manifest_path}: {exc}") from exc

    def _theme_dir(self, theme_name: str) -> Path:
        return self._themes_root / theme_name


def build_theme_loader(
    *,
    themes_root: Path,
    active_theme: str = DEFAULT_THEME_NAME,
    fallback_theme: str = DEFAULT_THEME_NAME,
) -> ThemeLoader:
    """Construct a ThemeLoader with helpful error reporting."""
    try:
        return ThemeLoader(
            themes_root=themes_root,
            active_theme=active_theme,
            fallback_theme=fallback_theme,
        )
    except ThemeError:
        raise
    except Exception as exc:  # pragma: no cover - defensive logging
        raise ThemeError(f"Unexpected error loading theme '{active_theme}': {exc}") from exc
