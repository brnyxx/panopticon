# Copyright (c) 2026 MCP Sentinel contributors
# SPDX-License-Identifier: MIT
"""AST-only MCP tool metadata extraction; target code is never imported."""

from __future__ import annotations

import ast
from pathlib import Path

from pydantic import Field, JsonValue

from panopticon.models.common import NonEmptyStr, StrictModel


class ToolMetadata(StrictModel):
    name: NonEmptyStr
    description: str | None = None
    input_schema: dict[str, JsonValue] = Field(default_factory=dict)
    path: NonEmptyStr
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class ToolCatalog(StrictModel):
    tools: tuple[ToolMetadata, ...] = ()
    warnings: tuple[str, ...] = ()

    def for_location(self, path: str, line: int) -> ToolMetadata | None:
        return next(
            (t for t in self.tools if t.path == path and t.start_line <= line <= t.end_line), None
        )


def extract_tool_catalog(root: Path, ignore_paths: tuple[str, ...] = ()) -> ToolCatalog:
    found: dict[str, ToolMetadata] = {}
    warnings: list[str] = []
    ignored = set(ignore_paths)
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            warnings.append("SYMLINK_SKIPPED")
            continue
        if rel in ignored or any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                _decorator(d) for d in node.decorator_list
            ):
                found.setdefault(
                    node.name,
                    ToolMetadata(
                        name=node.name,
                        description=ast.get_docstring(node),
                        input_schema=_signature(node),
                        path=rel,
                        start_line=node.lineno,
                        end_line=node.end_lineno or node.lineno,
                    ),
                )
            if isinstance(node, ast.If):
                name = _dispatcher(node.test)
                if name:
                    found.setdefault(
                        name,
                        ToolMetadata(
                            name=name,
                            path=rel,
                            start_line=node.lineno,
                            end_line=node.end_lineno or node.lineno,
                            input_schema={
                                "type": "object",
                                "properties": {},
                                "additionalProperties": False,
                            },
                        ),
                    )
    return ToolCatalog(
        tools=tuple(sorted(found.values(), key=lambda t: (t.name, t.path))),
        warnings=tuple(warnings),
    )


def _decorator(node: ast.expr) -> bool:
    value = node.func if isinstance(node, ast.Call) else node
    return isinstance(value, ast.Attribute) and value.attr == "tool"


def _dispatcher(node: ast.expr) -> str | None:
    if (
        not isinstance(node, ast.Compare)
        or len(node.ops) != 1
        or not isinstance(node.ops[0], ast.Eq)
        or len(node.comparators) != 1
    ):
        return None
    sides = (node.left, node.comparators[0])
    variable = any(isinstance(s, ast.Name) and s.id in {"name", "tool_name"} for s in sides)
    literals = [s.value for s in sides if isinstance(s, ast.Constant) and isinstance(s.value, str)]
    return literals[0] if variable and literals else None


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, JsonValue]:
    props: dict[str, JsonValue] = {}
    required: list[JsonValue] = []
    args = [*node.args.posonlyargs, *node.args.args]
    offset = len(args) - len(node.args.defaults)
    for i, a in enumerate(args):
        props[a.arg] = _annotation(a.annotation)
        required.extend([a.arg] if i < offset else [])
    for a, d in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True):
        props[a.arg] = _annotation(a.annotation)
        required.extend([a.arg] if d is None else [])
    result: dict[str, JsonValue] = {
        "type": "object",
        "properties": props,
        "additionalProperties": False,
    }
    if required:
        result["required"] = required
    return result


def _annotation(node: ast.expr | None) -> dict[str, JsonValue]:
    if isinstance(node, ast.Name):
        return {
            "type": {"str": "string", "int": "integer", "float": "number", "bool": "boolean"}.get(
                node.id, "string"
            )
        }
    if isinstance(node, ast.Subscript):
        return (
            {"type": "array", "items": {}}
            if _name(node.value) in {"list", "tuple", "set"}
            else {"type": "object"}
        )
    return {}


def _name(node: ast.expr) -> str:
    return (
        node.id
        if isinstance(node, ast.Name)
        else node.attr
        if isinstance(node, ast.Attribute)
        else ""
    )
