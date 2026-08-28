"""Engine boundary for badge generation."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from panopticon.badge.from_observation import BadgeResult
from panopticon.badge.from_observation import run_badge as _run_badge


def run_badge(
    observation: Path,
    output: Path,
    *,
    locale: Literal["en", "ko"] = "en",
) -> BadgeResult:
    return _run_badge(observation, output, locale=locale)


__all__ = ["run_badge"]
