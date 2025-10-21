from __future__ import annotations

import subprocess
from pathlib import Path
import pytest

import src.jsvalidate as jsvalidate
from src.jsvalidate import (
    JsValidationIssue,
    JsValidatorUnavailableError,
    validate_javascript,
)


def _write_js(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_validate_javascript_reports_clean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, Path]] = []

    def fake_available() -> tuple[str, tuple[int, int, int]]:
        return ("node", (18, 18, 0))

    def fake_run(node_path: str, js_file: Path) -> subprocess.CompletedProcess[str]:
        calls.append((node_path, js_file))
        return subprocess.CompletedProcess([node_path, "--check", str(js_file)], 0, "", "")

    monkeypatch.setattr(jsvalidate, "_node_available", fake_available)
    monkeypatch.setattr(jsvalidate, "_run_node_check", fake_run)

    target = _write_js(tmp_path / "app.js", "function demo() { return 1; }")

    report = validate_javascript(tmp_path)

    assert report.scanned_files == 1
    assert report.error_count == 0
    assert report.issues == []
    assert calls == [("node", target)]


def test_validate_javascript_handles_syntax_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_available() -> tuple[str, tuple[int, int, int]]:
        return ("node", (18, 0, 0))

    def fake_run(node_path: str, js_file: Path) -> subprocess.CompletedProcess[str]:
        stderr = f"{js_file}:{4}:5 - Error: Unexpected token ;\nSyntaxError: Unexpected token ;"
        return subprocess.CompletedProcess([node_path, "--check", str(js_file)], 1, "", stderr)

    monkeypatch.setattr(jsvalidate, "_node_available", fake_available)
    monkeypatch.setattr(jsvalidate, "_run_node_check", fake_run)

    _write_js(tmp_path / "broken.js", "function demo() { ; }")

    report = validate_javascript(tmp_path)

    assert report.scanned_files == 1
    assert report.error_count == 1
    issue = report.issues[0]
    assert isinstance(issue, JsValidationIssue)
    assert issue.line == 4
    assert issue.column == 5
    assert "Unexpected token" in issue.message


def test_validate_javascript_excludes_patterns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Path] = []

    def fake_available() -> tuple[str, tuple[int, int, int]]:
        return ("node", (18, 0, 0))

    def fake_run(node_path: str, js_file: Path) -> subprocess.CompletedProcess[str]:
        calls.append(js_file)
        return subprocess.CompletedProcess([node_path, "--check", str(js_file)], 0, "", "")

    monkeypatch.setattr(jsvalidate, "_node_available", fake_available)
    monkeypatch.setattr(jsvalidate, "_run_node_check", fake_run)

    _write_js(tmp_path / "ok.js", "const value = 42;")
    _write_js(tmp_path / "skip.min.js", "const value=42")

    report = validate_javascript(tmp_path, exclude_patterns=("*.min.js",))

    assert report.scanned_files == 1
    assert report.error_count == 0
    assert calls == [tmp_path / "ok.js"]


def test_validate_javascript_requires_node(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jsvalidate, "_node_available", lambda: None)
    with pytest.raises(JsValidatorUnavailableError):
        validate_javascript(tmp_path)


def test_validate_javascript_requires_modern_node(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jsvalidate, "_node_available", lambda: ("node", (12, 22, 0)))
    with pytest.raises(JsValidatorUnavailableError) as error:
        validate_javascript(tmp_path)
    assert ">= 14" in str(error.value)
