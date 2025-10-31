"""ML-driven captioning and tagging helpers for gallery images."""

from __future__ import annotations

import logging
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, TypedDict, cast

from PIL import Image

from ..config import Config

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AnnotationResult:
    """Captures outputs from captioning and tag derivation."""

    caption: str | None
    alt_text: str | None
    tags: list[str]
    tag_scores: dict[str, float]


class TagResult(TypedDict):
    tags: list[str]
    scores: dict[str, float]


class TaggingSession:
    """Manage ML model lifecycle for gallery tagging."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self.available = False
        self.failure_reason: str | None = None
        self.model_signature: str | None = None
        self._processor = None
        self._caption_model = None
        self._torch = None
        self._device = None
        self._max_tags = config.gallery.tagging_max_tags

        if not config.gallery.tagging_enabled:
            self.failure_reason = "Tagging disabled via configuration."
            return

        cache_root = (config.cache_dir / "ml").expanduser()
        caption_cache = cache_root / "caption"
        caption_cache.mkdir(parents=True, exist_ok=True)

        try:
            from transformers import BlipForConditionalGeneration, BlipProcessor
        except ImportError as exc:
            self.failure_reason = (
                "transformers package is required for captioning but was not found."
            )
            logger.warning(self.failure_reason)
            logger.debug("transformers import failure: %s", exc, exc_info=True)
            return

        # WD14 tagger removed; we now derive tags from text.

        try:
            import torch
        except ImportError as exc:
            self.failure_reason = "PyTorch is required for caption generation but is not installed."
            logger.warning(self.failure_reason)
            logger.debug("torch import failure: %s", exc, exc_info=True)
            return

        device_name = config.gallery.tagging_device
        if not device_name:
            device_name = "cuda" if torch.cuda.is_available() else "cpu"

        try:
            device = torch.device(device_name)
        except (TypeError, ValueError) as exc:
            self.failure_reason = f"Invalid torch device '{device_name}': {exc}"
            logger.warning(self.failure_reason)
            return

        try:
            processor = BlipProcessor.from_pretrained(
                config.gallery.caption_model,
                cache_dir=str(caption_cache),
                local_files_only=bool(config.gallery.local_models_only),
            )
            caption_model = BlipForConditionalGeneration.from_pretrained(
                config.gallery.caption_model,
                cache_dir=str(caption_cache),
                local_files_only=bool(config.gallery.local_models_only),
            )
            caption_model.to(device)
            caption_model.eval()
        except Exception as exc:  # pragma: no cover - model download paths hard to mock
            self.failure_reason = f"Failed to load caption model {config.gallery.caption_model}: {exc}"
            logger.warning(self.failure_reason)
            logger.debug("Caption model load error", exc_info=True)
            return

        self._processor = processor
        self._caption_model = caption_model
        self._torch = torch
        self._device = device
        self.available = True
        self.model_signature = f"caption:{config.gallery.caption_model}|tagger:none"
        logger.debug(
            "Initialised tagging session with models %s (%s)",
            self.model_signature,
            device,
        )

    def annotate(self, image_path: Path) -> Optional[AnnotationResult]:
        """Return ML-generated metadata for an image, or None if unavailable."""
        if not self.available or not self._processor or not self._caption_model:
            return None

        try:
            with Image.open(image_path) as base_image:
                rgb = base_image.convert("RGB")
                try:
                    caption = self._generate_caption(rgb)
                    tag_result = self._derive_tags_from_text(caption or "")
                finally:
                    rgb.close()
        except getattr(Image, "DecompressionBombError", Exception) as exc:
            logger.warning("Skipping ML annotation for oversized image %s: %s", image_path, exc)
            return None

        return AnnotationResult(
            caption=caption,
            alt_text=caption,
            tags=tag_result["tags"],
            tag_scores=tag_result["scores"],
        )

    def _generate_caption(self, image: Image.Image) -> str | None:
        assert self._processor is not None
        assert self._caption_model is not None
        assert self._torch is not None
        assert self._device is not None

        inputs = self._processor(images=image, return_tensors="pt").to(self._device)
        with self._torch.no_grad():
            output_ids = self._caption_model.generate(
                **inputs,
                max_new_tokens=60,
                num_beams=5,
                no_repeat_ngram_size=3,
                repetition_penalty=1.2,
                early_stopping=True,
            )
        processor = cast(Any, self._processor)
        caption = processor.decode(output_ids[0], skip_special_tokens=True)
        caption = caption.strip()
        return caption or None

    def _derive_tags_from_text(self, text: str) -> TagResult:
        alias_map = _load_alias_map()
        stopwords = _load_stopwords()

        candidates: list[str] = []
        cleaned_text = (text or "").strip()
        if cleaned_text:
            nlp = _load_spacy()
            if nlp is not None:
                try:
                    doc = nlp(cleaned_text)
                    for chunk in doc.noun_chunks:
                        chunk_text = chunk.text.strip()
                        if chunk_text:
                            candidates.append(chunk_text)
                    for token in doc:
                        if token.pos_ in {"PROPN", "NOUN"} and not token.is_stop:
                            candidates.append(token.text)
                except Exception:
                    candidates.extend(_rule_based_terms(cleaned_text))
            else:
                candidates.extend(_rule_based_terms(cleaned_text))

        def base_key(term: str) -> str:
            lower = term.lower().strip()
            lower = re.sub(r"[_\-]+", " ", lower)
            lower = re.sub(r"\s+", " ", lower).strip()
            lower = alias_map.get(lower, lower)
            if lower.endswith("ies") and len(lower) > 3:
                lower = lower[:-3] + "y"
            elif lower.endswith("ses") and len(lower) > 3:
                lower = lower[:-2]
            elif lower.endswith("s") and not lower.endswith("ss"):
                lower = lower[:-1]
            return lower

        grouped: dict[str, tuple[str, float]] = {}
        for term in candidates:
            key = base_key(term)
            if not key or key in stopwords:
                continue
            score = float(grouped.get(key, ("", 0.0))[1] + 1.0)
            prev = grouped.get(key)
            if prev is None or score > prev[1] or (abs(score - prev[1]) <= 1e-9 and len(term) > len(prev[0])):
                grouped[key] = (term, score)

        ordered = sorted(grouped.items(), key=lambda item: (-item[1][1], item[1][0].lower()))
        selected = [surface for _, (surface, _) in ordered]
        if self._max_tags and len(selected) > self._max_tags:
            selected = selected[: self._max_tags]

        seen: set[str] = set()
        final: list[str] = []
        for tag in selected:
            fmt = tag.strip()
            low = fmt.lower()
            if low in seen:
                continue
            seen.add(low)
            final.append(fmt)

        scores = {tag: float(idx + 1) for idx, tag in enumerate(final)}
        return {"tags": final, "scores": scores}


def ml_timestamp() -> datetime:
    """Return a timezone-aware timestamp for ML metadata."""
    return datetime.now(tz=timezone.utc)


@lru_cache(maxsize=1)
def _load_stopwords() -> set[str]:
    """Load optional project-level tag stopwords from gallery/tag_stopwords.txt."""
    path = Path("gallery/tag_stopwords.txt")
    builtins = {"image", "photo", "picture"}
    words: set[str] = set(builtins)
    try:
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                term = line.strip().lower()
                if term and not term.startswith("#"):
                    words.add(term)
    except OSError:
        pass
    return words


@lru_cache(maxsize=1)
def _load_alias_map() -> dict[str, str]:
    """Load optional project-level tag aliases from gallery/tag_aliases.json."""
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


@lru_cache(maxsize=1)
def _load_spacy() -> Any | None:
    """Return a loaded spaCy model if available, otherwise None.

    Tries to import spaCy and load 'en_core_web_sm'. If missing, attempts a
    best-effort runtime download using importlib to access spacy.cli.download,
    then loads again. Returns None if unavailable.
    """
    try:
        import spacy
    except Exception:
        return None
    try:
        return spacy.load("en_core_web_sm")
    except Exception:
        # Try to download the small English model and load again
        try:
            import importlib
            cli = importlib.import_module("spacy.cli")
            downloader = getattr(cli, "download", None)
            if callable(downloader):
                downloader("en_core_web_sm")
                return spacy.load("en_core_web_sm")
        except Exception:
            return None
        return None


def _rule_based_terms(text: str) -> list[str]:
    """Heuristic extraction of keywords from text as a fallback.

    - Captures capitalized multi-word sequences (proper nouns)
    - Includes non-stopword alphabetic words >= 3 chars
    """
    terms: list[str] = []
    for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", text):
        terms.append(m.group(1))
    raw_words = re.findall(r"[A-Za-z]{3,}", text)
    common_stops = {
        "the","and","for","with","from","that","this","there","their","your","have","has","was","were","are","been","into","over","under","between","within","about","above","below","after","before","during","without","because","while","where","when","which","will","would","could","should","can","may","might"
    }
    for w in raw_words:
        if w.lower() not in common_stops:
            terms.append(w)
    return terms
