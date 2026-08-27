"""Protocol-only watch pipeline boundary and its typed request."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from panopticon.engine.contracts import Result


@dataclass(frozen=True, slots=True)
class WatchRequest:
    target: str
    calls: int = 1
    timeout: int = 20


class WatchPlan(Protocol):
    def run(self, request: WatchRequest) -> Result: ...


__all__ = ["WatchPlan", "WatchRequest"]
