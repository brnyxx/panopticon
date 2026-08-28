from __future__ import annotations

from pathlib import Path

import pytest

from ._support import (
    JSONC_SOURCE,
    DocumentLike,
    DocumentSpec,
    EditInterval,
    JsonValue,
    PatchErrorLike,
    PatchSpec,
    WriteSpec,
    apply_patches,
    machine_value,
    make_patch,
    parse_document,
    patch_bytes,
    require_jsonc_api,
    require_symbol,
    span_for,
    write_source,
)


def _expected_edit_interval(document: DocumentLike, spec: PatchSpec) -> EditInterval:
    source = document.original_bytes
    if spec.operation == "REPLACE":
        span = span_for(document, spec.pointer)
        return EditInterval(span.start, span.end)
    if spec.operation == "ADD":
        env_start = source.index(b'  "env": {')
        insertion = source.index(b"      },\r\n    },", env_start)
        return EditInterval(insertion, insertion)
    if spec.operation == "REMOVE":
        marker = b' "--old",'
        start = source.index(marker)
        return EditInterval(start, start + len(marker))
    raise AssertionError(spec.operation)


def test_nested_patch_preserves_comments_and_untouched_bytes(tmp_path: Path) -> None:
    # Given: a BOM-prefixed CRLF JSONC document with nested source spans and variables.
    target = tmp_path / "config.jsonc"
    write_source(target)
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(JSONC_SOURCE, target))
    original = document.original_bytes
    span = span_for(document, "/mcpServers/fixture/args/1")
    patch = make_patch(api, PatchSpec("REPLACE", "/mcpServers/fixture/args/1", "--new"))

    # When: one nested value is replaced through the byte-range patcher.
    patched = patch_bytes(api, document, (patch,))

    # Then: only the selected span changes and syntax/unknown bytes remain exact.
    assert patched[: span.start] == original[: span.start]
    assert patched[span.end :] == original[span.end :]
    assert patched.startswith(b"\xef\xbb\xbf// leading comment must stay\r\n")
    assert b'"unknown": {"keep": "byte-for-byte",}, // untouched member\r\n' in patched
    assert b'"TOKEN": "${env:TOKEN}"' in patched
    assert patched.count(b"\r\n") == original.count(b"\r\n")
    assert patch_bytes(api, document, (patch,)) == patched

    reparsed = parse_document(api, DocumentSpec(patched, target))
    assert reparsed.value == {
        "unknown": {"keep": "byte-for-byte"},
        "mcpServers": {
            "fixture": {
                "command": "uvx",
                "args": ["fixture", "--new"],
                "env": {
                    "TOKEN": "${env:TOKEN}",
                    "INPUT": "${input:command}",
                    "ROOT": "${workspaceFolder}",
                },
            }
        },
    }
    assert any(span.pointer == "/mcpServers/fixture/args/1" for span in reparsed.spans)


def test_inline_object_remove_preserves_remaining_member(tmp_path: Path) -> None:
    # Given: an inline object whose first member is addressed for removal.
    source = b'{"a": 1, "b": 2}'
    target = tmp_path / "inline.jsonc"
    write_source(target, source)
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(source, target))
    patch = make_patch(api, PatchSpec("REMOVE", "/a"))

    # When: the first inline member is removed through the byte-range patcher.
    patched = patch_bytes(api, document, (patch,))

    # Then: the remaining member and object delimiters remain valid and exact.
    assert patched == b'{"b": 2}'
    reparsed = parse_document(api, DocumentSpec(patched, target))
    assert reparsed.value == {"b": 2}


def test_nested_object_add_preserves_member_indentation(tmp_path: Path) -> None:
    # Given: a nested multiline object whose existing member establishes indentation.
    source = b'{\n  "obj": {\n    "a": 1,\n  },\n}\n'
    target = tmp_path / "nested-object.jsonc"
    write_source(target, source)
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(source, target))
    patch = make_patch(api, PatchSpec("ADD", "/obj/b", 2))

    # When: a member is added before the nested object's closing delimiter.
    patched = patch_bytes(api, document, (patch,))

    # Then: the new member follows the existing four-space member indentation.
    assert patched == b'{\n  "obj": {\n    "a": 1,\n    "b": 2,\n  },\n}\n'
    assert parse_document(api, DocumentSpec(patched, target)).value == {"obj": {"a": 1, "b": 2}}


def test_nested_array_add_preserves_member_indentation(tmp_path: Path) -> None:
    # Given: a nested multiline array whose existing element establishes indentation.
    source = b'{\n  "items": [\n    1,\n  ],\n}\n'
    target = tmp_path / "nested-array.jsonc"
    write_source(target, source)
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(source, target))
    patch = make_patch(api, PatchSpec("ADD", "/items/1", 2))

    # When: an element is appended before the nested array's closing delimiter.
    patched = patch_bytes(api, document, (patch,))

    # Then: the new element follows the existing four-space element indentation.
    assert patched == b'{\n  "items": [\n    1,\n    2,\n  ],\n}\n'
    assert parse_document(api, DocumentSpec(patched, target)).value == {"items": [1, 2]}


