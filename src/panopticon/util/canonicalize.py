"""Versioned deterministic serialization and semantic comparison views."""

from __future__ import annotations

import json
from typing import Final

from pydantic import BaseModel, JsonValue, TypeAdapter

CANONICAL_VERSION: Final = "0.1"
_VOLATILE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "container_id",
        "created_at",
        "duration_ms",
        "first_seen",
        "observed_at",
        "pid",
        "timestamp",
        "ts",
    }
)
_JSON_ADAPTER: Final[TypeAdapter[JsonValue]] = TypeAdapter(JsonValue)


def _model_value(model: BaseModel) -> JsonValue:
    return _JSON_ADAPTER.validate_json(model.model_dump_json())


def _dump(value: JsonValue) -> bytes:
    text = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{text}\n".encode()


def canonical_json_bytes(model: BaseModel) -> bytes:
    """Serialize a typed model as deterministic canonical UTF-8 JSON."""
    return _dump(_model_value(model))


def canonical_json_text_bytes(text: str) -> bytes:
    """Validate and canonicalize an already-rendered JSON document."""
    return _dump(_JSON_ADAPTER.validate_json(text))


def _semantic(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {
            key: _semantic(child)
            for key, child in sorted(value.items())
            if key not in _VOLATILE_FIELDS
        }
    if isinstance(value, list):
        normalized = [_semantic(item) for item in value]
        return sorted(normalized, key=lambda item: _dump(item))
    return value


def semantic_json_bytes(model: BaseModel) -> bytes:
    """Build the stable semantic view while partitioning approved run volatility."""
    return _dump(_semantic(_model_value(model)))


def canonical_text_bytes(text: str) -> bytes:
    """Normalize line endings and require one terminal newline without altering content."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.endswith("\n"):
        normalized = f"{normalized}\n"
    return normalized.encode("utf-8")
