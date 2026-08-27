"""Protocol-only diff pipeline boundary and its typed request."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from panopticon.engine.contracts import Result


@dataclass(frozen=True, slots=True)
class DiffRequest:
    server: str | None = None
    since: str = "auto"


class DiffPlan(Protocol):
    def run(self, request: DiffRequest) -> Result: ...


__all__ = ["DiffPlan", "DiffRequest"]
