from __future__ import annotations

# Adapted semantic analyzer behavior.
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from panopticon.analyzers.semantic.cache import MemoryReviewCache, ReviewCacheRecord
from panopticon.analyzers.semantic.context import PATH_REDACTION, REDACTED_MARKER, sanitize_text
from panopticon.analyzers.semantic.model import ReviewBatchResponse
from panopticon.analyzers.semantic.tools import extract_tool_catalog


def test_semantic_context_redacts_values_and_absolute_paths() -> None:
    source = "api_key=abcdefghijklmnopqrst\n/Users/example/private/file.txt"

    sanitized = sanitize_text(source)

    assert sanitized == f"{REDACTED_MARKER}\n{PATH_REDACTION}"
    assert sanitized.count("\n") == source.count("\n")


def test_tool_catalog_is_ast_only_and_deterministic(tmp_path: Path) -> None:
    (tmp_path / "server.py").write_text(
        '@mcp.tool()\ndef search(query: str, limit: int = 2):\n    """Search."""\n    return []\n',
        encoding="utf-8",
    )

    first = extract_tool_catalog(tmp_path)
    second = extract_tool_catalog(tmp_path)

    assert first == second
    assert first.tools[0].name == "search"
    assert first.tools[0].input_schema["required"] == ["query"]


def test_review_models_and_value_cache_reject_invalid_records() -> None:
    payload = {
        "reviews": [
            {
                "finding_id": "00000000-0000-4000-8000-000000000001",
                "status": "needs_review",
                "confidence": 0.5,
                "reasoning": "Evidence is incomplete.",
                "evidence_refs": [
                    {
                        "path": "server.py",
                        "start_line": 1,
                        "end_line": 2,
                        "claim": "Observed call site.",
                    }
                ],
            }
        ]
    }
    response = ReviewBatchResponse.model_validate_json(json.dumps(payload))
    record = ReviewCacheRecord("key", response.model_dump_json())
    cache = MemoryReviewCache((record,))

    assert cache.get("key") == record
    with pytest.raises(ValidationError):
        ReviewBatchResponse.model_validate_json(
            json.dumps(
                {
                    **payload,
                    "reviews": [
                        {
                            **payload["reviews"][0],
                            "evidence_refs": [
                                {
                                    "path": "../escape",
                                    "start_line": 2,
                                    "end_line": 1,
                                    "claim": "Invalid.",
                                }
                            ],
                        }
                    ],
                }
            )
        )
