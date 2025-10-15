"""Audit helpers for media assets."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Iterator, Tuple

from ..config import Config
from ..content import ContentDocument

# File types considered "assets" when scanning for stray files.
ASSET_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".tiff",
    ".bmp",
    ".svg",
    ".mp3",
    ".wav",
    ".aac",
    ".flac",
    ".ogg",
    ".m4a",
    ".mp4",
    ".mov",
    ".webm",
    ".mkv",
    ".avi",
}

# Metadata/sidecar suffixes that should not be treated as orphaned assets.
IGNORED_SUFFIXES = {
    ".json",
    ".jsonl",
    ".yml",
    ".yaml",
    ".md",
    ".txt",
}

# Common filenames to skip when scanning source directories.
IGNORED_FILENAMES = {
    "meta.yml",
    "meta.yaml",
    "collection.json",
}


@dataclass(slots=True)
class ReferenceUsage:
    """Tracks documents/roles that reference a media path."""

    documents: set[str] = field(default_factory=set)
    roles: set[str] = field(default_factory=set)
    expected_path: Path | None = None

    def add(self, slug: str, role: str | None) -> None:
        self.documents.add(slug)
        if role:
            self.roles.add(role)


@dataclass(slots=True)
class MediaAuditResult:
    """Summary of media audit findings."""

    references: dict[str, ReferenceUsage] = field(default_factory=dict)
    actual_files: dict[str, Path] = field(default_factory=dict)
    missing_references: dict[str, ReferenceUsage] = field(default_factory=dict)
    out_of_bounds_references: dict[str, ReferenceUsage] = field(default_factory=dict)
    orphan_files: dict[str, Path] = field(default_factory=dict)
    stray_files: dict[str, Path] = field(default_factory=dict)

    @property
    def total_references(self) -> int:
        return len(self.references)

    @property
    def total_assets(self) -> int:
        return len(self.actual_files)

    @property
    def valid_references(self) -> int:
        return self.total_references - len(self.missing_references) - len(self.out_of_bounds_references)


def audit_media(documents: Iterable[ContentDocument], config: Config) -> MediaAuditResult:
    """Analyze media assets and surface missing, orphaned, or mislocated files."""
    mounts: Dict[str, Path] = {prefix: base for prefix, base in config.media_mounts}
    references = _collect_reference_usage(documents)
    actual_files = _collect_actual_files(mounts)

    missing: dict[str, ReferenceUsage] = {}
    out_of_bounds: dict[str, ReferenceUsage] = {}

    for path, usage in references.items():
        prefix, remainder = _split_prefix(path)
        base_dir = mounts.get(prefix)
        if not base_dir or not remainder:
            out_of_bounds[path] = usage
            continue

        expected = base_dir / remainder
        usage.expected_path = expected
        if not expected.exists():
            missing[path] = usage

    valid_paths = {
        path for path in references if path not in missing and path not in out_of_bounds
    }
    orphan_files = {path: real for path, real in actual_files.items() if path not in valid_paths}
    stray_files = _find_stray_assets(config, mounts)

    return MediaAuditResult(
        references=references,
        actual_files=actual_files,
        missing_references=missing,
        out_of_bounds_references=out_of_bounds,
        orphan_files=orphan_files,
        stray_files=stray_files,
    )


def _collect_reference_usage(documents: Iterable[ContentDocument]) -> dict[str, ReferenceUsage]:
    usage: dict[str, ReferenceUsage] = {}
    for document in documents:
        for path, role in _iter_document_references(document):
            normalized = _normalize_media_path(path)
            if not normalized:
                continue
            record = usage.setdefault(normalized, ReferenceUsage())
            record.add(document.slug, role)
    return usage


def _iter_document_references(document: ContentDocument) -> Iterator[tuple[str, str | None]]:
    hero = document.meta.hero_media
    if hero and hero.path:
        yield hero.path, "hero"
    for reference in document.assets:
        if reference.path:
            yield reference.path, "asset"
    download_path = document.meta.download_path
    if download_path:
        yield download_path, "download"


def _normalize_media_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("/")


def _split_prefix(path: str) -> Tuple[str, Path]:
    if not path:
        return "", Path()
    segments = path.split("/", 1)
    if len(segments) == 1:
        return segments[0], Path()
    return segments[0], Path(segments[1])


def _collect_actual_files(mounts: dict[str, Path]) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for prefix, base in mounts.items():
        if not base.exists():
            continue
        for item in base.rglob("*"):
            if not item.is_file():
                continue
            if _should_ignore_file(prefix, item):
                continue
            relative = item.relative_to(base).as_posix()
            key = f"{prefix}/{relative}" if relative else prefix
            files[key] = item
    return files


def _should_ignore_file(prefix: str, path: Path) -> bool:
    name = path.name
    if name.startswith("."):
        return True
    if name.lower() in {"thumbs.db", "desktop.ini"}:
        return True
    if name in IGNORED_FILENAMES:
        return True
    suffix = path.suffix.lower()
    return suffix in IGNORED_SUFFIXES


def _find_stray_assets(config: Config, mounts: dict[str, Path]) -> dict[str, Path]:
    allowed_roots = {base.resolve() for base in mounts.values() if base.exists()}
    derived_root = config.media_processing.output_dir
    if derived_root.exists():
        allowed_roots.add(derived_root.resolve())

    results: dict[str, Path] = {}
    scan_roots = {config.content_dir, config.media_dir}
    for root in scan_roots:
        if not root.exists():
            continue
        root_resolved = root.resolve()
        for item in root_resolved.rglob("*"):
            if not item.is_file():
                continue
            if item.suffix.lower() not in ASSET_SUFFIXES:
                continue
            if any(_is_within(item, allowed) for allowed in allowed_roots):
                continue
            results[_relative_to_workspace(item)] = item
    return results


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _relative_to_workspace(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.as_posix()
