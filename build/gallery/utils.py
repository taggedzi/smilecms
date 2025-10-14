"""Utility helpers for gallery processing."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Sequence


SLUG_PATTERN = re.compile(r"[^a-z0-9\-]+")
WHITESPACE_PATTERN = re.compile(r"\s+")


def slugify(value: str) -> str:
    """Convert arbitrary text into a filesystem-safe slug."""
    text = value.strip().lower()
    text = WHITESPACE_PATTERN.sub("-", text)
    text = re.sub(r"_+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    text = SLUG_PATTERN.sub("-", text)
    return text.strip("-") or "item"


def title_from_stem(stem: str) -> str:
    """Generate a human-friendly title from a filename stem."""
    text = stem.replace("_", " ").replace("-", " ")
    text = WHITESPACE_PATTERN.sub(" ", text).strip()
    if not text:
        return "Untitled"
    words = [word.capitalize() if not word.isupper() else word for word in text.split()]
    return " ".join(words)


def hash_file(path: Path, block_size: int = 1024 * 1024) -> str:
    """Compute a SHA256 digest for the given file."""
    digest = sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(block_size)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        try:
            data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping at {path}, received {type(data).__name__}")
    return data


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def chunked(sequence: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for index in range(0, len(sequence), size):
        yield sequence[index : index + size]


@dataclass(slots=True)
class ChangeTracker:
    """Track if a payload has changed compared to its initial state."""

    original: dict[str, Any]

    def has_changed(self, updated: dict[str, Any]) -> bool:
        return self.original != updated

