"""Docker runtime implementation using argument vectors only."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from .archive import archive_for_copy
from .base import Container, ContainerSpec, ExecResult, SandboxError, StreamResult
from .streams import communicate

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_CONTAINER_TMP = PurePosixPath("/").joinpath("tmp")
_CONTAINER_TRACE = _CONTAINER_TMP / "pano.strace"


def is_pinned_image(image: str) -> bool:
    return "@sha256:" in image and _DIGEST.fullmatch(image.rsplit("@", 1)[1]) is not None


class DockerContainer:
    def __init__(self, runtime: str, container_id: str) -> None:
        self.runtime, self.id = runtime, container_id
        self._cleaned = False
        self._terminated = False

    async def _command(self, argv: list[str], timeout: float = 30.0) -> ExecResult:
        process = await asyncio.create_subprocess_exec(
            self.runtime, *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            return await asyncio.wait_for(communicate(process, None, 1_048_576), timeout)
        except TimeoutError as exc:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise SandboxError("RUNTIME_TIMEOUT") from exc
        except asyncio.CancelledError:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise

    async def exec(self, argv: list[str], timeout: float, stdin: bytes | None = None) -> ExecResult:
        if not argv or any("\x00" in part for part in argv):
            raise SandboxError("INVALID_EXEC_ARGV")
        process = await asyncio.create_subprocess_exec(
            self.runtime,
            "exec",
            "-i",
            self.id,
            *argv,
            stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            return await asyncio.wait_for(communicate(process, stdin, 1_048_576), timeout)
        except TimeoutError as exc:
            if process.returncode is None:
                process.kill()
                await process.wait()
            await self.kill()
            raise SandboxError("EXEC_TIMEOUT") from exc
        except asyncio.CancelledError:
            if process.returncode is None:
                process.kill()
                await process.wait()
            await self.kill()
            raise

    async def logs(self, max_bytes: int = 1_048_576) -> StreamResult:
        result = await self._command(["logs", self.id])
        combined = result.stdout.data + result.stderr.data
        return StreamResult(
            combined[:max_bytes],
            result.stdout.truncated or result.stderr.truncated or len(combined) > max_bytes,
        )

    async def copy_in(self, source: Path, destination: str) -> None:
        target = PurePosixPath(destination)
        if not target.is_absolute() or ".." in target.parts:
            raise SandboxError("COPY_DESTINATION_INVALID")
        result = await self.exec(
            ["tar", "-xf", "-", "-C", destination],
            30,
            archive_for_copy(source),
        )
        if result.returncode:
            raise SandboxError("COPY_IN_FAILED")

    async def copy_out(self, source: str, destination: Path) -> None:
        result = await self._command(["cp", f"{self.id}:{source}", str(destination)])
        if result.returncode:
            raise SandboxError("COPY_OUT_FAILED")

    async def inspect(self) -> dict[str, object]:
        result = await self._command(["inspect", self.id])
        if result.returncode:
            raise SandboxError("INSPECT_FAILED")
        try:
            payload: object = json.loads(result.stdout.data)
            candidate: object = payload[0] if isinstance(payload, list) and payload else payload
            if not isinstance(candidate, dict):
                raise SandboxError("INSPECT_INVALID")
            return {key: value for key, value in candidate.items() if isinstance(key, str)}
        except (ValueError, TypeError, IndexError) as exc:
            raise SandboxError("INSPECT_INVALID") from exc

    async def assert_effective_options(self, expected: Mapping[str, object]) -> None:
        """Fail closed when the daemon did not apply requested isolation options."""
        actual = await self.inspect()
        config = actual.get("HostConfig", actual)
        if not isinstance(config, dict):
            raise SandboxError("INSPECT_MISMATCH")
        mismatches: list[str] = []
        for key, value in expected.items():
            actual_value = config.get(key)
            if key in {"CapAdd", "CapDrop"} and isinstance(actual_value, list):
                actual_value = [
                    item.removeprefix("CAP_") if isinstance(item, str) else item
                    for item in actual_value
                ]
                if key == "CapDrop" and value == ["ALL"] and len(actual_value) >= 10:
                    actual_value = ["ALL"]
            if actual_value != value:
                mismatches.append(key)
        if mismatches:
            raise SandboxError("INSPECT_MISMATCH:" + ",".join(sorted(mismatches)))

    async def trace(self, max_bytes: int = 1_048_576) -> StreamResult:
        result = await self.exec(["cat", str(_CONTAINER_TRACE)], 10)
        return StreamResult(
            result.stdout.data[:max_bytes],
            result.stdout.truncated or len(result.stdout.data) > max_bytes,
        )

    async def wait(self, timeout: float | None = None) -> int:
        result = await self._command(["wait", self.id], 30.0 if timeout is None else timeout)
        if result.returncode:
            raise SandboxError("WAIT_FAILED")
        try:
            return int(result.stdout.data.decode().strip())
        except ValueError as exc:
            raise SandboxError("WAIT_INVALID") from exc

    async def terminate(self, timeout: float = 5.0) -> None:
        if self._cleaned or self._terminated:
            return
        result = await self._command(
            ["stop", "-t", str(max(0, int(timeout))), self.id], timeout + 5
        )
        if result.returncode and b"no such container" not in result.stderr.data.lower():
            raise SandboxError("STOP_FAILED")
        self._terminated = True

    async def kill(self) -> None:
        if self._cleaned:
            return
        result = await self._command(["kill", self.id])
        if result.returncode and b"no such container" not in result.stderr.data.lower():
            raise SandboxError("KILL_FAILED")

    async def stop(self) -> None:
        await self.terminate()

    async def rm(self) -> None:
        if self._cleaned:
            return
        result = await self._command(["rm", "-f", self.id])
        self._cleaned = True
        if result.returncode and b"no such container" not in result.stderr.data.lower():
            raise SandboxError("RM_FAILED")


class DockerRuntime:
    name = "docker"

    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or shutil.which("docker") or "docker"

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    async def _command(self, argv: list[str]) -> ExecResult:
        process = await asyncio.create_subprocess_exec(
            self.executable,
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
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
        if not is_pinned_image(image_ref):
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
        if not is_pinned_image(spec.image):
            raise SandboxError("IMAGE_NOT_PINNED")
        if not spec.decoy_home.is_dir():
            raise SandboxError("DECOY_HOME_INVALID")
        if spec.self_source is not None and not spec.self_source.is_absolute():
            raise SandboxError("SELF_SOURCE_MUST_BE_ABSOLUTE")
        if not spec.read_only or spec.cap_add != ("SYS_PTRACE",):
            raise SandboxError("UNSUPPORTED_ISOLATION_OPTIONS")
        await self._ensure_network(spec.network)
        args = [
            "run",
            "-d",
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
            if key in protected_env:
                continue
            args += ["-e", f"{key}={value}"]
        # The only home visible to the process is the decoy tmpfs.
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
            await container.copy_in(spec.decoy_home, "/home/pano")
            await container.assert_effective_options(self._expected_options(spec))
        except BaseException:
            try:
                await container.rm()
            except SandboxError as cleanup_error:
                raise SandboxError("CONTAINER_CLEANUP_FAILED") from cleanup_error
            raise
        return container
