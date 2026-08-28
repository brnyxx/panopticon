from __future__ import annotations

from pathlib import Path
from typing import assert_never

import pytest

from panopticon.models import Baseline, Finding, Observation, WrapRecord
from panopticon.store import (
    ArtifactInput,
    BinaryArtifact,
    LeakContext,
    ModelArtifact,
    PersistRejected,
    PersistRequest,
    RejectionCode,
    RenderedArtifact,
    RenderField,
    RenderModel,
    SinkKind,
    persist,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
LEAK_FIXTURES = FIXTURES / "leak"
SCHEMA_FIXTURES = FIXTURES / "schemas"
OBSERVATION = Observation.model_validate_json((SCHEMA_FIXTURES / "observation.json").read_text())
BASELINE = Baseline.model_validate_json((SCHEMA_FIXTURES / "baseline.json").read_text())
FINDING = Finding.model_validate_json((SCHEMA_FIXTURES / "finding.json").read_text())
WRAP_RECORD = WrapRecord.model_validate_json((SCHEMA_FIXTURES / "wrap_record.json").read_text())
CONTEXT = LeakContext(
    home_paths=("/home/alice",),
    secrets=("REAL-SECRET-VALUE", "REAL/SECRET+VALUE=="),
)


def _artifact(kind: SinkKind, payload: str) -> ArtifactInput:
    render_model = RenderModel(
        schema_version="1.0",
        title="Leak fixture",
        fields=(RenderField(name="detail", value=payload),),
    )
    match kind:
        case SinkKind.OBSERVATION:
            return ModelArtifact(kind, OBSERVATION.model_copy(update={"pano_version": payload}))
        case SinkKind.BASELINE:
            return ModelArtifact(kind, BASELINE.model_copy(update={"label": payload}))
        case SinkKind.FINDING:
            return ModelArtifact(kind, FINDING.model_copy(update={"title": payload}))
        case SinkKind.WRAP_RECORD:
            span = WRAP_RECORD.span.model_copy(update={"tool": payload})
            return ModelArtifact(kind, WRAP_RECORD.model_copy(update={"span": span}))
        case (
            SinkKind.CACHE
            | SinkKind.ALERT
            | SinkKind.JOURNAL
            | SinkKind.BACKUP
            | SinkKind.LOG
            | SinkKind.JSON
        ):
            return ModelArtifact(kind, render_model)
        case SinkKind.PNG:
            return BinaryArtifact(kind, render_model, b"opaque-compressed-fixture")
        case SinkKind.SARIF | SinkKind.MARKDOWN | SinkKind.SVG:
            return RenderedArtifact(kind, render_model, payload)
        case unreachable:
            assert_never(unreachable)


def test_chunk_split_secret_and_wsl_home_are_rejected_by_every_sink(tmp_path: Path) -> None:
    # Given: a chunk-split secret and a native WSL transform of the registered home.
    payload = 'credential=REAL-""SECRET-VALUE home=/mnt/c/Users/alice/.ssh/config'

    # When: every product sink crosses the real mandatory pre-write boundary.
    for kind in SinkKind:
        target = tmp_path / f"{kind.value}.artifact"
        result = persist(PersistRequest(target, _artifact(kind, payload)), CONTEXT)

        # Then: typed rejection creates neither a target nor temporary residue.
        assert isinstance(result, PersistRejected), kind
        assert not target.exists(), kind
        assert not any(path.name.startswith(f".{target.name}.") for path in tmp_path.iterdir())


@pytest.mark.parametrize("kind", tuple(SinkKind))
@pytest.mark.parametrize(
    "fixture",
    sorted(LEAK_FIXTURES.glob("*.txt")),
    ids=lambda fixture: fixture.name,
)
def test_every_leak_class_is_rejected_by_every_sink(
    fixture: Path, kind: SinkKind, tmp_path: Path
) -> None:
    # Given: one direct, encoded, native, split, or nested leak fixture.
    payload = fixture.read_text(encoding="utf-8")
    target = tmp_path / f"{kind.value}.artifact"

    # When: the fixture reaches one closed sink kind.
    result = persist(PersistRequest(target, _artifact(kind, payload)), CONTEXT)

    # Then: the gateway rejects before creating any filesystem artifact.
    assert isinstance(result, PersistRejected)
    assert result.code is RejectionCode.LEAK_DETECTED
    assert not target.exists()
    assert tuple(tmp_path.iterdir()) == ()
