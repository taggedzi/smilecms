"""Site verification utilities for SmileCMS."""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterator, List, Tuple
from urllib.parse import unquote, urlsplit


@dataclass(slots=True)
class VerificationIssue:
    """Represents a problem discovered during site verification."""

    kind: str
    source: Path
    target: str
    message: str


@dataclass(slots=True)
class VerificationReport:
    """Aggregate verification results."""

    scanned_files: int
    issues: list[VerificationIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.kind != "warning")

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.kind == "warning")


class _ReferenceCollector(HTMLParser):
    """Collect href/src references from HTML content."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[tuple[str, str, str]] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, str | None]]) -> None:
        attr_map = {name: value for name, value in attrs if value is not None}

        if tag in {"a", "link"} and "href" in attr_map:
            self.references.append((tag, "href", attr_map["href"]))
        if tag in {"img", "script", "iframe", "audio", "video", "source", "track", "embed"}:
            src = attr_map.get("src")
            if src:
                self.references.append((tag, "src", src))
        if tag in {"img", "source"} and "srcset" in attr_map:
            srcset = attr_map["srcset"]
            for candidate in _parse_srcset(srcset):
                self.references.append((tag, "srcset", candidate))


def verify_site(output_dir: Path) -> VerificationReport:
    """Verify links and asset references within the generated site directory."""
    output_dir = output_dir.resolve()
    html_files = sorted(output_dir.rglob("*.html"))
    issues: list[VerificationIssue] = []

    for html_file in html_files:
        try:
            html = html_file.read_text(encoding="utf-8")
        except OSError as exc:
            issues.append(
                VerificationIssue(
                    kind="error",
                    source=html_file,
                    target=str(html_file),
                    message=f"Unable to read HTML file: {exc}",
                )
            )
            continue

        parser = _ReferenceCollector()
        parser.feed(html)

        for tag, attr, reference in parser.references:
            if _is_ignorable(reference):
                continue

            resolved_path, needs_index, special_issue = _resolve_reference(reference, html_file, output_dir)
            if special_issue:
                issues.append(
                    VerificationIssue(
                        kind=special_issue,
                        source=html_file,
                        target=reference,
                        message=f"Reference points outside the site bundle: '{reference}'",
                    )
                )
                continue

            if resolved_path is None:
                continue

            if resolved_path.exists():
                continue

            if needs_index and (resolved_path / "index.html").exists():
                continue

            issues.append(
                VerificationIssue(
                    kind=_classify_issue(tag),
                    source=html_file,
                    target=reference,
                    message=f"Missing target for {tag} {attr} '{reference}'",
                )
            )

    return VerificationReport(scanned_files=len(html_files), issues=issues)


def _parse_srcset(srcset: str) -> Iterator[str]:
    for part in srcset.split(","):
        candidate = part.strip().split(" ", 1)[0]
        if candidate:
            yield candidate


def _is_ignorable(reference: str) -> bool:
    if not reference:
        return True
    stripped = reference.strip()
    if not stripped:
        return True
    # Ignore templating placeholders (e.g., Jinja) that aren't concrete paths yet.
    if "{{" in stripped or "{%" in stripped or "}}" in stripped or "%}" in stripped:
        return True

    parsed = urlsplit(stripped)

    if parsed.scheme in {"http", "https", "mailto", "tel", "data", "javascript", "ftp"}:
        return True
    if parsed.netloc and not parsed.scheme:
        # Protocol-relative URL (e.g., //cdn.example.com)
        return True
    if not parsed.path and (parsed.fragment or parsed.query):
        return True

    return False


def _resolve_reference(
    reference: str, source: Path, output_dir: Path
) -> tuple[Path | None, bool, str | None]:
    parsed = urlsplit(reference)
    path = unquote(parsed.path or "")

    if not path:
        return None, False, None

    if path.startswith("/"):
        candidate = (output_dir / path.lstrip("/")).resolve()
    else:
        candidate = (source.parent / path).resolve()

    try:
        candidate.relative_to(output_dir)
    except ValueError:
        return None, False, "out-of-bounds"

    if candidate.is_dir():
        return candidate, True, None

    if candidate.suffix:
        return candidate, False, None

    return candidate, True, None


def _classify_issue(tag: str) -> str:
    if tag == "a":
        return "missing-page"
    if tag in {"img", "video", "audio", "source", "track"}:
        return "missing-asset"
    return "error"
