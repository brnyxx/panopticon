"""Docker daemon preflight for the sandbox runtime. See panopticon-buildplan.md §8.

The `test-docker` CI job builds `pano-sandbox-*` images and then runs `-m docker`.
These tests assert the daemon contract those images depend on, so a missing or
broken runtime fails the job here instead of deep inside a sandbox run.
"""

from __future__ import annotations

import asyncio

import pytest

DOCKER_TIMEOUT = 30.0


async def _docker(*args: str) -> str:
    """Run a docker CLI query and return its stdout, failing loudly on any error."""
    proc = await asyncio.create_subprocess_exec(
        "docker",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=DOCKER_TIMEOUT)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    query = " ".join(args)
    detail = stderr.decode().strip()
    assert proc.returncode == 0, f"`docker {query}` exited {proc.returncode}: {detail}"
    return stdout.decode().strip()


@pytest.mark.docker
async def test_docker_daemon_reports_a_server_version() -> None:
    # Given: the container runtime the sandbox line requires.
    # When: the client asks the daemon to identify itself.
    version = await _docker("version", "--format", "{{.Server.Version}}")

    # Then: a real server answered, so the daemon is reachable and not client-only.
    assert version, "docker reported no server version; the daemon is unreachable"


@pytest.mark.docker
async def test_docker_daemon_runs_linux_containers() -> None:
    # Given: `pano-sandbox-*` images are Linux images.
    # When: the daemon reports the platform it executes containers on.
    os_type = await _docker("info", "--format", "{{.OSType}}")

    # Then: it is a Linux runtime, so those images can actually run.
    assert os_type == "linux", f"sandbox images need a linux runtime, daemon reports {os_type!r}"