def test_hash_change_refuses_patch_without_write(tmp_path: Path) -> None:
    # Given: a parsed source whose target changes before the patch transaction starts.
    target = tmp_path / "config.jsonc"
    write_source(target)
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(JSONC_SOURCE, target))
    changed = JSONC_SOURCE.replace(b'"--old"', b'"--changed"')
    target.write_bytes(changed)
    patch = make_patch(api, PatchSpec("REPLACE", "/mcpServers/fixture/args/1", "--new"))

    # When: the stale document is submitted through the write boundary.
    result = apply_patches(
        api,
        WriteSpec(target, document, (patch,)),
    )

    # Then: a typed stale-source conflict leaves the concurrently changed bytes untouched.
    assert machine_value(result.status) == "CONFLICT"
    assert machine_value(result.reason_code) == "SOURCE_STALE"
    assert result.bytes_written == 0
    assert target.read_bytes() == changed
    assert tuple(path.name for path in tmp_path.iterdir()) == (target.name,)


@pytest.mark.parametrize(
    ("spec", "expected"),
    (
        (
            PatchSpec("ADD", "/mcpServers/fixture/env/ADDED", "new"),
            {
                "unknown": {"keep": "byte-for-byte"},
                "mcpServers": {
                    "fixture": {
                        "command": "uvx",
                        "args": ["fixture", "--old"],
                        "env": {
                            "TOKEN": "${env:TOKEN}",
                            "INPUT": "${input:command}",
                            "ROOT": "${workspaceFolder}",
                            "ADDED": "new",
                        },
                    }
                },
            },
        ),
        (
            PatchSpec("REPLACE", "/mcpServers/fixture/command", "node"),
            {
                "unknown": {"keep": "byte-for-byte"},
                "mcpServers": {
                    "fixture": {
                        "command": "node",
                        "args": ["fixture", "--old"],
                        "env": {
                            "TOKEN": "${env:TOKEN}",
                            "INPUT": "${input:command}",
                            "ROOT": "${workspaceFolder}",
                        },
                    }
                },
            },
        ),
        (
            PatchSpec("REMOVE", "/mcpServers/fixture/args/1"),
            {
                "unknown": {"keep": "byte-for-byte"},
                "mcpServers": {
                    "fixture": {
                        "command": "uvx",
                        "args": ["fixture"],
                        "env": {
                            "TOKEN": "${env:TOKEN}",
                            "INPUT": "${input:command}",
                            "ROOT": "${workspaceFolder}",
                        },
                    }
                },
            },
        ),
    ),
)
def test_nested_add_replace_remove_reparse_to_exact_value(
    spec: PatchSpec, expected: dict[str, JsonValue], tmp_path: Path
) -> None:
    # Given: one valid nested JSON pointer operation and the original source bytes.
    target = tmp_path / "config.jsonc"
    write_source(target)
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(JSONC_SOURCE, target))
    patch = make_patch(api, spec)

    # When: the operation is applied as a byte-range patch.
    patched = patch_bytes(api, document, (patch,))

    # Then: only the smallest operation-specific edit interval may differ.
    interval = _expected_edit_interval(document, spec)
    original = document.original_bytes
    assert 0 <= interval.start <= interval.end <= len(original)
    assert patched[: interval.start] == original[: interval.start]
    original_suffix = original[interval.end :]
    patched_suffix_start = len(patched) - len(original_suffix)
    assert patched_suffix_start >= interval.start
    assert patched[patched_suffix_start:] == original_suffix

    # Then: the reparse has the requested value while syntax and untouched comments survive.
    reparsed = parse_document(api, DocumentSpec(patched, target))
    assert reparsed.value == expected
    assert b"// leading comment must stay\r\n" in patched
    assert b"// untouched member\r\n" in patched
    assert patched.startswith(b"\xef\xbb\xbf")
    expected_newlines = JSONC_SOURCE.count(b"\r\n") + (1 if spec.operation == "ADD" else 0)
    assert patched.count(b"\r\n") == expected_newlines


@pytest.mark.parametrize(
    ("spec", "expected_code"),
    (
        (PatchSpec("REPLACE", "/mcpServers/missing", "value"), "INVALID_POINTER"),
        (PatchSpec("REMOVE", "/mcpServers/fixture/args/99"), "INVALID_INDEX"),
        (PatchSpec("REPLACE", "/mcpServers/fixture/args/not-an-index", "value"), "INVALID_INDEX"),
    ),
)
def test_invalid_pointer_or_index_returns_typed_patch_error(
    spec: PatchSpec, expected_code: str, tmp_path: Path
) -> None:
    # Given: a parsed document and a pointer that cannot address one value.
    target = tmp_path / "config.jsonc"
    write_source(target)
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(JSONC_SOURCE, target))
    patch = make_patch(api, spec)
    error_name = "JsoncPatchError"
    require_symbol(api, error_name)
    error_type = getattr(api, error_name)

    # When / Then: invalid addressing fails as a typed error without a partial byte result.
    with pytest.raises(error_type) as captured:
        patch_bytes(api, document, (patch,))
    assert isinstance(captured.value, PatchErrorLike)
    assert captured.value.code == expected_code
