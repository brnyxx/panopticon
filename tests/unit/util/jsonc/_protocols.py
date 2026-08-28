"""Typed structural contracts shared by JSONC tests."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, TypeAlias, runtime_checkable

from panopticon.models import ConfigPath, JsonPointer

JsonValue: TypeAlias = str | int | float | bool | list["JsonValue"] | dict[str, "JsonValue"] | None


@runtime_checkable
class TokenLike(Protocol):
    @property
    def kind(self) -> str: ...

    @property
    def start(self) -> int: ...

    @property
    def end(self) -> int: ...

    @property
    def raw(self) -> bytes: ...


@runtime_checkable
class SpanLike(Protocol):
    @property
    def pointer(self) -> JsonPointer: ...

    @property
    def start(self) -> int: ...

    @property
    def end(self) -> int: ...

    @property
    def line(self) -> int: ...

    @property
    def column(self) -> int: ...

    @property
    def offset(self) -> int: ...


@runtime_checkable
class DocumentLike(Protocol):
    @property
    def value(self) -> JsonValue: ...

    @property
    def original_bytes(self) -> bytes: ...

    @property
    def encoding(self) -> str: ...

    @property
    def bom(self) -> bytes: ...

    @property
    def newline(self) -> str: ...

    @property
    def logical_path(self) -> ConfigPath: ...

    @property
    def path(self) -> Path: ...

    @property
    def realpath(self) -> Path: ...

    @property
    def original_sha256(self) -> str: ...

    @property
    def spans(self) -> tuple[SpanLike, ...]: ...


@runtime_checkable
class ParseErrorLike(Protocol):
    @property
    def code(self) -> str: ...

    @property
    def line(self) -> int: ...

    @property
    def column(self) -> int: ...

    @property
    def offset(self) -> int: ...


@runtime_checkable
class PatchErrorLike(Protocol):
    @property
    def code(self) -> str: ...


@runtime_checkable
class PatchLike(Protocol):
    @property
    def operation(self) -> str: ...

    @property
    def pointer(self) -> JsonPointer: ...

    @property
    def value(self) -> JsonValue | None: ...


@runtime_checkable
class WriteRequestLike(Protocol):
    @property
    def target(self) -> Path: ...

    @property
    def document(self) -> DocumentLike: ...

    @property
    def patches(self) -> tuple[PatchLike, ...]: ...


@runtime_checkable
class PatchResultLike(Protocol):
    @property
    def status(self) -> str: ...

    @property
    def reason_code(self) -> str: ...

    @property
    def bytes_written(self) -> int: ...
