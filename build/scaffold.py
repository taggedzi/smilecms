"""Utilities for scaffolding new SmileCMS content."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Literal

from .config import Config
from .gallery.utils import slugify, title_from_stem


class ScaffoldError(RuntimeError):
    """Raised when scaffolding cannot continue."""


@dataclass(slots=True)
class ScaffoldResult:
    """Details about filesystem writes performed during scaffolding."""

    created: list[Path] = field(default_factory=list)
    updated: list[Path] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def record(self, path: Path, existed: bool) -> None:
        if existed:
            self.updated.append(path)
        else:
            self.created.append(path)


ContentKind = Literal["post", "gallery", "track"]


def normalize_slug(raw: str) -> str:
    """Convert arbitrary user input into a filesystem-safe slug."""
    slug = slugify(raw)
    if not slug or slug == "item":
        raise ScaffoldError("Unable to derive a valid slug. Provide letters, numbers, or hyphens.")
    return slug


def default_title(slug: str) -> str:
    """Generate a human-friendly title from a slug."""
    return title_from_stem(slug)


def scaffold_content(
    config: Config,
    kind: ContentKind,
    slug: str,
    title: str | None = None,
    *,
    force: bool = False,
) -> ScaffoldResult:
    """Create the on-disk structure for a new post, gallery, or track."""
    slug = normalize_slug(slug)
    title = title.strip() if title else ""
    if not title:
        title = default_title(slug)

    if kind == "post":
        return _scaffold_post(config, slug, title, force=force)
    if kind == "gallery":
        return _scaffold_gallery(config, slug, title, force=force)
    if kind == "track":
        return _scaffold_track(config, slug, title, force=force)
    raise ScaffoldError(f"Unsupported content type: {kind}")


def _scaffold_post(config: Config, slug: str, title: str, *, force: bool) -> ScaffoldResult:
    posts_dir = config.content_dir / "posts"
    posts_dir.mkdir(parents=True, exist_ok=True)
    post_path = posts_dir / f"{slug}.md"

    existed = _write_text(post_path, _render_post_front_matter(slug, title), force=force)

    result = ScaffoldResult()
    result.record(post_path, existed)
    asset_dir = config.article_media_dir / slug
    asset_dir.mkdir(parents=True, exist_ok=True)
    keep_path = asset_dir / ".gitkeep"
    if not keep_path.exists():
        keep_path.write_text("", encoding="utf-8")
        result.created.append(keep_path)
    result.notes.append(
        "Add article assets under "
        f"{(config.article_media_dir / slug).as_posix()} and reference them via 'media/<file>'."
    )
    return result


def _scaffold_gallery(config: Config, slug: str, title: str, *, force: bool) -> ScaffoldResult:
    collections_root = config.gallery.source_dir
    collection_dir = collections_root / slug
    collection_dir.mkdir(parents=True, exist_ok=True)

    meta_path = collection_dir / config.gallery.metadata_filename
    payload = _gallery_payload(slug, title)
    existed = _write_json(meta_path, payload, force=force)

    result = ScaffoldResult()
    result.record(meta_path, existed)

    keep_path = collection_dir / ".gitkeep"
    if not keep_path.exists():
        keep_path.write_text("", encoding="utf-8")
        result.created.append(keep_path)

    result.notes.append(
        "Drop raw images alongside generated sidecars in this directory; rerun 'smilecms build' to refresh metadata."
    )
    return result


def _scaffold_track(config: Config, slug: str, title: str, *, force: bool) -> ScaffoldResult:
    music_root = config.music.source_dir
    track_dir = music_root / slug
    track_dir.mkdir(parents=True, exist_ok=True)

    meta_path = track_dir / config.music.metadata_filename
    meta_text = _render_track_metadata(slug, title)
    meta_existed = _write_text(meta_path, meta_text, force=force)

    lyrics_path = track_dir / "lyrics.md"
    lyrics_text = f"# {title}\n\nWrite lyrics here or remove this file if instrumental.\n"
    lyrics_written = False
    if not lyrics_path.exists():
        _write_text(lyrics_path, lyrics_text, force=force)
        lyrics_written = True

    result = ScaffoldResult()
    result.record(meta_path, meta_existed)
    if lyrics_written:
        result.record(lyrics_path, False)
    result.notes.append(
        "Add the primary audio file and supporting media to this folder before running 'smilecms build'."
    )
    return result


def _render_post_front_matter(slug: str, title: str) -> str:
    timestamp = _timestamp()
    return (
        f"---\n"
        f'title: "{title}"\n'
        f"slug: {slug}\n"
        f"status: published\n"
        f"published_at: {timestamp}\n"
        f"updated_at: {timestamp}\n"
        f"tags: []\n"
        f"hero_media:\n"
        f'  path: "media/hero-image.jpg"\n'
        f'  alt_text: "Describe the hero image for accessibility"\n'
        f"assets:\n"
        f'  - path: "media/inline-still.jpg"\n'
        f'    alt_text: "Caption text"\n'
        f"---\n"
        f"Markdown body starts here.\n"
    )


def _gallery_payload(slug: str, title: str) -> dict[str, object]:
    timestamp = _timestamp()
    return {
        "version": 1,
        "id": slug,
        "title": title,
        "summary": None,
        "description": None,
        "tags": [],
        "sort_order": 0,
        "created_at": timestamp,
        "updated_at": timestamp,
        "cover_image_id": None,
        "hero_image_id": None,
        "options": {},
    }


def _render_track_metadata(slug: str, title: str) -> str:
    timestamp = _timestamp()
    return (
        f'title: "{title}"\n'
        f'summary: ""\n'
        f"description: |\n"
        f"  Long-form description (Markdown allowed) for {title}.\n"
        f"tags: []\n"
        f"status: published\n"
        f"published_at: {timestamp}\n"
        f"duration: 0\n"
        f"audio: {slug}.mp3\n"
        f"download: true\n"
        f"audio_meta:\n"
        f"  mime_type: audio/mpeg\n"
        f"assets:\n"
        f"  cover.png:\n"
        f'    alt_text: "Describe the cover art."\n'
    )


def _timestamp() -> str:
    moment = datetime.now(timezone.utc).replace(microsecond=0)
    return moment.isoformat().replace("+00:00", "Z")


def _write_text(path: Path, content: str, *, force: bool) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists()
    if existed and not force:
        raise ScaffoldError(f"Path already exists: {path}")
    path.write_text(content, encoding="utf-8")
    return existed


def _write_json(path: Path, payload: dict[str, object], *, force: bool) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists()
    if existed and not force:
        raise ScaffoldError(f"Path already exists: {path}")
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return existed
