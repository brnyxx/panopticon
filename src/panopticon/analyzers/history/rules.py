"""Executable HIST-001..004 rules over immutable snapshot series."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from packaging.version import InvalidVersion, Version

from panopticon.registry.history import SnapshotSeries
from panopticon.registry.model import HistoryStatus, NormalizedHistory, ReleaseRecord

from .catalog import RULE_BY_ID
from .model import HistoryEvidence, HistoryOutcome, HistoryRule
from .model import HistoryStatus as OutcomeStatus

RuleFn = Callable[[SnapshotSeries, datetime], HistoryOutcome]


def _unknown(rule: HistoryRule, reason: str) -> HistoryOutcome:
    return HistoryOutcome(
        rule.rule_id, OutcomeStatus.UNKNOWN, rule.severity, rule.kind, rule.fix_id, reason
    )


def _context(
    rule: HistoryRule, series: SnapshotSeries
) -> tuple[NormalizedHistory, NormalizedHistory] | None:
    if len(series.snapshots) < 2:
        return None
    previous, current = series.snapshots[-2].history, series.snapshots[-1].history
    if (
        current.status is not HistoryStatus.AVAILABLE
        or previous.status is not HistoryStatus.AVAILABLE
    ):
        return None
    if current.registry_fresh is not True or previous.registry_fresh is not True:
        return None
    if current.ecosystem.casefold() not in {"npm", "pypi", "github", "git"}:
        return None
    return previous, current


def _result(
    rule: HistoryRule, found: bool, reason: str, evidence: tuple[HistoryEvidence, ...]
) -> HistoryOutcome:
    return HistoryOutcome(
        rule.rule_id,
        OutcomeStatus.FINDING if found else OutcomeStatus.CLEAR,
        rule.severity,
        rule.kind,
        rule.fix_id,
        reason,
        evidence,
    )


def _releases(history: NormalizedHistory, *, stable: bool = False) -> tuple[ReleaseRecord, ...]:
    values = tuple(item for item in history.releases if not item.yanked)
    if not stable:
        return values
    retained: list[ReleaseRecord] = []
    for item in values:
        parsed = _version(item.version)
        if parsed is not None and not parsed[1]:
            retained.append(item)
    return tuple(retained)


def _version(value: str) -> tuple[int, bool] | None:
    try:
        parsed = Version(value.removeprefix("v").removeprefix("V"))
    except InvalidVersion:
        return None
    return parsed.major, parsed.is_prerelease or parsed.is_devrelease


def hist001(series: SnapshotSeries, now: datetime) -> HistoryOutcome:
    rule = RULE_BY_ID["HIST-001"]
    context = _context(rule, series)
    if context is None:
        return _unknown(rule, "INSUFFICIENT_FRESH_HISTORY")
    previous, current = context
    old = {record.version for record in _releases(previous)}
    added = tuple(
        sorted(record.version for record in _releases(current) if record.version not in old)
    )
    return _result(
        rule,
        bool(added),
        "RELEASES_ADDED" if added else "NO_RELEASES_ADDED",
        tuple(HistoryEvidence("release", value) for value in added),
    )


def hist002(series: SnapshotSeries, now: datetime) -> HistoryOutcome:
    rule = RULE_BY_ID["HIST-002"]
    context = _context(rule, series)
    if context is None:
        return _unknown(rule, "INSUFFICIENT_FRESH_HISTORY")
    previous, current = context
    old_versions = tuple(_version(item.version) for item in _releases(previous, stable=True))
    new_versions = tuple(_version(item.version) for item in _releases(current, stable=True))
    old_major = max((value[0] for value in old_versions if value is not None), default=None)
    new_major = max((value[0] for value in new_versions if value is not None), default=None)
    if old_major is None or new_major is None:
        return _result(rule, False, "NO_COMPARABLE_RELEASES", ())
    found = new_major > old_major
    evidence = (HistoryEvidence("major_version", f"{old_major}->{new_major}"),) if found else ()
    return _result(
        rule, found, "MAJOR_VERSION_JUMP" if found else "NO_MAJOR_VERSION_JUMP", evidence
    )


def hist003(series: SnapshotSeries, now: datetime) -> HistoryOutcome:
    rule = RULE_BY_ID["HIST-003"]
    context = _context(rule, series)
    if context is None:
        return _unknown(rule, "INSUFFICIENT_FRESH_HISTORY")
    previous, current = context
    if current.ecosystem.casefold() != "npm":
        return _unknown(rule, "UNSUPPORTED_ECOSYSTEM")
    added = tuple(sorted(set(current.maintainers) - set(previous.maintainers)))
    removed = tuple(sorted(set(previous.maintainers) - set(current.maintainers)))
    changed = bool(added or removed)
    evidence = tuple(HistoryEvidence("maintainer_added", item) for item in added) + tuple(
        HistoryEvidence("maintainer_removed", item) for item in removed
    )
    return _result(
        rule, changed, "MAINTAINERS_CHANGED" if changed else "MAINTAINERS_UNCHANGED", evidence
    )


def hist004(series: SnapshotSeries, now: datetime) -> HistoryOutcome:
    rule = RULE_BY_ID["HIST-004"]
    context = _context(rule, series)
    if context is None:
        return _unknown(rule, "INSUFFICIENT_FRESH_HISTORY")
    _, current = context
    if current.archived is True:
        return _result(
            rule, True, "REPOSITORY_ARCHIVED", (HistoryEvidence("repository", "archived"),)
        )
    if current.archived is None:
        return _unknown(rule, "ARCHIVE_STATUS_UNAVAILABLE")
    dates = [
        release.published_at for release in _releases(current) if release.published_at is not None
    ]
    if not dates:
        return _unknown(rule, "ACTIVITY_TIMESTAMP_UNAVAILABLE")
    latest = max(dates)
    if (
        latest.tzinfo is None
        or latest.utcoffset() is None
        or now.tzinfo is None
        or now.utcoffset() is None
    ):
        raise ValueError("history clock and activity timestamps must be timezone-aware")
    current_utc = now.astimezone(UTC)
    try:
        cutoff = current_utc.replace(year=current_utc.year - 1)
    except ValueError:
        cutoff = current_utc.replace(year=current_utc.year - 1, day=28)
    inactive = latest.astimezone(UTC) <= cutoff
    return _result(
        rule,
        inactive,
        "INACTIVITY_THRESHOLD_REACHED" if inactive else "RECENT_ACTIVITY",
        (HistoryEvidence("activity", "inactive_12_months"),) if inactive else (),
    )


_RULES: tuple[RuleFn, ...] = (hist001, hist002, hist003, hist004)


def analyze_history(series: SnapshotSeries, *, now: datetime) -> tuple[HistoryOutcome, ...]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return tuple(rule(series, now) for rule in _RULES)


def evaluate_rule(rule_id: str, series: SnapshotSeries, *, now: datetime) -> HistoryOutcome:
    try:
        index = ("HIST-001", "HIST-002", "HIST-003", "HIST-004").index(rule_id)
    except ValueError as exc:
        raise KeyError(rule_id) from exc
    return _RULES[index](series, now)
