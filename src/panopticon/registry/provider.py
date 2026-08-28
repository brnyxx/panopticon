"""Async orchestration over registry client and persistent normalized cache."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from panopticon.engine.contracts import EngineDiagnostic
from panopticon.models.inventory import InstalledServer, SourceKind

from .cache import CacheEnvelope, CacheLoadStatus, PersistentCache, make_lookup
from .client import RegistryClient
from .history import SnapshotSeries
from .model import CacheLookup, HistoryReason, HistoryStatus, NormalizedHistory


@dataclass(frozen=True, slots=True)
class RegistryProviderResult:
    history: NormalizedHistory | None
    series: SnapshotSeries
    status: HistoryStatus
    reason_code: HistoryReason
    diagnostics: tuple[EngineDiagnostic, ...] = ()


class RegistryProvider:
    def __init__(self, cache: PersistentCache, client: RegistryClient) -> None:
        self.cache = cache
        self.client = client

    async def lookup(
        self, server: InstalledServer, offline: bool = False
    ) -> RegistryProviderResult:
        identity = _identity(server)
        if identity is None:
            history = NormalizedHistory(
                status=HistoryStatus.UNKNOWN,
                reason_code=HistoryReason.UNSUPPORTED_ECOSYSTEM,
                ecosystem="unsupported",
                name=server.name,
                requested_spec="",
            )
            return RegistryProviderResult(
                history, SnapshotSeries(), history.status, history.reason_code
            )
        ecosystem, name, spec = identity
        lookup = make_lookup(ecosystem, name, spec)
        loaded = self.cache.load(lookup, now=self.client.clock.now())
        envelope = loaded.envelope
        if loaded.status is CacheLoadStatus.HIT and envelope is not None:
            history = _requested(envelope.snapshots.snapshots[-1].history, spec)
            series = _requested_series(envelope.snapshots, spec)
            return RegistryProviderResult(history, series, history.status, HistoryReason.OK)
        if offline:
            history = _unknown(
                lookup, HistoryReason.OFFLINE if envelope is None else HistoryReason.STALE_CACHE
            )
            series = (
                _requested_series(envelope.snapshots, spec)
                if envelope is not None
                else SnapshotSeries()
            )
            return RegistryProviderResult(history, series, history.status, history.reason_code)
        series = envelope.snapshots if envelope is not None else SnapshotSeries()
        fetched = await self.client.fetch(lookup, snapshots=series)
        if fetched.history.status is not HistoryStatus.AVAILABLE:
            reason = fetched.history.reason_code
            history = _unknown(lookup, reason)
            failure_diagnostics = (EngineDiagnostic("REGISTRY_FAILED", reason.value),)
            return RegistryProviderResult(
                history,
                _requested_series(series, spec),
                history.status,
                reason,
                failure_diagnostics,
            )
        effective = fetched.snapshots
        envelope_new = CacheEnvelope(
            ecosystem=lookup.ecosystem,
            name=lookup.name,
            snapshots=effective,
            fetched_at=self.client.clock.now(),
        )
        persisted = self.cache.persist(lookup, envelope_new)
        diagnostics: tuple[EngineDiagnostic, ...] = ()
        if persisted.status is CacheLoadStatus.PERSIST_FAILURE:
            diagnostics = (EngineDiagnostic("CACHE_PERSIST_FAILED", "CACHE_PERSIST_FAILED"),)
        history = _requested(fetched.history, spec)
        return RegistryProviderResult(
            history, effective, history.status, history.reason_code, diagnostics
        )


def _requested(history: NormalizedHistory, spec: str) -> NormalizedHistory:
    return history.model_copy(
        update={"requested_spec": spec, "registry_fresh": history.registry_fresh}
    )


def _requested_series(series: SnapshotSeries, spec: str) -> SnapshotSeries:
    if not series.snapshots:
        return series
    latest = series.snapshots[-1]
    snapshot = latest.model_copy(update={"history": _requested(latest.history, spec)})
    return SnapshotSeries(snapshots=(*series.snapshots[:-1], snapshot))


def _unknown(lookup: CacheLookup, reason: HistoryReason) -> NormalizedHistory:
    return NormalizedHistory(
        status=HistoryStatus.UNKNOWN,
        reason_code=reason,
        ecosystem=lookup.ecosystem,
        name=lookup.name,
        requested_spec=lookup.spec,
        registry_fresh=False,
    )


def _identity(server: InstalledServer) -> tuple[str, str, str] | None:
    if server.package is not None and server.package.ecosystem.value in {"npm", "pypi"}:
        package = server.package
        return package.ecosystem.value, package.name, package.pinned or package.resolved or ""
    if server.source.kind is SourceKind.GIT and server.source.url is not None:
        parsed = urlparse(str(server.source.url))
        if parsed.hostname and parsed.hostname.casefold() == "github.com":
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) >= 2:
                return "github", f"{parts[0]}/{parts[1].removesuffix('.git')}", ""
    return None


__all__ = ["RegistryProvider", "RegistryProviderResult"]
