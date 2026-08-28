"""Injected, offline-aware registry HTTP boundary with normalized-only outputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import quote

import httpx

from .cache import make_lookup
from .history import SnapshotSeries, append_snapshot
from .model import CacheLookup, HistoryReason, HistoryStatus, NormalizedHistory
from .normalize import normalize_registry_history


@dataclass(frozen=True, slots=True)
class HttpOutcome:
    status_code: int | None
    headers: tuple[tuple[str, str], ...] = ()
    body: object = None
    reason_code: str = "OK"


class RegistryHttp(Protocol):
    async def get(
        self,
        url: str,
        *,
        headers: tuple[tuple[str, str], ...],
        timeout: float,
    ) -> HttpOutcome: ...


class HttpxRegistryHttp:
    """Concrete HTTP boundary; only normalized wire outcomes escape."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def get(
        self, url: str, *, headers: tuple[tuple[str, str], ...], timeout: float
    ) -> HttpOutcome:
        client = self._client
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=timeout)
        try:
            response = await client.get(url, headers=dict(headers), timeout=timeout)
            try:
                body = response.json()
            except (ValueError, UnicodeDecodeError):
                return HttpOutcome(response.status_code, reason_code="MALFORMED_JSON")
            return HttpOutcome(
                response.status_code,
                tuple((str(k), str(v)) for k, v in response.headers.items()),
                body,
            )
        except httpx.TimeoutException:
            return HttpOutcome(None, reason_code="TIMEOUT")
        except httpx.TransportError:
            return HttpOutcome(None, reason_code="TRANSPORT_ERROR")
        finally:
            if owns_client:
                await client.aclose()


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


# Explicit aliases keep the production boundary discoverable by role.
RegistryHttpClient = HttpxRegistryHttp
UtcClock = SystemClock


