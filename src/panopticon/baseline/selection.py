"""Deterministic baseline selection; persistence remains the caller's concern."""

from __future__ import annotations

from collections.abc import Sequence

from panopticon.models.artifacts import Baseline, BaselineKind
from panopticon.models.observation import Observation


def select_baseline(
    explicit: Baseline | None,
    observations: Sequence[Observation],
) -> Baseline | Observation | None:
    """Select explicit, then latest observation, without mutating inputs."""
    if explicit is not None:
        return explicit
    if not observations:
        return None
    return max(observations, key=lambda item: (item.observed_at, str(item.installation_id)))


def baseline_kind(value: Baseline | Observation) -> BaselineKind:
    """Describe the selected source without persistence or filesystem access."""
    if isinstance(value, Baseline):
        return value.kind
    return BaselineKind.LAST_OBSERVATION


__all__ = ["baseline_kind", "select_baseline"]
