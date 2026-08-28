"""Podman runtime, reusing Docker's vector implementation."""

from __future__ import annotations

import asyncio
import io
import tarfile
from collections.abc import Mapping
from pathlib import PurePosixPath

from .base import ContainerSpec, SandboxError
from .docker import DockerContainer, DockerRuntime
from .streams import communicate


class PodmanContainer(DockerContainer):
    async def copy_archive_in(self, payload: bytes, destination: str) -> None:
        target = PurePosixPath(destination)
        if not target.is_absolute() or ".." in target.parts:
            raise SandboxError("COPY_DESTINATION_INVALID")
        if not payload or len(payload) > 32 * 1024 * 1024:
            raise SandboxError("DECOY_ARCHIVE_INVALID")
        try:
            with tarfile.open(fileobj=io.BytesIO(payload), mode="r:*") as archive:
                if not archive.getmembers():
                    return
        except tarfile.TarError as error:
            raise SandboxError("DECOY_ARCHIVE_INVALID") from error
        process = await asyncio.create_subprocess_exec(
            self.runtime,
            "cp",
            "-",
            f"{self.id}:{destination}",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        result = await communicate(process, payload, 1_048_576)
        if result.returncode:
            raise SandboxError("COPY_IN_FAILED")


class PodmanRuntime(DockerRuntime):
    name = "podman"

    def __init__(self, executable: str | None = None) -> None:
        super().__init__(executable or "podman")

    def _container(self, container_id: str) -> DockerContainer:
        return PodmanContainer(self.executable, container_id)

    def _expected_options(self, spec: ContainerSpec) -> Mapping[str, object]:
        return {
            "ReadonlyRootfs": True,
            "PidsLimit": spec.pids_limit,
            "CapDrop": ["ALL"],
            "CapAdd": ["SYS_PTRACE"],
        }
