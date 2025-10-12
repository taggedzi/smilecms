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

    source_dir: Path = Field(default=Path("media/raw"))
    output_dir: Path = Field(default=Path("media/derived"))
    profiles: list[DerivativeProfile] = Field(default_factory=_default_profiles)

    @field_validator("source_dir", "output_dir", mode="before")
    def _ensure_path(cls, value: Any) -> Path:
        return Path(value)

class Config(BaseModel):
    project_name: str = Field(default="SmileCMS Project")
    content_dir: Path = Field(default=Path("content"))
    media_dir: Path = Field(default=Path("media"))
    output_dir: Path = Field(default=Path("site"))
    templates_dir: Path = Field(default=Path("web"))
    cache_dir: Path = Field(default=Path(".cache"))
    media_processing: MediaProcessingConfig = Field(default_factory=MediaProcessingConfig)

    @field_validator("content_dir", "media_dir", "output_dir", "templates_dir", "cache_dir", mode="before")
    def _ensure_path(cls, value: Any) -> Path:
        return Path(value)

def load_config(path: str | Path) -> Config:
    config_path = Path(path)
    data: dict[str, Any] = {}
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    else:
        raise FileNotFoundError(config_path)
    return Config(**data)
