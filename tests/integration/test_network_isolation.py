"""Live proxy, DNS, and direct-egress isolation checks."""

from __future__ import annotations

import asyncio
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from panopticon.sandbox.base import ContainerSpec, Runtime
from panopticon.sandbox.docker import DockerContainer, DockerRuntime
from panopticon.sandbox.network import CapabilityStatus, NetworkController, NetworkServices
from panopticon.sandbox.podman import PodmanRuntime


@dataclass(frozen=True, slots=True)
class RuntimeCase:
    executable: str
    runtime: Runtime
    image_name: str
    rootless: bool


RUNTIME_CASES = (
    RuntimeCase(
        executable="docker",
        runtime=DockerRuntime(),
        image_name="pano-sandbox-base:ultragoal",
        rootless=False,
    ),
    RuntimeCase(
        executable="podman",
        runtime=PodmanRuntime(),
        image_name="localhost/pano-sandbox-base:ultragoal",
        rootless=os.environ.get("PANO_PODMAN_ROOTLESS", "1") != "0",
    ),
)


async def _local_image_ref(case: RuntimeCase) -> str:
    process = await asyncio.create_subprocess_exec(
        case.executable,
        "image",
        "inspect",
        case.image_name,
        "--format",
        "{{.Id}}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await asyncio.wait_for(process.communicate(), timeout=30)
    assert process.returncode == 0
    digest = stdout.decode().strip()
    if len(digest) == 64:
        digest = "sha256:" + digest
    assert digest.startswith("sha256:")
    return digest


@pytest.mark.docker
@pytest.mark.parametrize(
    "case",
    RUNTIME_CASES,
    ids=["docker", "podman"],
)
async def test_internal_network_forces_proxy_and_records_dns(
    tmp_path: Path,
    case: RuntimeCase,
) -> None:
    suffix = hashlib.sha256(str(tmp_path).encode()).hexdigest()[:8]
    image = await _local_image_ref(case)
    controller = NetworkController(case.executable)
    session = await controller.start(
        NetworkServices(
            image=image,
            name=f"pano-it-{suffix}",
            rootless=case.rootless,
        )
    )
    decoy_home = tmp_path / "decoy"
    decoy_home.mkdir()
    container = await case.runtime.run(
        session.apply(
            ContainerSpec(
                image=image,
                command=["sleep", "60"],
                env={},
                decoy_home=decoy_home,
            )
        )
    )

    try:
        proxied = await container.exec(
            ["git", "ls-remote", "https://github.com/git/git", "HEAD"],
            30,
        )
        bypass = await container.exec(
            [
                "env",
                "-u",
                "HTTP_PROXY",
                "-u",
                "HTTPS_PROXY",
                "-u",
                "http_proxy",
                "-u",
                "https_proxy",
                "git",
                "ls-remote",
                "https://github.com/git/git",
                "HEAD",
            ],
            15,
        )
        resolved = await container.exec(["getent", "hosts", "github.com"], 10)
        proxy_log = await DockerContainer(case.executable, session.proxy_id).exec(
            ["cat", "/tmp/tinyproxy.log"],
            10,
        )
        dns_log = await DockerContainer(case.executable, session.dns_id).logs()
        inspection = await container.inspect()
        host_config = inspection.get("HostConfig")

        assert proxied.returncode == 0
        assert b"HEAD" in proxied.stdout.data
        assert bypass.returncode != 0
        assert b"github.com" in proxy_log.stdout.data
        if case.rootless:
            assert session.plan.dns is CapabilityStatus.PARTIAL
        else:
            assert resolved.returncode == 0
            assert b"github.com" in dns_log.data
        assert isinstance(host_config, dict)
        assert host_config["Binds"] in (None, [])
    finally:
        await container.rm()
        await controller.stop(session)
