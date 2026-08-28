from datetime import UTC, datetime

from panopticon.registry.normalize import normalize_npm, normalize_pypi, parse_timestamp
from panopticon.registry.model import HistoryReason, HistoryStatus


def test_npm_exact_and_deprecated() -> None:
    payload = {
        "versions": {"1.0.0": {}, "2.0.0": {"deprecated": True}},
        "time": {"1.0.0": "2024-01-01T00:00:00Z", "2.0.0": "2024-02-01T00:00:00Z"},
        "dist-tags": {"latest": "2.0.0"},
        "homepage": "https://user:secret@example.test/pkg?token=x",
    }
    result = normalize_npm(payload, name="pkg", spec="latest", now=datetime(2025, 1, 1, tzinfo=UTC))
    assert result.status is HistoryStatus.AVAILABLE
    assert result.resolved_version == "1.0.0"
    assert "secret" not in (result.source_url or "")


def test_pypi_yanked_and_bad_timestamp() -> None:
    payload = {"releases": {"1.0.0": [{"upload_time_iso_8601": "bad"}], "2.0.0": [{"yanked": True, "upload_time_iso_8601": "2024-01-01T00:00:00Z"}]}}
    result = normalize_pypi(payload, name="pkg", spec="1.0.0")
    assert result.status is HistoryStatus.INCOMPLETE
    assert result.reason_code is HistoryReason.INVALID_TIMESTAMP
    assert parse_timestamp(None)[1] is HistoryReason.MISSING_TIMESTAMP
