"""Protocol-only scan pipeline boundary and its typed request."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from panopticon.engine.contracts import Result


@dataclass(frozen=True, slots=True)
class ScanRequest:
    path: str = "."
    mode: str = "quick"


class ScanPlan(Protocol):
    def run(self, request: ScanRequest) -> Result: ...


__all__ = ["ScanPlan", "ScanRequest"]
