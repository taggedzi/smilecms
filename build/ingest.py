"""High-level ingestion helpers to load content documents from the workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .config import Config
from .content import ContentDocument, load_markdown_document

SUPPORTED_SUFFIXES = {".md", ".markdown", ".mdx"}


def load_documents(config: Config) -> list[ContentDocument]:
    """Load all supported content documents from the configured content directory."""
    root = config.content_dir
    if not root.exists():
        return []

    documents: list[ContentDocument] = []
    for path in _iter_content_files(root):
        document = load_markdown_document(path)
        documents.append(document)
    return documents


def _iter_content_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            yield path
