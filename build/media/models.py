"""Domain models for media processing."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Set

from pydantic import BaseModel, ConfigDict, Field

from ..config import DerivativeProfile


class MediaDerivativeTask(BaseModel):
    """Single derivative generation task."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    source: Path = Field(description="Absolute path to the raw media asset.")
    destination: Path = Field(description="Destination path for the derivative.")
    profile: DerivativeProfile = Field(description="Derivative profile to apply.")
    media_path: str = Field(description="Original relative media path.")
    roles: Set[Literal["hero", "asset"]] = Field(
        default_factory=set, description="How the media is referenced."
    )
    documents: Set[str] = Field(default_factory=set, description="Slugs referencing this media.")

    def add_document(self, slug: str) -> None:
        self.documents.add(slug)

    def add_role(self, role: Literal["hero", "asset"]) -> None:
        self.roles.add(role)


class MediaPlan(BaseModel):
    """Aggregated derivative tasks for the build run."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tasks: list[MediaDerivativeTask] = Field(default_factory=list)
    static_assets: set[str] = Field(default_factory=set)

    def add_task(self, task: MediaDerivativeTask) -> None:
        self.tasks.append(task)

    def add_static_asset(self, path: str) -> None:
        self.static_assets.add(path)

    @property
    def asset_count(self) -> int:
        media_paths = {task.media_path for task in self.tasks}
        media_paths.update(self.static_assets)
        return len(media_paths)

    @property
    def profile_count(self) -> int:
        return len({task.profile.name for task in self.tasks})
