"""Bounded, value-free home directory snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .base import Container


@dataclass(frozen=True, slots=True)
class SnapshotEntry:
    path: str
    size: int
    mtime_ns: int


@dataclass(frozen=True, slots=True)
class SnapshotDiff:
    created: tuple[str, ...] = ()
    modified: tuple[str, ...] = ()
    deleted: tuple[str, ...] = ()

    @property
    def paths(
        self,
    ) -> tuple[tuple[Literal["create", "write", "delete"], str], ...]:
        return (
            tuple(("create", p) for p in self.created)
            + tuple(("write", p) for p in self.modified)
            + tuple(("delete", p) for p in self.deleted)
        )


def parse_snapshot(data: bytes, *, limit: int = 256) -> tuple[SnapshotEntry, ...]:
    entries: list[SnapshotEntry] = []
    for line in data.decode(errors="replace").splitlines()[:limit]:
        fields = line.split("\t", 2)
        path, size, mtime = fields if len(fields) == 3 else ("", "", "")
        if not path or not path.startswith("/home/pano/"):
            continue
        try:
            entries.append(SnapshotEntry(path, int(size), int(float(mtime) * 1_000_000_000)))
        except ValueError:
            continue
    return tuple(sorted(entries, key=lambda item: item.path))


def diff_snapshots(
    before: tuple[SnapshotEntry, ...], after: tuple[SnapshotEntry, ...]
) -> SnapshotDiff:
    left = {entry.path: entry for entry in before}
    right = {entry.path: entry for entry in after}
    return SnapshotDiff(
        created=tuple(sorted(set(right) - set(left))),
        modified=tuple(
            sorted(path for path in set(left) & set(right) if left[path] != right[path])
        ),
        deleted=tuple(sorted(set(left) - set(right))),
    )


async def collect_home(
    container: Container, *, timeout: float = 2.0, limit: int = 256
) -> tuple[SnapshotEntry, ...] | None:
    command = ["sh", "-c", "find /home/pano -type f -printf '%p\\t%s\\t%T@\\n' 2>/dev/null"]
    try:
        result = await container.exec(command, timeout=timeout)
    except (OSError, TimeoutError, AttributeError):
        return None
    if result.returncode != 0 or result.stdout.truncated:
        return None
    return parse_snapshot(result.stdout.data, limit=limit)


__all__ = ["SnapshotDiff", "SnapshotEntry", "collect_home", "diff_snapshots", "parse_snapshot"]
