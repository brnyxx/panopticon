"""Runtime selection with deterministic docker-first auto detection."""

from __future__ import annotations

from .base import Runtime, SandboxError
from .docker import DockerRuntime
from .podman import PodmanRuntime


def select_runtime(requested: str | None = None) -> Runtime:
    if requested is not None:
        if requested == "docker":
            runtime: Runtime = DockerRuntime()
        elif requested == "podman":
            runtime = PodmanRuntime()
        else:
            raise SandboxError("RUNTIME_UNSUPPORTED:" + requested)
        if not runtime.available():
            raise SandboxError("RUNTIME_UNAVAILABLE:" + requested)
        return runtime
    for runtime in (DockerRuntime(), PodmanRuntime()):
        if runtime.available():
            return runtime
    raise SandboxError("RUNTIME_UNAVAILABLE:docker,podman")
