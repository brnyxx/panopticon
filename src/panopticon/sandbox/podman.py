"""Podman runtime, reusing Docker's vector implementation."""

from __future__ import annotations

from collections.abc import Mapping

from .base import ContainerSpec
from .docker import DockerContainer, DockerRuntime


class PodmanRuntime(DockerRuntime):
    name = "podman"

    def __init__(self, executable: str | None = None) -> None:
        super().__init__(executable or "podman")

    def _container(self, container_id: str) -> DockerContainer:
        return DockerContainer(self.executable, container_id)

    def _expected_options(self, spec: ContainerSpec) -> Mapping[str, object]:
        return {
            "ReadonlyRootfs": True,
            "PidsLimit": spec.pids_limit,
            "CapDrop": ["ALL"],
            "CapAdd": ["SYS_PTRACE"],
        }
