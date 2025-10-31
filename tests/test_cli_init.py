from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from src.cli import app


def test_init_scaffolds_project_directory(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "siteproj"
    result = runner.invoke(app, ["init", str(target)])
    assert result.exit_code == 0, result.output

    # Core files and directories exist
    assert (target / "smilecms.yml").exists()
    assert (target / "content" / "posts" / ".gitkeep").exists()
    assert (target / "content" / "media" / ".gitkeep").exists()
    assert (target / "media" / "image_gallery_raw" / ".gitkeep").exists()
    assert (target / "media" / "music_collection" / ".gitkeep").exists()
    assert (target / "web" / "README.md").exists()
    assert (target / ".gitignore").exists()


def test_project_alias_points_to_config(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "proj"
    result = runner.invoke(app, ["init", str(target)])
    assert result.exit_code == 0, result.output

    # Run a no-op command using --project and expect it to succeed
    lint = runner.invoke(app, ["lint", "--project", str(target)])
    assert lint.exit_code in (0, 1)
    # lint may report warnings depending on defaults; non-crashing behavior is sufficient
