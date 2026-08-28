from __future__ import annotations

import json
from pathlib import Path

import pytest

from panopticon.sandbox._docker_container import DockerContainer
from panopticon.sandbox.base import ExecResult, SandboxError, StreamResult


def res(code: int = 0, out: bytes = b"", err: bytes = b"", trunc: bool = False) -> ExecResult:
    return ExecResult(code, StreamResult(out, trunc), StreamResult(err, trunc))


async def returned(value: ExecResult, argv: list[str], timeout: float = 30.0) -> ExecResult:
    return value


@pytest.mark.asyncio
async def test_container_inspect_options_and_mismatch(monkeypatch) -> None:
    c = DockerContainer("docker", "id")
    monkeypatch.setattr(
        c,
        "_command",
        lambda argv, timeout=30.0: returned(
            res(out=json.dumps([{"HostConfig": {"PidsLimit": 2, "CapDrop": ["CAP_A"]}}]).encode()),
            argv,
            timeout,
        ),
    )
    assert (await c.inspect())["HostConfig"] is not None
    with pytest.raises(SandboxError, match="INSPECT_MISMATCH:CapDrop"):
        await c.assert_effective_options({"CapDrop": ["ALL"]})

    monkeypatch.setattr(
        c,
        "_command",
        lambda argv, timeout=30.0: returned(res(out=b"not-json"), argv, timeout),
    )
    with pytest.raises(SandboxError, match="INSPECT_INVALID"):
        await c.inspect()


@pytest.mark.asyncio
async def test_container_validation_cleanup_and_resource_paths(tmp_path: Path, monkeypatch) -> None:
    c = DockerContainer("docker", "id")
    with pytest.raises(SandboxError, match="INVALID_EXEC_ARGV"):
        await c.exec(["bad\x00arg"], 1)
    with pytest.raises(SandboxError, match="COPY_DESTINATION_INVALID"):
        await c.copy_in(tmp_path, "../escape")

    calls: list[list[str]] = []

    async def command(argv: list[str], timeout: float = 30.0) -> ExecResult:
        calls.append(argv)
        return res(1, err=b"no such container")

    monkeypatch.setattr(c, "_command", command)
    await c.terminate(0)
    await c.kill()
    await c.rm()
    assert calls == [["stop", "-t", "0", "id"], ["kill", "id"], ["rm", "-f", "id"]]


@pytest.mark.asyncio
async def test_container_wait_logs_trace_and_copy_errors(tmp_path: Path, monkeypatch) -> None:
    c = DockerContainer("docker", "id")

    async def command(argv: list[str], timeout: float = 30.0) -> ExecResult:
        if argv[0] == "wait":
            return res(out=b"not-an-int")
        if argv[0] == "logs":
            return res(out=b"abc", trunc=True)
        return res(1)

    monkeypatch.setattr(c, "_command", command)
    with pytest.raises(SandboxError, match="WAIT_INVALID"):
        await c.wait()
    logs = await c.logs(2)
    assert logs.data == b"ab" and logs.truncated
    with pytest.raises(SandboxError, match="COPY_OUT_FAILED"):
        await c.copy_out("/x", tmp_path)
