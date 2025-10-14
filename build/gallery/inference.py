"""ML-driven captioning and tagging helpers for gallery images."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PIL import Image

from ..config import Config

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AnnotationResult:
    """Captures raw outputs from BLIP/WD14 style inference."""

    caption: str | None
    alt_text: str | None
    tags: list[str]
    tag_scores: dict[str, float]
    rating: str | None
    confidence: float | None


class TaggingSession:
    """Manage ML model lifecycle for gallery tagging."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self.available = False
        self.failure_reason: str | None = None
        self.model_signature: str | None = None
        self._processor = None
        self._caption_model = None
        self._tagger = None
        self._torch = None
        self._device = None
        self._general_threshold = config.gallery.tagger_general_threshold
        self._character_threshold = config.gallery.tagger_character_threshold
        self._max_tags = config.gallery.tagging_max_tags

        if not config.gallery.tagging_enabled:
            self.failure_reason = "Tagging disabled via configuration."
            return

        cache_root = (config.cache_dir / "ml").expanduser()
        caption_cache = cache_root / "caption"
        tagger_cache = cache_root / "tagger"
        caption_cache.mkdir(parents=True, exist_ok=True)
        tagger_cache.mkdir(parents=True, exist_ok=True)

        try:
            from transformers import BlipForConditionalGeneration, BlipProcessor
        except ImportError as exc:
            self.failure_reason = (
                "transformers package is required for captioning but was not found."
            )
            logger.warning(self.failure_reason)
            logger.debug("transformers import failure: %s", exc, exc_info=True)
            return

        try:
            from huggingface_hub import hf_hub_download
        except ImportError:
            hf_hub_download = None

        try:
            from .wdtagger import Tagger
        except ImportError as exc:  # pragma: no cover - should not happen when bundled
            self.failure_reason = "Bundled wdtagger module could not be imported."
            logger.warning(self.failure_reason)
            logger.debug("wdtagger import failure: %s", exc, exc_info=True)
            return

        try:
            import torch
        except ImportError as exc:
            self.failure_reason = "PyTorch is required for ML tagging but is not installed."
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
            )
            caption_model = BlipForConditionalGeneration.from_pretrained(
                config.gallery.caption_model,
                cache_dir=str(caption_cache),
            )
            caption_model.to(device)
            caption_model.eval()
        except Exception as exc:  # pragma: no cover - model download paths hard to mock
            self.failure_reason = f"Failed to load caption model {config.gallery.caption_model}: {exc}"
            logger.warning(self.failure_reason)
            logger.debug("Caption model load error", exc_info=True)
            return

        selected_tags_path: str | None = None
        if hf_hub_download is not None:
            try:
                selected_tags_path = hf_hub_download(
                    repo_id=config.gallery.tagger_model,
                    filename="selected_tags.csv",
                    cache_dir=str(tagger_cache),
                )
            except Exception as exc:  # pragma: no cover - network/cache issues
                logger.warning("Could not download selected_tags.csv: %s", exc)

        try:
            tagger = Tagger(
                model_repo=config.gallery.tagger_model,
                cache_dir=str(tagger_cache),
                device=device.type,
                tags_csv=selected_tags_path,
            )
        except Exception as exc:  # pragma: no cover - depends on external assets
            self.failure_reason = f"Failed to load tagger model {config.gallery.tagger_model}: {exc}"
            logger.warning(self.failure_reason)
            logger.debug("Tagger model load error", exc_info=True)
            return

        self._processor = processor
        self._caption_model = caption_model
        self._tagger = tagger
        self._torch = torch
        self._device = device
        self.available = True
        self.model_signature = (
            f"caption:{config.gallery.caption_model}|tagger:{config.gallery.tagger_model}"
        )
        logger.debug(
            "Initialised tagging session with models %s (%s)",
            self.model_signature,
            device,
        )

    def annotate(self, image_path: Path) -> Optional[AnnotationResult]:
        """Return ML-generated metadata for an image, or None if unavailable."""
        if not self.available or not self._processor or not self._caption_model or not self._tagger:
            return None

        with Image.open(image_path) as base_image:
            rgb = base_image.convert("RGB")
            try:
                caption = self._generate_caption(rgb)
                tag_result = self._tag_image(rgb)
            finally:
                rgb.close()

        return AnnotationResult(
            caption=caption,
            alt_text=caption,
            tags=tag_result["tags"],
            tag_scores=tag_result["scores"],
            rating=tag_result["rating"],
            confidence=tag_result["confidence"],
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
            )
        caption = self._processor.decode(output_ids[0], skip_special_tokens=True)
        caption = caption.strip()
        return caption or None

    def _tag_image(self, image: Image.Image) -> dict[str, Optional[object]]:
        assert self._tagger is not None

        output = self._tagger.tag(
            image,
            general_threshold=self._general_threshold,
            character_threshold=self._character_threshold,
        )
        combined_scores: dict[str, float] = {}
        selected: list[str] = []

        def _ingest(items: dict[str, float], prefix: str = "", threshold: float = 0.0) -> None:
            ordered = sorted(items.items(), key=lambda item: item[1], reverse=True)
            for name, score in ordered:
                key = name
                if prefix and not name.startswith(prefix):
                    key = f"{prefix}{name}"
                if key.upper().startswith("LABEL_"):
                    continue
                combined_scores[key] = float(score)
                if score >= threshold:
                    selected.append(key)

        _ingest(output.general_tag_data, prefix="", threshold=self._general_threshold)
        _ingest(output.character_tag_data, prefix="character:", threshold=self._character_threshold)

        if self._max_tags and len(selected) > self._max_tags:
            selected = selected[: self._max_tags]

        selected = list(dict.fromkeys(selected))
        confidence = max((combined_scores.get(tag, 0.0) for tag in selected), default=None)

        rating_label: str | None = None
        if output.rating:
            rating_label, rating_score = max(
                output.rating.items(),
                key=lambda item: item[1],
            )
            combined_scores[rating_label] = float(rating_score)

        return {
            "tags": selected,
            "scores": combined_scores,
            "confidence": confidence,
            "rating": rating_label,
        }


def ml_timestamp() -> datetime:
    """Return a timezone-aware timestamp for ML metadata."""
    return datetime.now(tz=timezone.utc)
