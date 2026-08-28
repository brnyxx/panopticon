from datetime import UTC, datetime

from panopticon.registry.history import SnapshotSeries, TransitionStatus, append_snapshot
from panopticon.registry.model import HistoryReason, HistoryStatus
from panopticon.registry.normalize import (
    normalize_github,
    normalize_npm,
    normalize_pypi,
    normalize_registry_history,
    parse_timestamp,
)


def test_npm_exact_and_deprecated() -> None:
    payload = {
        "versions": {"1.0.0": {}, "2.0.0": {"deprecated": True}},
        "time": {"1.0.0": "2024-01-01T00:00:00Z", "2.0.0": "2024-02-01T00:00:00Z"},
        "dist-tags": {"latest": "2.0.0"},
        "homepage": "https://user:secret@example.test/pkg?token=x",
    }
    result = normalize_npm(payload, name="pkg", spec="latest", now=datetime(2025, 1, 1, tzinfo=UTC))
    assert result.status is HistoryStatus.AVAILABLE
    assert result.resolved_version == "2.0.0"
    assert result.reason_code is HistoryReason.DEPRECATED
    assert "secret" not in (result.source_url or "")


def test_pypi_yanked_and_bad_timestamp() -> None:
    payload = {
        "releases": {
            "1.0.0": [{"upload_time_iso_8601": "bad"}],
            "2.0.0": [{"yanked": True, "upload_time_iso_8601": "2024-01-01T00:00:00Z"}],
        }
    }
    result = normalize_pypi(payload, name="pkg", spec="1.0.0")
    assert result.status is HistoryStatus.INCOMPLETE
    assert result.reason_code is HistoryReason.INVALID_TIMESTAMP
    assert parse_timestamp(None)[1] is HistoryReason.MISSING_TIMESTAMP


def test_semver_ranges_and_tags_are_numeric_not_lexicographic() -> None:
    payload = {
        "versions": {"1.9.0": {}, "2.0.0": {}, "10.0.0": {}},
        "time": {
            "1.9.0": "2024-01-01T00:00:00Z",
            "2.0.0": "2024-02-01T00:00:00Z",
            "10.0.0": "2024-03-01T00:00:00Z",
        },
        "dist-tags": {"latest": "10.0.0", "legacy": "1.9.0"},
    }
    now = datetime(2025, 1, 1, tzinfo=UTC)

    assert normalize_npm(payload, name="pkg", spec="latest", now=now).resolved_version == "10.0.0"
    assert normalize_npm(payload, name="pkg", spec="legacy", now=now).resolved_version == "1.9.0"
    assert normalize_npm(payload, name="pkg", spec=">=2 <10", now=now).resolved_version == "2.0.0"
    assert normalize_npm(payload, name="pkg", spec="^2.0.0", now=now).resolved_version == "2.0.0"


def test_exact_yanked_pypi_release_is_visible() -> None:
    payload = {
        "releases": {
            "1.0.0": [
                {
                    "yanked": True,
                    "upload_time_iso_8601": "2024-01-01T00:00:00Z",
                }
            ],
            "2.0.0": [
                {
                    "yanked": False,
                    "upload_time_iso_8601": "2024-02-01T00:00:00Z",
                }
            ],
        },
        "info": {"version": "2.0.0"},
    }

    exact = normalize_pypi(
        payload,
        name="pkg",
        spec="1.0.0",
        now=datetime(2025, 1, 1, tzinfo=UTC),
    )

    assert exact.status is HistoryStatus.AVAILABLE
    assert exact.reason_code is HistoryReason.YANKED
    assert exact.resolved_version == "1.0.0"
    assert exact.releases[0].yanked


def test_github_history_normalizes_archived_url_and_release_age() -> None:
    result = normalize_github(
        {
            "html_url": "https://User:token@GitHub.com/Owner/Repo?secret=x",
            "archived": True,
            "releases": [
                {
                    "tag_name": "v1.0.0",
                    "published_at": "2024-01-01T00:00:00Z",
                    "draft": False,
                }
            ],
        },
        name="Owner/Repo",
        spec="v1.0.0",
        now=datetime(2024, 1, 11, tzinfo=UTC),
    )

    assert result.status is HistoryStatus.AVAILABLE
    assert result.archived is True
    assert result.source_url == "https://github.com/Owner/Repo"
    assert result.releases[0].age_days == 10


def test_malformed_future_and_unsupported_inputs_never_pass() -> None:
    now = datetime(2025, 1, 1, tzinfo=UTC)

    malformed = normalize_pypi([], name="pkg", spec="latest", now=now)
    future = normalize_npm(
        {
            "versions": {"1.0.0": {}},
            "time": {"1.0.0": "2025-01-02T00:00:00Z"},
        },
        name="pkg",
        spec="1.0.0",
        now=now,
    )
    unsupported = normalize_registry_history("cargo", {}, name="pkg", spec="latest", now=now)

    assert malformed.status is HistoryStatus.INCOMPLETE
    assert malformed.reason_code is HistoryReason.MALFORMED_INPUT
    assert future.reason_code is HistoryReason.TIMESTAMP_TOO_LARGE
    assert unsupported.status is HistoryStatus.UNSUPPORTED
    assert unsupported.reason_code is HistoryReason.UNSUPPORTED_ECOSYSTEM


def test_snapshots_yield_release_and_maintainer_transition() -> None:
    now = datetime(2025, 1, 1, tzinfo=UTC)
    first = normalize_npm(
        {
            "versions": {"1.0.0": {}},
            "time": {"1.0.0": "2024-01-01T00:00:00Z"},
            "maintainers": [{"name": "alice"}],
        },
        name="pkg",
        spec="1.0.0",
        now=now,
    )
    second = normalize_npm(
        {
            "versions": {"1.0.0": {}, "2.0.0": {}},
            "time": {
                "1.0.0": "2024-01-01T00:00:00Z",
                "2.0.0": "2024-02-01T00:00:00Z",
            },
            "maintainers": [{"name": "bob"}],
        },
        name="pkg",
        spec="2.0.0",
        now=now,
    )

    series = append_snapshot(SnapshotSeries(), first, observed_at=now, etag='"one"')
    series = append_snapshot(series, second, observed_at=now, etag='"two"')

    assert series.snapshots[0].transition.status is TransitionStatus.UNKNOWN
    transition = series.snapshots[1].transition
    assert transition.status is TransitionStatus.CHANGED
    assert transition.added_releases == ("2.0.0",)
    assert transition.added_maintainers == ("bob",)
    assert transition.removed_maintainers == ("alice",)
