"""HTML validation utilities for SmileCMS."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence, TypedDict
from urllib.parse import unquote, urlparse

ValidatorRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


class HtmlValidatorError(RuntimeError):
    """Raised when the HTML validator fails to execute or returns invalid output."""


class HtmlValidatorUnavailableError(HtmlValidatorError):
    """Raised when the HTML validator tooling is not available in the environment."""


class _ValidatorMessage(TypedDict, total=False):
    type: str
    severity: str
    message: str
    url: str
    file: str
    lastLine: int
    lastColumn: int
    line: int
    column: int


class _ValidatorPayload(TypedDict, total=False):
    messages: list[_ValidatorMessage]


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
            return str(self.line)
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

    messages = payload.get("messages", [])
    issues = [_convert_message(message, html_root) for message in messages]

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


def _parse_validator_output(raw_output: str) -> _ValidatorPayload:
    text = raw_output.strip()
    if not text:
        return {"messages": []}
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {"messages": []}
    json_blob = text[start : end + 1]
    data = json.loads(json_blob)
    payload: _ValidatorPayload = {"messages": []}
    if isinstance(data, dict):
        messages_obj = data.get("messages")
        if isinstance(messages_obj, list):
            parsed_messages: list[_ValidatorMessage] = []
            for entry in messages_obj:
                if not isinstance(entry, dict):
                    continue
                message: _ValidatorMessage = {}
                value = entry.get("type")
                if isinstance(value, str):
                    message["type"] = value
                value = entry.get("severity")
                if isinstance(value, str):
                    message["severity"] = value
                value = entry.get("message")
                if isinstance(value, str):
                    message["message"] = value
                value = entry.get("url")
                if isinstance(value, str):
                    message["url"] = value
                value = entry.get("file")
                if isinstance(value, str):
                    message["file"] = value

                int_value = _coerce_int(entry.get("lastLine"))
                if int_value is not None:
                    message["lastLine"] = int_value
                int_value = _coerce_int(entry.get("lastColumn"))
                if int_value is not None:
                    message["lastColumn"] = int_value
                int_value = _coerce_int(entry.get("line"))
                if int_value is not None:
                    message["line"] = int_value
                int_value = _coerce_int(entry.get("column"))
                if int_value is not None:
                    message["column"] = int_value
                parsed_messages.append(message)
            payload["messages"] = parsed_messages
    return payload


def _convert_message(message: _ValidatorMessage, root: Path) -> HtmlValidationIssue:
    severity = _normalise_severity(message.get("type") or message.get("severity"))
    raw_text = message.get("message") or "HTML validation issue reported with no message."
    text = raw_text.strip()

    line = message.get("lastLine") if message.get("lastLine") is not None else message.get("line")
    column = (
        message.get("lastColumn") if message.get("lastColumn") is not None else message.get("column")
    )

    location = message.get("url") or message.get("file") or ""
    file_path = _resolve_message_path(location, root)

    return HtmlValidationIssue(
        file=file_path,
        message=text,
        severity=severity,
        line=line,
        column=column,
    )


def _normalise_severity(value: str | None) -> str:
    text = (value or "").strip().lower()
    if text in {"", "error", "fatal"}:
        return "error"
    if text in {"warning", "warn"}:
        return "warning"
    return "info"


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None
    return None


def _resolve_message_path(location: str, root: Path) -> Path:
    if not location:
        return root
    parsed = urlparse(location)
    if parsed.scheme == "file":
        netloc = unquote(parsed.netloc or "")
        path_part = unquote(parsed.path or "")
        if netloc:
            combined = f"{netloc}{path_part}"
            candidate = Path(combined)
        else:
            if path_part.startswith("/"):
                candidate = Path(path_part)
            else:
                candidate = (root / path_part).resolve()
    else:
        candidate = Path(unquote(location))
    if not candidate.is_absolute():
        candidate = (root / candidate).resolve()
    return candidate
