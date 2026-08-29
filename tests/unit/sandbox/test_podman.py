"""Podman subprocess and archive boundary tests."""

import io
import tarfile

import pytest

from panopticon.sandbox.base import ContainerSpec, SandboxError
from panopticon.sandbox.podman import PodmanContainer, PodmanRuntime


def _archive(*, member: bool = True) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        if member:
            info = tarfile.TarInfo("decoy.txt")
            info.size = 1
            archive.addfile(info, io.BytesIO(b"x"))
    return output.getvalue()


class _Reader:
    def __init__(self, data: bytes = b"") -> None:
        self.data = data

    async def read(self, _size: int) -> bytes:
        data, self.data = self.data, b""
        return data


class _Stdin:
    def __init__(self) -> None:
        self.data = bytearray()
        self.closed = False

    def write(self, data: bytes) -> None:
        self.data.extend(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class _Process:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode
        self.stdout = _Reader(b"stdout")
        self.stderr = _Reader(b"stderr")
        self.stdin = _Stdin()

    async def wait(self) -> int:
        return self.returncode


def test_podman_name_and_executable() -> None:
    runtime = PodmanRuntime("podman-test")
    assert runtime.name == "podman"
    assert runtime.executable == "podman-test"


@pytest.mark.asyncio
async def test_podman_rejects_unpinned_pull() -> None:
    with pytest.raises(SandboxError, match="IMAGE_NOT_PINNED"):
        await PodmanRuntime("podman").pull("alpine:latest")


@pytest.mark.asyncio
@pytest.mark.parametrize("destination", ["relative", "/home/pano/../escape", "/home/pano/../../"])
async def test_copy_archive_rejects_invalid_destination(destination: str) -> None:
    container = PodmanContainer("podman", "container-id")
    with pytest.raises(SandboxError, match="COPY_DESTINATION_INVALID"):
        await container.copy_archive_in(_archive(), destination)


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [b"", b"x" * (32 * 1024 * 1024 + 1), b"not a tar archive"])
async def test_copy_archive_rejects_empty_oversize_and_malformed_payload(payload: bytes) -> None:
    container = PodmanContainer("podman", "container-id")
    with pytest.raises(SandboxError, match="DECOY_ARCHIVE_INVALID"):
        await container.copy_archive_in(payload, "/home/pano")


@pytest.mark.asyncio
async def test_copy_archive_accepts_empty_valid_archive_without_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def unexpected_exec(*args: object, **kwargs: object) -> _Process:
        nonlocal called
        called = True
        return _Process(0)

    monkeypatch.setattr("panopticon.sandbox.podman.asyncio.create_subprocess_exec", unexpected_exec)
    await PodmanContainer("podman", "container-id").copy_archive_in(
        _archive(member=False), "/home/pano"
    )
    assert not called


@pytest.mark.asyncio
@pytest.mark.parametrize("returncode, succeeds", [(0, True), (23, False)])
async def test_copy_archive_streams_payload_and_reports_cp_result(
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
    succeeds: bool,
) -> None:
    process = _Process(returncode)
    calls: list[tuple[object, ...]] = []

    async def fake_exec(*args: object, **kwargs: object) -> _Process:
        calls.append(args)
        assert kwargs["stdin"] is not None
        return process

    monkeypatch.setattr("panopticon.sandbox.podman.asyncio.create_subprocess_exec", fake_exec)
    payload = _archive()
    operation = PodmanContainer("podman", "container-id").copy_archive_in(payload, "/home/pano")
    if succeeds:
        await operation
    else:
        with pytest.raises(SandboxError, match="COPY_IN_FAILED"):
            await operation
    assert calls == [("podman", "cp", "-", "container-id:/home/pano")]
    assert bytes(process.stdin.data) == payload
    assert process.stdin.closed


def test_podman_runtime_returns_podman_container() -> None:
    container = PodmanRuntime("podman-test")._container("id")
    assert isinstance(container, PodmanContainer)
    assert container.runtime == "podman-test"
    assert container.id == "id"


def test_podman_rootless_expected_options() -> None:
    spec = ContainerSpec("sha256:" + "a" * 64, [], {}, b"")
    assert PodmanRuntime()._expected_options(spec) == {
        "ReadonlyRootfs": True,
        "PidsLimit": 256,
        "CapDrop": ["ALL"],
        "CapAdd": ["SYS_PTRACE"],
    }
