"""Schema validation helpers for build artifacts."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any
from importlib import resources
from jsonschema import Draft202012Validator

from .content import ContentDocument

SCHEMA_PACKAGE = "build.schemas"
CONTENT_SCHEMA_NAME = "content_post.schema.json"


class DocumentValidationError(ValueError):
    """Raised when a content document fails schema validation."""

    def __init__(self, message: str, *, path: str | None = None) -> None:
        super().__init__(message)
        self.path = path


def validate_document(document: ContentDocument) -> None:
    """Validate a content document against the canonical JSON schema."""
    data = document.model_dump(mode="json")
    validator = _get_content_validator()
    errors = sorted(validator.iter_errors(data), key=lambda err: err.path)
    if errors:
        first = errors[0]
        pointer = "/".join(str(elem) for elem in first.path)
        source_path = document.source_path
        message = f"{source_path}: {first.message}"
        if pointer:
            message += f" (at {pointer})"
        raise DocumentValidationError(message, path=pointer or None)


@lru_cache(maxsize=1)
def _get_content_validator() -> Draft202012Validator:
    schema = _load_schema(CONTENT_SCHEMA_NAME)
    return Draft202012Validator(schema)


def _load_schema(name: str) -> dict[str, Any]:
    with resources.files(SCHEMA_PACKAGE).joinpath(name).open("r", encoding="utf-8") as handle:
        return json.load(handle)
