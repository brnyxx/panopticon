"""Stderr-only status rendering for transparent wrap failures."""

from __future__ import annotations

from dataclasses import dataclass

from panopticon.engine.wrap import WrapCommandResult


@dataclass(frozen=True, slots=True)
class RenderedWrap:
    stderr: str
    exit_code: int


def render(result: WrapCommandResult) -> RenderedWrap:
    if result.relay is not None:
        return RenderedWrap("", result.exit_code)
    return RenderedWrap(f"{result.reason_code}\n", result.exit_code)


__all__ = ["RenderedWrap", "render"]
