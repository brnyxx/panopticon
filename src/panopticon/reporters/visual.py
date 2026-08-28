"""Leak-checked store gateway for deterministic visual evidence outputs."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from panopticon.badge.model import EvidenceCardModel
from panopticon.badge.svg import render_svg
from panopticon.store.contracts import (
    ArtifactInput,
    BinaryArtifact,
    PersistRequest,
    PersistResult,
    RenderedArtifact,
    RenderField,
    RenderModel,
    SinkKind,
)
from panopticon.store.repository import ArtifactRepository

from .png import render_png


class VisualFormat(StrEnum):
    PNG = "png"
    SVG = "svg"


def _render_model(model: EvidenceCardModel) -> RenderModel:
    return RenderModel(
        schema_version="0.1",
        title="Panopticon observation evidence",
        fields=(
            RenderField(name="server", value=model.server),
            RenderField(name="observed_on", value=model.observed_on.isoformat()),
            RenderField(name="coverage", value=model.overall_coverage.value),
            RenderField(
                name="declaration",
                value=(f"{model.declaration_authority.value}/{model.declaration_coverage.value}"),
            ),
            RenderField(
                name="stages",
                value=",".join(f"{stage.name}:{stage.status.value}" for stage in model.stages),
            ),
            RenderField(
                name="finding_kinds",
                value=",".join(finding.kind for finding in model.findings),
            ),
        ),
    )


def persist_visual(
    repository: ArtifactRepository,
    target: Path,
    model: EvidenceCardModel,
    output_format: VisualFormat,
) -> PersistResult:
    render_model = _render_model(model)
    artifact: ArtifactInput
    if output_format is VisualFormat.PNG:
        artifact = BinaryArtifact(SinkKind.PNG, render_model, render_png(model))
    else:
        artifact = RenderedArtifact(SinkKind.SVG, render_model, render_svg(model))
    return repository.persist_request(PersistRequest(target, artifact))


__all__ = ["VisualFormat", "persist_visual"]
