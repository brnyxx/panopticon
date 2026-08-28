from __future__ import annotations

from datetime import UTC, datetime

import pytest

from panopticon.registry.client import HttpOutcome, RegistryClient, lookup
from panopticon.registry.history import TransitionStatus
from panopticon.registry.model import HistoryReason, HistoryStatus


class FixedClock:
    def now(self) -> datetime:
        return datetime(2025, 1, 1, tzinfo=UTC)


class FakeHttp:
    def __init__(self, *outcomes: HttpOutcome) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[tuple[str, tuple[tuple[str, str], ...], float]] = []

    async def get(
        self,
        url: str,
        *,
        headers: tuple[tuple[str, str], ...],
        timeout: float,
    ) -> HttpOutcome:
        self.requests.append((url, headers, timeout))
        return self.outcomes.pop(0)


def npm_body() -> dict[str, object]:
    return {
        "versions": {"1.0.0": {}},
        "time": {"1.0.0": "2024-01-01T00:00:00Z"},
        "dist-tags": {"latest": "1.0.0"},
        "maintainers": [{"name": "alice"}],
    }


@pytest.mark.asyncio
async def test_success_and_etag_304_use_normalized_snapshots_only() -> None:
    http = FakeHttp(
        HttpOutcome(200, (("ETag", '"v1"'),), npm_body()),
        HttpOutcome(304, (("etag", '"v1"'),)),
    )
    client = RegistryClient(http, FixedClock())
    package = lookup("npm", "@scope/pkg", "latest")

    first = await client.fetch(package)
    second = await client.fetch(package, snapshots=first.snapshots)

    assert first.history.resolved_version == "1.0.0"
    assert first.snapshots.snapshots[0].transition.status is TransitionStatus.UNKNOWN
    assert second.reason_code == "NOT_MODIFIED"
    assert second.snapshots.snapshots[-1].transition.status is TransitionStatus.UNCHANGED
    assert "%40scope%2Fpkg" in http.requests[0][0]
    assert ("if-none-match", '"v1"') in http.requests[1][1]
    assert "versions" not in repr(first)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outcome", "reason"),
    (
        (HttpOutcome(429), HistoryReason.RATE_LIMITED),
        (HttpOutcome(404), HistoryReason.NOT_FOUND),
        (HttpOutcome(None, reason_code="TIMEOUT"), HistoryReason.TIMEOUT),
    ),
)
async def test_wire_failures_are_typed_unknown(
    outcome: HttpOutcome,
    reason: HistoryReason,
) -> None:
    result = await RegistryClient(FakeHttp(outcome), FixedClock()).fetch(
        lookup("pypi", "package", "latest")
    )

    assert result.history.status is HistoryStatus.UNKNOWN
    assert result.history.reason_code is reason


@pytest.mark.asyncio
async def test_github_token_and_traversal_values_do_not_enter_results() -> None:
    token = "synthetic-provider-value"
    http = FakeHttp(
        HttpOutcome(
            200,
            body=[
                {
                    "tag_name": "v1.0.0",
                    "published_at": "2024-01-01T00:00:00Z",
                }
            ],
        )
    )
    client = RegistryClient(http, FixedClock(), github_token=token)

    result = await client.fetch(lookup("github", "Owner/Repo", "v1.0.0"))
    invalid = await client.fetch(lookup("github", "../Repo", "latest"))

    assert result.history.source_url == "https://github.com/Owner/Repo"
    assert token not in repr(result)
    assert invalid.history.reason_code is HistoryReason.MALFORMED_INPUT
    assert len(http.requests) == 1
