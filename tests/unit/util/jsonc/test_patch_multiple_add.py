from __future__ import annotations

from pathlib import Path

import pytest

from panopticon.util.jsonc import JsoncPatchError

from ._support import (
    DocumentSpec,
    PatchErrorLike,
    PatchSpec,
    make_patch,
    parse_document,
    patch_bytes,
    require_jsonc_api,
    require_symbol,
    write_source,
)


def test_distinct_object_additions_preserve_input_order_and_untouched_bytes(
    tmp_path: Path,
) -> None:
    # Given: a nonempty object and two distinct members added at one source boundary.
    source = b'{"obj": {"keep": 0}}'
    target = tmp_path / "object.jsonc"
    write_source(target, source)
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(source, target))
    patches = tuple(
        make_patch(api, PatchSpec("ADD", pointer, value))
        for pointer, value in (("/obj/a", 1), ("/obj/b", 2))
    )

    # When: both additions are applied in one patch_document call.
    try:
        patched = patch_bytes(api, document, patches)
    except JsoncPatchError as error:
        pytest.fail(f"distinct additions were rejected: {error.code}")

    # Then: additions retain caller order and the original suffix remains exact.
    insertion = source.index(b"}", source.index(b'"obj"'))
    assert patched == b'{"obj": {"keep": 0, "a": 1, "b": 2}}'
    assert patched[:insertion] == source[:insertion]
    assert patched[len(patched) - (len(source) - insertion) :] == source[insertion:]
    assert parse_document(api, DocumentSpec(patched, target)).value == {
        "obj": {"keep": 0, "a": 1, "b": 2}
    }
    assert patch_bytes(api, document, patches) == patched


def test_distinct_empty_object_additions_render_separated_members(tmp_path: Path) -> None:
    # Given: an empty object and two distinct members added at its closing boundary.
    source = b'{"obj": {}}'
    target = tmp_path / "empty-object.jsonc"
    write_source(target, source)
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(source, target))
    patches = tuple(
        make_patch(api, PatchSpec("ADD", pointer, value))
        for pointer, value in (("/obj/a", 1), ("/obj/b", 2))
    )

    # When: both additions are applied in one patch_document call.
    patched = patch_bytes(api, document, patches)

    # Then: the empty object receives valid, ordered members with one separator.
    assert patched == b'{"obj": {"a": 1, "b": 2}}'
    assert parse_document(api, DocumentSpec(patched, target)).value == {"obj": {"a": 1, "b": 2}}


@pytest.mark.parametrize(
    ("source", "expected", "expected_value"),
    (
        (
            b'\xef\xbb\xbf// header\r\n{\r\n  "obj": {\r\n    "keep": 0, // keep\r\n  },\r\n}\r\n',
            (
                b'\xef\xbb\xbf// header\r\n{\r\n  "obj": {\r\n'
                b'    "keep": 0, // keep\r\n    "a": 1,\r\n    "b": 2,\r\n  },\r\n}\r\n'
            ),
            {"obj": {"keep": 0, "a": 1, "b": 2}},
        ),
        (
            b'\xef\xbb\xbf// header\r\n{\r\n  "obj": {\r\n  },\r\n}\r\n',
            (
                b'\xef\xbb\xbf// header\r\n{\r\n  "obj": {\r\n'
                b'    "a": 1,\r\n    "b": 2\r\n  },\r\n}\r\n'
            ),
            {"obj": {"a": 1, "b": 2}},
        ),
    ),
)
def test_object_additions_preserve_multiline_jsonc_format(
    source: bytes, expected: bytes, expected_value: dict[str, dict[str, int]], tmp_path: Path
) -> None:
    # Given: a BOM-prefixed CRLF object with either existing or no members.
    target = tmp_path / "multiline-object.jsonc"
    write_source(target, source)
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(source, target))
    patches = tuple(
        make_patch(api, PatchSpec("ADD", pointer, value))
        for pointer, value in (("/obj/a", 1), ("/obj/b", 2))
    )

    # When: two members are composed at the same multiline insertion boundary.
    patched = patch_bytes(api, document, patches)

    # Then: CRLF, indentation, comments, and the untouched suffix remain exact.
    insertion = source.index(b"  },", source.index(b'"obj"'))
    assert patched == expected
    assert patched[:insertion] == source[:insertion]
    assert patched[len(patched) - (len(source) - insertion) :] == source[insertion:]
    assert parse_document(api, DocumentSpec(patched, target)).value == expected_value


@pytest.mark.parametrize(
    ("source", "specs", "expected", "expected_value"),
    (
        (
            b'{"items": []}',
            (("/items/0", 1), ("/items/-", 2)),
            b'{"items": [1, 2]}',
            {"items": [1, 2]},
        ),
        (
            b'{"items": [0]}',
            (("/items/1", 1), ("/items/-", 2)),
            b'{"items": [0, 1, 2]}',
            {"items": [0, 1, 2]},
        ),
        (
            b'{"items": [0, 3]}',
            (("/items/1", 1), ("/items/2", 2)),
            b'{"items": [0, 1, 3, 2]}',
            {"items": [0, 1, 3, 2]},
        ),
    ),
)
def test_array_additions_preserve_explicit_and_append_pointer_semantics(
    source: bytes,
    specs: tuple[tuple[str, int], ...],
    expected: bytes,
    expected_value: dict[str, list[int]],
    tmp_path: Path,
) -> None:
    # Given: an array with empty, append, or distinct explicit insertion positions.
    target = tmp_path / "array.jsonc"
    write_source(target, source)
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(source, target))
    patches = tuple(make_patch(api, PatchSpec("ADD", pointer, value)) for pointer, value in specs)

    # When: both values are applied against the original array in one call.
    patched = patch_bytes(api, document, patches)

    # Then: explicit indices and append semantics retain their frozen pointer behavior.
    assert patched == expected
    assert parse_document(api, DocumentSpec(patched, target)).value == expected_value
    assert patch_bytes(api, document, patches) == patched


