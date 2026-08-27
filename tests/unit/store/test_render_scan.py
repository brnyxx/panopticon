from __future__ import annotations

import errno
from dataclasses import dataclass
from pathlib import Path

from panopticon.store import (
    AtomicOperation,
    BinaryArtifact,
    LeakContext,
    PersistRejected,
    PersistRequest,
    RejectionCode,
    RenderedArtifact,
    RenderField,
    RenderModel,
    SinkKind,
    persist,
)


@dataclass(frozen=True, slots=True)
class RejectFilesystemAccess:
    def before(self, operation: AtomicOperation) -> None:
        raise OSError(errno.EIO, operation.value)


def test_binary_output_scans_render_model_before_encoding(tmp_path: Path) -> None:
    # Given: opaque compressed-looking bytes backed by a render model containing a known secret.
    render_model = RenderModel(
        schema_version="0.1",
        title="Evidence",
        fields=(RenderField(name="detail", value="REAL-SECRET-VALUE"),),
    )
    target = tmp_path / "report.png"

    # When: the binary artifact reaches the gateway.
    result = persist(
        PersistRequest(target, BinaryArtifact(SinkKind.PNG, render_model, b"compressed")),
        LeakContext(secrets=("REAL-SECRET-VALUE",)),
        RejectFilesystemAccess(),
    )

    # Then: typed rejection happens before any target or temporary file exists.
    assert isinstance(result, PersistRejected)
    assert result.code is RejectionCode.LEAK_DETECTED
    assert not target.exists()
    assert tuple(tmp_path.iterdir()) == ()


def test_markdown_leak_precedes_invalid_unicode_without_filesystem_access(tmp_path: Path) -> None:
    # Given: valid Markdown content containing a recognizable token and a lone surrogate.
    token = "sk-proj-abcdefghijklmnopqrstuvwxyz1234"
    render_model = RenderModel(
        schema_version="0.1",
        title="Markdown evidence",
        fields=(RenderField(name="detail", value="clean"),),
    )
    target = tmp_path / "report.md"
    markdown = f"# Evidence\n\nToken: {token}\n\nMarker: \ud800\n"

    # When: the mixed-content artifact crosses the public persistence boundary.
    result = persist(
        PersistRequest(target, RenderedArtifact(SinkKind.MARKDOWN, render_model, markdown)),
        LeakContext(),
        RejectFilesystemAccess(),
    )

    # Then: the leak rejection wins and no target or temporary artifact is created.
    assert isinstance(result, PersistRejected)
    assert result.code is RejectionCode.LEAK_DETECTED
    assert result.leak_hits
    assert token not in repr(result)
    assert tuple(tmp_path.iterdir()) == ()
