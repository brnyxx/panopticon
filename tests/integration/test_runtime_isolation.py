"""Live container-runtime isolation checks for the sandbox contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from panopticon.sandbox.base import ContainerSpec, Runtime, SandboxError
from panopticon.sandbox.decoy import decoy_archive, generate_decoy_home
from panopticon.sandbox.docker import DockerRuntime
from panopticon.sandbox.podman import PodmanRuntime

DEBIAN_IMAGE = (
    "debian:bookworm-slim@sha256:88200866dfff7ea7f5cbcb6ec7c8a701889efe6fe859fe64d6990e4b07ea4171"
)


@pytest.mark.docker
@pytest.mark.parametrize(
    "runtime",
    [DockerRuntime(), PodmanRuntime()],
    ids=["docker", "podman"],
)
async def test_container_runtime_populates_only_decoy_home_and_enforces_options(
    tmp_path: Path,
    runtime: Runtime,
) -> None:
    manifest = generate_decoy_home("runtime-isolation")
    marker_path = sorted(manifest.files)[0]
    spec = ContainerSpec(
        image=DEBIAN_IMAGE,
        command=["sleep", "60"],
        env={"HOME": "/prohibited", "FIXTURE": "present"},
        decoy_archive=decoy_archive(manifest),
    )
    container = await runtime.run(spec)
    second = None

    try:
        marker = await container.exec(["cat", f"/home/pano/{marker_path}"], 10)
        environment = await container.exec(["env"], 10)
        await container.exec(["mkdir", "-p", "/home/pano/.cache/npm"], 10)
        await container.exec(["touch", "/home/pano/.cache/npm/private-marker"], 10)
        second = await runtime.run(spec)
        isolated_cache = await second.exec(
            ["test", "!", "-e", "/home/pano/.cache/npm/private-marker"],
            10,
        )
        escape_attempts = [
            await container.exec(command, 10)
            for command in (
                ["touch", "/etc/pano-escape"],
                ["chmod", "0777", "/etc"],
                ["mknod", "/tmp/pano-device", "c", "1", "3"],
                ["cat", "/var/run/docker.sock"],
                ["cat", "/proc/1/root/etc/shadow"],
            )
        ]
        inspection = await container.inspect()
        host_config = inspection.get("HostConfig")
        network_settings = inspection.get("NetworkSettings")

        assert marker.returncode == 0
        assert marker.stdout.data == manifest.files[marker_path]
        assert isolated_cache.returncode == 0
        assert b"XDG_CACHE_HOME=/home/pano/.cache" in environment.stdout.data
        assert b"npm_config_cache=/home/pano/.cache/npm" in environment.stdout.data
        assert b"UV_CACHE_DIR=/home/pano/.cache/uv" in environment.stdout.data
        assert all(attempt.returncode != 0 for attempt in escape_attempts)
        assert isinstance(host_config, dict)
        assert host_config["ReadonlyRootfs"] is True
        assert host_config["Privileged"] is False
        assert host_config["PidMode"] in ("", "private")
        assert host_config["CapDrop"] == ["ALL"] or len(host_config["CapDrop"]) >= 10
        assert host_config["CapAdd"] in (["SYS_PTRACE"], ["CAP_SYS_PTRACE"])
        assert host_config["Binds"] in (None, [])
        assert set(host_config["Tmpfs"]) == {"/tmp", "/home/pano"}
        assert isinstance(network_settings, dict)
        networks = network_settings.get("Networks")
        assert isinstance(networks, dict)
        assert "pano-net" in networks
        with pytest.raises(SandboxError, match="EXEC_TIMEOUT"):
            await container.exec(["tail", "-f", "/dev/null"], 0.1)
    finally:
        if second is not None:
            await second.rm()
        await container.rm()
