from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from panopticon.models import Baseline, Finding, Observation, WrapRecord
from panopticon.store import (
    BinaryArtifact,
    LeakContext,
    ModelArtifact,
    PersistRejected,
    PersistRequest,
    PersistSuccess,
    RejectionCode,
    RenderedArtifact,
    RenderField,
    RenderModel,
    SinkKind,
    persist,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "schemas"
GENERIC_MODEL_SINKS = (
    SinkKind.CACHE,
    SinkKind.ALERT,
    SinkKind.JOURNAL,
    SinkKind.BACKUP,
    SinkKind.LOG,
    SinkKind.JSON,
)


def _render_model() -> RenderModel:
    return RenderModel(
        schema_version="0.1",
        title="Observation evidence",
        fields=(RenderField(name="coverage", value="UNKNOWN"),),
    )


def test_all_sink_types_round_trip_sanitized_models(tmp_path: Path) -> None:
    # Given: one task-3 typed model and focused render inputs for every closed sink kind.
    observation = Observation.model_validate_json((FIXTURES / "observation.json").read_text())
    render_model = _render_model()
    requests = (
        *(
            PersistRequest(tmp_path / f"{kind.value}.json", ModelArtifact(kind, observation))
            for kind in GENERIC_MODEL_SINKS
        ),
        PersistRequest(
            tmp_path / "observation.json",
            ModelArtifact(SinkKind.OBSERVATION, observation),
        ),
        PersistRequest(
            tmp_path / "baseline.json",
            ModelArtifact(
                SinkKind.BASELINE,
                Baseline.model_validate_json((FIXTURES / "baseline.json").read_text()),
            ),
        ),
        PersistRequest(
            tmp_path / "finding.json",
            ModelArtifact(
                SinkKind.FINDING,
                Finding.model_validate_json((FIXTURES / "finding.json").read_text()),
            ),
        ),
        PersistRequest(
            tmp_path / "wrap_record.json",
            ModelArtifact(
                SinkKind.WRAP_RECORD,
                WrapRecord.model_validate_json((FIXTURES / "wrap_record.json").read_text()),
            ),
        ),
        PersistRequest(
            tmp_path / "report.sarif",
            RenderedArtifact(SinkKind.SARIF, render_model, "ignored for canonical SARIF"),
        ),
        PersistRequest(
            tmp_path / "report.md",
            RenderedArtifact(SinkKind.MARKDOWN, render_model, "# Observation\r\nUNKNOWN"),
        ),
        PersistRequest(
            tmp_path / "report.png",
            BinaryArtifact(SinkKind.PNG, render_model, b"\x89PNG\r\n\x1a\nfixture"),
        ),
        PersistRequest(
            tmp_path / "badge.svg",
            RenderedArtifact(SinkKind.SVG, render_model, "<svg>UNKNOWN</svg>"),
        ),
    )

    # When: every artifact crosses the real public gateway.
    results = tuple(persist(request, LeakContext()) for request in requests)

    # Then: each sink atomically round-trips deterministic bytes.
    assert all(isinstance(result, PersistSuccess) for result in results)
    assert {request.artifact.kind for request in requests} == set(SinkKind)
    assert Observation.model_validate_json(requests[0].target.read_bytes()) == observation
    assert requests[-3].target.read_bytes() == b"# Observation\nUNKNOWN\n"
    assert requests[-2].target.read_bytes() == b"\x89PNG\r\n\x1a\nfixture"


@pytest.mark.parametrize(
    "kind",
    (
        SinkKind.OBSERVATION,
        SinkKind.BASELINE,
        SinkKind.FINDING,
        SinkKind.WRAP_RECORD,
    ),
)
def test_known_record_sink_rejects_mismatched_model(kind: SinkKind, tmp_path: Path) -> None:
    # Given: a focused render model incorrectly paired with a known task-3 record sink.
    target = tmp_path / f"{kind.value}.json"

    # When: the mismatched model reaches the public persistence boundary.
    result = persist(PersistRequest(target, ModelArtifact(kind, _render_model())), LeakContext())

    # Then: the mismatch is typed rejection and creates no filesystem artifact.
    assert isinstance(result, PersistRejected)
    assert result.code is RejectionCode.INVALID_ARTIFACT
    assert not target.exists()
    assert tuple(tmp_path.iterdir()) == ()


def test_invalid_unicode_is_typed_rejection_without_artifact(tmp_path: Path) -> None:
    # Given: rendered text containing an invalid lone surrogate.
    target = tmp_path / "report.md"
    artifact = RenderedArtifact(SinkKind.MARKDOWN, _render_model(), "invalid:\ud800")

    # When: malformed text reaches the public persistence boundary.
    result = persist(PersistRequest(target, artifact), LeakContext())

    # Then: no raw Unicode exception escapes and no file or temp is created.
    assert isinstance(result, PersistRejected)
    assert result.code is RejectionCode.INVALID_ARTIFACT
    assert not target.exists()
    assert tuple(tmp_path.iterdir()) == ()


def test_known_record_types_are_accepted_by_their_own_sinks(tmp_path: Path) -> None:
    # Given: each known task-3 persisted record paired with its exact sink.
    records = (
        (SinkKind.OBSERVATION, Observation, "observation.json"),
        (SinkKind.BASELINE, Baseline, "baseline.json"),
        (SinkKind.FINDING, Finding, "finding.json"),
        (SinkKind.WRAP_RECORD, WrapRecord, "wrap_record.json"),
    )

    # When: the typed records cross their matching sinks.
    results = tuple(
        persist(
            PersistRequest(
                tmp_path / f"{kind.value}.json",
                ModelArtifact(
                    kind,
                    model_type.model_validate_json((FIXTURES / fixture).read_text()),
                ),
            ),
            LeakContext(),
        )
        for kind, model_type, fixture in records
    )

    # Then: all exact pairings persist successfully.
    assert all(isinstance(result, PersistSuccess) for result in results)


def test_repeated_persistence_is_byte_identical_across_directories(tmp_path: Path) -> None:
    # Given: identical typed render input and two independent destinations.
    artifact = RenderedArtifact(SinkKind.SVG, _render_model(), "<svg>UNKNOWN</svg>\r\n")
    left = tmp_path / "left" / "badge.svg"
    right = tmp_path / "right" / "badge.svg"
    left.parent.mkdir()
    right.parent.mkdir()

    # When: both destinations are persisted.
    left_result = persist(PersistRequest(left, artifact), LeakContext())
    right_result = persist(PersistRequest(right, artifact), LeakContext())

    # Then: observable bytes and hashes are identical.
    assert isinstance(left_result, PersistSuccess)
    assert isinstance(right_result, PersistSuccess)
    assert left.read_bytes() == right.read_bytes()
    assert (
        hashlib.sha256(left.read_bytes()).hexdigest()
        == hashlib.sha256(right.read_bytes()).hexdigest()
    )
