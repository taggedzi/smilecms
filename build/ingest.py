"""High-level ingestion helpers to load content documents from the workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from .collections import load_gallery_documents, load_music_documents
from .config import Config
from .content import ContentDocument, load_markdown_document
from .validation import validate_document

SUPPORTED_SUFFIXES = {".md", ".markdown", ".mdx"}


def load_documents(config: Config) -> list[ContentDocument]:
    """Load all supported content documents from the configured content directory."""
    root = config.content_dir

    documents: List[ContentDocument] = []
    if root.exists():
        for path in _iter_content_files(root):
            document = load_markdown_document(path)
            validate_document(document)
            documents.append(document)

    for document in load_gallery_documents(config):
        validate_document(document)
        documents.append(document)

    for document in load_music_documents(config):
        validate_document(document)
        documents.append(document)

    return documents


def _iter_content_files(root: Path) -> Iterable[Path]:
    directories = sorted(p for p in root.rglob("*") if p.is_dir())
    directories.insert(0, root)

    for directory in directories:
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
                yield path
