from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ._support import (
    JSONC_SOURCE,
    LOGICAL_PATH,
    DocumentSpec,
    ParseErrorLike,
    assert_exact_spans,
    parse_document,
    require_jsonc_api,
    require_symbol,
    span_for,
    write_source,
)


def test_source_document_retains_bytes_identity_encoding_and_spans(tmp_path: Path) -> None:
    # Given: a regular CRLF JSONC file with a UTF-8 BOM and untouched comments.
    target = tmp_path / "config.jsonc"
    write_source(target)
    api = require_jsonc_api()

    # When: the source bytes are parsed into a typed source document.
    document = parse_document(api, DocumentSpec(JSONC_SOURCE, target))

    # Then: source identity and syntax metadata remain available without normalization.
    assert_exact_spans(document, JSONC_SOURCE)
    assert document.original_bytes == JSONC_SOURCE
    assert document.encoding == "utf-8"
    assert document.bom == b"\xef\xbb\xbf"
    assert document.newline == "\r\n"
    assert document.logical_path == LOGICAL_PATH
    assert document.path == target
    assert document.realpath == target.resolve()
    assert document.original_sha256 == hashlib.sha256(JSONC_SOURCE).hexdigest()
    assert b"// leading comment must stay\r\n" in document.original_bytes
    assert b"// untouched member\r\n" in document.original_bytes

    pointers = {span.pointer for span in document.spans}
    assert {
        "/unknown",
        "/unknown/keep",
        "/mcpServers",
        "/mcpServers/fixture",
        "/mcpServers/fixture/env",
        "/mcpServers/fixture/args",
        "/mcpServers/fixture/args/0",
        "/mcpServers/fixture/args/1",
    } <= pointers
    unknown_span = span_for(document, "/unknown")
    command_span = span_for(document, "/mcpServers/fixture/command")
    args_span = span_for(document, "/mcpServers/fixture/args")
    env_span = span_for(document, "/mcpServers/fixture/env")
    assert JSONC_SOURCE[unknown_span.start : unknown_span.end] == b'{"keep": "byte-for-byte",}'
    assert JSONC_SOURCE[command_span.start : command_span.end] == b'"uvx"'
    assert JSONC_SOURCE[args_span.start : args_span.end] == b'["fixture", "--old",]'
    assert JSONC_SOURCE[env_span.start : env_span.end] == (
        b"{\r\n"
        b'        "TOKEN": "${env:TOKEN}",\r\n'
        b'        "INPUT": "${input:command}",\r\n'
        b'        "ROOT": "${workspaceFolder}",\r\n'
        b"      }"
    )


def test_symlinked_source_keeps_logical_path_and_records_realpath(tmp_path: Path) -> None:
    # Given: a source file reached through a symlinked config path.
    real_target = tmp_path / "real" / "config.jsonc"
    real_target.parent.mkdir()
    write_source(real_target)
    linked_target = tmp_path / "linked.jsonc"
    linked_target.symlink_to(real_target)
    api = require_jsonc_api()

    # When: the linked source is parsed without resolving away its logical path.
    document = parse_document(api, DocumentSpec(JSONC_SOURCE, linked_target))

    # Then: logical path and realpath remain distinct, while source bytes stay exact.
    assert document.path == linked_target
    assert document.logical_path == LOGICAL_PATH
    assert document.realpath == real_target.resolve()
    assert document.original_bytes == JSONC_SOURCE


def test_utf8_without_bom_and_with_bom_have_explicit_encoding_metadata(tmp_path: Path) -> None:
    # Given: the same JSON value in the two repository-supported UTF-8 byte forms.
    api = require_jsonc_api()
    plain = b'{"mcpServers": {"fixture": {},},}\n'
    cases = (("plain", plain, b""), ("bom", b"\xef\xbb\xbf" + plain, b"\xef\xbb\xbf"))

    # When: both source forms are parsed.
    documents = []
    for name, source, _bom in cases:
        path = tmp_path / f"{name}.jsonc"
        write_source(path, source)
        documents.append(parse_document(api, DocumentSpec(source, path)))

    # Then: BOM is represented separately while the encoding stays UTF-8.
    assert tuple(document.encoding for document in documents) == ("utf-8", "utf-8")
    assert tuple(document.bom for document in documents) == (b"", b"\xef\xbb\xbf")
    assert tuple(document.newline for document in documents) == ("\n", "\n")
    assert documents[0].value == documents[1].value


def test_utf16_is_a_typed_unsupported_encoding(tmp_path: Path) -> None:
    # Given: a syntactically valid JSON value encoded outside the supported UTF-8 policy.
    source = b"\xff\xfe{\x00}\x00"
    path = tmp_path / "utf16.jsonc"
    write_source(path, source)
    api = require_jsonc_api()
    error_name = "JsoncParseError"
    require_symbol(api, error_name)
    error_type = getattr(api, error_name)

    # When / Then: unsupported encoding fails before semantic parsing with typed state.
    with pytest.raises(error_type) as captured:
        parse_document(api, DocumentSpec(source, path))
    error = captured.value
    assert isinstance(error, ParseErrorLike)
    assert error.code == "UNSUPPORTED_ENCODING"
    assert error.offset == 0
    assert error.line == 1
    assert error.column == 1
