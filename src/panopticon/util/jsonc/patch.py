"""Deterministic JSON-pointer edits over original JSONC byte ranges."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum, unique
from itertools import pairwise
from typing import NoReturn, assert_never

from panopticon.models import JsonPointer

from .document import JsonValue, SourceDocument, SourceSpan
from .edit import (
    Edit,
    array_add,
    combine_additions,
    object_add,
    object_member_start,
    remove_interval,
)
from .pointer import array_index, decode_pointer, encode_pointer, value_at


@unique
class PatchOperation(StrEnum):
    """Supported syntax-preserving JSONC operations."""

    ADD = "ADD"
    REPLACE = "REPLACE"
    REMOVE = "REMOVE"


@dataclass(frozen=True, slots=True)
class JsoncPatch:
    """One typed RFC-6901 operation over a parsed source document."""

    operation: PatchOperation
    pointer: JsonPointer
    value: JsonValue | None = None


@dataclass(frozen=True, slots=True)
class _PlannedEdit:
    """One validated edit plus canonical pointer identity for composition."""

    edit: Edit
    operation: PatchOperation
    pointer: str
    parent_pointer: str


@dataclass(slots=True)
class JsoncPatchError(Exception):
    """A patch addressing, value, or overlap error."""

    code: str
    detail: str = ""

    def __str__(self) -> str:
        return self.code if not self.detail else f"{self.code}: {self.detail}"


def _fail(code: str, detail: str = "") -> NoReturn:
    raise JsoncPatchError(code, detail)


def _span_at(document: SourceDocument, pointer: str) -> SourceSpan:
    for span in document.spans:
        if str(span.pointer) == pointer:
            return span
    _fail("INVALID_POINTER", pointer)


def _json_bytes(value: JsonValue) -> bytes:
    try:
        rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        return rendered.encode("utf-8")
    except (TypeError, UnicodeError, ValueError) as error:
        _fail("INVALID_VALUE", str(error))


def _make_edit(document: SourceDocument, patch: JsoncPatch) -> Edit:
    parts = decode_pointer(patch.pointer)
    pointer = encode_pointer(parts)
    match patch.operation:
        case PatchOperation.REPLACE:
            value_at(document.value, parts)
            span = _span_at(document, pointer)
            return Edit(span.start, span.end, _json_bytes(patch.value))
        case PatchOperation.REMOVE:
            if not parts:
                _fail("INVALID_POINTER", pointer)
            parent_parts = parts[:-1]
            parent_pointer = encode_pointer(parent_parts)
            parent_value = value_at(document.value, parent_parts)
            parent_span = _span_at(document, parent_pointer)
            value_at(document.value, parts)
            span = _span_at(document, pointer)
            match parent_value:
                case dict():
                    member_start = object_member_start(document.original_bytes, span)
                    if member_start is None:
                        _fail("INVALID_POINTER", pointer)
                case list():
                    member_start = None
                case _:
                    _fail("INVALID_POINTER", parent_pointer)
            start, end = remove_interval(document.original_bytes, span, member_start)
            return Edit(start, end, b"")
        case PatchOperation.ADD:
            if not parts:
                _fail("INVALID_POINTER", pointer)
            parent_parts = parts[:-1]
            parent_pointer = encode_pointer(parent_parts)
            parent_value = value_at(document.value, parent_parts)
            parent_span = _span_at(document, parent_pointer)
            child = parts[-1]
            value_bytes = _json_bytes(patch.value)
            match parent_value:
                case dict() as mapping:
                    if child in mapping:
                        _fail("INVALID_POINTER", pointer)
                    return object_add(document, parent_span, child, value_bytes)
                case list() as sequence:
                    index = (
                        len(sequence)
                        if child == "-"
                        else array_index(child, len(sequence), allow_end=True)
                    )
                    return array_add(document, parent_span, index, len(sequence), value_bytes)
                case _:
                    _fail("INVALID_POINTER", parent_pointer)
        case _:
            _fail("INVALID_OPERATION", str(patch.operation))


def _plan_edit(document: SourceDocument, patch: JsoncPatch) -> _PlannedEdit:
    """Attach canonical pointer identities to one validated byte-range edit."""
    parts = decode_pointer(patch.pointer)
    return _PlannedEdit(
        _make_edit(document, patch),
        patch.operation,
        encode_pointer(parts),
        encode_pointer(parts[:-1]),
    )


def _add_group_key(planned: _PlannedEdit) -> tuple[str, int, int] | None:
    """Return the composition key for one compatible ADD candidate."""
    match planned.operation:
        case PatchOperation.ADD:
            return (planned.parent_pointer, planned.edit.start, planned.edit.end)
        case PatchOperation.REPLACE | PatchOperation.REMOVE:
            return None
        case unreachable:
            assert_never(unreachable)


def _compose_add_group(document: SourceDocument, group: tuple[_PlannedEdit, ...]) -> _PlannedEdit:
    """Compose distinct same-parent additions while retaining their input order."""
    pointers = tuple(planned.pointer for planned in group)
    if len(set(pointers)) != len(pointers):
        _fail("OVERLAPPING_PATCHES")
    first = group[0]
    parent = _span_at(document, first.parent_pointer)
    combined = combine_additions(document, parent, tuple(planned.edit for planned in group))
    return _PlannedEdit(combined, first.operation, first.pointer, first.parent_pointer)


def _compose_edits(
    document: SourceDocument, planned: tuple[_PlannedEdit, ...]
) -> tuple[_PlannedEdit, ...]:
    """Collapse only compatible ADDs into one edit per original insertion interval."""
    groups: list[list[_PlannedEdit]] = []
    group_indexes: dict[tuple[str, int, int], int] = {}
    for candidate in planned:
        key = _add_group_key(candidate)
        if key is None:
            groups.append([candidate])
            continue
        group_index = group_indexes.get(key)
        if group_index is None:
            group_indexes[key] = len(groups)
            groups.append([candidate])
        else:
            groups[group_index].append(candidate)
    return tuple(
        _compose_add_group(document, tuple(group)) if len(group) > 1 else group[0]
        for group in groups
    )


def patch_document(document: SourceDocument, patches: tuple[JsoncPatch, ...]) -> bytes:
    """Validate all JSON-pointer edits, then apply only their byte ranges."""
    planned = tuple(_plan_edit(document, patch) for patch in patches)
    composed = _compose_edits(document, planned)
    ordered = tuple(
        sorted(composed, key=lambda planned_edit: (planned_edit.edit.start, planned_edit.edit.end))
    )
    for previous, current in pairwise(ordered):
        previous_edit = previous.edit
        current_edit = current.edit
        same_start_overlap = current_edit.start == previous_edit.start and (
            current_edit.end == previous_edit.end or previous_edit.start == previous_edit.end
        )
        if current_edit.start < previous_edit.end or same_start_overlap:
            _fail("OVERLAPPING_PATCHES")
    result = document.original_bytes
    for planned_edit in reversed(ordered):
        edit = planned_edit.edit
        result = result[: edit.start] + edit.replacement + result[edit.end :]
    return result


__all__ = ["JsoncPatch", "JsoncPatchError", "PatchOperation", "patch_document"]
