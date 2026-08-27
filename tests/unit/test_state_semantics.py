"""Stage status, reason, coverage, and protocol-era combinations are exhaustive."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from panopticon.models import Observation, StageResult

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "schemas"
STAGE_ADAPTER: TypeAdapter[StageResult] = TypeAdapter(StageResult)


def test_stage_status_has_exactly_seven_values() -> None:
    # Given: the machine-consumed JSON schema for the exhaustive stage union.
    schema = STAGE_ADAPTER.json_schema()

    # When: status constants are collected from every variant.
    definitions = schema["$defs"]
    statuses = {
        definitions[variant["$ref"].rsplit("/", maxsplit=1)[-1]]["properties"]["status"]["const"]
        for variant in schema["oneOf"]
    }

    # Then: domain reasons do not widen the shared stage status enum.
    assert statuses == {
        "COMPLETE",
        "PARTIAL",
        "INCOMPLETE",
        "FAILED",
        "UNSUPPORTED",
        "SKIPPED",
        "NOT_REQUESTED",
    }
    assert "SKIPPED_DESTRUCTIVE" not in statuses


def test_status_reason_and_overall_coverage_combinations_are_enforced() -> None:
    # Given: an invalid status/reason pair and a complete overall state with partial coverage.
    invalid_stage = '{"status":"COMPLETE","reason_code":"SKIPPED_DESTRUCTIVE","diagnostics":[]}'
    payload = json.loads((FIXTURES / "observation.json").read_text())
    payload["state"]["overall"] = {
        "status": "COMPLETE",
        "reason_code": "COMPLETED",
        "diagnostics": [],
    }
    payload["state"]["coverage"]["file"] = {
        "status": "PARTIAL",
        "reason_code": "PARTIAL_COVERAGE",
        "diagnostics": [],
    }

    # When / Then: both boundary violations are rejected.
    with pytest.raises(ValidationError):
        STAGE_ADAPTER.validate_json(invalid_stage)
    with pytest.raises(ValidationError) as coverage_error:
        Observation.model_validate_json(json.dumps(payload))
    assert coverage_error.value.errors()[0]["type"] == "value_error"


def test_protocol_era_stage_transitions_are_enforced() -> None:
    # Given: a modern observation that incorrectly performs the legacy handshake stage.
    payload = json.loads((FIXTURES / "observation.json").read_text())
    payload["state"]["stages"]["handshake"] = {
        "status": "COMPLETE",
        "reason_code": "COMPLETED",
        "diagnostics": [],
    }

    # When / Then: the modern-to-legacy transition mismatch is rejected.
    with pytest.raises(ValidationError) as transition_error:
        Observation.model_validate_json(json.dumps(payload))
    assert transition_error.value.errors()[0]["type"] == "value_error"
