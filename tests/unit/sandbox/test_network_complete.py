from __future__ import annotations

import json

import pytest

from panopticon.sandbox.base import ExecResult, SandboxError, StreamResult
from panopticon.sandbox.netlog import NetworkLogReason, NetworkLogStatus
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


@pytest.mark.asyncio
async def test_collect_logs_parses_timestamped_stdout_and_stderr_as_complete() -> None:
    class Fake(NetworkController):
        def __init__(self) -> None:
            super().__init__("docker")
            self.argv: list[list[str]] = []

        async def _command(self, argv: list[str]) -> ExecResult:
            self.argv.append(argv)
            if argv[-1] == "dns-id":
                return result(
                    out=b"2026-01-02T03:04:05Z query[A] example.test from 10.0.0.1\n",
                    err=b"2026-01-02T03:04:06Z query[AAAA] example.test from 10.0.0.1\n",
                )
            return result(
                out=b"2026-01-02T03:04:07+00:00 CONNECT proxy.test:443\n",
                err=b"2026-01-02T03:04:08Z Established connection to host other.test:80\n",
            )

    from panopticon.sandbox.network import NetworkSession

    fake = Fake()
    logs = await fake.collect_logs(
        NetworkSession("n", "e", "proxy-id", "dns-id", "1", "2", plan_network(rootless=False))
    )
    assert all(call[:4] == ["logs", "--timestamps", "--tail", "10000"] for call in fake.argv)
    assert logs.dns.status is NetworkLogStatus.COMPLETE
    assert logs.dns.reason_code is NetworkLogReason.COMPLETED
    assert logs.dns.events[0].timestamp is not None
    assert logs.proxy.status is NetworkLogStatus.COMPLETE
    assert {event.host for event in logs.proxy.events} == {"proxy.test", "other.test"}
    assert logs.blocked_egress.status is NetworkLogStatus.COMPLETE
    assert logs.blocked_egress.reason_code is NetworkLogReason.COMPLETED


@pytest.mark.asyncio
async def test_collect_logs_empty_nonzero_and_malformed_outputs_are_failed_or_partial() -> None:
    class Fake(NetworkController):
        def __init__(self, responses: dict[str, ExecResult]) -> None:
            super().__init__("docker")
            self.responses = responses

        async def _command(self, argv: list[str]) -> ExecResult:
            return self.responses[argv[-1]]

    from panopticon.sandbox.network import NetworkSession

    session = NetworkSession("n", "e", "proxy-id", "dns-id", "1", "2", plan_network(rootless=False))
    logs = await Fake(
        {
            "dns-id": result(
                out=b"2026-01-02T03:04:05Z query[A] valid.test from 10.0.0.1\nnot a dns log\n"
            ),
            "proxy-id": result(3, err=b"container stopped"),
        }
    ).collect_logs(session)
    assert logs.dns.status is NetworkLogStatus.PARTIAL
    assert logs.dns.reason_code is NetworkLogReason.MALFORMED_LINE
    assert logs.dns.diagnostics == (NetworkLogReason.MALFORMED_LINE.value,)
    assert logs.proxy.status is NetworkLogStatus.FAILED
    assert logs.proxy.diagnostics == ("LOG_UNAVAILABLE",)

    empty = await Fake({"dns-id": result(), "proxy-id": result()}).collect_logs(session)
    assert empty.dns.status is NetworkLogStatus.FAILED
    assert empty.proxy.status is NetworkLogStatus.FAILED
    assert empty.dns.diagnostics == empty.proxy.diagnostics == ("LOG_UNAVAILABLE",)


@pytest.mark.asyncio
async def test_network_start_connect_error_cleans_all_resources_and_rejects_bad_inputs() -> None:
    class Fake(NetworkController):
        def __init__(self) -> None:
            super().__init__("docker")
            self.argv: list[list[str]] = []

        async def _command(self, argv: list[str]) -> ExecResult:
            self.argv.append(argv)
            if argv[:2] == ["run", "-d"]:
                return result(out=(b"dns-id\n" if "dns" in argv else b"proxy-id\n"))
            if argv[:2] == ["network", "connect"]:
                return result(1)
            if argv[:2] == ["network", "create"] and argv[-1].endswith("-internal"):
                return result()
            if argv[0] == "inspect":
                return result(
                    out=b'[{"NetworkSettings":{"Networks":{"n-internal":{"IPAddress":"10.0.0.2"}}}}]'
                )
            return result()

    fake = Fake()
    with pytest.raises(SandboxError, match="NETWORK_CONNECT_FAILED"):
        await fake.start(NetworkServices("repo@sha256:" + "c" * 64, "n", False))
    assert ["rm", "-f", "n-proxy", "n-dns"] in fake.argv
    assert ["network", "rm", "n-internal", "n-egress"] in fake.argv

    with pytest.raises(SandboxError, match="IMAGE_NOT_PINNED"):
        await fake.start(NetworkServices("latest", "n", False))
    with pytest.raises(SandboxError, match="INVALID_NETWORK_NAME"):
        await fake.start(NetworkServices("repo@sha256:" + "d" * 64, "Bad_Name", False))
