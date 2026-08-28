from __future__ import annotations

import json
from pathlib import Path

import pytest

from panopticon.analyzers.behavior.catalog import RULE_BY_ID
from panopticon.analyzers.behavior.model import (
    Authority,
    BehaviorInput,
    CoverageState,
    DeclaredAuthority,
    EvidenceKind,
    OutcomeState,
    WatchEvidence,
)
from panopticon.analyzers.behavior.rules import evaluate, evaluate_rule
from panopticon.analyzers.behavior.spans import SpanKind
from panopticon.findings.build import occurrence_id
from panopticon.models.finding import EvidenceKind as FindingEvidenceKind
from panopticon.models.finding import FindingEvidence
from panopticon.models.ids import InstallationId

FIXTURE = Path(__file__).parents[2] / "fixtures/rules/behavior/expected_sets.json"


def _context(case: dict[str, object]) -> BehaviorInput:
    evidence = tuple(
        WatchEvidence(
            EvidenceKind(str(item["kind"])),
            str(item["value"]),
            str(item.get("operation", "")),
            span_kind=(SpanKind(str(item["span_kind"])) if item.get("span_kind") else None),
        )
        for item in case.get("evidence", [])
    )
    paths = tuple(str(item) for item in case.get("paths", []))
    hosts = tuple(str(item) for item in case.get("hosts", []))
    authority = Authority(
        "fixture",
        paths=paths,
        hosts=hosts,
        coverage=CoverageState.COMPLETE,
        authority=(
            DeclaredAuthority.AUTHORITATIVE
            if case.get("authoritative")
            else DeclaredAuthority.PARTIAL
        ),
    )
    return BehaviorInput(
        evidence=evidence,
        authorities=(authority,),
        decoys=frozenset(str(item) for item in case.get("decoys", [])),
        coverage=dict.fromkeys(EvidenceKind, CoverageState.COMPLETE),
    )


@pytest.mark.parametrize("group", ("evil", "clean"))
def test_data_driven_finding_sets(group: str) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for case in payload[group]:
        matches = evaluate(_context(case))
        confirmed = {
            match.rule_id
            for match in matches
            if match.state is OutcomeState.MATCH and RULE_BY_ID[match.rule_id].kind == "confirmed"
        }
        expected = set(case.get("expected", [])) if group == "evil" else set()
        assert confirmed == expected, case["name"]


def test_canonical_finding_id_is_stable() -> None:
    evidence = (
        FindingEvidence(kind=FindingEvidenceKind.HOST, subject="evil.example", value="connect"),
    )
    installation = InstallationId("inst_0123456789abcdef")
    assert occurrence_id("WATCH-003", installation, evidence) == occurrence_id(
        "WATCH-003", installation, evidence
    )


def test_allowlist_exclusion_is_recorded() -> None:
    match = evaluate_rule(
        "WATCH-005",
        _context(
            {
                "evidence": [
                    {
                        "kind": "network",
                        "value": "registry.npmjs.org",
                        "operation": "connect",
                        "span_kind": "install",
                    }
                ],
                "authoritative": True,
            }
        ),
    )
    assert match.state is OutcomeState.CLEAR
    assert [item.value for item in match.excluded] == ["registry.npmjs.org"]


@pytest.mark.parametrize("case", json.loads(FIXTURE.read_text(encoding="utf-8"))["clean"])
def test_clean_inputs_have_no_confirmed_findings(case: dict[str, object]) -> None:
    assert all(
        not (match.state is OutcomeState.MATCH and RULE_BY_ID[match.rule_id].kind == "confirmed")
        for match in evaluate(_context(case))
    )
