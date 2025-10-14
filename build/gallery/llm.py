"""Lightweight metadata cleaning to mimic an LLM guard-rail."""

from __future__ import annotations

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
    unique: dict[str, str] = {}
    for tag in tags:
        raw = str(tag).strip()
        if not raw:
            continue
        lowered = raw.lower()
        if lowered in {"image", "photo", "picture"}:
            # Avoid extremely generic tags; they add no value.
            continue
        if lowered not in unique:
            unique[lowered] = _format_tag(raw)

    cleaned = list(unique.values())
    return cleaned, cleaned != list(tags)


def _format_tag(tag: str) -> str:
    if " " in tag:
        return tag.title()
    if "-" in tag:
        return tag.lower()
    return tag.capitalize()
