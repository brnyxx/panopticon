"""Deterministic client-entry and JSON-pointer selection for fixes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from panopticon.discovery import discover, registered_adapters
from panopticon.discovery.base import DiscoveryEnv, DiscoveryStatus, RawServerEntry
from panopticon.fix.cli_model import FixChoice, FixSelection
from panopticon.models.ids import JsonPointer
from panopticon.util.jsonc.document import JsonValue
from panopticon.util.jsonc.pointer import decode_pointer, encode_pointer


@dataclass(frozen=True, slots=True)
class FixCommandRequest:
    server: str | None
    rule: str | None
    yes: bool = False
    dry_run: bool = False
    undo: str | None = None
    value: str | None = None
    version: str | None = None
    client: str | None = None
    config_path: Path | None = None


def _entries(
    env: DiscoveryEnv,
    client: str | None,
    config_path: Path | None,
) -> tuple[RawServerEntry, ...]:
    found: list[RawServerEntry] = []
    for adapter in registered_adapters(env, generic_config=config_path):
        if client is not None and adapter.name != client:
            continue
        for _path, result in discover(adapter, env):
            if result.status is DiscoveryStatus.FOUND:
                found.extend(result.entries)
    return tuple(found)


def _child(entry: RawServerEntry, *parts: str) -> JsonPointer:
    return JsonPointer(encode_pointer(decode_pointer(entry.json_pointer) + parts))


def _find_nested(
    value: JsonValue | Mapping[str, JsonValue],
    targets: frozenset[str],
) -> tuple[str, ...] | None:
    if isinstance(value, Mapping):
        for key in sorted(value):
            nested = _find_nested(value[key], targets)
            if nested is not None:
                return (str(key), *nested)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, str) and item in targets:
                return (str(index),)
            nested = _find_nested(item, targets)
            if nested is not None:
                return (str(index), *nested)
    elif isinstance(value, str) and value in targets:
        return ()
    return None


def _package_index(entry: RawServerEntry) -> int | None:
    args = entry.raw.get("args")
    if not isinstance(args, list):
        return None
    for index, argument in enumerate(args):
        if not isinstance(argument, str) or argument.startswith("-"):
            continue
        if argument.startswith("@") or "@latest" in argument:
            return index
        if "/" not in argument and "\\" not in argument and argument not in {"node", "python"}:
            return index
    return None


def selection(entry: RawServerEntry, request: FixCommandRequest) -> FixSelection:
    rule = request.rule or ""
    pointer: JsonPointer
    if rule == "FIX-001":
        for field in ("env", "headers"):
            values = entry.raw.get(field)
            if isinstance(values, Mapping) and values:
                key = sorted(str(item) for item in values)[0]
                pointer = _child(entry, field, key)
                break
        else:
            raise ValueError("SECRET_POINTER_NOT_FOUND")
    elif rule in {"FIX-002", "FIX-005"}:
        index = _package_index(entry)
        if index is None:
            raise ValueError("PACKAGE_POINTER_NOT_FOUND")
        pointer = _child(entry, "args", str(index))
    elif rule == "FIX-004":
        nested = _find_nested(entry.raw, frozenset({"/", "~", "$HOME"}))
        if nested is None:
            raise ValueError("PATH_POINTER_NOT_FOUND")
        pointer = _child(entry, *nested)
    elif rule == "FIX-008":
        pointer = _child(entry, "url")
    elif rule == "FIX-010":
        pointer = entry.json_pointer
    else:
        raise ValueError("FIX_RULE_REQUIRED")
    return FixSelection(
        rule,
        entry.config_path,
        pointer,
        FixChoice.APPLY,
        request.value,
        request.version,
        request.client,
    )


def matching_entries(env: DiscoveryEnv, request: FixCommandRequest) -> tuple[RawServerEntry, ...]:
    matched = tuple(
        entry
        for entry in _entries(env, request.client, request.config_path)
        if entry.name == request.server
    )
    return matched if request.rule == "FIX-005" else matched[:1]


__all__ = ["FixCommandRequest", "matching_entries", "selection"]
