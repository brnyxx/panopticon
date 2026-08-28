import pytest

from panopticon.sandbox.base import SandboxError
from panopticon.sandbox.runtime import select_runtime


def test_forced_runtime_rejects_unknown() -> None:
    with pytest.raises(SandboxError, match="RUNTIME_UNSUPPORTED"):
        select_runtime("runc")


def test_auto_detection_prefers_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("panopticon.sandbox.runtime.DockerRuntime.available", lambda self: True)
    monkeypatch.setattr("panopticon.sandbox.runtime.PodmanRuntime.available", lambda self: True)
    assert select_runtime().name == "docker"
