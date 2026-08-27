from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from panopticon.util.canonicalize import canonical_json_bytes, semantic_json_bytes


class CanonicalFixture(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    observed_at: datetime
    pid: int
    duration_ms: int
    container_id: str
    evidence: tuple[str, ...]


def test_canonical_json_preserves_run_metadata_and_orders_keys() -> None:
    # Given: a typed model with unordered semantic evidence and run metadata.
    fixture = CanonicalFixture(
        name="fixture",
        observed_at=datetime(2026, 8, 27, tzinfo=UTC),
        pid=42,
        duration_ms=9,
        container_id="container-a",
        evidence=("z", "a"),
    )

    # When: the persisted canonical form is serialized.
    result = canonical_json_bytes(fixture)

    # Then: UTF-8, key ordering, tuple order, and metadata are preserved.
    assert result.endswith(b"\n")
    assert b'"container_id":"container-a"' in result
    assert result.index(b'"container_id"') < result.index(b'"duration_ms"')
    assert b'"evidence":["z","a"]' in result


def test_semantic_view_strips_only_approved_volatility_and_sorts_arrays() -> None:
    # Given: semantically equal runs with distinct approved volatile fields.
    first = CanonicalFixture(
        name="fixture",
        observed_at=datetime(2026, 8, 27, tzinfo=UTC),
        pid=42,
        duration_ms=9,
        container_id="container-a",
        evidence=("z", "a"),
    )
    second = CanonicalFixture(
        name="fixture",
        observed_at=datetime(2027, 1, 1, tzinfo=UTC),
        pid=99,
        duration_ms=500,
        container_id="container-b",
        evidence=("a", "z"),
    )

    # When: semantic views are built.
    first_view = semantic_json_bytes(first)
    second_view = semantic_json_bytes(second)

    # Then: approved run volatility alone is partitioned from behavioral evidence.
    assert first_view == second_view
    assert b"observed_at" not in first_view
    assert b'"evidence":["a","z"]' in first_view
