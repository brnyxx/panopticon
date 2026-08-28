"""Explicit idempotent baseline migrations through the 1.0 freeze."""

from __future__ import annotations

import json
from typing import Any

from panopticon.models.artifacts import Baseline


def _upgrade_schema_versions(value: Any) -> Any:
    if isinstance(value, dict):
        upgraded = {key: _upgrade_schema_versions(item) for key, item in value.items()}
        if upgraded.get("schema_version") == "0.1":
            upgraded["schema_version"] = "1.0"
        return upgraded
    if isinstance(value, list):
        return [_upgrade_schema_versions(item) for item in value]
    return value


def migrate_baseline_json(payload: str) -> Baseline:
    """Dispatch shipped development versions and converge idempotently on 1.0."""
    raw: Any = json.loads(payload)
    if not isinstance(raw, dict):
        return Baseline.model_validate(raw)

    version = raw.get("schema_version")
    if version == "0.0":
        raw = {**raw, "schema_version": "0.1", "label": None}
    upgraded = _upgrade_schema_versions(raw) if version in {"0.0", "0.1"} else raw
    return Baseline.model_validate_json(json.dumps(upgraded))
