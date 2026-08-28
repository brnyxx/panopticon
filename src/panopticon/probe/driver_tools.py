"""Normalize deterministic MCP tool definitions for the call driver."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .argument_schema import Schema


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    schema: Schema
    destructive: bool = False


def tool_definition(value: object) -> ToolDefinition | None:
    if not isinstance(value, dict):
        return None
    name = value.get("name")
    raw_schema = value.get("inputSchema", {})
    if not isinstance(name, str) or not name or not isinstance(raw_schema, (bool, dict)):
        return None
    annotations = value.get("annotations", {})
    annotated = isinstance(annotations, dict) and annotations.get("destructiveHint") is True
    inferred = re.search(r"(?:delete|remove|write|execute|shell|send|publish)", name, re.I)
    return ToolDefinition(name, raw_schema, annotated or inferred is not None)


__all__ = ["ToolDefinition", "tool_definition"]
