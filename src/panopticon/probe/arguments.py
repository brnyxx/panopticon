"""Deterministic, bounded JSON-Schema argument generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ArgumentResult:
    value: Any = None
    reason_code: str = "OK"
    supported: bool = True


class ArgumentGenerator:
    def __init__(self, seed: str = "panopticon-probe") -> None:
        self.seed = seed

    def generate(self, schema: dict[str, Any] | None, *, call_index: int = 1) -> ArgumentResult:
        try:
            return ArgumentResult(self._gen(schema or {}, call_index, ()))
        except _UnsupportedSchemaError as exc:
            return ArgumentResult({}, str(exc), False)

    def _gen(self, s: dict[str, Any], idx: int, stack: tuple[int, ...]) -> Any:
        sid = id(s)
        if sid in stack:
            raise _UnsupportedSchemaError("UNSUPPORTED_RECURSION")
        if "const" in s:
            return s["const"]
        if "enum" in s:
            vals = s["enum"]
            if not vals:
                raise _UnsupportedSchemaError("UNSATISFIABLE_SCHEMA")
            return vals[0]
        for comb in ("oneOf", "anyOf"):
            if comb in s:
                branches = s[comb]
                if not branches:
                    raise _UnsupportedSchemaError("UNSATISFIABLE_SCHEMA")
                return self._gen(branches[0], idx, stack)
        if "default" in s:
            return s["default"]
        typ = s.get("type")
        if isinstance(typ, list):
            typ = next((x for x in typ if x != "null"), typ[0] if typ else None)
        if typ == "object" or "properties" in s:
            props = s.get("properties", {})
            required = s.get("required", [])
            if not isinstance(props, dict) or not isinstance(required, list):
                return {}
            out = {}
            for name in required:
                if name not in props:
                    raise _UnsupportedSchemaError("UNSATISFIABLE_SCHEMA")
                out[name] = self._gen(props[name], idx, (*stack, sid))
            return out
        if typ == "array":
            if s.get("maxItems", 1) < 1:
                raise _UnsupportedSchemaError("UNSATISFIABLE_SCHEMA")
            item = self._gen(s.get("items", {}), idx, (*stack, sid))
            return [item]
        if typ in ("integer", "number"):
            value = s.get("minimum", s.get("exclusiveMinimum", 1))
            if s.get("maximum") is not None and value > s["maximum"]:
                raise _UnsupportedSchemaError("UNSATISFIABLE_SCHEMA")
            return value
        if typ == "boolean":
            return False
        if typ == "null":
            return None
        if typ == "string" or "format" in s:
            fmt = s.get("format")
            if fmt == "uri" or fmt == "url":
                value = "https://example.com/pano"
            elif fmt == "email":
                value = "probe@example.com"
            elif fmt == "date":
                value = "2026-01-01"
            else:
                name = str(s.get("title", "") + " " + s.get("description", "")).lower()
                value = (
                    "~/project/README.md"
                    if any(x in name for x in ("path", "file", "dir"))
                    else (
                        "https://example.com/pano"
                        if "url" in name
                        else (
                            "panopticon"
                            if any(x in name for x in ("query", "search", " q "))
                            else "panopticon-probe"
                        )
                    )
                )
            if idx > 1:
                value += f"-{idx}"
            if s.get("minLength", 0) > len(value):
                value += "x" * (s["minLength"] - len(value))
            if s.get("maxLength") is not None and s["maxLength"] < len(value):
                value = value[: s["maxLength"]]
            return value
        return {}


class _UnsupportedSchemaError(Exception):
    pass


def generate_arguments(
    schema: dict[str, Any] | None, seed: str = "panopticon-probe", *, call_index: int = 1
) -> ArgumentResult:
    return ArgumentGenerator(seed).generate(schema, call_index=call_index)
