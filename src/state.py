"""Helpers for tracking build inputs between runs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Mapping, Sequence

from .config import Config


STATE_FILENAME = "build-state.json"
STATE_VERSION = 1


@dataclass
class BuildState:
    """Snapshot of the previous build inputs and staged assets."""

    version: int
    fingerprints: Dict[str, str]
    staged_template_paths: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "fingerprints": self.fingerprints,
            "staged_template_paths": self.staged_template_paths,
        }

    @classmethod
    def empty(cls) -> "BuildState":
        return cls(version=STATE_VERSION, fingerprints={}, staged_template_paths=[])

    @classmethod
    def load(cls, path: Path) -> "BuildState":
        if not path.exists():
            return cls.empty()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return cls.empty()

        version = int(payload.get("version") or STATE_VERSION)
        fingerprints = dict(payload.get("fingerprints") or {})
        staged_paths = list(payload.get("staged_template_paths") or [])
        return cls(version=version, fingerprints=fingerprints, staged_template_paths=staged_paths)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


@dataclass
class ChangeSummary:
    """Description of which input groups have changed since the last build."""

    changed_keys: set[str]
    first_run: bool

    @property
    def has_changes(self) -> bool:
        return bool(self.changed_keys) or self.first_run


class BuildTracker:
    """Compute and persist build fingerprints for incremental rebuilds."""

    def __init__(self, config: Config, config_path: Path):
        self._config = config
        self._config_path = Path(config_path)
        self._state_path = config.cache_dir / STATE_FILENAME
        self._previous_state = BuildState.load(self._state_path)

    @property
    def previous_state(self) -> BuildState:
        return self._previous_state

    @property
    def previous_template_paths(self) -> set[Path]:
        output_root = self._config.output_dir
        paths: set[Path] = set()
        for entry in self._previous_state.staged_template_paths:
            candidate = output_root / Path(entry)
            paths.add(candidate)
        return paths

    def compute_fingerprints(self) -> Dict[str, str]:
        config = self._config
        return {
            "config_file": _hash_file(self._config_path),
            "config_values": _hash_text(config.model_dump_json()),
            "content_dir": _hash_tree(config.content_dir),
            "article_media_dir": _hash_tree(config.article_media_dir),
            "gallery_dir": _hash_tree(config.gallery.source_dir),
            "music_dir": _hash_tree(config.music.source_dir),
            "templates_dir": _hash_tree(config.resolved_templates_dir),
        }

    def summarize_changes(self, current: Mapping[str, str]) -> ChangeSummary:
        previous = self._previous_state.fingerprints
        changed = {key for key, value in current.items() if previous.get(key) != value}
        first_run = not bool(previous)
        return ChangeSummary(changed_keys=changed, first_run=first_run)

    def persist(self, fingerprints: Mapping[str, str], template_paths: Sequence[Path]) -> None:
        relative_paths = []
        for path in template_paths:
            try:
                relative = path.relative_to(self._config.output_dir)
            except ValueError:
                # Only persist paths living under the output directory.
                continue
            relative_paths.append(relative.as_posix())

        state = BuildState(
            version=STATE_VERSION,
            fingerprints=dict(fingerprints),
            staged_template_paths=sorted(relative_paths),
        )
        state.save(self._state_path)


def _hash_tree(root: Path) -> str:
    hasher = hashlib.sha256()
    if not root.exists():
        return hasher.hexdigest()

    for path in sorted(_iter_files(root)):
        relative = path.relative_to(root)
        stat = path.stat()
        hasher.update(relative.as_posix().encode("utf-8"))
        hasher.update(str(stat.st_mtime_ns).encode("utf-8"))
        hasher.update(str(stat.st_size).encode("utf-8"))
    return hasher.hexdigest()


def _iter_files(root: Path) -> Iterable[Path]:
    for entry in root.rglob("*"):
        if entry.is_file():
            yield entry


def _hash_file(path: Path) -> str:
    hasher = hashlib.sha256()
    if not path.exists():
        return hasher.hexdigest()
    hasher.update(path.read_bytes())
    return hasher.hexdigest()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
