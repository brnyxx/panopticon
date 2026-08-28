"""Byte-range edit construction for JSONC add and remove operations."""

from __future__ import annotations

import json
from dataclasses import dataclass

from .document import SourceDocument, SourceSpan
from .tokenizer import Token, TokenKind, tokenize


@dataclass(frozen=True, slots=True)
class Edit:
    """One replacement interval in the original source byte stream."""

    start: int
    end: int
    replacement: bytes


def _significant_tokens(source: bytes) -> tuple[Token, ...]:
    trivia = {TokenKind.BOM, TokenKind.WHITESPACE, TokenKind.COMMENT}
    return tuple(token for token in tokenize(source) if token.kind not in trivia)


def object_member_start(source: bytes, span: SourceSpan) -> int | None:
    """Find the source start of the object key owning a value span."""
    tokens = _significant_tokens(source)
    for index, token in enumerate(tokens):
        if (
            token.start == span.start
            and index >= 2
            and tokens[index - 2].kind is TokenKind.STRING
            and tokens[index - 1].kind is TokenKind.COLON
        ):
            return tokens[index - 2].start
    return None


def _member_token_index(tokens: tuple[Token, ...], start: int) -> int | None:
    for index, token in enumerate(tokens):
        if token.start == start:
            return index
    return None


def remove_interval(source: bytes, span: SourceSpan, member_start: int | None) -> tuple[int, int]:
    """Choose the smallest valid interval that removes one object or array value."""
    tokens = _significant_tokens(source)
    start = span.start if member_start is None else member_start
    member_index = _member_token_index(tokens, start)
    if member_index is None:
        return start, span.end
    next_index = member_index + 1
    while next_index < len(tokens) and tokens[next_index].start < span.end:
        next_index += 1
    if next_index < len(tokens) and tokens[next_index].kind is TokenKind.COMMA:
        end = tokens[next_index].end
        while end < len(source) and source[end] in b" \t":
            end += 1
        return start, end
    if member_index > 0 and tokens[member_index - 1].kind is TokenKind.COMMA:
        return tokens[member_index - 1].start, span.end
    return start, span.end


def _line_start(source: bytes, position: int) -> int:
    return max(source.rfind(b"\n", 0, position), source.rfind(b"\r", 0, position)) + 1


def _line_indent(source: bytes, position: int) -> bytes:
    index = position
    while index < len(source) and source[index] in b" \t":
        index += 1
    return source[position:index]


def _inside_tokens(source: bytes, parent: SourceSpan) -> tuple[Token, ...]:
    return tuple(
        token
        for token in _significant_tokens(source)
        if parent.start < token.start and token.end < parent.end
    )


def _member_indent(source: bytes, parent: SourceSpan, closing_line: int) -> bytes:
    opening_line = _line_start(source, parent.start)
    for token in _inside_tokens(source, parent):
        token_line = _line_start(source, token.start)
        if token_line > opening_line:
            return _line_indent(source, token_line)
    return _line_indent(source, closing_line) + b"  "


def _single_line_add(
    parent: SourceSpan, member: bytes, separator: bytes, has_trailing_comma: bool
) -> Edit:
    suffix = b"," if has_trailing_comma else b""
    return Edit(parent.end - 1, parent.end - 1, separator + member + suffix)


def object_add(document: SourceDocument, parent: SourceSpan, key: str, value_bytes: bytes) -> Edit:
    """Build one object-member insertion while retaining the parent's formatting."""
    source = document.original_bytes
    key_bytes = json.dumps(key, ensure_ascii=False).encode("utf-8")
    member = key_bytes + b": " + value_bytes
    inside = _inside_tokens(source, parent)
    has_trailing_comma = bool(inside and inside[-1].kind is TokenKind.COMMA)
    opening_line = _line_start(source, parent.start)
    closing_line = _line_start(source, parent.end - 1)
    if opening_line == closing_line:
        separator = b"" if not inside or has_trailing_comma else b", "
        return _single_line_add(parent, member, separator, has_trailing_comma)

    indent = _member_indent(source, parent, closing_line)
    newline = document.newline.encode("ascii")
    rendered_member = indent + member + (b"," if has_trailing_comma else b"") + newline
    if not inside or has_trailing_comma:
        return Edit(closing_line, closing_line, rendered_member)
    last = inside[-1]
    return Edit(last.end, closing_line, b"," + source[last.end : closing_line] + rendered_member)


def _line_is_indented(source: bytes, position: int, parent: SourceSpan) -> bool:
    line_start = _line_start(source, position)
    parent_line = _line_start(source, parent.start)
    return line_start > parent_line and not source[line_start:position].strip(b" \t")


def _join_multiline_members(members: tuple[bytes, ...], newline: bytes) -> bytes:
    """Join multiline members and add separators before every non-final member."""
    last_index = len(members) - 1
    return b"".join(
        member if index == last_index else member[: -len(newline)] + b"," + newline
        for index, member in enumerate(members)
    )


def combine_additions(
    document: SourceDocument, parent: SourceSpan, edits: tuple[Edit, ...]
) -> Edit:
    """Compose compatible additions into one original source-range edit."""
    source = document.original_bytes
    inside = _inside_tokens(source, parent)
    first = edits[0]
    opening_line = _line_start(source, parent.start)
    closing_line = _line_start(source, parent.end - 1)
    if opening_line == closing_line:
        separator = b", " if not inside else b""
        replacement = separator.join(edit.replacement for edit in edits)
        return Edit(first.start, first.end, replacement)

    newline = document.newline.encode("ascii")
    has_trailing_comma = bool(inside and inside[-1].kind is TokenKind.COMMA)
    if has_trailing_comma:
        replacement = b"".join(edit.replacement for edit in edits)
    elif not inside:
        replacement = _join_multiline_members(tuple(edit.replacement for edit in edits), newline)
    else:
        source_gap = source[first.start : first.end]
        members = tuple(edit.replacement[1 + len(source_gap) :] for edit in edits)
        replacement = b"," + source_gap + _join_multiline_members(members, newline)
    return Edit(first.start, first.end, replacement)


def array_add(
    document: SourceDocument,
    parent: SourceSpan,
    index: int,
    length: int,
    value_bytes: bytes,
) -> Edit:
    """Build one array-element insertion while retaining the parent's formatting."""
    source = document.original_bytes
    encoded_value = value_bytes
    if index < length:
        target_pointer = str(parent.pointer) + f"/{index}"
        target = next(span for span in document.spans if str(span.pointer) == target_pointer)
        if _line_is_indented(source, target.start, parent):
            line_start = _line_start(source, target.start)
            indent = source[line_start : target.start]
            return Edit(
                line_start,
                line_start,
                indent + encoded_value + b"," + document.newline.encode("ascii"),
            )
        return Edit(target.start, target.start, encoded_value + b", ")

    inside = _inside_tokens(source, parent)
    has_trailing_comma = bool(inside and inside[-1].kind is TokenKind.COMMA)
    opening_line = _line_start(source, parent.start)
    closing_line = _line_start(source, parent.end - 1)
    if opening_line == closing_line:
        separator = b"" if not inside or has_trailing_comma else b", "
        return _single_line_add(parent, encoded_value, separator, has_trailing_comma)

    indent = _member_indent(source, parent, closing_line)
    newline = document.newline.encode("ascii")
    rendered_member = indent + encoded_value + (b"," if has_trailing_comma else b"") + newline
    if not inside or has_trailing_comma:
        return Edit(closing_line, closing_line, rendered_member)
    last = inside[-1]
    return Edit(last.end, closing_line, b"," + source[last.end : closing_line] + rendered_member)
