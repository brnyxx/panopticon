from __future__ import annotations

import json

import pytest

from panopticon.sandbox.base import ExecResult, SandboxError, StreamResult
from panopticon.sandbox.network import (
    CapabilityStatus,
    NetworkController,
    NetworkServices,
    plan_network,
)


def result(code: int = 0, out: bytes = b"", err: bytes = b"") -> ExecResult:
    return ExecResult(code, StreamResult(out), StreamResult(err))


def test_plan_network_unavailable_and_rootless_variants() -> None:
    assert plan_network(rootless=False, proxy_available=False).proxy is CapabilityStatus.UNSUPPORTED
    plan = plan_network(rootless=True, dns_available=False)
    assert plan.dns is CapabilityStatus.UNSUPPORTED
    assert plan.direct_drop is CapabilityStatus.PARTIAL


@pytest.mark.asyncio
async def test_network_start_builds_typed_proxy_dns_argv() -> None:
    class Fake(NetworkController):
        def __init__(self) -> None:
            super().__init__("podman")
            self.argv: list[list[str]] = []

        async def _command(self, argv: list[str]) -> ExecResult:
            self.argv.append(argv)
            if argv[:2] == ["run", "-d"]:
                return result(
                    out=(b"dns-id\n" if "dns" in argv[argv.index("--name") + 1] else b"proxy-id\n")
                )
            if argv[0] == "inspect":
                cid = argv[1]
                ip = "10.0.0.3" if cid == "dns-id" else "10.0.0.2"
                return result(
                    out=json.dumps(
                        [{"NetworkSettings": {"Networks": {"n-internal": {"IPAddress": ip}}}}]
                    ).encode()
                )
            return result()

    fake = Fake()
    session = await fake.start(NetworkServices("repo@sha256:" + "a" * 64, "n", True))
    assert session.dns_id == "dns-id" and session.proxy_ip == "10.0.0.2"
    assert [
        "network",
        "create",
        "--driver",
        "bridge",
        "--internal",
        "--disable-dns",
        "n-internal",
    ] in fake.argv


@pytest.mark.asyncio
async def test_network_start_rejects_and_cleans_on_service_failure() -> None:
    class Fake(NetworkController):
        def __init__(self) -> None:
            super().__init__("docker")
            self.argv: list[list[str]] = []

        async def _command(self, argv: list[str]) -> ExecResult:
            self.argv.append(argv)
            if argv[:2] == ["run", "-d"]:
                return result(1)
            return result()

    fake = Fake()
    with pytest.raises(SandboxError, match="NETWORK_SERVICE_START_FAILED"):
        await fake.start(NetworkServices("repo@sha256:" + "b" * 64, "ok", False))
    assert ["rm", "-f", "ok-proxy", "ok-dns"] in fake.argv


@pytest.mark.asyncio
async def test_network_stop_accepts_orphan_markers_and_rejects_real_errors() -> None:
    class Fake(NetworkController):
        def __init__(self, code: int, err: bytes) -> None:
            super().__init__("docker")
            self.code, self.err = code, err

        async def _command(self, argv: list[str]) -> ExecResult:
            return result(self.code, err=self.err)

    from panopticon.sandbox.network import NetworkSession

    session = NetworkSession("n", "e", "p", "d", "1", "2", plan_network(rootless=False))
    await Fake(1, b"no such container").stop(session)
    with pytest.raises(SandboxError, match="NETWORK_CLEANUP_FAILED"):
        await Fake(1, b"permission denied").stop(session)
