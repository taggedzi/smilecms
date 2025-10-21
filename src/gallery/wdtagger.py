"""Lightweight WD14 tagger implementation bundled with the gallery pipeline."""

from __future__ import annotations

import csv
import dataclasses
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple, cast

import torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModelForImageClassification


@dataclasses.dataclass
class TaggerOutput:
    general_tag_data: Dict[str, float]
    character_tag_data: Dict[str, float]
    rating: Dict[str, float]


class Tagger:
    """Minimal WD14 tagger implemented with Hugging Face transformers.

    Mirrors the behaviour expected by the gallery inference module so we can
    avoid depending on external helper packages.
    """

    def __init__(
        self,
        model_repo: str = "SmilingWolf/wd-swinv2-tagger-v3",
        *,
        device: str | None = None,
        cache_dir: str | None = None,
        trust_remote_code: bool = False,
        revision: str | None = None,
        tags_csv: str | Path | None = None,
    ) -> None:
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"

        self.device = torch.device(device)
        processor_cls = cast(Any, AutoImageProcessor)
        self.processor = processor_cls.from_pretrained(
            model_repo,
            cache_dir=cache_dir,
            trust_remote_code=trust_remote_code,
            revision=revision,
        )
        self.model = AutoModelForImageClassification.from_pretrained(
            model_repo,
            cache_dir=cache_dir,
            trust_remote_code=trust_remote_code,
            revision=revision,
        )
        self.model.eval()
        self.model.to(self.device)

        self._label_categories = self._load_label_categories(tags_csv)

    def tag(
        self,
        image: Image.Image,
        *,
        general_threshold: float | None = None,
        character_threshold: float | None = None,
    ) -> TaggerOutput:
        """Return tag probabilities for a single Pillow image."""

        inputs = self.processor(images=image, return_tensors="pt")
        inputs = {key: value.to(self.device) for key, value in inputs.items()}

        with torch.no_grad():
            outputs = self.model(**inputs)

        logits = outputs.logits.float()
        probabilities = torch.sigmoid(logits).squeeze(0).cpu().tolist()

        general: Dict[str, float] = {}
        character: Dict[str, float] = {}
        rating: Dict[str, float] = {}

        for prob, (category, name) in zip(probabilities, self._label_categories):
            score = float(prob)
            if category == "character":
                character[name] = score
            elif category == "rating":
                rating[name] = score
            else:
                general[name] = score

        if general_threshold is not None:
            general = {
                tag: score
                for tag, score in general.items()
                if score >= general_threshold
            }
        if character_threshold is not None:
            character = {
                tag: score
                for tag, score in character.items()
                if score >= character_threshold
            }

        return TaggerOutput(
            general_tag_data=general,
            character_tag_data=character,
            rating=rating,
        )

    def _load_label_categories(
        self,
        tags_csv: str | Path | None,
    ) -> list[Tuple[str, str]]:
        """Load (category, tag) tuples aligned with model outputs.

        The SmilingWolf repositories ship a ``selected_tags.csv`` file whose row
        order matches the classifier head. We fall back to the generic Hugging
        Face label metadata when the CSV is unavailable.
        """

        candidates: list[Path] = []
        if tags_csv is not None:
            candidates.append(Path(tags_csv))

        module_default = Path(__file__).with_name("selected_tags.csv")
        if module_default.is_file():
            candidates.append(module_default)

        for candidate in candidates:
            if not candidate.is_file():
                continue
            try:
                records: list[Tuple[str, str]] = []
                with candidate.open("r", encoding="utf-8", newline="") as handle:
                    reader = csv.DictReader(handle)
                    for row in reader:
                        name = (row.get("name") or "").strip()
                        if not name:
                            records.append(("general", ""))
                            continue
                        cat_code = (row.get("category") or "").strip()
                        category = {
                            "0": "general",
                            "4": "character",
                            "9": "rating",
                        }.get(cat_code, "general")
                        if category == "rating" and not name.startswith("rating:"):
                            name = f"rating:{name}"
                        records.append((category, name))

                target = self.model.config.num_labels
                if records and len(records) >= target:
                    return records[:target]
            except OSError:
                continue

        # Fallback: derive placeholder labels from the Hugging Face config.
        label_categories: list[Tuple[str, str]] = []
        id2label = self.model.config.id2label or {}
        if isinstance(id2label, dict):
            collected: list[Tuple[int, Any]] = []
            for key, value in id2label.items():
                try:
                    index = int(key)
                except (TypeError, ValueError):
                    index = len(collected)
                collected.append((index, value))
            items: Iterable[Tuple[int, Any]] = sorted(
                collected,
                key=lambda item: item[0],
            )
        else:
            items = enumerate(id2label)

        for idx, raw_label in items:
            tag_name = str(raw_label).strip()
            if not tag_name:
                tag_name = f"label-{idx}"
            label_categories.append(("general", tag_name))

        return label_categories
