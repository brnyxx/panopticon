"""Deterministic, bounded JSON-Schema argument generation coverage."""

from __future__ import annotations

from panopticon.probe.arguments import generate_arguments


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
    assert generate_arguments({"type": "number", "exclusiveMinimum": 2, "maximum": 3}).value == 2
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
    ).value == [1]
    assert generate_arguments({"type": "string"}, call_index=2).value == "panopticon-probe-2"
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
    assert (
        generate_arguments({"type": "array", "maxItems": 0}).reason_code == "UNSATISFIABLE_SCHEMA"
    )
    assert (
        generate_arguments({"type": "integer", "minimum": 9, "maximum": 2}).reason_code
        == "UNSATISFIABLE_SCHEMA"
    )
    assert generate_arguments(
        {"$schema": "https://unknown.example/dialect", "type": "object"}
    ).supported
    assert generate_arguments({"allOf": [{"const": 1}, {"const": 2}]}).value == {}
