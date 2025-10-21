"""Schema validation helpers and lint diagnostics for build artifacts."""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from enum import Enum, auto
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Callable, Iterator, Protocol, cast


class _Validator(Protocol):
    def iter_errors(self, instance: Any) -> Iterator[Any]:
        ...


ValidatorFactory = Callable[[Any], _Validator]

_jsonschema = importlib.import_module("jsonschema")
Draft202012Validator = cast(ValidatorFactory, getattr(_jsonschema, "Draft202012Validator"))

from .collections import load_gallery_documents, load_music_documents
from .config import Config
from .content import ContentDocument, ContentStatus, MediaReference, load_markdown_document
from .content.parsers import FrontMatterError
from .gallery.pipeline import prepare_workspace

SCHEMA_PACKAGE = "src.schemas"
CONTENT_SCHEMA_NAME = "content_post.schema.json"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".svg"}
SUPPORTED_SUFFIXES = {".md", ".markdown", ".mdx"}


class DocumentValidationError(ValueError):
    """Raised when a content document fails schema validation."""

    def __init__(self, message: str, *, path: str | None = None) -> None:
        super().__init__(message)
        self.path = path


class IssueSeverity(Enum):
    """Severity level for lint issues."""

    ERROR = auto()
    WARNING = auto()


@dataclass(slots=True)
class DocumentIssue:
    """Represents a lint finding for a document."""

    slug: str
    source_path: str
    message: str
    severity: IssueSeverity
    pointer: str | None = None


@dataclass(slots=True)
class LintReport:
    """Aggregate lint results for a workspace."""

    issues: list[DocumentIssue] = field(default_factory=list)
    document_count: int = 0

    def add(self, issue: DocumentIssue) -> None:
        self.issues.append(issue)

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity is IssueSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity is IssueSeverity.WARNING)


def validate_document(document: ContentDocument) -> None:
    """Validate a content document against the canonical JSON schema."""
    data = document.model_dump(mode="json", exclude_none=True)
    validator = _get_content_validator()
    errors = sorted(validator.iter_errors(data), key=lambda err: err.path)
    if errors:
        first = errors[0]
        pointer = "/".join(str(elem) for elem in first.path)
        source_path = document.source_path
        message = f"{source_path}: {first.message}"
        if pointer:
            message += f" (at {pointer})"
        raise DocumentValidationError(message, path=pointer or None)


def lint_document(document: ContentDocument, config: Config) -> list[DocumentIssue]:
    """Run lint checks against a single document."""
    issues: list[DocumentIssue] = []

    try:
        validate_document(document)
    except DocumentValidationError as exc:
        issues.append(
            DocumentIssue(
                slug=document.slug,
                source_path=document.source_path,
                message=str(exc),
                severity=IssueSeverity.ERROR,
                pointer=exc.path,
            )
        )

    if document.meta.status is not ContentStatus.PUBLISHED:
        issues.append(
            DocumentIssue(
                slug=document.slug,
                source_path=document.source_path,
                message=f"Document status is '{document.meta.status.value}'. Publish before deployment.",
                severity=IssueSeverity.WARNING,
                pointer="meta.status",
            )
        )

    hero = document.meta.hero_media
    if hero is not None:
        issues.extend(_lint_media_reference(document, hero, config, pointer="meta.hero_media"))

    for index, asset in enumerate(document.assets):
        issues.extend(_lint_media_reference(document, asset, config, pointer=f"assets[{index}]"))

    download_path = document.meta.download_path
    if download_path:
        issues.extend(
            _lint_media_path(
                document,
                download_path,
                config,
                pointer="meta.download_path",
            )
        )

    return issues


def lint_workspace(config: Config) -> LintReport:
    """Collect documents and emit lint diagnostics for the configured workspace."""
    report = LintReport()
    documents: list[ContentDocument] = []

    content_dir = config.content_dir
    if content_dir.exists():
        for path in _iter_markdown_files(content_dir):
            try:
                document = load_markdown_document(path)
            except FrontMatterError as exc:
                report.add(
                    DocumentIssue(
                        slug=Path(path).stem,
                        source_path=str(path),
                        message=str(exc),
                        severity=IssueSeverity.ERROR,
                    )
                )
                continue
            documents.append(document)

    gallery_workspace = prepare_workspace(config, auto_generate=False, run_llm_cleanup=False)
    documents.extend(load_gallery_documents(config, workspace=gallery_workspace))
    documents.extend(load_music_documents(config))

    report.document_count = len(documents)

    for document in documents:
        for issue in lint_document(document, config):
            report.add(issue)

    return report


@lru_cache(maxsize=1)
def _get_content_validator() -> _Validator:
    schema = _load_schema(CONTENT_SCHEMA_NAME)
    return Draft202012Validator(schema)


def _load_schema(name: str) -> dict[str, Any]:
    with resources.files(SCHEMA_PACKAGE).joinpath(name).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Schema '{name}' must be a JSON object.")
    return cast(dict[str, Any], payload)


def _lint_media_reference(
    document: ContentDocument,
    reference: MediaReference,
    config: Config,
    *,
    pointer: str,
) -> list[DocumentIssue]:
    issues: list[DocumentIssue] = []
    path_value = (reference.path or "").strip()
    location = f"{pointer}.path"
    if not path_value:
        issues.append(
            DocumentIssue(
                slug=document.slug,
                source_path=document.source_path,
                message="Media reference is missing a path.",
                severity=IssueSeverity.ERROR,
                pointer=location,
            )
        )
        return issues

    resolved = _resolve_media_path(path_value, config)
    if resolved is None:
        issues.append(
            DocumentIssue(
                slug=document.slug,
                source_path=document.source_path,
                message=f"Media path '{path_value}' is outside configured media roots.",
                severity=IssueSeverity.ERROR,
                pointer=location,
            )
        )
    elif not resolved.exists():
        issues.append(
            DocumentIssue(
                slug=document.slug,
                source_path=document.source_path,
                message=f"Media file not found: {path_value} (expected at {resolved})",
                severity=IssueSeverity.ERROR,
                pointer=location,
            )
        )

    if _requires_alt_text(path_value) and not _has_alt_text(reference):
        issues.append(
            DocumentIssue(
                slug=document.slug,
                source_path=document.source_path,
                message=f"Image reference '{path_value}' is missing alt_text.",
                severity=IssueSeverity.WARNING,
                pointer=f"{pointer}.alt_text",
            )
        )

    return issues


def _lint_media_path(
    document: ContentDocument,
    media_path: str,
    config: Config,
    *,
    pointer: str,
) -> list[DocumentIssue]:
    reference = MediaReference(path=media_path)
    return _lint_media_reference(document, reference, config, pointer=pointer)


def _resolve_media_path(relative_path: str, config: Config) -> Path | None:
    normalized = relative_path.strip().lstrip("/")
    if not normalized:
        return None
    prefix, sep, remainder = normalized.partition("/")
    if not sep:
        return None

    for mount, root in config.media_mounts:
        if prefix != mount:
            continue

        base = Path(root).resolve()
        candidate = (base / remainder).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            return None
        return candidate

    return None


def _requires_alt_text(path_value: str) -> bool:
    suffix = Path(path_value).suffix.lower()
    return suffix in IMAGE_EXTENSIONS


def _has_alt_text(reference: MediaReference) -> bool:
    text = reference.alt_text
    return bool(text and text.strip())


def _iter_markdown_files(root: Path) -> Iterator[Path]:
    directories = sorted(p for p in root.rglob("*") if p.is_dir())
    directories.insert(0, root)

    for directory in directories:
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
                yield path
