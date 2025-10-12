from pathlib import Path

from build.config import Config
from build.ingest import load_documents


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

    config = Config(content_dir=content)
    documents = load_documents(config)

    slugs = [doc.slug for doc in documents]
    assert slugs == ["first", "second"]
    assert documents[0].meta.title == "First"
    assert documents[1].meta.title == "Second"


def test_returns_empty_when_directory_missing(tmp_path: Path) -> None:
    config = Config(content_dir=tmp_path / "missing")
    documents = load_documents(config)
    assert documents == []
