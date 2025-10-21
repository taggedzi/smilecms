"""HTML validation utilities for SmileCMS."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence
from urllib.parse import unquote, urlparse


ValidatorRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


class HtmlValidatorError(RuntimeError):
    """Raised when the HTML validator fails to execute or returns invalid output."""


class HtmlValidatorUnavailableError(HtmlValidatorError):
    """Raised when the HTML validator tooling is not available in the environment."""


@dataclass(slots=True)
class HtmlValidationIssue:
    """Represents a single issue reported by the HTML validator."""

    file: Path
    message: str
    severity: str
    line: int | None = None
    column: int | None = None

    def location(self) -> str:
        if self.line is None:
            return ""
        if self.column is None:
            return f"{self.line}"
        return f"{self.line}:{self.column}"


@dataclass(slots=True)
class HtmlValidationReport:
    """Validation summary returned after checking the generated site."""

    scanned_files: int
    issues: list[HtmlValidationIssue]

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")


def validate_html(
    output_dir: Path,
    *,
    command: Sequence[str] | None = None,
    runner: ValidatorRunner | None = None,
) -> HtmlValidationReport:
    """Validate rendered HTML files under ``output_dir`` using html5validator."""
    html_root = output_dir.resolve()
    if not html_root.exists():
        raise HtmlValidatorError(f"Output directory does not exist: {html_root}")

    checked_files = _count_html_files(html_root)

    validator_cmd = (
        list(command) if command else [sys.executable, "-m", "html5validator.cli"]
    )
    validator_cmd.extend(["--root", str(html_root), "--format", "json"])
    validator_cmd.extend(["--blacklist", "templates", "themes"])

    exec_runner = runner or _run_subprocess

    try:
        result = exec_runner(validator_cmd)
    except FileNotFoundError as exc:
        raise HtmlValidatorUnavailableError(
            "html5validator is not installed or not available in PATH."
        ) from exc

    if "No module named html5validator" in result.stderr:
        raise HtmlValidatorUnavailableError(
            "html5validator is not installed in the active environment."
        )

    if result.returncode not in {0, 1}:
        raise HtmlValidatorError(
            f"html5validator failed with exit code {result.returncode}: {result.stderr.strip()}"
        )

    try:
        payload = _parse_validator_output(result.stdout or result.stderr)
    except json.JSONDecodeError as exc:
        raise HtmlValidatorError(f"Unable to parse html5validator output: {exc}") from exc

    issues = [
        _convert_message(message, html_root)
        for message in payload.get("messages", [])
    ]

    return HtmlValidationReport(
        scanned_files=checked_files,
        issues=issues,
    )


def _run_subprocess(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )


def _count_html_files(root: Path) -> int:
    return sum(1 for _ in root.rglob("*.html"))


def _parse_validator_output(raw_output: str) -> dict[str, object]:
    text = raw_output.strip()
    if not text:
        return {"messages": []}
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {"messages": []}
    json_blob = text[start : end + 1]
    return json.loads(json_blob)


def _convert_message(message: dict[str, object], root: Path) -> HtmlValidationIssue | None:
    severity = _normalise_severity(message.get("type") or message.get("severity"))
    text = str(message.get("message") or "").strip()
    if not text:
        text = "HTML validation issue reported with no message."

    line = _coerce_int(message.get("lastLine") or message.get("line"))
    column = _coerce_int(message.get("lastColumn") or message.get("column"))

    url = message.get("url") or message.get("file") or ""
    file_path = _resolve_message_path(str(url), root)

    return HtmlValidationIssue(
        file=file_path,
        message=text,
        severity=severity,
        line=line,
        column=column,
    )


def _normalise_severity(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in {"", "error", "fatal"}:
        return "error"
    if text in {"warning", "warn"}:
        return "warning"
    return "info"


def _coerce_int(value: object) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_message_path(location: str, root: Path) -> Path:
    if not location:
        return root
    parsed = urlparse(location)
    if parsed.scheme in {"file"}:
        netloc = unquote(parsed.netloc or "")
        path_part = unquote(parsed.path or "")
        if not netloc and path_part.startswith("/"):
            path_part = path_part.lstrip("/")
        candidate_str = f"{netloc}{path_part}" if netloc else path_part
        candidate = Path(candidate_str)
    else:
        candidate = Path(unquote(location))
    if not candidate.is_absolute():
        candidate = (root / candidate).resolve()
    return candidate
