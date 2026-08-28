"""Leak-checked persistence adapter for deterministic report formats."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from panopticon.store.contracts import (
    PersistRequest,
    PersistResult,
    RenderedArtifact,
    RenderField,
    RenderModel,
    SinkKind,
)
from panopticon.store.gateway import persist
from panopticon.util.leak_check import LeakContext

from .markdown import render_markdown
from .report_bundle import ReportBundle
from .sarif import render_sarif


class ReportFormat(StrEnum):
    SARIF = "sarif"
    MARKDOWN = "markdown"


def persist_report(
    target: Path,
    report: ReportBundle,
    output_format: ReportFormat,
    leak_context: LeakContext,
) -> PersistResult:
    """Render from the sanitized bundle and write only through ``store.persist``."""
    if output_format is ReportFormat.SARIF:
        text = render_sarif(report)
        kind = SinkKind.SARIF
    else:
        text = render_markdown(report)
        kind = SinkKind.MARKDOWN
    render_model = RenderModel(
        schema_version="1.0",
        title="Panopticon report",
        fields=(
            RenderField(name="status", value=report.model.status),
            RenderField(name="reason_code", value=report.model.reason_code),
            RenderField(name="category", value=report.category),
            RenderField(name="finding_count", value=str(len(report.findings))),
        ),
    )
    request = PersistRequest(target, RenderedArtifact(kind, render_model, text))
    return persist(request, leak_context)


__all__ = ["ReportFormat", "persist_report"]
