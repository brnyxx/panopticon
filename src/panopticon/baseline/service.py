"""Baseline construction and repository lifecycle."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import datetime

from panopticon.models.artifacts import Baseline, BaselineKind
from panopticon.models.ids import BaselineId
from panopticon.models.inventory import InstalledServer
from panopticon.models.observation import Observation
from panopticon.store.contracts import PersistSuccess
from panopticon.store.repository import (
    ArtifactRepository,
    BaselineLoad,
    LoadStatus,
    RemoveStatus,
)


def build_baseline(
    inventory: Iterable[InstalledServer],
    observations: Iterable[Observation],
    *,
    now: datetime,
    label: str | None = None,
    kind: BaselineKind = BaselineKind.EXPLICIT,
) -> Baseline:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("baseline time must be timezone-aware")
    normalized_inventory = tuple(sorted(inventory, key=lambda item: str(item.installation_id)))
    latest: dict[str, Observation] = {}
    for observation in observations:
        key = str(observation.installation_id)
        previous = latest.get(key)
        if previous is None or (
            observation.observed_at,
            str(observation.observation_id),
        ) > (previous.observed_at, str(previous.observation_id)):
            latest[key] = observation
    normalized_observations = tuple(latest[key] for key in sorted(latest))
    findings = tuple(
        sorted(
            (
                finding
                for observation in normalized_observations
                for finding in observation.findings
            ),
            key=lambda finding: (str(finding.logical_key), str(finding.id)),
        )
    )
    identity = json.dumps(
        {
            "inventory": [str(item.installation_id) for item in normalized_inventory],
            "observations": [str(item.observation_id) for item in normalized_observations],
            "label": label,
            "kind": kind.value,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    baseline_id = BaselineId(f"bl_{hashlib.sha256(identity.encode()).hexdigest()[:16]}")
    return Baseline(
        schema_version="1.0",
        baseline_id=baseline_id,
        created_at=now,
        label=label,
        kind=kind,
        inventory=normalized_inventory,
        observations=normalized_observations,
        findings=findings,
    )


class BaselineService:
    def __init__(self, repository: ArtifactRepository) -> None:
        self.repository = repository

    def create(
        self,
        inventory: Iterable[InstalledServer],
        *,
        now: datetime,
        label: str | None = None,
    ) -> BaselineLoad:
        baseline = build_baseline(
            inventory,
            self.repository.latest_observations(),
            now=now,
            label=label,
        )
        result = self.repository.persist_baseline(baseline)
        if isinstance(result, PersistSuccess):
            return BaselineLoad(LoadStatus.AVAILABLE, baseline)
        return BaselineLoad(LoadStatus.INVALID, reason_code=type(result).__name__.upper())

    def list(self) -> tuple[BaselineLoad, ...]:
        return self.repository.list_baselines()

    def show(self, baseline_id: str) -> BaselineLoad:
        return self.repository.load_baseline(baseline_id)

    def remove(self, baseline_id: str) -> RemoveStatus:
        return self.repository.remove_baseline(baseline_id)


__all__ = ["BaselineService", "build_baseline"]
