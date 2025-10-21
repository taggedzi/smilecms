"""JavaScript validation utilities for SmileCMS."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, Tuple


class JsValidatorError(RuntimeError):
    """Raised when JavaScript validation fails unexpectedly."""


class JsValidatorUnavailableError(JsValidatorError):
    """Raised when JavaScript validation cannot run due to missing tooling."""


@dataclass(slots=True)
class JsValidationIssue:
    """Represents a problem detected while parsing JavaScript."""

    file: Path
    message: str
    severity: str = "error"
    line: int | None = None
    column: int | None = None

    def location(self) -> str:
        if self.line is None:
            return ""
        if self.column is None:
            return str(self.line)
        return f"{self.line}:{self.column}"


@dataclass(slots=True)
class JsValidationReport:
    """Aggregate JavaScript validation results."""

    scanned_files: int
    issues: list[JsValidationIssue]

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")


def validate_javascript(
    output_dir: Path,
    *,
    include_patterns: Sequence[str] | None = None,
    exclude_patterns: Sequence[str] | None = None,
) -> JsValidationReport:
    """Validate generated JavaScript assets using `node --check`."""
    root = output_dir.resolve()
    if not root.exists():
        raise JsValidatorError(f"Output directory does not exist: {root}")

    node_info = _node_available()
    if node_info is None:
        raise JsValidatorUnavailableError("Node.js >= 14 is required for JavaScript validation.")

    node_path, node_version = node_info
    if node_version < (14, 0, 0):
        version_text = ".".join(str(part) for part in node_version)
        raise JsValidatorUnavailableError(
            f"Node.js {version_text} detected; JavaScript validation requires Node.js >= 14."
        )

    include_patterns = tuple(include_patterns or ("*.js",))
    exclude_patterns = tuple(exclude_patterns or ("*.min.js",))

    js_files = _collect_files(root, include_patterns, exclude_patterns)
    issues: list[JsValidationIssue] = []

    for js_file in js_files:
        try:
            result = _run_node_check(node_path, js_file)
        except OSError as exc:
            issues.append(
                JsValidationIssue(
                    file=js_file,
                    message=f"Failed to execute Node.js for {js_file.name}: {exc}",
                )
            )
            continue

        if result.returncode != 0:
            issue = _convert_node_error(js_file, result.stderr or result.stdout)
            issues.append(issue)

    return JsValidationReport(scanned_files=len(js_files), issues=issues)


def _collect_files(
    root: Path,
    include_patterns: Sequence[str],
    exclude_patterns: Sequence[str],
) -> list[Path]:
    files: list[Path] = []
    for pattern in include_patterns:
        for candidate in root.rglob(pattern):
            if not candidate.is_file():
                continue
            if any(candidate.match(ex_pattern) for ex_pattern in exclude_patterns):
                continue
            files.append(candidate)
    return sorted(files)


def _node_available() -> tuple[str, Tuple[int, int, int]] | None:
    node_path = shutil.which("node")
    if not node_path:
        return None
    try:
        result = subprocess.run(
            [node_path, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None

    version_text = (result.stdout or result.stderr or "").strip()
    if version_text.startswith("v"):
        version_text = version_text[1:]

    parts = version_text.split(".")
    major = _safe_int(parts, 0)
    minor = _safe_int(parts, 1)
    patch = _safe_int(parts, 2)

    return node_path, (major, minor, patch)


def _safe_int(parts: Sequence[str], index: int) -> int:
    try:
        return int(parts[index])
    except (IndexError, ValueError):
        return 0


def _run_node_check(node_path: str, js_file: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [node_path, "--check", str(js_file)],
        capture_output=True,
        text=True,
    )


_NODE_ERROR_RE = re.compile(
    r"^(?P<path>.*?):(?P<line>\d+)(?::(?P<column>\d+))?\s*(?:-)?\s*Error",
    re.MULTILINE,
)


def _convert_node_error(js_file: Path, output: str) -> JsValidationIssue:
    message = output.strip() or "Node.js reported a syntax error."
    line: int | None = None
    column: int | None = None

    for match in _NODE_ERROR_RE.finditer(output):
        candidate_path = Path(match.group("path")).resolve()
        if candidate_path != js_file.resolve():
            continue
        try:
            line = int(match.group("line"))
        except (TypeError, ValueError):
            line = None
        column_text = match.group("column")
        if column_text is not None:
            try:
                column = int(column_text)
            except ValueError:
                column = None
        break

    return JsValidationIssue(
        file=js_file,
        message=message.splitlines()[-1] if message else "Node.js reported a syntax error.",
        line=line,
        column=column,
    )
