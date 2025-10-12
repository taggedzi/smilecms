"""Persistence helpers for manifest pages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .models import ManifestPage


def write_manifest_pages(pages: Iterable[ManifestPage], destination: Path) -> list[Path]:
    """Serialize manifest pages to JSON files within the destination directory."""
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for page in pages:
        path = destination / f"{page.id}.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(page.model_dump(mode="json"), handle, ensure_ascii=False, indent=2)
        written.append(path)

    return written
