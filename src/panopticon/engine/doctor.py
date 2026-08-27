"""Protocol-only doctor pipeline boundary and its typed request."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from panopticon.engine.contracts import Result


@dataclass(frozen=True, slots=True)
class DoctorRequest:
    client: str | None = None
    list_clients: bool = False
    fix: bool = False


class DoctorPlan(Protocol):
    def run(self, request: DoctorRequest) -> Result: ...


__all__ = ["DoctorPlan", "DoctorRequest"]
