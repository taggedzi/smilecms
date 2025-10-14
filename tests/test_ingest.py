from pathlib import Path

from build.config import Config, GalleryConfig, MusicConfig
import pytest

from build.ingest import load_documents
from build.validation import DocumentValidationError


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_load_documents_from_nested_directories(tmp_path: Path) -> None:
    content = tmp_path / "content"
    _write(
        content / "posts" / "first.md",
        "---\ntitle: First\nstatus: published\n---\nFirst body",
    )
    _write(
        content / "notes" / "second.markdown",
        "---\ntitle: Second\n---\nSecond body",
    )
    _write(content / "notes" / "ignore.txt", "Plain text")

    config = Config(
        content_dir=content,
        gallery=GalleryConfig(source_dir=tmp_path / "gallery"),
        music=MusicConfig(source_dir=tmp_path / "music"),
    )
    documents = sorted(load_documents(config), key=lambda doc: doc.slug)

    slugs = [doc.slug for doc in documents]
    assert slugs == ["first", "second"]
    assert documents[0].meta.title == "First"
    assert documents[1].meta.title == "Second"


def test_returns_empty_when_directory_missing(tmp_path: Path) -> None:
    config = Config(
        content_dir=tmp_path / "missing",
        gallery=GalleryConfig(source_dir=tmp_path / "gallery"),
        music=MusicConfig(source_dir=tmp_path / "music"),
    )
    documents = load_documents(config)
    assert documents == []


def test_invalid_document_raises_validation_error(tmp_path: Path) -> None:
    content = tmp_path / "content"
    _write(
        content / "posts" / "bad.md",
        "---\nslug: \"Bad Slug\"\ntitle: Invalid\n---\nBody",
    )

    config = Config(
        content_dir=content,
        gallery=GalleryConfig(source_dir=tmp_path / "gallery"),
        music=MusicConfig(source_dir=tmp_path / "music"),
    )
    with pytest.raises(DocumentValidationError) as excinfo:
        load_documents(config)

    assert "bad.md" in str(excinfo.value)
