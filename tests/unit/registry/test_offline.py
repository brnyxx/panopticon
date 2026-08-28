from __future__ import annotations

from datetime import UTC, datetime

import pytest

from panopticon.registry.client import RegistryClient, lookup
from panopticon.registry.history import SnapshotSeries, append_snapshot
from panopticon.registry.http import HttpOutcome
from panopticon.registry.model import HistoryReason, HistoryStatus, NormalizedHistory


class FixedClock:
    def now(self) -> datetime:
        return datetime(2025, 1, 1, tzinfo=UTC)


class ExplodingHttp:
    def __init__(self) -> None:
        self.calls = 0

    async def get(
        self,
        _url: str,
        *,
        headers: tuple[tuple[str, str], ...],
        timeout: float,
    ) -> HttpOutcome:
        del headers, timeout
        self.calls += 1
        raise AssertionError("offline mode attempted HTTP")


@pytest.mark.asyncio
async def test_missing_cache_performs_zero_http_and_reports_unknown() -> None:
    http = ExplodingHttp()
    client = RegistryClient(http, FixedClock())

    result = await client.fetch(lookup("npm", "pkg", "latest"), offline=True)

    assert http.calls == 0
    assert not result.network_attempted
    assert result.history.status is HistoryStatus.UNKNOWN
    assert result.history.reason_code is HistoryReason.OFFLINE


@pytest.mark.asyncio
async def test_offline_cache_hit_is_retained_but_freshness_is_unknown() -> None:
    http = ExplodingHttp()
    clock = FixedClock()
    history = NormalizedHistory(
        status=HistoryStatus.AVAILABLE,
        reason_code=HistoryReason.OK,
        ecosystem="npm",
        name="pkg",
        requested_spec="1.0.0",
        resolved_version="1.0.0",
        registry_fresh=True,
    )
    snapshots = append_snapshot(SnapshotSeries(), history, observed_at=clock.now())

    result = await RegistryClient(http, clock).fetch(
        lookup("npm", "pkg", "1.0.0"),
        snapshots=snapshots,
        offline=True,
    )

    assert http.calls == 0
    assert result.history.resolved_version == "1.0.0"
    assert result.history.registry_fresh is False
