from __future__ import annotations

import re
from pathlib import Path

from typer.testing import CliRunner

from src.cli import app


def _write_config(path: Path) -> None:
    path.write_text("project_name: Test Project\n", encoding="utf-8")


def test_lint_flags_missing_hero_and_alt_text() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _write_config(Path("smilecms.yml"))

        posts_dir = Path("content/posts")
        media_dir = Path("content/media")
        posts_dir.mkdir(parents=True)
        media_dir.mkdir(parents=True)

        (media_dir / "image-without-alt.jpg").write_bytes(b"")

        (posts_dir / "problem.md").write_text(
            """---
title: "Problem Post"
slug: problem-post
status: draft
published_at: 2025-01-01T00:00:00Z
hero_media:
  path: "media/missing-hero.jpg"
assets:
  - path: "media/image-without-alt.jpg"
---
Body text.
""",
            encoding="utf-8",
        )

        result = runner.invoke(app, ["lint"])
        assert result.exit_code == 1, result.output
        assert re.search(r"Media\s+file\s+not\s+found", result.output)
        assert "media/missing-hero.jpg" in result.output
        assert "assets[0].alt_text" in result.output
        assert "image-without-alt.jpg" in result.output
        assert re.search(r"Document\s+status\s+is\s+'draft'", result.output)


def test_lint_clean_when_content_is_valid() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _write_config(Path("smilecms.yml"))

        posts_dir = Path("content/posts")
        media_dir = Path("content/media")
        posts_dir.mkdir(parents=True)
        media_dir.mkdir(parents=True)

        (media_dir / "hero.jpg").write_bytes(b"")

        (posts_dir / "ok.md").write_text(
            """---
title: "Ready Post"
slug: ready-post
status: published
published_at: 2025-01-01T00:00:00Z
hero_media:
  path: "media/hero.jpg"
  alt_text: "Hero alt text"
assets:
  - path: "media/hero.jpg"
    alt_text: "Duplicate alt text"
---
All good.
""",
            encoding="utf-8",
        )

        result = runner.invoke(app, ["lint"])
        assert result.exit_code == 0, result.output
        assert "Lint clean" in result.output


def test_lint_strict_treats_warnings_as_errors() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _write_config(Path("smilecms.yml"))

        posts_dir = Path("content/posts")
        media_dir = Path("content/media")
        posts_dir.mkdir(parents=True)
        media_dir.mkdir(parents=True)

        (media_dir / "hero.jpg").write_bytes(b"")

        (posts_dir / "draft.md").write_text(
            """---
title: "Draft Post"
slug: draft-post
status: draft
published_at: 2025-01-01T00:00:00Z
hero_media:
  path: "media/hero.jpg"
  alt_text: "Hero alt"
---
Draft body.
""",
            encoding="utf-8",
        )

        result = runner.invoke(app, ["lint", "--strict"])
        assert result.exit_code == 1, result.output
        assert "WARNING" in result.output
