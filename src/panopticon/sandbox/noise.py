"""Deterministic sandbox trace noise policy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .trace_model import TraceEvent

_DEFAULT = Path(__file__).with_name("noise.yaml")


@dataclass(frozen=True, slots=True)
class NoisePolicy:
    prefixes: tuple[str, ...] = ()
    exact: frozenset[str] = frozenset()

    def matches(self, path: str) -> bool:
        return path in self.exact or any(
            path == prefix or path.startswith(prefix.rstrip("/") + "/") for prefix in self.prefixes
        )

    def filter(
        self, events: tuple[TraceEvent, ...], *, raw: bool = False
    ) -> tuple[tuple[TraceEvent, ...], int]:
        if raw:
            return events, 0
        kept: list[TraceEvent] = []
        filtered = 0
        file_ops = {"open", "read", "write", "stat"}
        for event in events:
            interpreter = (
                event.operation == "exec"
                and event.path is not None
                and not any("PANO_DECOY_" in argument for argument in event.arguments)
                and event.path.rsplit("/", 1)[-1].lower() in {"python", "python3", "node", "nodejs"}
            )
            if event.path and (
                (event.operation in file_ops and self.matches(event.path)) or interpreter
            ):
                filtered += 1
            else:
                kept.append(event)
        return tuple(kept), filtered


def load_noise_policy(path: Path | None = None) -> NoisePolicy:
    source = path or _DEFAULT
    try:
        data: Any = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return NoisePolicy()
    prefixes = tuple(item for item in data.get("prefixes", ()) if isinstance(item, str))
    exact = frozenset(item for item in data.get("exact", ()) if isinstance(item, str))
    return NoisePolicy(prefixes=prefixes, exact=exact)


DEFAULT_NOISE_POLICY = load_noise_policy()

__all__ = ["DEFAULT_NOISE_POLICY", "NoisePolicy", "load_noise_policy"]