class Clock(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class RegistryFetch:
    history: NormalizedHistory
    snapshots: SnapshotSeries
    network_attempted: bool
    reason_code: str


class RegistryClient:
    def __init__(
        self,
        http: RegistryHttp,
        clock: Clock,
        *,
        timeout: float = 10.0,
        github_token: str | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("registry timeout must be positive")
        self.http = http
        self.clock = clock
        self.timeout = timeout
        self._github_token = github_token

    async def fetch(
        self,
        lookup: CacheLookup,
        *,
        snapshots: SnapshotSeries | None = None,
        offline: bool = False,
    ) -> RegistryFetch:
        series = snapshots or SnapshotSeries()
        if offline:
            return self._offline(lookup, series)
        request = _request(lookup, series, self._github_token)
        if request is None:
            return RegistryFetch(
                _unavailable(lookup, HistoryStatus.INCOMPLETE, HistoryReason.MALFORMED_INPUT),
                series,
                False,
                "MALFORMED_LOOKUP",
            )
        urls, headers = request
        if isinstance(urls, tuple):
            outcomes = [
                await self.http.get(url, headers=headers, timeout=self.timeout) for url in urls
            ]
            outcome = outcomes[0]
            if any(item.status_code == 304 for item in outcomes):
                outcome = next(item for item in outcomes if item.status_code == 304)
            elif any(item.status_code != 200 for item in outcomes):
                outcome = next(item for item in outcomes if item.status_code != 200)
            else:
                outcome = HttpOutcome(
                    200,
                    outcome.headers,
                    {
                        "repository": outcomes[0].body,
                        "releases": outcomes[1].body,
                        "tags": outcomes[2].body,
                    },
                )
        else:
            outcome = await self.http.get(urls, headers=headers, timeout=self.timeout)
        observed_at = self.clock.now()
        if outcome.status_code == 304:
            if not series.snapshots:
                return RegistryFetch(
                    _unavailable(lookup, HistoryStatus.UNKNOWN, HistoryReason.CACHE_MISS),
                    series,
                    True,
                    "NOT_MODIFIED_WITHOUT_CACHE",
                )
            previous = series.snapshots[-1]
            updated = append_snapshot(
                series,
                previous.history.model_copy(
                    update={"registry_fetched_at": observed_at, "registry_fresh": True}
                ),
                observed_at=observed_at,
                etag=_header(outcome.headers, "etag") or previous.etag,
            )
            return RegistryFetch(updated.snapshots[-1].history, updated, True, "NOT_MODIFIED")
        failure = _failure_reason(outcome)
        if failure is not None:
            status = (
                HistoryStatus.INCOMPLETE
                if failure is HistoryReason.MALFORMED_INPUT
                else HistoryStatus.UNKNOWN
            )
            history = _unavailable(lookup, status, failure)
            return RegistryFetch(history, series, True, failure.value)
        if outcome.status_code != 200:
            history = _unavailable(lookup, HistoryStatus.UNKNOWN, HistoryReason.REGISTRY_FAILURE)
            return RegistryFetch(history, series, True, HistoryReason.REGISTRY_FAILURE.value)
        body = outcome.body
        if lookup.ecosystem.casefold() in {"github", "git"} and isinstance(body, list):
            body = {
                "releases": body,
                "html_url": f"https://github.com/{lookup.name}",
            }
        history = normalize_registry_history(
            lookup.ecosystem,
            body,
            name=lookup.name,
            spec=lookup.spec,
            now=observed_at,
        )
        history = history.model_copy(
            update={"registry_fetched_at": observed_at, "registry_fresh": True}
        )
        updated = append_snapshot(
            series,
            history,
            observed_at=observed_at,
            etag=_header(outcome.headers, "etag"),
        )
        return RegistryFetch(history, updated, True, updated.snapshots[-1].transition.reason_code)

    @staticmethod
    def _offline(lookup: CacheLookup, series: SnapshotSeries) -> RegistryFetch:
        if not series.snapshots:
            history = _unavailable(lookup, HistoryStatus.UNKNOWN, HistoryReason.OFFLINE)
            return RegistryFetch(history, series, False, HistoryReason.OFFLINE.value)
        history = series.snapshots[-1].history.model_copy(update={"registry_fresh": False})
        return RegistryFetch(history, series, False, "OFFLINE_CACHE_HIT")


def lookup(ecosystem: str, name: str, spec: str) -> CacheLookup:
    return make_lookup(ecosystem, name, spec)


def _request(
    lookup: CacheLookup,
    snapshots: SnapshotSeries,
    github_token: str | None,
) -> tuple[str | tuple[str, str, str], tuple[tuple[str, str], ...]] | None:
    headers: list[tuple[str, str]] = [("accept", "application/json")]
    if snapshots.snapshots and snapshots.snapshots[-1].etag:
        headers.append(("if-none-match", snapshots.snapshots[-1].etag or ""))
    ecosystem = lookup.ecosystem.casefold()
    url: str | tuple[str, str, str]
    if ecosystem == "npm":
        url = f"https://registry.npmjs.org/{quote(lookup.name, safe='')}"
    elif ecosystem in {"pypi", "python"}:
        url = f"https://pypi.org/pypi/{quote(lookup.name, safe='')}/json"
    elif ecosystem in {"github", "git"}:
        parts = lookup.name.split("/")
        if len(parts) != 2 or not all(_safe_segment(part) for part in parts):
            return None
        base = f"https://api.github.com/repos/{parts[0]}/{parts[1]}"
        url = (base, f"{base}/releases", f"{base}/tags")
        if github_token:
            headers.append(("authorization", f"Bearer {github_token}"))
    else:
        return None
    return url, tuple(headers)


def _safe_segment(value: str) -> bool:
    return (
        bool(value)
        and value not in {".", ".."}
        and all(character.isalnum() or character in "-_." for character in value)
    )


def _header(headers: tuple[tuple[str, str], ...], name: str) -> str | None:
    return next((value for key, value in headers if key.casefold() == name.casefold()), None)


def _failure_reason(outcome: HttpOutcome) -> HistoryReason | None:
    if outcome.status_code == 404:
        return HistoryReason.NOT_FOUND
    if outcome.status_code == 429:
        return HistoryReason.RATE_LIMITED
    if outcome.status_code is None and outcome.reason_code == "TIMEOUT":
        return HistoryReason.TIMEOUT
    if outcome.status_code is None:
        return HistoryReason.REGISTRY_FAILURE
    if outcome.reason_code == "MALFORMED_JSON":
        return HistoryReason.MALFORMED_INPUT
    return None


def _unavailable(
    lookup: CacheLookup,
    status: HistoryStatus,
    reason: HistoryReason,
) -> NormalizedHistory:
    return NormalizedHistory(
        status=status,
        reason_code=reason,
        ecosystem=lookup.ecosystem,
        name=lookup.name,
        requested_spec=lookup.spec,
    )
