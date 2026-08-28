from __future__ import annotations

from pathlib import Path

from panopticon.store import (
    LeakContext,
    ModelArtifact,
    PersistRejected,
    PersistRequest,
    RejectionCode,
    RenderField,
    RenderModel,
    SinkKind,
    persist,
)


def test_plaintext_control_is_rejected_without_target_or_temp_file(tmp_path: Path) -> None:
    # Given: a non-secret control value and a separately registered secret.
    target = tmp_path / "control.pano-bak"
    model = RenderModel(
        schema_version="1.0",
        title="control",
        fields=(RenderField(name="value", value="registered-secret"),),
    )

    # When: the control crosses the existing Task4 backup sink.
    result = persist(
        PersistRequest(target, ModelArtifact(SinkKind.BACKUP, model)),
        LeakContext(secrets=("registered-secret",)),
    )

    # Then: the leak boundary rejects it before any filesystem artifact exists.
    assert isinstance(result, PersistRejected)
    assert result.code is RejectionCode.LEAK_DETECTED
    assert not target.exists()
    assert tuple(tmp_path.iterdir()) == ()
