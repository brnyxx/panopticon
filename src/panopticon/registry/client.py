"""Injected, offline-aware registry HTTP boundary with normalized-only outputs."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from .cache import make_lookup
from .history import SnapshotSeries, append_snapshot
from .http import Clock, HttpOutcome, RegistryHttp
from .model import CacheLookup, HistoryReason, HistoryStatus, NormalizedHistory
from .normalize import normalize_registry_history


@dataclass(frozen=True, slots=True)
class RegistryFetch:
    history: NormalizedHistory
    snapshots: SnapshotSeries
    network_attempted: bool
    reason_code: str
    etags: tuple[tuple[str, str], ...] = ()


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
        etags: tuple[tuple[str, str], ...] = (),
        offline: bool = False,
    ) -> RegistryFetch:
        series = snapshots or SnapshotSeries()
        if offline:
            return self._offline(lookup, series)
        request = _request(lookup, self._github_token)
        if request is None:
            return RegistryFetch(
                _unavailable(lookup, HistoryStatus.INCOMPLETE, HistoryReason.MALFORMED_INPUT),
                series,
                False,
                "MALFORMED_LOOKUP",
            )
        resources, base_headers = request
        validators = dict(etags)
        outcomes = await self._fetch_resources(resources, base_headers, validators)
        if (
            len(outcomes) > 1
            and any(outcome.status_code == 304 for outcome in outcomes)
            and not all(outcome.status_code == 304 for outcome in outcomes)
        ):
            outcomes = await self._fetch_resources(resources, base_headers, {})
        outcome = _aggregate(resources, outcomes)
        response_etags = tuple(
            sorted(
                (resource, value)
                for (resource, _), item in zip(resources, outcomes, strict=True)
                if (value := _header(item.headers, "etag")) is not None
            )
        )
        effective_etags = response_etags or etags
        observed_at = self.clock.now()
        if outcome.status_code == 304:
            if not series.snapshots:
                return RegistryFetch(
                    _unavailable(lookup, HistoryStatus.UNKNOWN, HistoryReason.CACHE_MISS),
                    series,
                    True,
                    "NOT_MODIFIED_WITHOUT_CACHE",
                    effective_etags,
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
            return RegistryFetch(
                updated.snapshots[-1].history, updated, True, "NOT_MODIFIED", effective_etags
            )
        failure = _failure_reason(outcome)
        if failure is not None:
            status = (
                HistoryStatus.INCOMPLETE
                if failure is HistoryReason.MALFORMED_INPUT
                else HistoryStatus.UNKNOWN
            )
            history = _unavailable(lookup, status, failure)
            return RegistryFetch(history, series, True, failure.value, effective_etags)
        if outcome.status_code != 200:
            history = _unavailable(lookup, HistoryStatus.UNKNOWN, HistoryReason.REGISTRY_FAILURE)
            return RegistryFetch(
                history, series, True, HistoryReason.REGISTRY_FAILURE.value, effective_etags
            )
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
        return RegistryFetch(
            history,
            updated,
            True,
            updated.snapshots[-1].transition.reason_code,
            effective_etags,
        )

    async def _fetch_resources(
        self,
        resources: tuple[tuple[str, str], ...],
        base_headers: tuple[tuple[str, str], ...],
        validators: dict[str, str],
    ) -> tuple[HttpOutcome, ...]:
        outcomes: list[HttpOutcome] = []
        for resource, url in resources:
            headers = base_headers
            if resource in validators:
                headers = (*headers, ("if-none-match", validators[resource]))
            outcomes.append(await self.http.get(url, headers=headers, timeout=self.timeout))
        return tuple(outcomes)

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
    github_token: str | None,
) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]] | None:
    headers: list[tuple[str, str]] = [("accept", "application/json")]
    ecosystem = lookup.ecosystem.casefold()
    resources: tuple[tuple[str, str], ...]
    if ecosystem == "npm":
        resources = (("package", f"https://registry.npmjs.org/{quote(lookup.name, safe='')}"),)
    elif ecosystem in {"pypi", "python"}:
        resources = (("package", f"https://pypi.org/pypi/{quote(lookup.name, safe='')}/json"),)
    elif ecosystem in {"github", "git"}:
        parts = lookup.name.split("/")
        if len(parts) != 2 or not all(_safe_segment(part) for part in parts):
            return None
        base = f"https://api.github.com/repos/{parts[0]}/{parts[1]}"
        resources = (
            ("repository", base),
            ("releases", f"{base}/releases"),
            ("tags", f"{base}/tags"),
        )
        if github_token:
            headers.append(("authorization", f"Bearer {github_token}"))
    else:
        return None
    return resources, tuple(headers)


def _aggregate(
    resources: tuple[tuple[str, str], ...], outcomes: tuple[HttpOutcome, ...]
) -> HttpOutcome:
    if all(outcome.status_code == 304 for outcome in outcomes):
        return outcomes[0]
    failure = next((outcome for outcome in outcomes if outcome.status_code != 200), None)
    if failure is not None:
        return failure
    if len(outcomes) == 1:
        return outcomes[0]
    bodies = {
        resource: outcome.body for (resource, _), outcome in zip(resources, outcomes, strict=True)
    }
    return HttpOutcome(200, body=bodies)


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
