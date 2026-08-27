"""Every generated schema validates and round-trips its representative fixture."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import TypeVar

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from panopticon.models.schema import SchemaName, validate_runtime_json

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"
FIXTURES = ROOT / "tests" / "fixtures" / "schemas"
FormatValue = TypeVar("FormatValue")


def _is_utc_datetime(value: FormatValue) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.utcoffset() == timedelta(0)


def _format_checker() -> FormatChecker:
    checker = FormatChecker()
    checker.checks("date-time")(_is_utc_datetime)
    return checker


@pytest.mark.parametrize("name", tuple(name.value for name in SchemaName))
def test_representative_fixture_validates_and_round_trips(name: str) -> None:
    # Given: a shipped schema and its machine-consumed representative fixture.
    schema = json.loads((SCHEMAS / f"{name}.json").read_text())
    payload = (FIXTURES / f"{name}.json").read_text()

    # When: JSON Schema and the runtime model independently parse it.
    Draft202012Validator(schema, format_checker=_format_checker()).validate(json.loads(payload))
    record = validate_runtime_json(SchemaName(name), payload)
    reloaded = validate_runtime_json(SchemaName(name), record.model_dump_json())

    # Then: the typed persisted value is stable.
    assert reloaded == record


def test_absolute_home_path_rejected_in_event() -> None:
    # Given: a file event containing a real-home absolute path.
    schema = json.loads((SCHEMAS / "event.json").read_text())
    payload = json.loads((FIXTURES / "event.json").read_text())
    payload["path"] = "/Users/alice/.ssh/config"

    # When: active schema validation checks it.
    errors = list(
        Draft202012Validator(schema, format_checker=_format_checker()).iter_errors(payload)
    )

    # Then: the path boundary rejects the leak-prone value.
    assert errors
