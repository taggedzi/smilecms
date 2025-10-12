from pathlib import Path
from typing import Any
import yaml
from pydantic import BaseModel, Field, field_validator

class Config(BaseModel):
    project_name: str = Field(default="SmileCMS Project")
    content_dir: Path = Field(default=Path("content"))
    media_dir: Path = Field(default=Path("media"))
    output_dir: Path = Field(default=Path("site"))
    templates_dir: Path = Field(default=Path("web"))
    cache_dir: Path = Field(default=Path(".cache"))

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
