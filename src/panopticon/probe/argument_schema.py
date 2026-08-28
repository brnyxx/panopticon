"""Typed JSON-Schema value helpers for deterministic probe arguments."""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from typing import TypeAlias

JsonValue: TypeAlias = bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"] | None
Schema: TypeAlias = bool | dict[str, object]

KNOWN_DIALECTS = frozenset(
    {
        "https://json-schema.org/draft/2020-12/schema",
        "https://json-schema.org/draft/2020-12/schema#",
        "http://json-schema.org/draft-07/schema#",
    }
)


class UnsupportedSchemaError(Exception):
    pass


def schema_type(schema: dict[str, object]) -> str | None:
    raw = schema.get("type")
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        return next((item for item in raw if isinstance(item, str) and item != "null"), "null")
    return "object" if "properties" in schema else None


def number(schema: dict[str, object], *, integer: bool) -> int | float:
    try:
        multiple = Decimal(str(schema.get("multipleOf", 1 if integer else "0.1")))
        lower = Decimal(str(schema.get("minimum", schema.get("exclusiveMinimum", 0))))
        if "exclusiveMinimum" in schema:
            lower += multiple
        value = (lower / multiple).to_integral_value(rounding="ROUND_CEILING") * multiple
        upper_raw = schema.get("maximum", schema.get("exclusiveMaximum"))
        if upper_raw is not None:
            upper = Decimal(str(upper_raw))
            if "exclusiveMaximum" in schema:
                upper -= multiple
            if value > upper:
                raise UnsupportedSchemaError("UNSATISFIABLE_SCHEMA")
    except (InvalidOperation, ValueError, ZeroDivisionError):
        raise UnsupportedSchemaError("INVALID_SCHEMA") from None
    if integer:
        if value != value.to_integral_value():
            raise UnsupportedSchemaError("UNSATISFIABLE_SCHEMA")
        return int(value)
    result = float(value)
    if not math.isfinite(result):
        raise UnsupportedSchemaError("UNSATISFIABLE_SCHEMA")
    return result


def merge_all_of(schema: dict[str, object]) -> dict[str, object]:
    merged = {key: value for key, value in schema.items() if key != "allOf"}
    branches = schema.get("allOf")
    if not isinstance(branches, list) or not branches:
        raise UnsupportedSchemaError("UNSATISFIABLE_SCHEMA")
    for branch in branches:
        if not isinstance(branch, dict):
            raise UnsupportedSchemaError("UNPROBEABLE_SCHEMA")
        if "const" in merged and "const" in branch and merged["const"] != branch["const"]:
            raise UnsupportedSchemaError("UNSATISFIABLE_SCHEMA")
        for key, value in branch.items():
            if key == "properties" and isinstance(value, dict):
                current = merged.get(key, {})
                merged[key] = {**(current if isinstance(current, dict) else {}), **value}
            elif key == "required" and isinstance(value, list):
                current = merged.get(key, [])
                previous = current if isinstance(current, list) else []
                merged[key] = list(dict.fromkeys([*previous, *value]))
            else:
                merged[key] = value
    return merged


def non_negative_int(value: object, *, default: int) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise UnsupportedSchemaError("INVALID_SCHEMA")
    return value


def formatted_string(raw_format: object) -> str | None:
    if not isinstance(raw_format, str):
        return None
    return {
        "uri": "https://example.com/pano",
        "url": "https://example.com/pano",
        "email": "probe@example.com",
        "date": "2026-01-01",
        "date-time": "2026-01-01T00:00:00Z",
        "uuid": "00000000-0000-4000-8000-000000000000",
    }.get(raw_format)


def json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [json_value(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {str(key): json_value(item) for key, item in value.items()}
    raise UnsupportedSchemaError("INVALID_SCHEMA_VALUE")
