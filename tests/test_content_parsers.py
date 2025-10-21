from pathlib import Path

import pytest

from src.content.parsers import FrontMatterError, load_markdown_document

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "content" / "posts"


def test_loads_complete_document() -> None:
    path = FIXTURE_DIR / "example.md"
    document = load_markdown_document(path)

    assert document.slug == "example-post"
    assert document.meta.title == "Example Post"
    assert document.status.value == "published"
    assert document.meta.tags == ["testing", "examples"]
    assert document.meta.hero_media is not None
    assert document.assets and document.assets[0].path == "audio/example.mp3"
    assert "Hello world" in document.body


def test_slug_defaults_to_filename_when_missing() -> None:
    path = FIXTURE_DIR / "minimal.md"
    document = load_markdown_document(path)

    assert document.slug == "minimal"
    assert document.meta.title == "Minimal Post"


def test_rejects_missing_front_matter_end(tmp_path: Path) -> None:
    markdown = "---\ntitle: Missing\n"
    tmp = tmp_path / "broken.md"
    tmp.write_text(markdown, encoding="utf-8")
    with pytest.raises(FrontMatterError):
        load_markdown_document(tmp)
