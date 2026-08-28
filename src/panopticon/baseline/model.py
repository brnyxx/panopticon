"""Immutable baseline business values and semantic observation views."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import RootModel

from panopticon.models.artifacts import Baseline
from panopticon.models.common import StrictModel
from panopticon.models.observation import Observation


class BaselineView(StrictModel):
    """A baseline plus the observations it was selected from."""

    baseline: Baseline
    semantic: tuple[Mapping[str, object], ...]


class SemanticObservation(RootModel[Mapping[str, object]]):
    """Canonical, timestamp-free observation representation."""


def semantic_observation(observation: Observation) -> SemanticObservation:
    """Return a deterministic view suitable for equality and diffing."""
    value = observation.model_dump(mode="json")
    volatile = {"observed_at", "observation_id", "duration_ms", "container_id", "pid"}

    def clean(item: object) -> object:
        if isinstance(item, dict):
            result: dict[str, object] = {}
            for key, child in item.items():
                if key in volatile:
                    continue
                if key == "decoy_key" and isinstance(child, str):
                    child = child.casefold()
                result[key] = clean(child)
            return {key: result[key] for key in sorted(result)}
        if isinstance(item, list):
            values = [clean(child) for child in item]
            return sorted(values, key=lambda child: repr(child))
        return item

    cleaned = clean(value)
    assert isinstance(cleaned, dict)
    return SemanticObservation.model_validate(cleaned)


def run_metadata(observation: Observation) -> Mapping[str, object]:
    """Return run identity and timing, kept out of semantic comparisons."""
    return {
        "observation_id": str(observation.observation_id),
        "installation_id": str(observation.installation_id),
        "server_id": str(observation.server_id),
        "observed_at": observation.observed_at.isoformat(),
        "pano_version": str(observation.pano_version),
    }


__all__ = ["BaselineView", "SemanticObservation", "run_metadata", "semantic_observation"]
