from __future__ import annotations

from pathlib import Path

import pytest

from ._support import (
    DocumentSpec,
    JsonValue,
    PatchErrorLike,
    PatchSpec,
    make_patch,
    parse_document,
    patch_bytes,
    require_jsonc_api,
    require_symbol,
    write_source,
)


def test_huge_array_index_returns_typed_error(tmp_path: Path) -> None:
    # Given: an array pointer whose numeric component exceeds Python's integer limit.
    source = b'{"items": [1]}'
    target = tmp_path / "huge-index.jsonc"
    write_source(target, source)
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(source, target))
    patch = make_patch(api, PatchSpec("REMOVE", f"/items/{'9' * 5000}"))
    error_name = "JsoncPatchError"
    require_symbol(api, error_name)

    # When / Then: the index is rejected as typed addressing data.
    with pytest.raises(getattr(api, error_name)) as captured:
        patch_bytes(api, document, (patch,))
    assert isinstance(captured.value, PatchErrorLike)
    assert captured.value.code == "INVALID_INDEX"


def test_unencodable_patch_value_returns_typed_error(tmp_path: Path) -> None:
    # Given: a patch value containing an unpaired Unicode surrogate.
    source = b'{"value": 1}'
    target = tmp_path / "invalid-value.jsonc"
    write_source(target, source)
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(source, target))
    patch = make_patch(api, PatchSpec("REPLACE", "/value", "\ud800"))
    error_name = "JsoncPatchError"
    require_symbol(api, error_name)

    # When / Then: UTF-8 rendering fails at the typed patch boundary.
    with pytest.raises(getattr(api, error_name)) as captured:
        patch_bytes(api, document, (patch,))
    assert isinstance(captured.value, PatchErrorLike)
    assert captured.value.code == "INVALID_VALUE"


@pytest.mark.parametrize(
    ("source", "pointer", "value", "expected", "expected_value"),
    (
        (b'{"obj": {}}', "/obj/a", 1, b'{"obj": {"a": 1}}', {"obj": {"a": 1}}),
        (b'{"items": []}', "/items/0", 1, b'{"items": [1]}', {"items": [1]}),
        (
            b'{"obj": {"a": 1,}}',
            "/obj/b",
            2,
            b'{"obj": {"a": 1,"b": 2,}}',
            {"obj": {"a": 1, "b": 2}},
        ),
        (b'{"items": [1,]}', "/items/-", 2, b'{"items": [1,2,]}', {"items": [1, 2]}),
    ),
)
def test_inline_container_add_preserves_empty_and_trailing_comma_syntax(
    source: bytes,
    pointer: str,
    value: JsonValue,
    expected: bytes,
    expected_value: JsonValue,
    tmp_path: Path,
) -> None:
    # Given: an inline object or array with either no members or a trailing comma.
    target = tmp_path / "inline-edge.jsonc"
    write_source(target, source)
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(source, target))
    patch = make_patch(api, PatchSpec("ADD", pointer, value))

    # When: a new member or element is appended.
    patched = patch_bytes(api, document, (patch,))

    # Then: syntax stays valid and the input's comma convention remains intact.
    assert patched == expected
    assert parse_document(api, DocumentSpec(patched, target)).value == expected_value


def test_insertion_at_replacement_start_is_rejected_as_overlapping(
    tmp_path: Path,
) -> None:
    # Given: two edits that address the same original byte boundary.
    source = b'{"items": [1]}'
    target = tmp_path / "overlap.jsonc"
    write_source(target, source)
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(source, target))
    replacement = make_patch(api, PatchSpec("REPLACE", "/items/0", 2))
    insertion = make_patch(api, PatchSpec("ADD", "/items/0", 3))
    error_name = "JsoncPatchError"
    require_symbol(api, error_name)

    # When / Then: the patcher rejects the ambiguous zero-width overlap.
    with pytest.raises(getattr(api, error_name)) as captured:
        patch_bytes(api, document, (replacement, insertion))
    assert isinstance(captured.value, PatchErrorLike)
    assert captured.value.code == "OVERLAPPING_PATCHES"
