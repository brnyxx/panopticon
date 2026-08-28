"""Deterministic, bounded JSON-Schema argument generation coverage."""

from __future__ import annotations

import pytest

from panopticon.probe.argument_schema import JsonValue
from panopticon.probe.arguments import generate_arguments
from panopticon.probe.driver import CallDriver, DriverStatus
from panopticon.probe.protocol import ProbeResult, ProbeStatus


def test_scalars_const_default_enum_and_null_are_deterministic() -> None:
    assert generate_arguments({"const": "fixed"}).value == "fixed"
    assert generate_arguments({"default": 7}).value == 7
    assert generate_arguments({"enum": ["a", "b"]}).value == "a"
    assert generate_arguments({"type": "null"}).value is None
    assert generate_arguments({"enum": []}).reason_code == "UNSATISFIABLE_SCHEMA"


def test_combinators_bounds_multiple_pattern_and_formats() -> None:
    assert generate_arguments({"oneOf": [{"const": 3}, {"const": 4}]}).value == 3
    assert generate_arguments({"anyOf": [{"type": "boolean"}]}).value is False
    assert (
        generate_arguments({"type": "integer", "minimum": 4, "maximum": 8, "multipleOf": 2}).value
        == 4
    )
    assert generate_arguments({"type": "number", "exclusiveMinimum": 2, "maximum": 3}).value == 2.1
    assert (
        len(
            generate_arguments(
                {"type": "string", "minLength": 20, "maxLength": 20, "pattern": "x+"}
            ).value
        )
        == 20
    )
    assert generate_arguments({"format": "email"}).value == "probe@example.com"
    assert generate_arguments({"format": "uri"}).value.startswith("https://")


def test_arrays_tuples_required_objects_and_call_index_order() -> None:
    schema = {
        "type": "object",
        "required": ["id", "tags"],
        "properties": {
            "id": {"type": "integer", "minimum": 1},
            "tags": {"type": "array", "items": {"const": "tag"}},
        },
    }
    assert generate_arguments(schema).value == {"id": 1, "tags": ["tag"]}
    assert generate_arguments(
        {"type": "array", "prefixItems": [{"const": 1}, {"const": 2}], "items": False}
    ).value == [1, 2]
    assert generate_arguments({"type": "string"}, call_index=2).value == "panopticon-probe-2"
    assert generate_arguments({"type": "array", "minItems": 2, "items": {"const": 1}}).value == [
        1,
        1,
    ]
    assert (
        generate_arguments(
            {"type": "object", "required": ["missing"], "properties": {}}
        ).reason_code
        == "UNSATISFIABLE_SCHEMA"
    )


def test_unknown_dialect_recursion_and_unsatisfiable_states_are_visible() -> None:
    recursive: dict[str, object] = {"type": "object"}
    recursive["properties"] = {"self": recursive}
    recursive["required"] = ["self"]
    assert generate_arguments(recursive).reason_code == "UNSUPPORTED_RECURSION"
    assert generate_arguments({"type": "array", "maxItems": 0}).value == []
    assert (
        generate_arguments(
            {"$schema": "https://unknown.example/dialect", "type": "object"}
        ).reason_code
        == "UNSUPPORTED_DIALECT"
    )
    assert (
        generate_arguments({"allOf": [{"const": 1}, {"const": 2}]}).reason_code
        == "UNSATISFIABLE_SCHEMA"
    )


def test_local_refs_invalid_defaults_and_seeded_identity_are_bounded() -> None:
    referenced = {
        "$defs": {"identifier": {"type": "integer", "minimum": 4}},
        "$ref": "#/$defs/identifier",
    }
    invalid_default = {"type": "integer", "default": "not-an-integer"}

    assert generate_arguments(referenced).value == 4
    assert generate_arguments(invalid_default).reason_code == "UNPROBEABLE_SCHEMA"
    assert generate_arguments({"type": "string"}, seed="server-a") == generate_arguments(
        {"type": "string"},
        seed="server-a",
    )
    assert (
        generate_arguments({"type": "string"}, seed="server-a").value
        != generate_arguments(
            {"type": "string"},
            seed="server-b",
        ).value
    )


@pytest.mark.asyncio
async def test_impossible_recursive_schema_is_unprobeable_and_not_called() -> None:
    schema: dict[str, object] = {"type": "object"}
    schema["properties"] = {"self": schema}
    schema["required"] = ["self"]

    class RecordingClient:
        def __init__(self) -> None:
            self.called = False

        async def list_paginated(
            self,
            _method: str,
            *,
            timeout: float | None = None,
        ) -> ProbeResult:
            del timeout
            return ProbeResult(ProbeStatus.COMPLETE, "OK", {"tools": []})

        async def request(
            self,
            _method: str,
            params: dict[str, JsonValue] | None = None,
            *,
            timeout: float | None = None,
        ) -> ProbeResult:
            del params, timeout
            self.called = True
            return ProbeResult(ProbeStatus.COMPLETE, "OK", {})

    client = RecordingClient()
    result = await CallDriver(client).run([{"name": "recursive", "inputSchema": schema}])

    assert result.status is DriverStatus.PARTIAL
    assert result.calls[0].reason_code == "UNSUPPORTED_RECURSION"
    assert not client.called
