"""Small immutable values used by the diff core."""

from __future__ import annotations

from enum import StrEnum

from pydantic import RootModel

from panopticon.models.common import StrictModel


class DeltaKind(StrEnum):
    NEW = "NEW"
    CHANGED = "CHANGED"
    UNCHANGED = "UNCHANGED"
    RESOLVED = "RESOLVED"
    UNKNOWN = "UNKNOWN"


class SemanticValue(RootModel[str]):
    """A stable key used in a category delta."""


class CategoryDelta(StrictModel):
    category: str
    key: str
    kind: DeltaKind


__all__ = ["CategoryDelta", "DeltaKind", "SemanticValue"]
