from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from panopticon.analyzers.semantic.cache import MemoryReviewCache
from panopticon.analyzers.semantic.context import REDACTED_MARKER
from panopticon.analyzers.semantic.reviewer import (
    DisclosureDecision,
    JsonObject,
    SemanticReviewer,
    SemanticStatus,
    allow_disclosure,
)
from panopticon.models.common import PersistedPath
from panopticon.models.finding import (
    EvidenceKind,
    Finding,
    FindingEvidence,
    FindingKind,
    FindingSeverity,
    SourceLocation,
)
from panopticon.models.ids import (
    FindingId,
    InstallationId,
    LogicalKey,
    ObservationId,
    ServerId,
)


@dataclass
class RecordingTransport:
    requests: list[JsonObject]

    async def create(self, request: JsonObject) -> JsonObject:
        self.requests.append(request)
        response = {
            "reviews": [
                {
                    "finding_id": "00000000-0000-4000-8000-000000000001",
                    "status": "needs_review",
                    "confidence": 0.5,
                    "reasoning": "Evidence remains incomplete.",
                    "evidence_refs": [
                        {
                            "path": "server.py",
                            "start_line": 1,
                            "end_line": 1,
                            "claim": "The supplied source line was reviewed.",
                        }
                    ],
                }
            ]
        }
        return {"text": json.dumps(response)}


class DenyDisclosure:
    def disclose(self, request: JsonObject) -> DisclosureDecision:
        return DisclosureDecision(None, "USER_DECLINED")


class RecordingDisclosure:
    def __init__(self) -> None:
        self.requests: list[JsonObject] = []

    def disclose(self, request: JsonObject) -> DisclosureDecision:
        self.requests.append(request)
        return DisclosureDecision(dict(request))


def _finding() -> Finding:
    return Finding(
        schema_version="1.0",
        id=FindingId("0000000000000001"),
        logical_key=LogicalKey("lk_0000000000000001"),
        rule_id="SENT-003",
        severity=FindingSeverity.MEDIUM,
        kind=FindingKind.CONFIRMED,
        title="Input validation evidence",
        evidence=(FindingEvidence(kind=EvidenceKind.PATH, subject="source", value="fp"),),
        location=SourceLocation(path=PersistedPath("server.py"), line=1, column=1),
        server_id=ServerId("local:test"),
        installation_id=InstallationId("inst_0000000000000001"),
        observation_id=ObservationId("obs_test"),
        span_ref=None,
        remediation_key=None,
        fix_available=False,
        declared_source=None,
        first_seen=datetime(1970, 1, 1, tzinfo=UTC),
        suppressed_by=None,
    )


def test_semantic_reviewer_redacts_before_transport(tmp_path: Path) -> None:
    token = "sk-abcdefghijklmnopqrstuvwx"
    (tmp_path / "server.py").write_text(f"api_key={token}\n", encoding="utf-8")
    disclosure = RecordingDisclosure()
    transport = RecordingTransport([])
    outcome = asyncio.run(
        SemanticReviewer(
            root=tmp_path,
            transport=transport,
            disclosure=disclosure,
        ).review((_finding(),))
    )
    assert outcome.status is SemanticStatus.COMPLETE
    approved = json.dumps(disclosure.requests[0], ensure_ascii=False)
    assert token not in approved and REDACTED_MARKER in approved
    assert transport.requests == disclosure.requests


def test_semantic_reviewer_denied_disclosure_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "server.py").write_text("value = 1\n", encoding="utf-8")
    transport = RecordingTransport([])
    outcome = asyncio.run(
        SemanticReviewer(
            root=tmp_path,
            transport=transport,
            disclosure=DenyDisclosure(),
        ).review((_finding(),))
    )
    assert outcome.status is SemanticStatus.UNSUPPORTED
    assert outcome.reason_code == "DISCLOSURE_DENIED"
    assert transport.requests == []


def test_semantic_reviewer_replays_approved_cassette_without_transport(
    tmp_path: Path,
) -> None:
    (tmp_path / "server.py").write_text("value = 1\n", encoding="utf-8")
    transport = RecordingTransport([])
    first = asyncio.run(
        SemanticReviewer(
            root=tmp_path,
            transport=transport,
            disclosure=allow_disclosure(),
        ).review((_finding(),))
    )
    assert first.cache_record is not None
    unused = RecordingTransport([])
    replay = asyncio.run(
        SemanticReviewer(
            root=tmp_path,
            transport=unused,
            disclosure=allow_disclosure(),
            cache=MemoryReviewCache((first.cache_record,)),
        ).review((_finding(),))
    )
    assert replay.status is SemanticStatus.COMPLETE
    assert replay.reason_code == "CACHE_HIT"
    assert unused.requests == []
