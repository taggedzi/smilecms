"""Parse source files into `ContentDocument` instances."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .models import ContentDocument, ContentMeta, MediaReference


class FrontMatterError(ValueError):
    """Raised when a markdown file has malformed front matter."""


def load_markdown_document(path: str | Path) -> ContentDocument:
    """Load a markdown file with YAML front matter into a content document."""
    source_path = Path(path)
    text = source_path.read_text(encoding="utf-8")
    front_matter, body = _split_front_matter(text)

    try:
        meta, assets = _parse_meta(front_matter, source_path)
    except ValidationError as exc:
        raise FrontMatterError(f"Invalid metadata in {source_path}") from exc

    return ContentDocument(
        meta=meta,
        body=body.strip(),
        source_path=str(source_path),
        assets=assets,
    )


def _split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    if not lines:
        return {}, ""
    if lines[0].strip() != "---":
        return {}, text

    front_lines: list[str] = []
    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            raw_front_matter = "\n".join(front_lines)
            body = "\n".join(lines[idx + 1 :])
            data = yaml.safe_load(raw_front_matter) or {}
            return data, body
        front_lines.append(line)
    raise FrontMatterError("Closing front matter delimiter '---' missing.")


def _parse_meta(data: dict[str, Any], source_path: Path) -> tuple[ContentMeta, list[MediaReference]]:
    data = dict(data)
    assets_data = data.pop("assets", []) or []

    hero_data = data.get("hero_media")
    if isinstance(hero_data, dict):
        data["hero_media"] = MediaReference(**hero_data)

    if "slug" not in data:
        data["slug"] = source_path.stem.replace(" ", "-").lower()

    meta = ContentMeta(**data)
    assets = [_ensure_media(entry, source_path) for entry in assets_data]
    return meta, assets


def _ensure_media(entry: Any, source_path: Path) -> MediaReference:
    if isinstance(entry, MediaReference):
        return entry
    if not isinstance(entry, dict):
        raise FrontMatterError(
            f"Media entry in {source_path} must be an object, got {type(entry)!r}"
        )
    return MediaReference(**entry)
