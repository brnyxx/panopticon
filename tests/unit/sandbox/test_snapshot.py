from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import pytest

from panopticon.sandbox.base import Container, ExecResult, StreamResult
from panopticon.sandbox.snapshot import (
    SnapshotEntry,
    collect_home,
    diff_snapshots,
    parse_snapshot,
)


def test_parse_snapshot_valid_entries_are_sorted_and_mtime_is_nanoseconds() -> None:
    data = b"/home/pano/z.txt\t3\t2.5\n/home/pano/a.txt\t7\t1\n"

    assert parse_snapshot(data) == (
        SnapshotEntry("/home/pano/a.txt", 7, 1_000_000_000),
        SnapshotEntry("/home/pano/z.txt", 3, 2_500_000_000),
    )


def test_parse_snapshot_skips_invalid_lines_and_honors_limit() -> None:
    data = (
        b"/home/pano/first\t1\t1\n"
        b"/tmp/outside\t2\t2\n"
        b"malformed\n"
        b"/home/pano/bad-size\tnot-int\t3\n"
        b"/home/pano/bad-time\t4\tnot-float\n"
        b"/home/pano/second\t2\t2\n"
    )

    assert parse_snapshot(data, limit=0) == ()
    assert parse_snapshot(data, limit=2) == (SnapshotEntry("/home/pano/first", 1, 1_000_000_000),)


def test_diff_snapshots_reports_create_modify_delete_and_paths() -> None:
    before = (
        SnapshotEntry("/home/pano/delete", 1, 1),
        SnapshotEntry("/home/pano/keep", 2, 2),
        SnapshotEntry("/home/pano/change", 3, 3),
    )
    after = (
        SnapshotEntry("/home/pano/create", 4, 4),
        SnapshotEntry("/home/pano/keep", 2, 2),
        SnapshotEntry("/home/pano/change", 9, 3),
    )

    diff = diff_snapshots(before, after)
    assert diff.created == ("/home/pano/create",)
    assert diff.modified == ("/home/pano/change",)
    assert diff.deleted == ("/home/pano/delete",)
    assert diff.paths == (
        ("create", "/home/pano/create"),
        ("write", "/home/pano/change"),
        ("delete", "/home/pano/delete"),
    )


@dataclass
class FakeContainer:
    result: ExecResult | None = None
    error: BaseException | None = None

    async def exec(self, argv: list[str], timeout: float, stdin: bytes | None = None) -> ExecResult:
        assert argv[:2] == ["sh", "-c"]
        assert timeout > 0
        assert stdin is None
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def fake(
    *, code: int = 0, data: bytes = b"/home/pano/file\t5\t3\n", truncated: bool = False
) -> Container:
    return cast(
        Container,
        FakeContainer(ExecResult(code, StreamResult(data, truncated), StreamResult(b""))),
    )


@pytest.mark.asyncio
async def test_collect_home_success_parses_typed_container_result() -> None:
    assert await collect_home(fake(), timeout=1.5, limit=256) == (
        SnapshotEntry("/home/pano/file", 5, 3_000_000_000),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "container",
    [
        fake(code=1),
        fake(truncated=True),
        cast(Container, FakeContainer(error=OSError("runtime unavailable"))),
    ],
    ids=["nonzero", "truncated", "exception"],
)
async def test_collect_home_failure_modes_return_none(container: Container) -> None:
    assert await collect_home(container) is None
