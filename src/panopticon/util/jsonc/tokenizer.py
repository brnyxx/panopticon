"""Byte-preserving JSONC tokenization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique


@unique
class TokenKind(StrEnum):
    """Closed token kinds emitted by the contiguous tokenizer."""

    BOM = "BOM"
    WHITESPACE = "WHITESPACE"
    COMMENT = "COMMENT"
    STRING = "STRING"
    NUMBER = "NUMBER"
    IDENTIFIER = "IDENTIFIER"
    LBRACE = "LBRACE"
    RBRACE = "RBRACE"
    LBRACKET = "LBRACKET"
    RBRACKET = "RBRACKET"
    COLON = "COLON"
    COMMA = "COMMA"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class Token:
    """One contiguous source token, including trivia and comments."""

    kind: TokenKind
    start: int
    end: int
    raw: bytes


@dataclass(frozen=True, slots=True)
class TokenizeError(Exception):
    """A lexical error identified by its source byte offset."""

    code: str
    offset: int

    def __str__(self) -> str:
        return self.code


_PUNCTUATION: dict[int, TokenKind] = {
    ord("{"): TokenKind.LBRACE,
    ord("}"): TokenKind.RBRACE,
    ord("["): TokenKind.LBRACKET,
    ord("]"): TokenKind.RBRACKET,
    ord(":"): TokenKind.COLON,
    ord(","): TokenKind.COMMA,
}
_WHITESPACE = frozenset({0x09, 0x0A, 0x0D, 0x20})
_IDENTIFIER = frozenset(b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_$")
_NUMBER = frozenset(b"0123456789+-.eE")


def _bom_length(source: bytes) -> int:
    return 3 if source.startswith(b"\xef\xbb\xbf") else 0


def _validate_utf8(source: bytes, bom_length: int) -> None:
    payload = source[bom_length:]
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise TokenizeError("UNSUPPORTED_ENCODING", error.start + bom_length) from error
    if b"\x00" in payload:
        raise TokenizeError("UNSUPPORTED_ENCODING", bom_length + payload.index(b"\x00"))


def _scan_string(source: bytes, start: int) -> int:
    index = start + 1
    while index < len(source):
        byte = source[index]
        if byte in {0x00, 0x0A, 0x0D}:
            raise TokenizeError("MALFORMED_JSONC", start)
        if byte == ord("\\"):
            index += 2
            if index > len(source):
                raise TokenizeError("MALFORMED_JSONC", start)
            continue
        if byte == ord('"'):
            return index + 1
        index += 1
    raise TokenizeError("MALFORMED_JSONC", start)


def _scan_line_comment(source: bytes, start: int) -> int:
    index = start + 2
    while index < len(source) and source[index] not in {0x0A, 0x0D}:
        index += 1
    return index


def _scan_block_comment(source: bytes, start: int) -> int:
    end = source.find(b"*/", start + 2)
    if end == -1:
        raise TokenizeError("MALFORMED_COMMENT", start)
    return end + 2


def _scan_run(source: bytes, start: int, allowed: frozenset[int]) -> int:
    index = start
    while index < len(source) and source[index] in allowed:
        index += 1
    return index


def tokenize(source: bytes) -> tuple[Token, ...]:
    """Tokenize UTF-8 JSONC without dropping any source byte."""
    bom_length = _bom_length(source)
    _validate_utf8(source, bom_length)
    tokens: list[Token] = []
    index = 0
    if bom_length:
        tokens.append(Token(TokenKind.BOM, 0, bom_length, source[:bom_length]))
        index = bom_length

    while index < len(source):
        start = index
        byte = source[index]
        if byte in _WHITESPACE:
            index = _scan_run(source, index, _WHITESPACE)
            kind = TokenKind.WHITESPACE
        elif source.startswith(b"//", index):
            index = _scan_line_comment(source, index)
            kind = TokenKind.COMMENT
        elif source.startswith(b"/*", index):
            index = _scan_block_comment(source, index)
            kind = TokenKind.COMMENT
        elif byte == ord('"'):
            index = _scan_string(source, index)
            kind = TokenKind.STRING
        elif byte in _PUNCTUATION:
            index += 1
            kind = _PUNCTUATION[byte]
        elif byte in _NUMBER:
            index = _scan_run(source, index, _NUMBER)
            kind = TokenKind.NUMBER
        elif byte in _IDENTIFIER:
            index = _scan_run(source, index, _IDENTIFIER)
            kind = TokenKind.IDENTIFIER
        else:
            index += 1
            kind = TokenKind.INVALID
        tokens.append(Token(kind, start, index, source[start:index]))
    return tuple(tokens)
