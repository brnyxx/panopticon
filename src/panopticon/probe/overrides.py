"""Typed manual probe-argument override boundary."""

from __future__ import annotations

import json

from .argument_schema import JsonValue, UnsupportedSchemaError, json_value


def parse_overrides(text: str) -> dict[str, dict[str, JsonValue]]:
    try:
        raw: object = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError("invalid override JSON") from error
    if not isinstance(raw, dict):
        raise ValueError("overrides must be an object")
    output: dict[str, dict[str, JsonValue]] = {}
    for tool, arguments in raw.items():
        if not isinstance(tool, str) or not isinstance(arguments, dict):
            raise ValueError("each override must map a tool to an object")
        try:
            output[tool] = {str(key): json_value(value) for key, value in arguments.items()}
        except UnsupportedSchemaError as error:
            raise ValueError("override contains a non-JSON value") from error
    return output
