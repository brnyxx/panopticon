"""Validate generated schemas and representative fixtures against runtime contracts."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final, TypeVar

from jsonschema import Draft202012Validator, FormatChecker

from panopticon.models.schema import (
    SchemaName,
    generate_schema_documents,
    validate_runtime_json,
)

ROOT: Final = Path(__file__).resolve().parents[1]
SCHEMAS: Final = ROOT / "schemas"
FIXTURES: Final = ROOT / "tests" / "fixtures" / "schemas"
FormatValue = TypeVar("FormatValue")


def _is_utc_datetime(value: FormatValue) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.utcoffset() == timedelta(0)


def schema_format_checker() -> FormatChecker:
    """Build the active checker, including UTC RFC 3339 date-time validation."""
    checker = FormatChecker()
    checker.checks("date-time")(_is_utc_datetime)
    return checker


def main() -> int:
    """Reject schema drift and validate each machine-consumed fixture twice."""
    first = generate_schema_documents()
    second = generate_schema_documents()
    if first != second:
        print("error  schema generation is nondeterministic")
        return 1

    for document in first:
        shipped = (SCHEMAS / document.name).read_text()
        if shipped != document.content:
            print(f"error  generated schema differs: {document.name}")
            return 1
        schema = json.loads(shipped)
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=schema_format_checker())
        fixture_path = FIXTURES / document.name
        payload = fixture_path.read_text()
        validator.validate(json.loads(payload))
        validate_runtime_json(SchemaName(fixture_path.stem), payload)
        print(f"ok  {document.name}")

    observation_schema = json.loads((SCHEMAS / "observation.json").read_text())
    remote_payload = (FIXTURES / "observation_remote.json").read_text()
    Draft202012Validator(observation_schema, format_checker=schema_format_checker()).validate(
        json.loads(remote_payload)
    )
    validate_runtime_json(SchemaName.OBSERVATION, remote_payload)
    print("ok  observation_remote.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