@pytest.mark.parametrize(
    ("source", "specs", "expected", "expected_value"),
    (
        (
            b'\xef\xbb\xbf// header\r\n{\r\n  "items": [\r\n  ],\r\n}\r\n',
            (("/items/0", 1), ("/items/-", 2)),
            b'\xef\xbb\xbf// header\r\n{\r\n  "items": [\r\n    1,\r\n    2\r\n  ],\r\n}\r\n',
            {"items": [1, 2]},
        ),
        (
            b'\xef\xbb\xbf// header\r\n{\r\n  "items": [\r\n    0,\r\n  ],\r\n}\r\n',
            (("/items/1", 1), ("/items/-", 2)),
            (
                b'\xef\xbb\xbf// header\r\n{\r\n  "items": [\r\n'
                b"    0,\r\n    1,\r\n    2,\r\n  ],\r\n}\r\n"
            ),
            {"items": [0, 1, 2]},
        ),
    ),
)
def test_array_appends_preserve_multiline_jsonc_format(
    source: bytes,
    specs: tuple[tuple[str, int], ...],
    expected: bytes,
    expected_value: dict[str, list[int]],
    tmp_path: Path,
) -> None:
    # Given: a BOM-prefixed CRLF array with empty or trailing-comma syntax.
    target = tmp_path / "multiline-array.jsonc"
    write_source(target, source)
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(source, target))
    patches = tuple(make_patch(api, PatchSpec("ADD", pointer, value)) for pointer, value in specs)

    # When: two values are composed at the array's closing boundary.
    patched = patch_bytes(api, document, patches)

    # Then: the values are ordered, indented, reparsable, and byte-local.
    insertion = source.index(b"  ],", source.index(b'"items"'))
    assert patched == expected
    assert patched[:insertion] == source[:insertion]
    assert patched[len(patched) - (len(source) - insertion) :] == source[insertion:]
    assert parse_document(api, DocumentSpec(patched, target)).value == expected_value


def test_escaped_object_addition_pointers_remain_distinct(tmp_path: Path) -> None:
    # Given: two new members whose RFC-6901 pointers encode slash and tilde.
    source = b'{"obj": {}}'
    target = tmp_path / "escaped-additions.jsonc"
    write_source(target, source)
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(source, target))
    patches = tuple(
        make_patch(api, PatchSpec("ADD", pointer, value))
        for pointer, value in (("/obj/a~1b", 1), ("/obj/c~0d", 2))
    )

    # When: the escaped member additions are applied together.
    patched = patch_bytes(api, document, patches)

    # Then: decoded member names and their caller order survive the composition.
    assert patched == b'{"obj": {"a/b": 1, "c~d": 2}}'
    assert parse_document(api, DocumentSpec(patched, target)).value == {"obj": {"a/b": 1, "c~d": 2}}


@pytest.mark.parametrize(
    ("source", "specs", "expected_code"),
    (
        (
            b'{"obj": {}}',
            (PatchSpec("ADD", "/obj/a", 1), PatchSpec("ADD", "/obj/a", 2)),
            "OVERLAPPING_PATCHES",
        ),
        (
            b'{"value": 0}',
            (PatchSpec("REPLACE", "/value", 1), PatchSpec("REPLACE", "/value", 2)),
            "OVERLAPPING_PATCHES",
        ),
        (
            b'{"obj": {"a": 1}}',
            (PatchSpec("REMOVE", "/obj/a"), PatchSpec("REPLACE", "/obj", {"a": 2})),
            "OVERLAPPING_PATCHES",
        ),
        (
            b'{"obj": {"a": 1}}',
            (PatchSpec("REPLACE", "/obj", {"a": 2}), PatchSpec("REPLACE", "/obj/a", 3)),
            "OVERLAPPING_PATCHES",
        ),
        (
            b'{"items": []}',
            (PatchSpec("ADD", "/items/1", 1),),
            "INVALID_INDEX",
        ),
    ),
)
def test_incompatible_patch_intervals_remain_typed_rejections(
    source: bytes,
    specs: tuple[PatchSpec, ...],
    expected_code: str,
    tmp_path: Path,
) -> None:
    # Given: duplicate, overlapping, stale ancestor/descendant, or invalid edits.
    target = tmp_path / "invalid-composition.jsonc"
    write_source(target, source)
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(source, target))
    patches = tuple(make_patch(api, spec) for spec in specs)
    error_name = "JsoncPatchError"
    require_symbol(api, error_name)

    # When / Then: validation rejects the incompatible batch with its typed reason.
    with pytest.raises(getattr(api, error_name)) as captured:
        patch_bytes(api, document, patches)
    assert isinstance(captured.value, PatchErrorLike)
    assert captured.value.code == expected_code
