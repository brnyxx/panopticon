"""OMO Wave 4 contract tests for the WATCH rule catalog."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from panopticon.analyzers.behavior.catalog import RULE_CATALOG, RULE_IDS
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

CASES = json.loads(
    (Path(__file__).parents[4] / "tests/fixtures/rules/behavior/cases.json").read_text()
)


def _context(raw: dict) -> BehaviorInput:
    source_state = CoverageState(
        raw.get(
            "source_coverage",
            "PARTIAL" if raw.get("direction") == "unknown" else "COMPLETE",
        )
    )
    evidence = tuple(
        WatchEvidence(
            kind=EvidenceKind(e["kind"]),
            value=e["value"],
            operation=e.get("operation", ""),
            span_id=e.get("span_id"),
            span_kind=SpanKind(e["span_kind"]) if e.get("span_kind") else None,
            certain=e.get("certain", True),
            tls=e.get("tls", False),
            post=e.get("post", False),
            source=e.get("source", "trace"),
            declared=e.get("declared", False),
        )
        for e in raw.get("evidence", ())
    )
    authorities = tuple(
        Authority(
            tool=a["tool"],
            paths=tuple(a.get("paths", ())),
            hosts=tuple(a.get("hosts", ())),
            processes=tuple(a.get("processes", ())),
            read_only_hint=a.get("read_only_hint"),
            coverage=CoverageState(a.get("coverage", "NONE")),
            authority=DeclaredAuthority(
                "AUTHORITATIVE"
                if a.get("coverage") == "COMPLETE"
                else ("PARTIAL" if a.get("coverage") == "PARTIAL" else "NONE")
            ),
        )
        for a in raw.get("authorities", ())
    )
    if not authorities and raw.get("direction") != "unknown":
        authorities = (
            Authority(
                tool="t",
                coverage=CoverageState.COMPLETE,
                authority=DeclaredAuthority.AUTHORITATIVE,
            ),
        )
    return BehaviorInput(
        evidence=evidence,
        authorities=authorities,
        decoys=frozenset(raw.get("decoys", ())),
        coverage=dict.fromkeys(EvidenceKind, source_state),
        complete_spans=source_state is CoverageState.COMPLETE,
        withheld=raw.get("withheld", False),
        suppressed_rule_ids=frozenset(raw.get("suppressed_rule_ids", ())),
    )


def test_each_fixture_yields_exact_watch_finding() -> None:
    assert tuple(RULE_IDS) == tuple(f"WATCH-{i:03d}" for i in range(1, 15))
    coverage = CASES["coverage"]
    for direction in ("positive", "negative", "unknown"):
        assert set(coverage[direction]) == set(RULE_IDS)
    by_key = {(c["id"], c["direction"]): c for c in CASES["cases"]}
    assert set(by_key) == {
        (rule_id, direction)
        for rule_id in RULE_IDS
        for direction in ("positive", "negative", "unknown")
    }
    metadata = {r.rule_id: (r.severity, r.kind, r.condition) for r in RULE_CATALOG}
    assert metadata == {rule_id: tuple(values) for rule_id, values in CASES["metadata"].items()}
    for rule_id in RULE_IDS:
        for direction in ("positive", "negative", "unknown"):
            case = by_key[(rule_id, direction)]
            match = evaluate_rule(rule_id, _context(case))
            assert (match.rule_id, match.state.value) == (rule_id, case["state"])
            expected = tuple(
                sorted(
                    (
                        WatchEvidence(
                            kind=EvidenceKind(e["kind"]),
                            value=e["value"],
                            operation=e.get("operation", ""),
                            span_kind=SpanKind(e["span_kind"]) if e.get("span_kind") else None,
                            certain=e.get("certain", True),
                            post=e.get("post", False),
                        )
                        for e in case.get("evidence", ())
                    ),
                    key=lambda e: (e.span_id or "", e.kind.value, e.value, e.operation),
                )
            )
            expected_signatures = {(e.kind, e.value, e.operation, e.span_kind) for e in expected}
            observed = (*match.evidence, *match.excluded)
            observed_signatures = {(e.kind, e.value, e.operation, e.span_kind) for e in observed}
            assert observed_signatures <= expected_signatures
            assert match.evidence == tuple(
                sorted(
                    match.evidence,
                    key=lambda e: (e.span_id or "", e.kind.value, e.value, e.operation),
                )
            )
            if direction == "positive" and rule_id not in {"WATCH-010", "WATCH-011"}:
                assert match.evidence
    assert all(len(metadata[r]) == 3 for r in RULE_IDS)


def test_partial_evidence_never_confirms_or_grants_badge() -> None:
    by_key = {(c["id"], c["direction"]): c for c in CASES["cases"]}
    for rule_id in RULE_IDS:
        case = by_key[(rule_id, "unknown")]
        match = evaluate_rule(rule_id, _context(case))
        if rule_id == "WATCH-011":
            assert match.state is OutcomeState.MATCH
            assert match.reason == "DECLARATION_INCOMPLETE"
        else:
            assert match.state is OutcomeState.UNKNOWN, (rule_id, match)
    # Excluded interpreter/process observations cannot make declared=observed eligible.
    badge = evaluate_rule(
        "WATCH-010",
        _context(
            {
                "evidence": [{"kind": "process", "value": "python3"}],
                "authorities": [{"tool": "t", "coverage": "COMPLETE"}],
            }
        ),
    )
    assert badge.state is OutcomeState.UNKNOWN
    assert evaluate(_context(by_key[("WATCH-010", "positive")]))[9].state is OutcomeState.MATCH


@pytest.mark.parametrize(
    ("coverage", "badge", "withheld"),
    [("NONE", "UNKNOWN", "MATCH"), ("PARTIAL", "UNKNOWN", "MATCH"), ("COMPLETE", "MATCH", "CLEAR")],
)
def test_every_source_coverage_transition_is_explicit(
    coverage: str, badge: str, withheld: str
) -> None:
    raw = {
        "evidence": [{"kind": "read", "value": "~/declared"}],
        "authorities": [
            {"tool": "t", "paths": ["~/declared"], "coverage": coverage},
        ],
    }
    assert evaluate_rule("WATCH-010", _context(raw)).state.value == badge
    assert evaluate_rule("WATCH-011", _context(raw)).state.value == withheld


@pytest.mark.parametrize("count,expected", [(9, "CLEAR"), (10, "MATCH")])
def test_broad_enumeration_boundary(count: int, expected: str) -> None:
    case = {"evidence": [{"kind": "stat", "value": f"~/Documents/f{i}"} for i in range(count)]}
    assert evaluate_rule("WATCH-009", _context(case)).state.value == expected


@pytest.mark.parametrize("count,expected", [(9, "CLEAR"), (10, "MATCH")])
def test_many_external_urls_boundary(count: int, expected: str) -> None:
    case = {"evidence": [{"kind": "url", "value": f"https://x{i}.example"} for i in range(count)]}
    assert evaluate_rule("WATCH-012", _context(case)).state.value == expected
