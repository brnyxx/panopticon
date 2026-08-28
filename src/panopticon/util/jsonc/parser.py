"""Typed JSONC parsing with exact semantic source spans."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from panopticon.models import ConfigPath, JsonPointer

from .document import (
    JsonValue,
    SourceDocument,
    SourceSpan,
    detect_newline,
    path_identity,
    source_location,
)
from .tokenizer import Token, TokenizeError, TokenKind, tokenize


@dataclass(frozen=True, slots=True)
class JsoncParseError(Exception):
    """A JSONC syntax or encoding error with a byte location."""

    code: str
    line: int
    column: int
    offset: int

    def __str__(self) -> str:
        return self.code


class _Parser:
    __slots__ = ("_bom_length", "_index", "_source", "_spans", "_tokens")

    def __init__(self, source: bytes, tokens: tuple[Token, ...], bom_length: int) -> None:
        self._source = source
        self._tokens = tokens
        self._index = 0
        self._bom_length = bom_length
        self._spans: list[SourceSpan] = []

    def _peek(self) -> Token | None:
        while self._index < len(self._tokens):
            token = self._tokens[self._index]
            if token.kind not in {TokenKind.BOM, TokenKind.WHITESPACE, TokenKind.COMMENT}:
                return token
            self._index += 1
        return None

    def _take(self) -> Token | None:
        token = self._peek()
        if token is not None:
            self._index += 1
        return token

    def _fail(self, code: str, offset: int) -> NoReturn:
        line, column = source_location(self._source, offset, self._bom_length)
        raise JsoncParseError(code, line, column, offset)

    def _expect(self, kind: TokenKind) -> Token:
        token = self._take()
        if token is None or token.kind is not kind:
            self._fail("MALFORMED_JSONC", len(self._source) if token is None else token.start)
        return token

    @staticmethod
    def _token_error_offset(token: Token, error: json.JSONDecodeError) -> int:
        """Translate a decoded-character error position to a source byte offset."""
        prefix = token.raw.decode("utf-8")[: error.pos]
        return token.start + len(prefix.encode("utf-8"))

    def _decode_string(self, token: Token) -> str:
        try:
            value = json.loads(token.raw.decode("utf-8"))
        except json.JSONDecodeError as error:
            self._fail("MALFORMED_JSONC", self._token_error_offset(token, error))
        if not isinstance(value, str):
            self._fail("MALFORMED_JSONC", token.start)
        return value

    def _scalar(self, token: Token) -> JsonValue:
        if token.kind is TokenKind.STRING:
            return self._decode_string(token)
        if token.kind is TokenKind.IDENTIFIER:
            values: dict[bytes, JsonValue] = {
                b"true": True,
                b"false": False,
                b"null": None,
            }
            if token.raw in values:
                return values[token.raw]
        if token.kind is TokenKind.NUMBER:
            try:
                value = json.loads(token.raw.decode("ascii"))
            except json.JSONDecodeError as error:
                self._fail("MALFORMED_JSONC", self._token_error_offset(token, error))
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if isinstance(value, float) and not math.isfinite(value):
                    self._fail("MALFORMED_JSONC", token.start)
                return value
        self._fail("MALFORMED_JSONC", token.start)
        raise AssertionError("unreachable scalar")

    @staticmethod
    def _escape_pointer(part: str) -> str:
        return part.replace("~", "~0").replace("/", "~1")

    def _child_pointer(self, pointer: str, part: str) -> str:
        escaped = self._escape_pointer(part)
        return f"{pointer}/{escaped}" if pointer else f"/{escaped}"

    def _record_span(self, pointer: str, start: int, end: int) -> None:
        line, column = source_location(self._source, start, self._bom_length)
        self._spans.append(SourceSpan(JsonPointer(pointer), start, end, line, column, start))

    def _parse_value(self, pointer: str) -> tuple[JsonValue, int, int]:
        token = self._peek()
        if token is None:
            self._fail("MALFORMED_JSONC", len(self._source))
        match token.kind:
            case TokenKind.STRING | TokenKind.NUMBER | TokenKind.IDENTIFIER:
                self._take()
                value = self._scalar(token)
                self._record_span(pointer, token.start, token.end)
                return value, token.start, token.end
            case TokenKind.LBRACE:
                return self._parse_object(pointer)
            case TokenKind.LBRACKET:
                return self._parse_array(pointer)
            case _:
                self._fail("MALFORMED_JSONC", token.start)
                raise AssertionError("unreachable value")

    def _parse_object(self, pointer: str) -> tuple[dict[str, JsonValue], int, int]:
        opening = self._expect(TokenKind.LBRACE)
        values: dict[str, JsonValue] = {}
        seen: set[str] = set()
        next_token = self._peek()
        if next_token is not None and next_token.kind is TokenKind.RBRACE:
            closing = self._expect(TokenKind.RBRACE)
            self._record_span(pointer, opening.start, closing.end)
            return values, opening.start, closing.end
        while True:
            key_token = self._expect(TokenKind.STRING)
            key = self._decode_string(key_token)
            if key in seen:
                self._fail("DUPLICATE_KEY", key_token.start)
            seen.add(key)
            self._expect(TokenKind.COLON)
            value, _, _ = self._parse_value(self._child_pointer(pointer, key))
            values[key] = value
            separator = self._peek()
            if separator is not None and separator.kind is TokenKind.COMMA:
                self._take()
                after_comma = self._peek()
                if after_comma is not None and after_comma.kind is TokenKind.RBRACE:
                    closing = self._expect(TokenKind.RBRACE)
                    break
                continue
            if separator is not None and separator.kind is TokenKind.RBRACE:
                closing = self._expect(TokenKind.RBRACE)
                break
            offset = len(self._source) if separator is None else separator.start
            self._fail("MALFORMED_JSONC", offset)
        self._record_span(pointer, opening.start, closing.end)
        return values, opening.start, closing.end

    def _parse_array(self, pointer: str) -> tuple[list[JsonValue], int, int]:
        opening = self._expect(TokenKind.LBRACKET)
        values: list[JsonValue] = []
        next_token = self._peek()
        if next_token is not None and next_token.kind is TokenKind.RBRACKET:
            closing = self._expect(TokenKind.RBRACKET)
            self._record_span(pointer, opening.start, closing.end)
            return values, opening.start, closing.end
        while True:
            value, _, _ = self._parse_value(self._child_pointer(pointer, str(len(values))))
            values.append(value)
            separator = self._peek()
            if separator is not None and separator.kind is TokenKind.COMMA:
                self._take()
                after_comma = self._peek()
                if after_comma is not None and after_comma.kind is TokenKind.RBRACKET:
                    closing = self._expect(TokenKind.RBRACKET)
                    break
                continue
            if separator is not None and separator.kind is TokenKind.RBRACKET:
                closing = self._expect(TokenKind.RBRACKET)
                break
            offset = len(self._source) if separator is None else separator.start
            self._fail("MALFORMED_JSONC", offset)
        self._record_span(pointer, opening.start, closing.end)
        return values, opening.start, closing.end


def parse_document(source: bytes, *, path: Path, logical_path: ConfigPath) -> SourceDocument:
    """Parse UTF-8 JSONC while retaining source identity and semantic spans."""
    bom = b"\xef\xbb\xbf" if source.startswith(b"\xef\xbb\xbf") else b""
    try:
        tokens = tokenize(source)
    except TokenizeError as error:
        line, column = source_location(source, error.offset, len(bom))
        raise JsoncParseError(error.code, line, column, error.offset) from error
    parser = _Parser(source, tokens, len(bom))
    value, _, _ = parser._parse_value("")
    extra = parser._peek()
    if extra is not None:
        parser._fail("MALFORMED_JSONC", extra.start)
    return SourceDocument(
        value=value,
        original_bytes=source,
        encoding="utf-8",
        bom=bom,
        newline=detect_newline(source),
        logical_path=logical_path,
        path=path,
        realpath=path.resolve(),
        original_sha256=hashlib.sha256(source).hexdigest(),
        spans=tuple(parser._spans),
        _identity=path_identity(path),
    )


__all__ = [
    "JsonValue",
    "JsoncParseError",
    "SourceDocument",
    "SourceSpan",
    "parse_document",
]
