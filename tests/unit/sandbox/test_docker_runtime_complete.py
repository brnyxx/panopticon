from __future__ import annotations

from pathlib import Path

import pytest

from panopticon.sandbox._docker_runtime import DockerRuntime
from panopticon.sandbox.base import ContainerSpec, ExecResult, SandboxError, StreamResult


def out(code: int = 0, data: bytes = b"") -> ExecResult:
    return ExecResult(code, StreamResult(data), StreamResult(b""))


@pytest.mark.asyncio
async def test_runtime_rejects_invalid_isolation_and_paths(tmp_path) -> None:
    runtime = DockerRuntime("docker")
    image = "repo@sha256:" + "a" * 64
    with pytest.raises(SandboxError, match="DECOY_HOME_INVALID"):
        await runtime.run(ContainerSpec(image, [], {}, tmp_path / "missing"))
    home = tmp_path / "home"
    home.mkdir()
    with pytest.raises(SandboxError, match="SELF_SOURCE_MUST_BE_ABSOLUTE"):
        await runtime.run(ContainerSpec(image, [], {}, home, self_source=Path("relative")))
    with pytest.raises(SandboxError, match="UNSUPPORTED_ISOLATION_OPTIONS"):
        await runtime.run(ContainerSpec(image, [], {}, home, read_only=False))


@pytest.mark.asyncio
async def test_runtime_network_and_start_failures(tmp_path, monkeypatch) -> None:
    runtime = DockerRuntime("docker")
    with pytest.raises(SandboxError, match="INVALID_NETWORK_NAME"):
        await runtime._ensure_network("bad/name")

    calls: list[list[str]] = []

    async def command(argv: list[str]) -> ExecResult:
        calls.append(argv)
        if argv[:2] == ["network", "inspect"]:
            return out(1)
        return out(1)

    monkeypatch.setattr(runtime, "_command", command)
    with pytest.raises(SandboxError, match="NETWORK_CREATE_FAILED"):
        await runtime._ensure_network("valid-net")


@pytest.mark.asyncio
async def test_runtime_run_rejects_empty_id_and_cleanup_error(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    image = "repo@sha256:" + "b" * 64
    runtime = DockerRuntime("docker")
    monkeypatch.setattr(runtime, "_ensure_network", lambda network: _done())

    class FakeContainer:
        async def copy_in(self, source, destination):
            return None

        async def assert_effective_options(self, expected):
            raise SandboxError("INSPECT_MISMATCH:x")

        async def rm(self):
            raise SandboxError("RM_FAILED")

    output = b"id\n"

    class Reader:
        def __init__(self, data):
            self.data = data

        async def read(self, size):
            data, self.data = self.data, b""
            return data

    class Process:
        def __init__(self):
            self.returncode, self.stdout, self.stderr, self.stdin = (
                0,
                Reader(output),
                Reader(b""),
                None,
            )

        async def wait(self):
            return 0

    async def _exec(*args, **kwargs):
        return Process()

    monkeypatch.setattr("panopticon.sandbox._docker_runtime.asyncio.create_subprocess_exec", _exec)
    monkeypatch.setattr(runtime, "_container", lambda cid: FakeContainer())
    with pytest.raises(SandboxError, match="CONTAINER_CLEANUP_FAILED"):
        await runtime.run(ContainerSpec(image, [], {}, home))


async def _done():
    return None
