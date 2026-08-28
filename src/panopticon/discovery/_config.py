"""Shared read-only JSONC configuration extraction for client adapters."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Protocol, cast

from panopticon.discovery.base import (
    DiscoveryStatus,
    ParseError,
    ParseResult,
    RawServerEntry,
    SourceLocation,
)
from panopticon.models import (
    ConfigPath,
    ConfigScope,
    ContractViolationError,
    JsonPointer,
    normalize_config_path,
)
from panopticon.util.jsonc.document import JsonValue, SourceDocument
from panopticon.util.jsonc.parser import JsoncParseError, parse_document


class ConfigReader(Protocol):
    """Injectable read boundary for deterministic discovery failures."""

    def read_bytes(self, path: Path) -> bytes: ...


class FileConfigReader:
    """Read configuration bytes from the local filesystem."""

    def read_bytes(self, path: Path) -> bytes:
        return path.read_bytes()


def logical_path(path: Path, home: Path) -> ConfigPath:
    try:
        return normalize_config_path(str(path), str(home))
    except ContractViolationError:
        return ConfigPath("~/" + path.name)


def read_entries(
    path: Path,
    *,
    home: Path,
    scope: ConfigScope,
    pointers: Iterable[str] = ("/mcpServers",),
    reader: ConfigReader | None = None,
) -> ParseResult:
    """Read one config and extract server maps without resolving any values."""
    source_reader = reader or FileConfigReader()
    try:
        source = source_reader.read_bytes(path)
    except FileNotFoundError:
        return ParseResult(DiscoveryStatus.NOT_FOUND)
    except PermissionError:
        return ParseResult(
            DiscoveryStatus.PERMISSION,
            error=ParseError(path, "PERMISSION"),
        )
    except OSError:
        return ParseResult(DiscoveryStatus.PERMISSION, error=ParseError(path, "IO_ERROR"))
    try:
        document = parse_document(source, path=path, logical_path=logical_path(path, home))
    except JsoncParseError as error:
        return ParseResult(
            DiscoveryStatus.PARSE_ERROR,
            error=ParseError(path, error.code, error.line, error.column, error.offset),
        )
    entries = _extract(document, scope, pointers)
    return ParseResult(DiscoveryStatus.FOUND, entries=entries)


def _extract(
    document: SourceDocument, scope: ConfigScope, pointers: Iterable[str]
) -> list[RawServerEntry]:
    value = document.value
    spans = {str(span.pointer): span for span in document.spans}
    result: list[RawServerEntry] = []
    for pointer in pointers:
        node: JsonValue = value
        for part in pointer.strip("/").split("/") if pointer else ():
            if not isinstance(node, dict):
                node = None
                break
            node = node.get(part.replace("~1", "/").replace("~0", "~"))
        if not isinstance(node, dict):
            continue
        for name in sorted(node):
            raw = node[name]
            if not isinstance(raw, Mapping):
                continue
            raw_mapping = cast(Mapping[str, JsonValue], raw)
            escaped_name = name.replace("~", "~0").replace("/", "~1")
            entry_pointer = f"{pointer}/{escaped_name}"
            span = spans.get(entry_pointer) or spans.get(pointer)
            if span is None:
                location = SourceLocation(1, 1, 0)
            else:
                location = SourceLocation(span.line, span.column, span.offset)
            result.append(
                RawServerEntry(
                    name=name,
                    raw=raw_mapping,
                    scope=scope,
                    config_path=document.path,
                    logical_path=document.logical_path,
                    realpath=document.realpath,
                    original_sha256=document.original_sha256,
                    json_pointer=JsonPointer(entry_pointer),
                    source_location=location,
                )
            )
    return result
