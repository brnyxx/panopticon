"""Coverage-aware baseline diff engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from panopticon.baseline.service import build_baseline
from panopticon.diff.compute import compute_diff
from panopticon.engine.baseline import collect_inventory, runtime_environment
from panopticon.engine.contracts import (
    CompleteResult,
    EngineDiagnostic,
    EngineReason,
    FailedResult,
    Result,
)
from panopticon.models.artifacts import Baseline, BaselineKind, DiffResult
from panopticon.store.repository import ArtifactRepository, LoadStatus


@dataclass(frozen=True, slots=True)
class DiffRequest:
    server: str | None = None
    since: str = "auto"


@dataclass(frozen=True, slots=True)
class DiffOutcome:
    result: Result
    diff: DiffResult | None = None


class DiffPlan(Protocol):
    def run(self, request: DiffRequest) -> DiffOutcome: ...


def _select_baseline(repository: ArtifactRepository, since: str) -> Baseline | None:
    if since != "auto":
        return repository.load_baseline(since).baseline
    available = tuple(
        item.baseline
        for item in repository.list_baselines()
        if item.status is LoadStatus.AVAILABLE and item.baseline is not None
    )
    return max(available, key=lambda item: (item.created_at, str(item.baseline_id)), default=None)


def _filter(baseline: Baseline, server: str | None) -> Baseline:
    if server is None:
        return baseline
    observations = tuple(item for item in baseline.observations if str(item.server_id) == server)
    installation_ids = {item.installation_id for item in observations}
    return baseline.model_copy(
        update={
            "inventory": tuple(
                item for item in baseline.inventory if item.installation_id in installation_ids
            ),
            "observations": observations,
            "findings": tuple(
                item for item in baseline.findings if item.installation_id in installation_ids
            ),
        }
    )


def run_diff(
    request: DiffRequest,
    *,
    repository: ArtifactRepository | None = None,
    now: datetime | None = None,
) -> DiffOutcome:
    artifacts = repository or ArtifactRepository()
    previous = _select_baseline(artifacts, request.since)
    if previous is None:
        return DiffOutcome(
            FailedResult(
                reason_code=EngineReason.STAGE_ERROR,
                diagnostics=(EngineDiagnostic("BASELINE_NOT_FOUND", request.since),),
            )
        )
    inventory, diagnostics = collect_inventory(runtime_environment())
    current = build_baseline(
        inventory,
        artifacts.latest_observations(),
        now=now or datetime.now(UTC),
        kind=BaselineKind.LAST_OBSERVATION,
    )
    return DiffOutcome(
        CompleteResult(diagnostics=diagnostics),
        compute_diff(_filter(previous, request.server), _filter(current, request.server)),
    )


__all__ = ["DiffOutcome", "DiffPlan", "DiffRequest", "run_diff"]
