from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class DerivativeProfile(BaseModel):
    """Desired output variant for image/video assets."""

    name: str
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    format: str = Field(default="webp")
    quality: int = Field(default=80, ge=1, le=100)


def _default_profiles() -> list["DerivativeProfile"]:
    return [
        DerivativeProfile(name="thumb", width=320, height=320, format="webp", quality=75),
        DerivativeProfile(name="large", width=1920, format="jpg", quality=85),
    ]


class MediaProcessingConfig(BaseModel):
    """Configuration for media derivative generation."""

    source_dir: Path = Field(default=Path("content/media"))
    output_dir: Path = Field(default=Path("media/derived"))
    profiles: list[DerivativeProfile] = Field(default_factory=_default_profiles)

    @field_validator("source_dir", "output_dir", mode="before")
    def _ensure_path(cls, value: Any) -> Path:
        return Path(value)


class GalleryConfig(BaseModel):
    """Configuration for gallery collection ingestion and publication."""

    source_dir: Path = Field(default=Path("media/image_gallery_raw"))
    metadata_filename: str = Field(
        default="collection.json",
        description="Filename for the collection-level sidecar stored inside each collection.",
    )
    image_sidecar_extension: str = Field(
        default=".json",
        description="Extension used for image sidecars (same stem as image file).",
    )
    data_subdir: str = Field(
        default="data/gallery",
        description="Path (relative to site output) for exported gallery data files.",
    )
    llm_enabled: bool = Field(
        default=True,
        description="Toggle automatic LLM-based metadata cleanup.",
    )
    llm_prompt_path: Path | None = Field(
        default=None,
        description="Optional path to a custom prompt template used for metadata cleanup.",
    )
    tagging_enabled: bool = Field(
        default=True,
        description="Enable ML-powered captioning and tagging for gallery images.",
    )
    caption_model: str = Field(
        default="Salesforce/blip-image-captioning-base",
        description="Hugging Face model identifier used for image caption generation.",
    )
    tagger_model: str = Field(
        default="SmilingWolf/wd-swinv2-tagger-v3",
        description="Hugging Face model identifier used for WD14-compatible tagging.",
    )
    tagger_general_threshold: float = Field(
        default=0.35,
        description="Minimum probability for general tags to be accepted.",
    )
    tagger_character_threshold: float = Field(
        default=0.85,
        description="Minimum probability for character tags to be accepted.",
    )
    tagging_max_tags: int = Field(
        default=48,
        ge=1,
        description="Maximum number of tags to store from the ML tagging stage.",
    )
    tagging_device: str | None = Field(
        default=None,
        description="Optional torch device string (e.g. 'cuda', 'cpu') for ML inference.",
    )
    profile_map: dict[str, str] = Field(
        default_factory=lambda: {"thumbnail": "thumb", "web": "large", "download": "large"},
        description="Mapping from semantic derivative roles to configured profile names.",
    )

    @field_validator("source_dir", "llm_prompt_path", mode="before")
    def _ensure_path(cls, value: Any) -> Path | None:
        if value is None:
            return None
        return Path(value)

    @field_validator("image_sidecar_extension")
    def _normalize_extension(cls, value: str) -> str:
        text = value.strip()
        if not text:
            return ".json"
        if not text.startswith("."):
            text = f".{text}"
        return text.lower()

    @field_validator("tagger_general_threshold", "tagger_character_threshold", mode="before")
    def _normalize_threshold(cls, value: Any) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            raise ValueError("Tagger thresholds must be numeric values between 0 and 1.") from None
        if numeric < 0 or numeric > 1:
            raise ValueError("Tagger thresholds must be between 0 and 1.")
        return numeric


class MusicConfig(BaseModel):
    """Configuration for music collection ingestion."""

    source_dir: Path = Field(default=Path("media/music_collection"))
    metadata_filename: str = Field(default="meta.yml")
    data_subdir: str = Field(
        default="data/music",
        description="Path (relative to site output) for exported music datasets.",
    )

    @field_validator("source_dir", mode="before")
    def _ensure_path(cls, value: Any) -> Path:
        return Path(value)


class FeedConfig(BaseModel):
    """Options controlling feed generation."""

    enabled: bool = Field(
        default=True,
        description="Toggle syndication feed generation.",
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Maximum number of entries to include per feed.",
    )
    base_url: str | None = Field(
        default=None,
        description="Canonical site URL used for absolute links (e.g., 'https://example.com').",
    )
    site_config_path: Path | None = Field(
        default=None,
        description="Optional override for the site metadata JSON used when populating feed metadata.",
    )
    output_subdir: Path | None = Field(
        default=None,
        description="Optional subdirectory (relative to output_dir) where feeds should be written.",
    )

    @field_validator("site_config_path", "output_subdir", mode="before")
    def _ensure_path(cls, value: Any) -> Path | None:
        if value is None:
            return None
        return Path(value)


class Config(BaseModel):
    project_name: str = Field(default="SmileCMS Project")
    content_dir: Path = Field(default=Path("content"))
    media_dir: Path = Field(default=Path("media"))
    article_media_dir: Path = Field(default=Path("content/media"))
    output_dir: Path = Field(default=Path("site"))
    templates_dir: Path = Field(default=Path("web"))
    cache_dir: Path = Field(default=Path(".cache"))
    media_processing: MediaProcessingConfig = Field(default_factory=MediaProcessingConfig)
    gallery: GalleryConfig = Field(default_factory=GalleryConfig)
    music: MusicConfig = Field(default_factory=MusicConfig)
    feeds: FeedConfig = Field(default_factory=FeedConfig)

    @field_validator(
        "content_dir",
        "media_dir",
        "article_media_dir",
        "output_dir",
        "templates_dir",
        "cache_dir",
        mode="before",
    )
    def _ensure_path(cls, value: Any) -> Path:
        return Path(value)

    @property
    def media_mounts(self) -> list[tuple[str, Path]]:
        return [
            ("media", self.article_media_dir),
            ("gallery", self.gallery.source_dir),
            ("audio", self.music.source_dir),
        ]


def load_config(path: str | Path) -> Config:
    config_path = Path(path)
    data: dict[str, Any] = {}
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    else:
        raise FileNotFoundError(config_path)
    return Config(**data)
