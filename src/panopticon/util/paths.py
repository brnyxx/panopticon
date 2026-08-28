"""Deterministic project-path traversal helpers."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


def project_roots(cwd: Path) -> tuple[Path, ...]:
    """Return cwd followed by exactly its next three parent levels."""
    roots: list[Path] = []
    current = cwd
    for _ in range(4):
        roots.append(current)
        current = current.parent
    return tuple(roots)


def order_candidate_paths(
    project_paths: Iterable[Path], global_paths: Iterable[Path]
) -> tuple[Path, ...]:
    """Place nearest project candidates first, then unique sorted global candidates."""
    ordered: list[Path] = []
    seen: set[Path] = set()
    for path in project_paths:
        if path not in seen:
            ordered.append(path)
            seen.add(path)
    for path in sorted(global_paths, key=Path.as_posix):
        if path not in seen:
            ordered.append(path)
            seen.add(path)
    return tuple(ordered)
