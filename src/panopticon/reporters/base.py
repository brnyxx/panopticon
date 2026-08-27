"""Sanitized render value and reporter protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from panopticon.engine.contracts import Result


@dataclass(frozen=True, slots=True)
class Render:
    """Value-only output returned to the CLI for stream selection."""

    stdout: str
    stderr: str
    exit_code: int


class Reporter(Protocol):
    def render(self, result: Result, *, json_output: bool) -> Render: ...


__all__ = ["Render", "Reporter"]
