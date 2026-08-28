import pytest

from panopticon.sandbox.base import SandboxError
from panopticon.sandbox.podman import PodmanRuntime


def test_podman_name_and_executable() -> None:
    runtime = PodmanRuntime("podman-test")
    assert runtime.name == "podman"
    assert runtime.executable == "podman-test"


@pytest.mark.asyncio
async def test_podman_rejects_unpinned_pull() -> None:
    with pytest.raises(SandboxError, match="IMAGE_NOT_PINNED"):
        await PodmanRuntime("podman").pull("alpine:latest")
