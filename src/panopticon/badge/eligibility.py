"""Single deterministic predicate for evidence-badge eligibility."""

from __future__ import annotations

from panopticon.models.state import StageStatus

from .model import DeclarationAuthority, EvidenceCardModel


def badge_eligible(model: EvidenceCardModel) -> bool:
    """Require authoritative declarations and complete, unobscured observation."""
    if model.declaration_authority is not DeclarationAuthority.AUTHORITATIVE:
        return False
    if model.declaration_coverage is not StageStatus.COMPLETE:
        return False
    if model.overall_coverage is not StageStatus.COMPLETE:
        return False
    if model.uncovered_events or model.leaks or model.excluded_evidence:
        return False
    if any(stage.applicable and stage.status is not StageStatus.COMPLETE for stage in model.stages):
        return False
    return not any(finding.affects_eligibility for finding in model.findings)


__all__ = ["badge_eligible"]
