"""Isolated proxy and DNS network orchestration."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, replace
from enum import StrEnum

from panopticon.sandbox.base import ContainerSpec, ExecResult, SandboxError
from panopticon.sandbox.docker import is_pinned_image
from panopticon.sandbox.streams import communicate


class CapabilityStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class NetworkPlan:
    network: str
    proxy: CapabilityStatus
    dns: CapabilityStatus
    direct_drop: CapabilityStatus
    reason: str = ""


@dataclass(frozen=True, slots=True)
class NetworkServices:
    image: str
    name: str
    rootless: bool


@dataclass(frozen=True, slots=True)
class NetworkSession:
    network: str
    egress_network: str
    proxy_id: str
    dns_id: str
    proxy_ip: str
    dns_ip: str
    plan: NetworkPlan

    def apply(self, spec: ContainerSpec) -> ContainerSpec:
        return replace(
            spec,
            network=self.network,
            dns=self.dns_ip,
            proxy_url=f"http://{self.proxy_ip}:8888",
        )


@dataclass(frozen=True, slots=True)
class _Service:
    name: str
    network: str
    image: str
    entrypoint: str
    command: tuple[str, ...]
    user: str | None = None
    cap_add: tuple[str, ...] = ()


def plan_network(
    *,
    rootless: bool,
    proxy_available: bool = True,
    dns_available: bool = True,
) -> NetworkPlan:
    if rootless:
        return NetworkPlan(
            "pano-net",
            CapabilityStatus.PARTIAL if proxy_available else CapabilityStatus.UNSUPPORTED,
            CapabilityStatus.PARTIAL if dns_available else CapabilityStatus.UNSUPPORTED,
            CapabilityStatus.PARTIAL,
            "ROOTLESS_ATTRIBUTION_PARTIAL",
        )
    return NetworkPlan(
        "pano-net",
        CapabilityStatus.COMPLETE if proxy_available else CapabilityStatus.UNSUPPORTED,
        CapabilityStatus.COMPLETE if dns_available else CapabilityStatus.UNSUPPORTED,
        CapabilityStatus.COMPLETE,
        "",
    )


class NetworkController:
    """Create one internal network plus proxy and DNS egress services."""

    def __init__(self, executable: str) -> None:
        self._executable = executable

    async def _command(self, argv: list[str]) -> ExecResult:
        process = await asyncio.create_subprocess_exec(
            self._executable,
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        return await communicate(process, None, 1_048_576)

    async def _create_network(self, name: str, *, internal: bool) -> None:
        args = ["network", "create", "--driver", "bridge"]
        if internal:
            args.append("--internal")
            if self._executable == "podman":
                args.append("--disable-dns")
        args.append(name)
        if (await self._command(args)).returncode:
            raise SandboxError("NETWORK_CREATE_FAILED")

    async def _run_service(self, service: _Service) -> str:
        args = [
            "run",
            "-d",
            "--rm",
            "--name",
            service.name,
            "--network",
            service.network,
            "--entrypoint",
            service.entrypoint,
        ]
        if service.user is not None:
            args += ["--user", service.user]
        for capability in service.cap_add:
            args += ["--cap-add", capability]
        args += [service.image, *service.command]
        result = await self._command(args)
        if result.returncode:
            raise SandboxError("NETWORK_SERVICE_START_FAILED")
        container_id = result.stdout.data.decode().strip()
        if not container_id:
            raise SandboxError("NETWORK_SERVICE_ID_MISSING")
        return container_id

    async def _connect(self, network: str, container_id: str) -> None:
        if (await self._command(["network", "connect", network, container_id])).returncode:
            raise SandboxError("NETWORK_CONNECT_FAILED")

    async def _network_ip(self, container_id: str, network: str) -> str:
        inspected = await self._command(["inspect", container_id])
        if inspected.returncode:
            raise SandboxError("NETWORK_INSPECT_FAILED")
        try:
            payload: object = json.loads(inspected.stdout.data)
        except json.JSONDecodeError as error:
            raise SandboxError("NETWORK_INSPECT_INVALID") from error
        candidate: object = payload[0] if isinstance(payload, list) and payload else None
        if not isinstance(candidate, dict):
            raise SandboxError("NETWORK_INSPECT_INVALID")
        settings = candidate.get("NetworkSettings")
        if not isinstance(settings, dict):
            raise SandboxError("NETWORK_INSPECT_INVALID")
        networks = settings.get("Networks")
        if not isinstance(networks, dict):
            raise SandboxError("NETWORK_INSPECT_INVALID")
        details = networks.get(network)
        if not isinstance(details, dict):
            raise SandboxError("NETWORK_INSPECT_INVALID")
        address = details.get("IPAddress")
        if not isinstance(address, str) or not address:
            raise SandboxError("NETWORK_INSPECT_INVALID")
        return address

    async def start(self, services: NetworkServices) -> NetworkSession:
        if not is_pinned_image(services.image):
            raise SandboxError("IMAGE_NOT_PINNED")
        if re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,47}", services.name) is None:
            raise SandboxError("INVALID_NETWORK_NAME")
        internal = f"{services.name}-internal"
        egress = f"{services.name}-egress"
        dns_name = f"{services.name}-dns"
        proxy_name = f"{services.name}-proxy"
        await self._create_network(egress, internal=False)
        try:
            await self._create_network(internal, internal=True)
            dns_id = await self._run_service(
                _Service(
                    name=dns_name,
                    network=internal,
                    image=services.image,
                    entrypoint="/usr/sbin/dnsmasq",
                    command=(
                        "--keep-in-foreground",
                        "--log-queries",
                        "--log-facility=-",
                        "--no-resolv",
                        "--server=1.1.1.1",
                    ),
                    user="0:0",
                    cap_add=("NET_BIND_SERVICE",),
                )
            )
            proxy_id = await self._run_service(
                _Service(
                    name=proxy_name,
                    network=internal,
                    image=services.image,
                    entrypoint="/usr/bin/tinyproxy",
                    command=("-d", "-c", "/etc/tinyproxy/pano.conf"),
                )
            )
            await self._connect(egress, dns_id)
            await self._connect(egress, proxy_id)
            return NetworkSession(
                network=internal,
                egress_network=egress,
                proxy_id=proxy_id,
                dns_id=dns_id,
                proxy_ip=await self._network_ip(proxy_id, internal),
                dns_ip=await self._network_ip(dns_id, internal),
                plan=replace(plan_network(rootless=services.rootless), network=internal),
            )
        except SandboxError:
            await self._command(["rm", "-f", proxy_name, dns_name])
            await self._command(["network", "rm", internal, egress])
            raise

    async def stop(self, session: NetworkSession) -> None:
        containers = await self._command(["rm", "-f", session.proxy_id, session.dns_id])
        networks = await self._command(["network", "rm", session.network, session.egress_network])
        missing_markers = (b"no such", b"not found", b"unable to find")
        container_missing = any(
            marker in containers.stderr.data.lower() for marker in missing_markers
        )
        network_missing = any(marker in networks.stderr.data.lower() for marker in missing_markers)
        if (containers.returncode and not container_missing) or (
            networks.returncode and not network_missing
        ):
            raise SandboxError("NETWORK_CLEANUP_FAILED")
