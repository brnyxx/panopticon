"""Docker runtime lifecycle and command construction."""

from __future__ import annotations

import asyncio
import re
import shutil
from collections.abc import Mapping

from . import docker
from ._docker_container import _CONTAINER_TMP, DockerContainer
from .base import Container, ContainerSpec, ExecResult, SandboxError
from .streams import communicate


class DockerRuntime:
    name = "docker"

    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or shutil.which("docker") or "docker"

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    async def _command(self, argv: list[str]) -> ExecResult:
        process = await asyncio.create_subprocess_exec(
            self.executable, *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        return await communicate(process, None, 1_048_576)

    async def _ensure_network(self, network: str) -> None:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}", network):
            raise SandboxError("INVALID_NETWORK_NAME")
        inspected = await self._command(["network", "inspect", network])
        if inspected.returncode == 0:
            return
        created = await self._command(
            ["network", "create", "--driver", "bridge", "--internal", network]
        )
        if created.returncode:
            raise SandboxError("NETWORK_CREATE_FAILED")

    def _container(self, container_id: str) -> DockerContainer:
        return DockerContainer(self.executable, container_id)

    def _expected_options(self, spec: ContainerSpec) -> Mapping[str, object]:
        return {
            "ReadonlyRootfs": True,
            "PidsLimit": spec.pids_limit,
            "CapDrop": ["ALL"],
            "CapAdd": ["SYS_PTRACE"],
            "NetworkMode": spec.network,
        }

    async def pull(self, image_ref: str) -> None:
        if not docker.is_pinned_image(image_ref):
            raise SandboxError("IMAGE_NOT_PINNED")
        process = await asyncio.create_subprocess_exec(
            self.executable,
            "pull",
            image_ref,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        result = await communicate(process, None, 1_048_576)
        if result.returncode:
            raise SandboxError("IMAGE_PULL_FAILED")

    async def run(self, spec: ContainerSpec) -> Container:
        if not docker.is_pinned_image(spec.image):
            raise SandboxError("IMAGE_NOT_PINNED")
        if not spec.decoy_archive or len(spec.decoy_archive) > 32 * 1024 * 1024:
            raise SandboxError("DECOY_ARCHIVE_INVALID")
        if spec.self_source is not None and not spec.self_source.is_absolute():
            raise SandboxError("SELF_SOURCE_MUST_BE_ABSOLUTE")
        if not spec.read_only or spec.cap_add != ("SYS_PTRACE",):
            raise SandboxError("UNSUPPORTED_ISOLATION_OPTIONS")
        await self._ensure_network(spec.network)
        args = [
            "run",
            "-d",
            "-i",
            "--rm",
            "--read-only",
            "--tmpfs",
            str(_CONTAINER_TMP),
            "--tmpfs",
            "/home/pano:mode=1777",
            "--cap-drop",
            "ALL",
            "--cap-add",
            "SYS_PTRACE",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            str(spec.pids_limit),
            "--memory",
            spec.memory,
            "--cpus",
            str(spec.cpus),
            "--network",
            spec.network,
            "--user",
            "1000:1000",
        ]
        if spec.dns is not None:
            args += ["--dns", spec.dns]
        protected_env = {
            "HOME",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "UV_CACHE_DIR",
            "XDG_CACHE_HOME",
            "http_proxy",
            "https_proxy",
            "npm_config_cache",
        }
        for key, value in sorted(spec.env.items()):
            if key not in protected_env:
                args += ["-e", f"{key}={value}"]
        args += [
            "-e",
            "HOME=/home/pano",
            "-e",
            "XDG_CACHE_HOME=/home/pano/.cache",
            "-e",
            "npm_config_cache=/home/pano/.cache/npm",
            "-e",
            "UV_CACHE_DIR=/home/pano/.cache/uv",
        ]
        if spec.proxy_url is not None:
            args += [
                "-e",
                f"HTTP_PROXY={spec.proxy_url}",
                "-e",
                f"HTTPS_PROXY={spec.proxy_url}",
                "-e",
                f"http_proxy={spec.proxy_url}",
                "-e",
                f"https_proxy={spec.proxy_url}",
            ]
        if spec.self_source is not None:
            args += ["--mount", f"type=bind,src={spec.self_source},dst=/self,readonly"]
        args += [spec.image, *spec.command]
        process = await asyncio.create_subprocess_exec(
            self.executable, *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        result = await communicate(process, None, 65536)
        if result.returncode:
            raise SandboxError("CONTAINER_START_FAILED")
        container_id = (
            result.stdout.data.decode().strip().splitlines()[0] if result.stdout.data else ""
        )
        if not container_id:
            raise SandboxError("CONTAINER_ID_MISSING")
        container = self._container(container_id)
        try:
            await container.copy_archive_in(spec.decoy_archive, "/home/pano")
            await container.assert_effective_options(self._expected_options(spec))
        except BaseException:
            try:
                await container.rm()
            except SandboxError as cleanup_error:
                raise SandboxError("CONTAINER_CLEANUP_FAILED") from cleanup_error
            raise
        return container
