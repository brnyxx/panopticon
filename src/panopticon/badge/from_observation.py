"""Convert persisted observations into deterministic badge models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from panopticon.models.observation import DeclaredCompleteness, Observation
from panopticon.models.state import StageStatus
from panopticon.reporters.visual import VisualFormat, persist_visual
from panopticon.store.contracts import PersistFailure, PersistResult, PersistSuccess
from panopticon.store.repository import ArtifactRepository, LoadStatus

from .eligibility import badge_eligible
from .model import CardFinding, CardStage, DeclarationAuthority, EvidenceCardModel, model_from


@dataclass(frozen=True, slots=True)
class BadgeDiagnostic:
    code: str
    detail: str


@dataclass(frozen=True, slots=True)
class BadgeResult:
    model: EvidenceCardModel | None
    diagnostic: BadgeDiagnostic | None = None


def model_from_observation(
    observation: Observation, *, locale: Literal["en", "ko"] = "en"
) -> EvidenceCardModel:
    completeness = observation.declared.completeness
    if completeness is DeclaredCompleteness.COMPLETE:
        authority = DeclarationAuthority.AUTHORITATIVE
    elif completeness is DeclaredCompleteness.PARTIAL:
        authority = DeclarationAuthority.PARTIAL
    else:
        authority = DeclarationAuthority.NONE
    stage_groups = (("stage", observation.state.stages), ("coverage", observation.state.coverage))
    stages = tuple(
        CardStage(
            f"{group_name}.{name}",
            value.status,
            value.status is not StageStatus.NOT_REQUESTED,
        )
        for group_name, group in stage_groups
        for name in type(group).model_fields
        for value in (getattr(group, name),)
    )
    leaks = sum(
        event.root.count
        for span in observation.spans
        for event in span.events
        if event.root.kind == "leak"
    )
    excluded = sum(finding.suppressed_by is not None for finding in observation.findings)
    findings = tuple(
        CardFinding(
            finding.rule_id,
            finding.kind.value,
            finding.kind.value != "info",
            finding.suppressed_by is not None,
        )
        for finding in observation.findings
    )
    return model_from(
        server=observation.protocol.server_info.name,
        observed_on=observation.observed_at.date(),
        overall_coverage=observation.state.overall.status,
        declaration_authority=authority,
        declaration_coverage=observation.state.stages.declared.status,
        stages=stages,
        leaks=leaks,
        findings=findings,
        locale=locale,
        excluded_evidence=excluded,
    )


def load_and_build(
    repository: ArtifactRepository,
    path: Path,
    *,
    locale: Literal["en", "ko"] = "en",
) -> BadgeResult:
    loaded = repository.load_observation(path)
    if loaded.status is not LoadStatus.AVAILABLE or loaded.observation is None:
        return BadgeResult(None, BadgeDiagnostic(loaded.reason_code, "observation unavailable"))
    model = model_from_observation(loaded.observation, locale=locale)
    if not badge_eligible(model):
        return BadgeResult(
            None,
            BadgeDiagnostic("BADGE_INELIGIBLE", "observation prerequisites incomplete"),
        )
    return BadgeResult(model)


def persist_badge(repository: ArtifactRepository, target: Path, result: BadgeResult) -> BadgeResult:
    if result.model is None:
        return result
    persisted = persist_visual(repository, target, result.model, VisualFormat.SVG)
    if isinstance(persisted, PersistSuccess):
        return result
    code = persisted.code.value if isinstance(persisted, PersistFailure) else "PERSIST_FAILED"
    return BadgeResult(None, BadgeDiagnostic(code, "badge output unavailable"))


def persist_observation_png(
    repository: ArtifactRepository,
    observation: Observation,
) -> PersistResult:
    target = repository.root / "cards" / f"{observation.observation_id}.png"
    return persist_visual(
        repository,
        target,
        model_from_observation(observation),
        VisualFormat.PNG,
    )


def run_badge(path: Path, target: Path, *, locale: Literal["en", "ko"] = "en") -> BadgeResult:
    repository = ArtifactRepository()
    return persist_badge(repository, target, load_and_build(repository, path, locale=locale))


__all__ = [
    "BadgeDiagnostic",
    "BadgeResult",
    "load_and_build",
    "model_from_observation",
    "persist_badge",
    "persist_observation_png",
    "run_badge",
]
