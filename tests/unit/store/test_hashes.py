from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from panopticon.store import (
    ArtifactInput,
    BinaryArtifact,
    LeakContext,
    ModelArtifact,
    PersistRequest,
    RenderedArtifact,
    RenderField,
    RenderModel,
    SinkKind,
    persist,
)

EXPECTED_HASHES = {
    "json": "f8b5a8e4d48add6bb1b96b573c05b49633876001ecdd1476e79221d2dbb1f2e0",
    "markdown": "0a335c4fee1b8b7950e2f2578d544bb14a6a2647561a018fe4f18deba5303178",
    "sarif": "4c4955ba66cddc917669b35f068b75ec9375d01cb5660208800f7c450aeff412",
    "png": "bd54b02fae14b6b9ed73887ded339b8ef846fbcba0d4e5f9d95470ac23ade242",
    "svg": "f9fe7eda1ebd52d8720369ac4db4311a3246c0e666f86c540dd97f86fed8e8cf",
}


@pytest.mark.parametrize("name", tuple(EXPECTED_HASHES))
def test_representative_artifact_hash_is_fixed(name: str, tmp_path: Path) -> None:
    # Given: a fixed typed render model and representative reporter output.
    model = RenderModel(
        schema_version="0.1",
        title="Evidence",
        fields=(RenderField(name="coverage", value="UNKNOWN"),),
    )
    artifacts: dict[str, ArtifactInput] = {
        "json": ModelArtifact(SinkKind.JSON, model),
        "markdown": RenderedArtifact(SinkKind.MARKDOWN, model, "# Evidence\nUNKNOWN\n"),
        "sarif": RenderedArtifact(
            SinkKind.SARIF,
            model,
            '{"version":"2.1.0","runs":[]}',
        ),
        "png": BinaryArtifact(SinkKind.PNG, model, b"\x89PNG\r\n\x1a\nfixture"),
        "svg": RenderedArtifact(SinkKind.SVG, model, "<svg>UNKNOWN</svg>\n"),
    }
    target = tmp_path / name

    # When: the artifact is persisted through its real sink.
    persist(PersistRequest(target, artifacts[name]), LeakContext())

    # Then: its shipped bytes retain the reviewed digest.
    assert hashlib.sha256(target.read_bytes()).hexdigest() == EXPECTED_HASHES[name]
