from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from panopticon.analyzers.history import analyze_history, evaluate_rule
from panopticon.analyzers.history.catalog import RULES
from panopticon.registry.history import SnapshotSeries, TransitionStatus, append_snapshot
from panopticon.registry.model import HistoryReason, HistoryStatus, NormalizedHistory, ReleaseRecord

CASES = json.loads(
    (Path(__file__).parents[3] / "fixtures" / "rules" / "history" / "cases.json").read_text()
)
EXPECTED_METADATA = {
    "HIST-001": ("INFO", "info", None),
    "HIST-002": ("MEDIUM", "info", None),
    "HIST-003": ("HIGH", "review", None),
    "HIST-004": ("MEDIUM", "info", None),
}
NOW = datetime(2025, 2, 28, tzinfo=UTC)


def _history(data: dict, ecosystem: str, name: str) -> NormalizedHistory:
    releases = tuple(
        ReleaseRecord(
            **{
                **release,
                "published_at": (
                    datetime.fromisoformat(release["published_at"])
                    if isinstance(release.get("published_at"), str)
                    else release.get("published_at")
                ),
            }
        )
        for release in data.get("releases", ())
    )
    return NormalizedHistory(
        status=HistoryStatus(data["status"]),
        reason_code=HistoryReason(data["reason_code"]),
        ecosystem=ecosystem,
        name=name,
        requested_spec="*",
        maintainers=tuple(data.get("maintainers", ())),
        archived=data.get("archived"),
        releases=releases,
        registry_fresh=data.get("registry_fresh"),
    )


def _series(case: dict) -> SnapshotSeries:
    series = SnapshotSeries()
    for key in ("previous", "current"):
        series = append_snapshot(
            series,
            _history(case[key], case["ecosystem"], case["name"]),
            observed_at=datetime(2025, 1 if key == "previous" else 2, 1, tzinfo=UTC),
        )
    return series


def test_snapshot_transition_yields_exact_hist_set() -> None:
    assert tuple(rule.rule_id for rule in RULES) == (
        "HIST-001",
        "HIST-002",
        "HIST-003",
        "HIST-004",
    )
    for rule in RULES:
        assert (rule.severity.value, rule.kind.value, rule.fix_id) == EXPECTED_METADATA[
            rule.rule_id
        ]

    for case in CASES:
        series = _series(case)
        current = series.snapshots[-1]
        previous = series.snapshots[-2]
        expected_added = tuple(
            sorted(
                {release.version for release in current.history.releases}
                - {release.version for release in previous.history.releases}
            )
        )
        expected_removed = tuple(
            sorted(
                {release.version for release in previous.history.releases}
                - {release.version for release in current.history.releases}
            )
        )
        expected_added_maintainers = tuple(
            sorted(set(current.history.maintainers) - set(previous.history.maintainers))
        )
        expected_removed_maintainers = tuple(
            sorted(set(previous.history.maintainers) - set(current.history.maintainers))
        )
        assert current.transition.status is (
            TransitionStatus.CHANGED
            if expected_added
            or expected_removed
            or expected_added_maintainers
            or expected_removed_maintainers
            else TransitionStatus.UNCHANGED
        )
        assert current.transition.added_releases == expected_added
        assert current.transition.removed_releases == expected_removed
        assert current.transition.added_maintainers == expected_added_maintainers
        assert current.transition.removed_maintainers == expected_removed_maintainers
        expected = case["expected"]
        now = datetime.fromisoformat(case.get("now", NOW.isoformat()))
        outcome = evaluate_rule(case["id"], series, now=now)
        assert outcome.status.value == expected["status"]
        assert outcome.reason == expected["reason"]
        assert [(item.subject, item.classification) for item in outcome.evidence] == [
            tuple(item) for item in expected["evidence"]
        ]

        all_outcomes = analyze_history(series, now=now)
        assert tuple(item.rule_id for item in all_outcomes) == tuple(rule.rule_id for rule in RULES)

    archived_case = next(case for case in CASES if case["name"] == "pypi-inactive-exact-12-months")
    with pytest.raises(ValueError, match="timezone-aware"):
        evaluate_rule("HIST-004", _series(archived_case), now=datetime(2025, 2, 28))


def test_missing_prior_snapshot_is_unknown() -> None:
    for ecosystem in ("npm", "pypi", "github"):
        history = _history(
            {"status": "AVAILABLE", "reason_code": "OK", "archived": False, "registry_fresh": True},
            ecosystem,
            "missing-prior",
        )
        series = append_snapshot(
            SnapshotSeries(), history, observed_at=datetime(2025, 2, 1, tzinfo=UTC)
        )
        snapshot = series.snapshots[0]
        assert snapshot.transition.status is TransitionStatus.UNKNOWN
        assert snapshot.transition.reason_code == "FIRST_OBSERVATION"
        for rule in RULES:
            outcome = evaluate_rule(rule.rule_id, series, now=NOW)
            assert outcome.status.value == "unknown"
            assert outcome.reason == "INSUFFICIENT_FRESH_HISTORY"
            assert outcome.evidence == ()

    stale = next(case for case in CASES if case["name"] == "github-stale-history-unknown")
    outcomes = analyze_history(_series(stale), now=NOW)
    assert all(outcome.status.value == "unknown" for outcome in outcomes)
