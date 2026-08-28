"""Typed assertions shared by JSONC tests."""

from __future__ import annotations

from pathlib import Path

from panopticon.models import JsonPointer

from ._protocols import DocumentLike, JsonValue, SpanLike


def span_for(document: DocumentLike, pointer: str) -> SpanLike:
    """Find exactly one value span by its RFC-6901 pointer."""
    matches = tuple(span for span in document.spans if span.pointer == JsonPointer(pointer))
    assert len(matches) == 1, pointer
    return matches[0]


def assert_exact_spans(document: DocumentLike, source: bytes) -> None:
    """Require every semantic span to identify an exact, valid source interval."""
    spans = tuple(document.spans)
    assert spans
    line_count = source.count(b"\n") + 1
    for span in spans:
        assert 0 <= span.start < span.end <= len(source)
        assert span.offset == span.start
        assert 1 <= span.line <= line_count
        line_start = source.rfind(b"\n", 0, span.start) + 1
        if line_start == 0:
            line_start = len(document.bom)
        assert span.column == span.start - line_start + 1
        assert source[span.start : span.end]


def machine_value(value: str) -> str:
    """Read an enum-like state as its machine value."""
    candidate = getattr(value, "value", value)
    assert isinstance(candidate, str)
    return candidate


def as_object(value: JsonValue) -> dict[str, JsonValue]:
    """Narrow one parsed JSON value to an object for typed assertions."""
    assert isinstance(value, dict)
    return value


def assert_no_temp_residue(tmp_path: Path, target: Path) -> None:
    """Require a failed atomic operation to leave no same-directory temporary file."""
    assert not any(path.name.startswith(f".{target.name}.") for path in tmp_path.iterdir())
