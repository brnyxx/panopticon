"""Shipped schemas are canonical deterministic projections of runtime models."""

from __future__ import annotations

from pathlib import Path

from panopticon.models.schema import generate_schema_documents

SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"


def test_generated_schemas_match_shipped_bytes_across_two_generations() -> None:
    # Given / When: runtime schemas are independently generated twice.
    first = generate_schema_documents()
    second = generate_schema_documents()

    # Then: generation is stable and shipped files are the exact canonical bytes.
    assert first == second
    assert all((SCHEMAS / document.name).read_text() == document.content for document in first)
    assert all('"schema_version"' in document.content for document in first)
    assert all('"const": "1.0"' in document.content for document in first)
