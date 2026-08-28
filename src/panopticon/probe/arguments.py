"""Deterministic, bounded JSON-Schema argument generation."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError

from .argument_schema import (
    KNOWN_DIALECTS,
    JsonValue,
    Schema,
    UnsupportedSchemaError,
    formatted_string,
    json_value,
    merge_all_of,
    non_negative_int,
    number,
    schema_type,
)


@dataclass(frozen=True, slots=True)
class ArgumentResult:
    value: JsonValue = None
    reason_code: str = "OK"
    supported: bool = True


class ArgumentGenerator:
    def __init__(self, seed: str = "panopticon-probe", *, max_depth: int = 32) -> None:
        if not seed or max_depth < 1:
            raise ValueError("argument generation requires a seed and positive depth")
        self.seed = seed
        self.max_depth = max_depth

    def generate(self, schema: Schema | None, *, call_index: int = 1) -> ArgumentResult:
        root: Schema = schema if schema is not None else {}
        if isinstance(root, dict):
            dialect = root.get("$schema")
            if isinstance(dialect, str) and dialect not in KNOWN_DIALECTS:
                return ArgumentResult({}, "UNSUPPORTED_DIALECT", False)
        try:
            Draft202012Validator.check_schema(root)
            value = self._generate(root, root, call_index, (), 0)
            Draft202012Validator(root, format_checker=FormatChecker()).validate(value)
        except UnsupportedSchemaError as error:
            return ArgumentResult({}, str(error), False)
        except RecursionError:
            return ArgumentResult({}, "UNSUPPORTED_RECURSION", False)
        except SchemaError:
            return ArgumentResult({}, "INVALID_SCHEMA", False)
        except ValidationError:
            return ArgumentResult({}, "UNPROBEABLE_SCHEMA", False)
        return ArgumentResult(value)

    def _generate(
        self,
        schema: Schema,
        root: Schema,
        call_index: int,
        stack: tuple[int, ...],
        depth: int,
        name_hint: str | None = None,
    ) -> JsonValue:
        if schema is False:
            raise UnsupportedSchemaError("UNSATISFIABLE_SCHEMA")
        if schema is True:
            return {}
        if depth >= self.max_depth or id(schema) in stack:
            raise UnsupportedSchemaError("UNSUPPORTED_RECURSION")
        next_stack = (*stack, id(schema))
        if "$ref" in schema:
            target = self._resolve_ref(schema["$ref"], root)
            return self._generate(target, root, call_index, next_stack, depth + 1, name_hint)
        if "const" in schema:
            return json_value(schema["const"])
        if "enum" in schema:
            values = schema["enum"]
            if not isinstance(values, list) or not values:
                raise UnsupportedSchemaError("UNSATISFIABLE_SCHEMA")
            return json_value(values[0])
        if "default" in schema:
            return json_value(schema["default"])
        for combinator in ("oneOf", "anyOf"):
            branches = schema.get(combinator)
            if isinstance(branches, list):
                return self._combinator(schema, branches, root, call_index, next_stack, depth)
        if isinstance(schema.get("allOf"), list):
            merged = merge_all_of(schema)
            return self._generate(merged, root, call_index, next_stack, depth + 1, name_hint)
        kind = schema_type(schema)
        if kind == "object":
            return self._object(schema, root, call_index, next_stack, depth)
        if kind == "array":
            return self._array(schema, root, call_index, next_stack, depth)
        if kind in {"integer", "number"}:
            return number(schema, integer=kind == "integer")
        if kind == "boolean":
            return False
        if kind == "null":
            return None
        if kind == "string" or "format" in schema or "pattern" in schema:
            return self._string(schema, call_index, name_hint)
        return {}

    def _combinator(
        self,
        schema: dict[str, object],
        branches: list[object],
        root: Schema,
        call_index: int,
        stack: tuple[int, ...],
        depth: int,
        name_hint: str | None = None,
    ) -> JsonValue:
        for branch in branches:
            if not isinstance(branch, (bool, dict)):
                continue
            try:
                candidate = self._generate(branch, root, call_index, stack, depth + 1, name_hint)
                Draft202012Validator(schema).validate(candidate)
            except (ValidationError, UnsupportedSchemaError):
                continue
            return candidate
        raise UnsupportedSchemaError("UNSATISFIABLE_SCHEMA")

    def _object(
        self,
        schema: dict[str, object],
        root: Schema,
        call_index: int,
        stack: tuple[int, ...],
        depth: int,
    ) -> dict[str, JsonValue]:
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(properties, dict) or not isinstance(required, list):
            raise UnsupportedSchemaError("INVALID_SCHEMA")
        output: dict[str, JsonValue] = {}
        for raw_name in required:
            if not isinstance(raw_name, str) or raw_name not in properties:
                raise UnsupportedSchemaError("UNSATISFIABLE_SCHEMA")
            child = properties[raw_name]
            if not isinstance(child, (bool, dict)):
                raise UnsupportedSchemaError("INVALID_SCHEMA")
            output[raw_name] = self._generate(child, root, call_index, stack, depth + 1, raw_name)
        return output

    def _array(
        self,
        schema: dict[str, object],
        root: Schema,
        call_index: int,
        stack: tuple[int, ...],
        depth: int,
    ) -> list[JsonValue]:
        minimum = non_negative_int(schema.get("minItems"), default=0)
        prefix = schema.get("prefixItems", [])
        prefix_items = prefix if isinstance(prefix, list) else []
        items = schema.get("items", {})
        maximum = non_negative_int(
            schema.get("maxItems"),
            default=max(1, minimum, len(prefix_items)),
        )
        target = max(minimum, len(prefix_items))
        if target == 0 and items is not False and maximum > 0:
            target = 1
        if target > maximum:
            raise UnsupportedSchemaError("UNSATISFIABLE_SCHEMA")
        output: list[JsonValue] = []
        for index in range(target):
            child = prefix_items[index] if index < len(prefix_items) else items
            if not isinstance(child, (bool, dict)):
                raise UnsupportedSchemaError("INVALID_SCHEMA")
            output.append(self._generate(child, root, call_index + index, stack, depth + 1))
        return output

    def _string(
        self, schema: dict[str, object], call_index: int, name_hint: str | None = None
    ) -> str:
        minimum = non_negative_int(schema.get("minLength"), default=0)
        maximum = non_negative_int(schema.get("maxLength"), default=max(64, minimum))
        if minimum > maximum:
            raise UnsupportedSchemaError("UNSATISFIABLE_SCHEMA")
        value = formatted_string(schema.get("format"))
        if not value:
            lowered = (name_hint or "").lower()
            if any(token in lowered for token in ("path", "file", "dir")):
                value = "~/project/README.md"
            elif lowered in {"url", "uri"}:
                value = "https://example.com/pano"
            elif any(token in lowered for token in ("query", "search", "q")):
                value = "panopticon"
            else:
                value = self._seeded_text(call_index)
        if call_index > 1 and value in {
            "~/project/README.md",
            "https://example.com/pano",
            "panopticon",
        }:
            value = f"{value}-{call_index}"
        pattern = schema.get("pattern")
        candidates = (
            value,
            "x" * max(1, minimum),
            "a" * max(1, minimum),
            "0" * max(1, minimum),
        )
        if isinstance(pattern, str):
            value = next(
                (candidate for candidate in candidates if re.search(pattern, candidate)), ""
            )
            if not value:
                raise UnsupportedSchemaError("UNPROBEABLE_SCHEMA")
        if len(value) < minimum:
            value += "x" * (minimum - len(value))
        return value[:maximum]

    def _seeded_text(self, call_index: int) -> str:
        if self.seed == "panopticon-probe":
            base = self.seed
        else:
            digest = hashlib.sha256(self.seed.encode()).hexdigest()[:12]
            base = f"panopticon-{digest}"
        return base if call_index == 1 else f"{base}-{call_index}"

    @staticmethod
    def _resolve_ref(reference: object, root: Schema) -> Schema:
        if not isinstance(reference, str) or not reference.startswith("#/"):
            raise UnsupportedSchemaError("UNSUPPORTED_REFERENCE")
        current: object = root
        for token in reference[2:].split("/"):
            token = token.replace("~1", "/").replace("~0", "~")
            if not isinstance(current, dict) or token not in current:
                raise UnsupportedSchemaError("UNRESOLVED_REFERENCE")
            current = current[token]
        if not isinstance(current, (bool, dict)):
            raise UnsupportedSchemaError("INVALID_SCHEMA")
        return current


def generate_arguments(
    schema: Schema | None,
    seed: str = "panopticon-probe",
    *,
    call_index: int = 1,
) -> ArgumentResult:
    return ArgumentGenerator(seed).generate(schema, call_index=call_index)
