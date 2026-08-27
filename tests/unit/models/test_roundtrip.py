"""Persistence-boundary models round-trip without losing typed structure."""

from __future__ import annotations

from pathlib import Path

from panopticon.models import Observation

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "schemas"


def test_local_and_remote_observations_round_trip() -> None:
    # Given: representative local-modern and remote-legacy persisted observations.
    payloads = (
        (FIXTURES / "observation.json").read_text(),
        (FIXTURES / "observation_remote.json").read_text(),
    )

    # When: each record crosses the runtime boundary twice.
    observations = tuple(Observation.model_validate_json(payload) for payload in payloads)
    reloaded = tuple(
        Observation.model_validate_json(observation.model_dump_json())
        for observation in observations
    )

    # Then: immutable typed values and protocol-era distinctions survive exactly.
    assert reloaded == observations
    assert observations[0].protocol.era.value == "modern"
    assert observations[1].protocol.era.value == "legacy"
