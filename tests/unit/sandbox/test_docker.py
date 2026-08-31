"""Docker command construction tests; no daemon is required."""

import asyncio
import json
from pathlib import Path

import pytest

from panopticon.sandbox.base import ContainerSpec, SandboxError
from panopticon.sandbox.docker import DockerContainer, DockerRuntime, is_pinned_image


class _Reader:
    def __init__(self, value: bytes) -> None:
        self.value = value

    async def read(self, _size: int) -> bytes:
        value, self.value = self.value, b""
        return value


class _Process:
    def __init__(self, output: bytes = b"container-id\n", returncode: int = 0) -> None:
        self.returncode = returncode
        self.stdout, self.stderr = _Reader(output), _Reader(b"")
        self.stdin = None

    async def wait(self) -> int:
        return 0


@pytest.mark.asyncio
async def test_run_uses_isolation_flags_and_vector(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, ...]] = []

    async def fake_exec(*args: object, **kwargs: object) -> _Process:
        calls.append(tuple(str(arg) for arg in args))
        operation = str(args[1])
        if operation == "network" and str(args[2]) == "inspect":
            return _Process(b"", returncode=1)
        if operation == "network":
            return _Process(b"network-id\n")
        if operation == "run":
            return _Process()
        if operation == "inspect":
            host_config = {
                "ReadonlyRootfs": True,
                "PidsLimit": 256,
                "CapDrop": ["ALL"],
                "CapAdd": ["SYS_PTRACE"],
                "NetworkMode": "pano-net",
            }
            return _Process(json.dumps([{"HostConfig": host_config}]).encode())
        return _Process(b"")

    monkeypatch.setattr(
        "panopticon.sandbox._docker_runtime.asyncio.create_subprocess_exec",
        fake_exec,
    )
    monkeypatch.setattr(
        "panopticon.sandbox._docker_container.asyncio.create_subprocess_exec",
        fake_exec,
    )
    image = "registry.example/pano@sha256:" + "a" * 64
    await DockerRuntime("docker").run(ContainerSpec(image, ["serve"], {}, b"archive"))
    command = next(call for call in calls if call[1] == "run")
    assert "--read-only" in command and "--cap-drop" in command
    assert "--pull=never" in command
    assert "--user" in command and "1000:1000" in command
    assert "--tmpfs" in command
    assert "/home/pano:mode=1777" in command
    assert "HOME=/home/pano" in command
    assert "XDG_CACHE_HOME=/home/pano/.cache" in command
    assert "npm_config_cache=/home/pano/.cache/npm" in command
    assert "UV_CACHE_DIR=/home/pano/.cache/uv" in command
    assert "shell=True" not in command
    assert any(call[1:5] == ("exec", "-i", "container-id", "tar") for call in calls)
    assert any(call[1] == "inspect" for call in calls)
    assert any(call[1:4] == ("network", "create", "--driver") for call in calls)


@pytest.mark.asyncio
async def test_run_rejects_mutable_image(tmp_path: Path) -> None:
    runtime = DockerRuntime("docker")
    spec = ContainerSpec("registry.example/pano:latest", [], {}, b"archive")
    with pytest.raises(SandboxError, match="IMAGE_NOT_PINNED"):
        await runtime.run(spec)


@pytest.mark.asyncio
async def test_run_rejects_missing_image_without_implicit_pull(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    async def fake_exec(*args: object, **kwargs: object) -> _Process:
        calls.append(tuple(str(arg) for arg in args))
        return _Process(b"", returncode=1)

    monkeypatch.setattr(
        "panopticon.sandbox._docker_runtime.asyncio.create_subprocess_exec",
        fake_exec,
    )
    image = "registry.example/pano@sha256:" + "a" * 64
    with pytest.raises(SandboxError, match="IMAGE_NOT_PRESENT"):
        await DockerRuntime("docker").run(ContainerSpec(image, ["serve"], {}, b"archive"))
    assert [call[1:] for call in calls] == [("image", "inspect", image)]


def test_local_content_digest_is_an_immutable_image_reference() -> None:
    assert is_pinned_image("sha256:" + "a" * 64)


async def test_cancelled_setup_removes_created_container(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    entered = asyncio.Event()

    class BlockingContainer:
        cleaned = False

        async def copy_archive_in(self, payload: bytes, destination: str) -> None:
            del payload, destination
            entered.set()
            await asyncio.Future()

        async def assert_effective_options(self, expected: object) -> None:
            del expected

        async def rm(self) -> None:
            self.cleaned = True

    container = BlockingContainer()
    runtime = DockerRuntime("docker")

    async def available_network(_name: str) -> None:
        return None

    async def started(*args: object, **kwargs: object) -> _Process:
        del args, kwargs
        return _Process()

    monkeypatch.setattr(runtime, "_ensure_network", available_network)
    monkeypatch.setattr(runtime, "_container", lambda _container_id: container)
    monkeypatch.setattr(
        "panopticon.sandbox._docker_runtime.asyncio.create_subprocess_exec",
        started,
    )
    task = asyncio.create_task(
        runtime.run(
            ContainerSpec(
                "registry.example/pano@sha256:" + "a" * 64,
                ["serve"],
                {},
                b"archive",
            )
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=1)

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert container.cleaned


async def test_lifecycle_methods_emit_vector_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []

    async def fake_exec(*args: object, **kwargs: object) -> _Process:
        del kwargs
        calls.append(tuple(str(arg) for arg in args))
        return _Process(b"")

    monkeypatch.setattr(
        "panopticon.sandbox._docker_container.asyncio.create_subprocess_exec",
        fake_exec,
    )
    container = DockerContainer("docker", "container-id")

    await container.terminate(3)
    await container.kill()
    await container.rm()
    await container.rm()

    assert [call[1] for call in calls] == ["stop", "kill", "rm"]
    assert calls[0][1:] == ("stop", "-t", "3", "container-id")
