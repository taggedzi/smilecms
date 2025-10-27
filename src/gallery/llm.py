"""Lightweight metadata cleaning to mimic an LLM guard-rail.

Extended with optional project-level stopwords and alias maps to improve
tag quality without external dependencies.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Iterable

from .models import GalleryImageEntry

TOKEN_SPLIT = re.compile(r"[,\s;]+")


def clean_metadata(entry: GalleryImageEntry, now: datetime) -> bool:
    """Perform deterministic clean-up of generated metadata.

    This acts as a placeholder for a real LLM integration while still providing
    value: it normalises case, deduplicates tokens, and keeps fields readable.
    """
    metadata = entry.metadata
    changed = False

    cleaned_alt, alt_changed = _clean_sentence(metadata.alt_text or "", fallback=metadata.title)
    if alt_changed:
        metadata.alt_text = cleaned_alt
        changed = True

    cleaned_desc, desc_changed = _clean_sentence(
        metadata.description or "",
        fallback=metadata.alt_text,
        ensure_period=True,
    )
    if desc_changed:
        metadata.description = cleaned_desc
        changed = True

    cleaned_caption, caption_changed = _clean_sentence(
        metadata.caption or "",
        fallback=metadata.description,
        ensure_period=False,
    )
    if caption_changed:
        metadata.caption = cleaned_caption
        changed = True

    cleaned_tags, tags_changed = _clean_tags(metadata.tags or metadata.tags_raw)
    if tags_changed:
        metadata.tags = cleaned_tags
        changed = True

    if changed:
        metadata.llm_revision += 1
        metadata.llm_updated_at = now

    entry.metadata = metadata
    return changed


def _clean_sentence(
    text: str,
    *,
    fallback: str | None = None,
    ensure_period: bool = False,
) -> tuple[str, bool]:
    original = text or ""
    candidate = original.strip()

    if not candidate and fallback:
        candidate = fallback.strip()

    if not candidate:
        return original, False

    if ensure_period and not candidate.endswith((".", "!", "?")):
        candidate = f"{candidate.rstrip('.')}."

    # Normalise spacing and capitalisation.
    candidate = re.sub(r"\s+", " ", candidate)
    if candidate and candidate[0].islower():
        candidate = candidate[0].upper() + candidate[1:]

    changed = candidate != original
    return candidate, changed


def _clean_tags(tags: Iterable[str]) -> tuple[list[str], bool]:
    # Load optional project stopwords and alias map once per process.
    stopwords = _load_stopwords()
    aliases = _load_aliases()

    unique: dict[str, str] = {}
    for tag in tags:
        raw = str(tag).strip()
        if not raw:
            continue
        lowered = raw.lower()
        base = lowered
        # Strip known prefix for base matching but preserve original display
        if base.startswith("character:"):
            base = base[len("character:") :]
        # Apply aliases on the base term
        base = aliases.get(base, base)
        if base in stopwords or base in {"image", "photo", "picture"}:
            continue
        # Unique by base key; store formatted display
        if base not in unique:
            unique[base] = _format_tag(raw)

    cleaned = list(unique.values())
    return cleaned, cleaned != list(tags)


def _format_tag(tag: str) -> str:
    if " " in tag:
        return tag.title()
    if "-" in tag:
        return tag.lower()
    return tag.capitalize()


def _load_stopwords() -> set[str]:
    # Lazy import to avoid cycle
    from pathlib import Path

    builtins = {"image", "photo", "picture"}
    words: set[str] = set(builtins)
    path = Path("gallery/tag_stopwords.txt")
    try:
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                term = line.strip().lower()
                if term and not term.startswith("#"):
                    words.add(term)
    except OSError:
        pass
    return words


def _load_aliases() -> dict[str, str]:
    # Lazy import to avoid cycle
    from pathlib import Path

    path = Path("gallery/tag_aliases.json")
    mapping: dict[str, str] = {}
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key, value in data.items():
                    k = str(key).strip().lower()
                    v = str(value).strip().lower()
                    if k and v:
                        mapping[k] = v
    except (OSError, json.JSONDecodeError):
        return {}
    return mapping
