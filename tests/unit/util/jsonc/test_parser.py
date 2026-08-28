from __future__ import annotations

from pathlib import Path

import pytest

from ._support import (
    JSONC_SOURCE,
    DocumentSpec,
    ParseErrorLike,
    TokenLike,
    as_object,
    assert_exact_spans,
    parse_document,
    require_jsonc_api,
    require_jsonc_module,
    require_symbol,
    span_for,
    tokenize_source,
    write_source,
)


def _assert_token_stream(source: bytes, tokens: tuple[TokenLike, ...]) -> None:
    assert tokens
    cursor = 0
    raw_parts: list[bytes] = []
    for token in tokens:
        assert token.kind.strip()
        assert token.start == cursor
        assert 0 <= token.start < token.end <= len(source)
        assert token.raw == source[token.start : token.end]
        raw_parts.append(token.raw)
        cursor = token.end
    assert cursor == len(source)
    assert b"".join(raw_parts) == source


def test_tokenizer_and_parser_accept_jsonc_comments_and_trailing_commas(
    tmp_path: Path,
) -> None:
    # Given: standard JSON and JSONC sources with line/block comments and trailing commas.
    sources = (
        b'{"servers":{"fixture":{"args":["one",2]}}}',
        b'/* header */\n{"servers": {"fixture": [1, 2,],}, // footer\n}',
        JSONC_SOURCE,
    )
    tokenizer = require_jsonc_module("tokenizer")
    require_symbol(tokenizer, "tokenize")
    for module_name, symbol in (("parser", "parse_document"), ("patch", "patch_document")):
        module = require_jsonc_module(module_name)
        require_symbol(module, symbol)
    api = require_jsonc_api()
    documents = []
    for index, source in enumerate(sources):
        path = tmp_path / f"config-{index}.jsonc"
        write_source(path, source)
        tokens = tokenize_source(tokenizer, source)
        _assert_token_stream(source, tokens)
        document = parse_document(api, DocumentSpec(source, path))
        assert_exact_spans(document, source)
        documents.append(document)

    # When: the public parser parses each source covered by the tokenizer.
    values = tuple(document.value for document in documents)

    # Then: comments and trailing commas do not change the semantic values.
    assert values[0] == {"servers": {"fixture": {"args": ["one", 2]}}}
    assert values[1] == {"servers": {"fixture": [1, 2]}}
    third = as_object(values[2])
    servers = as_object(third["mcpServers"])
    fixture = as_object(servers["fixture"])
    assert fixture["command"] == "uvx"


def test_json_pointer_escapes_slashes_and_tildes_in_member_names(tmp_path: Path) -> None:
    # Given: member names containing both RFC-6901 escape characters.
    source = b'{"a/b": {"~key": "value"}}'
    path = tmp_path / "escaped-pointers.jsonc"
    write_source(path, source)
    api = require_jsonc_api()

    # When: the document is parsed and spans are indexed.
    document = parse_document(api, DocumentSpec(source, path))

    # Then: slash and tilde are escaped and the value span remains byte-exact.
    assert_exact_spans(document, source)
    escaped_span = span_for(document, "/a~1b/~0key")
    assert source[escaped_span.start : escaped_span.end] == b'"value"'


def test_malformed_comment_reports_typed_line_column_and_byte_offset(tmp_path: Path) -> None:
    # Given: an unterminated block comment at a known source position.
    source = b'{\r\n  "servers": {\r\n    /* never closes\r\n  }\r\n}\r\n'
    path = tmp_path / "malformed-comment.jsonc"
    write_source(path, source)
    api = require_jsonc_api()
    error_name = "JsoncParseError"
    require_symbol(api, error_name)
    error_type = getattr(api, error_name)
    offset = source.index(b"/*")

    # When: malformed JSONC crosses the parser boundary.
    with pytest.raises(error_type) as captured:
        parse_document(api, DocumentSpec(source, path))

    # Then: the typed error identifies the stable reason and exact byte location.
    error = captured.value
    assert isinstance(error, ParseErrorLike)
    assert error.code == "MALFORMED_COMMENT"
    assert error.line == 3
    assert error.column == 5
    assert error.offset == offset


def test_malformed_trailing_comma_reports_typed_error(tmp_path: Path) -> None:
    # Given: a JSONC document with two separators where one trailing comma is allowed.
    source = b'{"servers": ["fixture",],,}'
    path = tmp_path / "malformed-trailing-comma.jsonc"
    write_source(path, source)
    api = require_jsonc_api()
    error_name = "JsoncParseError"
    require_symbol(api, error_name)
    error_type = getattr(api, error_name)
    double_comma = source.index(b",,")

    # When / Then: the second separator is a typed syntax rejection with its offset.
    with pytest.raises(error_type) as captured:
        parse_document(api, DocumentSpec(source, path))
    error = captured.value
    assert isinstance(error, ParseErrorLike)
    assert error.code == "MALFORMED_JSONC"
    assert error.line == 1
    assert error.column == double_comma + 2
    assert error.offset == double_comma + 1


def test_nonfinite_numeric_values_are_rejected_as_malformed_jsonc(tmp_path: Path) -> None:
    # Given: a JSON number whose exponent overflows the supported finite value type.
    source = b'{"number": 1e309}'
    path = tmp_path / "nonfinite.jsonc"
    write_source(path, source)
    api = require_jsonc_api()
    error_name = "JsoncParseError"
    require_symbol(api, error_name)
    error_type = getattr(api, error_name)

    # When / Then: non-finite numeric output is rejected at the parser boundary.
    with pytest.raises(error_type) as captured:
        parse_document(api, DocumentSpec(source, path))
    error = captured.value
    assert isinstance(error, ParseErrorLike)
    assert error.code == "MALFORMED_JSONC"
    assert error.offset == source.index(b"1e309")


def test_duplicate_keys_are_rejected_before_pointer_resolution(tmp_path: Path) -> None:
    # Given: an object whose duplicate member would make one RFC-6901 pointer ambiguous.
    source = b'{"mcpServers": {"fixture": {"command": "one"}, "fixture": {}}}'
    path = tmp_path / "duplicate.jsonc"
    write_source(path, source)
    api = require_jsonc_api()
    error_name = "JsoncParseError"
    require_symbol(api, error_name)
    error_type = getattr(api, error_name)

    # When / Then: the authoritative json5 duplicate-rejection policy is surfaced as typed data.
    with pytest.raises(error_type) as captured:
        parse_document(api, DocumentSpec(source, path))
    error = captured.value
    assert isinstance(error, ParseErrorLike)
    assert error.code == "DUPLICATE_KEY"
    assert error.offset == source.rfind(b'"fixture"')


def test_unresolved_variable_strings_are_preserved_exactly(tmp_path: Path) -> None:
    # Given: client variables that must remain unresolved in the parsed semantic value.
    path = tmp_path / "variables.jsonc"
    write_source(path)
    api = require_jsonc_api()

    # When: the JSONC source is parsed.
    document = parse_document(api, DocumentSpec(JSONC_SOURCE, path))

    # Then: each variable token remains byte-for-byte identical as a string value.
    parsed = as_object(document.value)
    servers = as_object(parsed["mcpServers"])
    fixture = as_object(servers["fixture"])
    env = as_object(fixture["env"])
    assert env == {
        "TOKEN": "${env:TOKEN}",
        "INPUT": "${input:command}",
        "ROOT": "${workspaceFolder}",
    }
