from __future__ import annotations

from pathlib import Path

import pytest

from ._support import (
    DocumentSpec,
    ParseErrorLike,
    parse_document,
    require_jsonc_api,
    require_symbol,
    write_source,
)


def test_invalid_string_escape_reports_offending_byte_after_multibyte_prefix(
    tmp_path: Path,
) -> None:
    # Given: a UTF-8 string whose invalid escape follows a multibyte character.
    source = b'{"message": "\xc3\xa9\\q"}'
    path = tmp_path / "invalid-escape.jsonc"
    write_source(path, source)
    api = require_jsonc_api()
    error_name = "JsoncParseError"
    require_symbol(api, error_name)
    error_type = getattr(api, error_name)
    bad_escape = source.index(b"\\q")

    # When: malformed JSONC crosses the parser boundary.
    with pytest.raises(error_type) as captured:
        parse_document(api, DocumentSpec(source, path))

    # Then: the typed error points at the invalid escape byte, not the token start.
    error = captured.value
    assert isinstance(error, ParseErrorLike)
    assert error.code == "MALFORMED_JSONC"
    assert error.line == 1
    assert error.column == bad_escape + 1
    assert error.offset == bad_escape


def test_malformed_number_reports_offending_byte(tmp_path: Path) -> None:
    # Given: a number with a leading zero followed by another digit.
    source = b'{"number": 01}'
    path = tmp_path / "malformed-number.jsonc"
    write_source(path, source)
    api = require_jsonc_api()
    error_name = "JsoncParseError"
    require_symbol(api, error_name)
    error_type = getattr(api, error_name)
    bad_number = source.index(b"01") + 1

    # When: malformed JSONC crosses the parser boundary.
    with pytest.raises(error_type) as captured:
        parse_document(api, DocumentSpec(source, path))

    # Then: the typed error points at the second digit rejected by strict JSON.
    error = captured.value
    assert isinstance(error, ParseErrorLike)
    assert error.code == "MALFORMED_JSONC"
    assert error.line == 1
    assert error.column == bad_number + 1
    assert error.offset == bad_number
