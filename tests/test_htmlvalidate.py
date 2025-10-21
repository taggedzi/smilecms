from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.htmlvalidate import (
    HtmlValidatorError,
    HtmlValidatorUnavailableError,
    validate_html,
)


def _make_stub_html(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "<!doctype html><html><head><title>Test</title></head><body></body></html>",
        encoding="utf-8",
    )
    return path


def test_validate_html_returns_empty_report(tmp_path: Path) -> None:
    _make_stub_html(tmp_path, "index.html")

    def runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 0, stdout='{"messages": []}', stderr="")

    report = validate_html(tmp_path, runner=runner)

    assert report.scanned_files == 1
    assert report.error_count == 0
    assert report.warning_count == 0
    assert report.issues == []


def test_validate_html_parses_validator_messages(tmp_path: Path) -> None:
    file_path = _make_stub_html(tmp_path, "about/index.html")

    payload = {
        "messages": [
            {
                "type": "error",
                "url": f"file://{file_path}",
                "lastLine": 4,
                "lastColumn": 2,
                "message": "Element “head” is missing a required child element “title”.",
            },
            {
                "type": "warning",
                "url": f"file://{file_path}",
                "lastLine": 5,
                "lastColumn": 1,
                "message": "Consider adding a lang attribute to the html element.",
            },
        ]
    }

    def runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 1, stdout=str(payload).replace("'", '"'), stderr="")

    report = validate_html(tmp_path, runner=runner)

    assert report.scanned_files == 1
    assert report.error_count == 1
    assert report.warning_count == 1
    assert len(report.issues) == 2
    first = report.issues[0]
    assert first.file == file_path.resolve()
    assert first.line == 4
    assert first.column == 2
    assert first.severity == "error"


def test_validate_html_handles_missing_validator(tmp_path: Path) -> None:
    _make_stub_html(tmp_path, "index.html")

    def runner(_cmd: list[str]) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("not found")

    with pytest.raises(HtmlValidatorUnavailableError):
        validate_html(tmp_path, runner=runner)


def test_validate_html_raises_on_unknown_exit_code(tmp_path: Path) -> None:
    _make_stub_html(tmp_path, "index.html")

    def runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 3, stdout="", stderr="unexpected failure")

    with pytest.raises(HtmlValidatorError):
        validate_html(tmp_path, runner=runner)
