from __future__ import annotations

import shutil
from pathlib import Path

from typer.testing import CliRunner

from src.cli import app


def _write_minimal_config(path: Path) -> None:
    path.write_text(
        (
            "project_name: Test\n"
            "templates_dir: web\n"
            "site_theme: \n"
            "gallery:\n"
            "  enabled: false\n"
            "music:\n"
            "  enabled: false\n"
        ),
        encoding="utf-8",
    )


def test_build_respects_output_dir_override(tmp_path: Path) -> None:
    runner = CliRunner()
    project = tmp_path / "proj"
    project.mkdir()
    (project / "web").mkdir(parents=True, exist_ok=True)
    # Copy minimal test theme into the project
    fixture = Path(__file__).resolve().parent / "fixtures" / "test-theme" / "themes" / "default"
    dest = project / "web" / "themes" / "default"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(fixture, dest)
    _write_minimal_config(project / "smilecms.yml")

    result = runner.invoke(
        app,
        [
            "build",
            "--project",
            str(project),
            "--output-dir",
            "public_html",
        ],
    )
    assert result.exit_code == 0, result.output

    out_dir = project / "public_html"
    assert out_dir.exists()
