# Copyright (c) 2026 MCP Sentinel contributors
# SPDX-License-Identifier: MIT
"""Strict typed semantic-review response contracts."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, ValidationInfo, field_validator

from panopticon.models.common import StrictModel
from panopticon.models.finding import FindingSeverity

ReviewText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ReasoningText = Annotated[ReviewText, StringConstraints(max_length=800)]
ClaimText = Annotated[ReviewText, StringConstraints(max_length=300)]


class ReviewEvidenceReference(StrictModel):
    path: ReviewText
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    claim: ClaimText

    @field_validator("path")
    @classmethod
    def path_relative(cls, value: str) -> str:
        if value.startswith(("/", "\\")) or ".." in value.replace("\\", "/").split("/"):
            raise ValueError("evidence path must be relative")
        return value.replace("\\", "/")

    @field_validator("end_line")
    @classmethod
    def ordered(cls, value: int, info: ValidationInfo) -> int:
        start = info.data.get("start_line")
        if isinstance(start, int) and value < start:
            raise ValueError("end_line cannot precede start_line")
        return value


class ReviewArgumentBinding(StrictModel):
    probe_id: Literal["SENT-009", "SENT-010", "SENT-011"]
    field: ReviewText
    value: Literal[
        "__SENTINEL_OVERSIZED__",
        "__SENTINEL_INJECTION__",
        "__SENTINEL_WRONG_TYPE__",
        "__SENTINEL_OMIT__",
    ]


class ReviewProbePlan(StrictModel):
    ordered_probe_ids: tuple[Literal["SENT-008", "SENT-009", "SENT-010", "SENT-011"], ...]
    target_tool: ReviewText
    argument_bindings: tuple[ReviewArgumentBinding, ...] = Field(min_length=3, max_length=3)


class FindingReviewDecision(StrictModel):
    finding_id: UUID
    status: Literal["confirmed", "suppressed", "needs_review"]
    confidence: float = Field(ge=0, le=1)
    reasoning: ReasoningText
    evidence_refs: tuple[ReviewEvidenceReference, ...] = Field(min_length=1, max_length=3)
    probe_plan: ReviewProbePlan | None = None
    suggested_severity_override: FindingSeverity | None = None


class ReviewBatchResponse(StrictModel):
    reviews: tuple[FindingReviewDecision, ...] = Field(min_length=1, max_length=10)
