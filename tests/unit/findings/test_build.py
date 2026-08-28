from datetime import UTC, datetime

from panopticon.findings.build import FindingDraft, build_finding, normalize_evidence
from panopticon.models.finding import EvidenceKind, FindingEvidence
from panopticon.models.ids import InstallationId, ObservationId, ServerId
from panopticon.rules.registry import RuleMeta


def test_evidence_normalization_is_sorted_and_redacts_home() -> None:
    evidence = normalize_evidence(
        [
            FindingEvidence(kind=EvidenceKind.HOST, subject="h", value="EXAMPLE.COM:443"),
            FindingEvidence(kind=EvidenceKind.PATH, subject="p", value="/Users/alice/x"),
        ]
    )
    assert evidence[0].value == "example.com"
    assert evidence[1].value == "~/x"


def test_occurrence_changes_with_evidence_but_logical_key_does_not() -> None:
    meta = RuleMeta("WATCH-001", "HIGH", "confirmed", "observe")
    installation_id = InstallationId("inst_0123456789abcdef")
    first = build_finding(
        FindingDraft(
            meta=meta,
            server_id=ServerId("local:test"),
            installation_id=installation_id,
            observation_id=ObservationId("obs_one"),
            subject="tool",
            title="title",
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
            evidence=(
                {"kind": "HOST", "subject": "x", "value": "a.com"},
                {"kind": "PATH", "subject": "config", "value": "/Users/alice/.config"},
            ),
        )
    )
    second = build_finding(
        FindingDraft(
            meta=meta,
            server_id=ServerId("local:test"),
            installation_id=installation_id,
            observation_id=ObservationId("obs_one"),
            subject="tool",
            title="title",
            # A later observation and reversed, equivalent evidence must
            # retain the same canonical occurrence ID.
            first_seen=datetime(2026, 1, 2, tzinfo=UTC),
            evidence=(
                {"kind": "PATH", "subject": "config", "value": "/home/bob/.config"},
                {"kind": "HOST", "subject": "x", "value": "a.com"},
            ),
        )
    )
    assert first.logical_key == second.logical_key
    assert first.id == second.id

    changed = build_finding(
        FindingDraft(
            meta=meta,
            server_id=ServerId("local:test"),
            installation_id=installation_id,
            observation_id=ObservationId("obs_two"),
            subject="tool",
            title="title",
            first_seen=datetime(2026, 1, 2, tzinfo=UTC),
            evidence=({"kind": "HOST", "subject": "x", "value": "changed.example"},),
        )
    )
    assert first.logical_key == changed.logical_key
    assert first.id != changed.id
