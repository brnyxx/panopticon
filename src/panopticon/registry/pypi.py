"""PyPI history normalization."""

from __future__ import annotations

from datetime import datetime

from .common import normalize_registry
from .model import NormalizedHistory


def normalize_pypi(
    payload: object, *, name: str, spec: str, now: datetime | None = None
) -> NormalizedHistory:
    return normalize_registry("pypi", payload, name=name, spec=spec, now=now)
