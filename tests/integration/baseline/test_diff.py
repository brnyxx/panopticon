"""Contract acceptance tests for deterministic, coverage-aware baseline diffs."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from panopticon.diff.compute import compute_diff
from panopticon.models.artifacts import Baseline, BaselineKind
from panopticon.models.finding import EvidenceKind, Finding, FindingEvidence
from panopticon.models.observation import Observation
from panopticon.models.state import StageStatus


def _obs(
    *,
    oid="obs",
    install="inst_0000000000000001",
    findings=(),
    tools=(),
    events=(),
    coverage=None,
    at=None,
):
    complete = SimpleNamespace(status=StageStatus.COMPLETE)
    coverage = coverage or dict.fromkeys(
        ("file", "net", "process", "dns", "proxy", "snapshot", "stdio"), complete
    )
    state = SimpleNamespace(coverage=SimpleNamespace(**coverage), overall=complete)
    spans = (
        (SimpleNamespace(events=tuple(SimpleNamespace(root=e) for e in events)),) if events else ()
    )
    return Observation.model_construct(
        schema_version="1.0",
        observation_id=oid,
        server_id="server",
        installation_id=install,
        observed_at=at or datetime(2025, 1, 1, tzinfo=UTC),
        pano_version="0.1",
        sandbox=SimpleNamespace(),
        package_resolved=None,
        protocol=SimpleNamespace(),
        tools=tuple(tools),
        spans=spans,
        declared=SimpleNamespace(),
        findings=tuple(findings),
        state=state,
    )


def _finding(key, install="inst_0000000000000001", evidence=()):
    return Finding.model_construct(logical_key=key, installation_id=install, evidence=evidence)


def _tool(name, schema="aaaaaaaaaaaaaaaa", destructive=False):
    return SimpleNamespace(
        name=name,
        input_schema_hash=schema,
        annotations=SimpleNamespace(destructive=destructive),
        model_dump=lambda **_: {"name": name, "schema": schema, "destructive": destructive},
    )


def _event(kind, **kwargs):
    return SimpleNamespace(kind=kind, **kwargs)


def test_one_behavior_mutation_yields_one_meaningful_delta():
    before = _obs(events=(_event("net", host="old.example", port=443),))
    after = _obs(events=(_event("net", host="new.example", port=443),))
    diff = compute_diff(before, after)
    assert {(d.kind, d.key) for d in diff.behavior} == {
        ("REMOVED_HOST", "host:old.example:443"),
        ("NEW_HOST", "host:new.example:443"),
    }
    assert [(d.kind, d.key) for d in diff.meaningful] == [("NEW_HOST", "host:new.example:443")]


def test_missing_old_coverage_is_unknown():
    partial = {
        k: SimpleNamespace(status=StageStatus.PARTIAL)
        for k in ("net", "file", "process", "dns", "proxy", "snapshot", "stdio")
    }
    before = _obs(events=(_event("net", host="x", port=1),), coverage=partial)
    after = _obs(
        events=(), coverage={k: SimpleNamespace(status=StageStatus.COMPLETE) for k in partial}
    )
    assert compute_diff(before, after).behavior[0].kind == "UNKNOWN"


def test_absence_resolves_only_when_both_overall_sides_are_complete():
    finding = _finding("CFG-010")
    complete = _obs(findings=(finding,))
    partial = _obs(findings=())
    partial = Observation.model_construct(
        **{
            **partial.__dict__,
            "state": SimpleNamespace(
                coverage=partial.state.coverage, overall=SimpleNamespace(status=StageStatus.PARTIAL)
            ),
        }
    )
    assert compute_diff(complete, partial).findings.unknown[0].kind == "UNKNOWN"
    assert compute_diff(complete, _obs(findings=())).findings.resolved[0].kind == "RESOLVED"


@pytest.mark.parametrize(
    "old,new,expected", [("", "k", "NEW"), ("k", "", "RESOLVED"), ("k", "k2", "RESOLVED")]
)
def test_logical_findings_new_changed_resolved(old, new, expected):
    left = (_finding(old),) if old else ()
    right = (_finding(new),) if new else ()
    result = compute_diff(_obs(findings=left), _obs(findings=right))
    bucket = getattr(result.findings, expected.lower())
    assert bucket and bucket[0].kind == expected


def test_finding_change_and_evidence_only_change_are_distinct():
    old = _finding(
        "CFG-001",
        evidence=(FindingEvidence(kind=EvidenceKind.PATH, subject="p", value="1"),),
    )
    new = _finding(
        "CFG-001",
        evidence=(FindingEvidence(kind=EvidenceKind.PATH, subject="p", value="2"),),
    )
    result = compute_diff(_obs(findings=(old,)), _obs(findings=(new,)))
    assert result.findings.changed[0].kind == "CHANGED"


@pytest.mark.parametrize(
    "category", ["net", "file", "process", "dns", "proxy", "snapshot", "stdio"]
)
def test_behavior_removal_requires_complete_coverage(category):
    event = _event("net", host="x", port=1)
    partial = {
        k: SimpleNamespace(status=StageStatus.COMPLETE)
        for k in ("net", "file", "process", "dns", "proxy", "snapshot", "stdio")
    }
    partial["net"] = SimpleNamespace(status=StageStatus.PARTIAL)
    result = compute_diff(
        _obs(events=(event,), coverage=partial), _obs(events=(), coverage=partial)
    )
    assert result.behavior[0].kind == "UNKNOWN"


def test_behavior_removal_is_resolved_with_complete_coverage_on_both_sides():
    event = _event("net", host="x", port=1)
    result = compute_diff(_obs(events=(event,)), _obs(events=()))
    assert result.behavior[0].kind == "REMOVED_HOST"


def test_capability_behavior_inventory_changes_and_duplicates_are_deterministic():
    left = _obs(tools=(_tool("z"), _tool("z")), events=(_event("file", path="/a"),))
    right = _obs(
        tools=(_tool("z", schema="bbbbbbbbbbbbbbbb"), _tool("a")),
        events=(_event("file", path="/b"),),
    )
    result = compute_diff(left, right)
    assert [d.kind for d in result.capability] == ["NEW_TOOL", "SCHEMA_CHANGED"]
    assert [d.key for d in result.behavior] == ["path:/b", "path:/a"]


def test_dns_and_connect_remain_distinct_and_decoy_keys_do_not_collide():
    left = _obs(events=(_event("leak", decoy_key="alpha"), _event("net", host="x", port=53)))
    right = _obs(events=(_event("leak", decoy_key="beta"), _event("net", host="x", port=443)))
    result = compute_diff(left, right)
    assert {d.key for d in result.behavior} == {
        "host:x:53",
        "host:x:443",
        "leak:alpha",
        "leak:beta",
    }


def test_reordered_inputs_and_identical_semantics_are_zero_diff():
    a = _obs(oid="a", install="inst_0000000000000001", tools=(_tool("b"), _tool("a")))
    b = _obs(oid="b", install="inst_0000000000000001", tools=(_tool("a"), _tool("b")))
    result = compute_diff(a, b)
    assert not result.capability and not result.behavior and not result.meaningful


def _baseline(*observations, inventory=()):
    return Baseline.model_construct(
        schema_version="1.0",
        baseline_id="base",
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        label=None,
        kind=BaselineKind.EXPLICIT,
        inventory=tuple(inventory),
        observations=tuple(observations),
        findings=(),
    )


@pytest.mark.parametrize("field", ["command", "env_keys", "package"])
def test_inventory_changes_are_reported(field):
    def server(command, env, version):
        package = SimpleNamespace(resolved=version) if version else None
        return SimpleNamespace(
            installation_id="inst_0000000000000001",
            command=command,
            env_keys=(env,),
            package=package,
        )

    old = server("run", "A", "1")
    new = server(
        "run2" if field == "command" else "run",
        "B" if field == "env_keys" else "A",
        "2" if field == "package" else "1",
    )
    kinds = {
        entry.kind
        for entry in compute_diff(
            _baseline(inventory=(old,)), _baseline(inventory=(new,))
        ).inventory
    }
    assert {
        "command": "COMMAND_CHANGED",
        "env_keys": "ENV_KEYS_CHANGED",
        "package": "VERSION_CHANGED",
    }[field] in kinds
