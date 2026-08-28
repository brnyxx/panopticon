"""Docker container command and lifecycle helpers."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from .archive import archive_for_copy
from .base import ExecResult, InteractiveSession, SandboxError, StreamResult
from .streams import communicate

_CONTAINER_TMP = PurePosixPath("/").joinpath("tmp")
_CONTAINER_TRACE = _CONTAINER_TMP / "pano.strace"


class _InteractiveSession:
    def __init__(
        self,
        container: DockerContainer,
        process: asyncio.subprocess.Process,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        stderr: asyncio.StreamReader,
    ) -> None:
        self._container = container
        self._process = process
        self.reader = reader
        self.writer = writer
        self._stderr = stderr
        self._cleaned = False

    async def read_stderr(self, max_bytes: int = 1_048_576) -> StreamResult:
        if max_bytes < 0:
            raise ValueError("max_bytes must be non-negative")
        data = await self._stderr.read(max_bytes + 1)
        return StreamResult(data[:max_bytes], len(data) > max_bytes)

    async def wait(self, timeout: float | None = None) -> int:
        result = self._process.wait()
        return await asyncio.wait_for(result, timeout) if timeout is not None else await result

    def close_stdin(self) -> None:
        if self.writer is not None:
            self.writer.close()

    async def terminate(self) -> None:
        if self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), 5.0)
            except TimeoutError:
                self._process.kill()
                await self._process.wait()

    async def cleanup(self) -> None:
        if self._cleaned:
            return
        self._cleaned = True
        cleanup = asyncio.create_task(self._cleanup_impl())
        await asyncio.shield(cleanup)

    async def _cleanup_impl(self) -> None:
        try:
            await self.terminate()
        finally:
            try:
                await self._container.terminate()
            finally:
                await self._container.rm()


class DockerContainer:
    def __init__(self, runtime: str, container_id: str) -> None:
        self.runtime, self.id = runtime, container_id
        self._cleaned = False
        self._terminated = False

    async def open_stdio(self) -> InteractiveSession:
        try:
            process = await asyncio.create_subprocess_exec(
                self.runtime,
                "attach",
                self.id,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except BaseException:
            try:
                await self.terminate()
            finally:
                await self.rm()
            raise
        if process.returncode is not None and process.returncode != 0:
            streams = (process.stdout, process.stdin, process.stderr)
            if any(stream is None for stream in streams):
                await self.terminate()
                await self.rm()
                raise SandboxError("ATTACH_STREAM_UNAVAILABLE")
            reader, writer, stderr = streams
            assert reader is not None and writer is not None and stderr is not None
            session = _InteractiveSession(self, process, reader, writer, stderr)
            await session.cleanup()
            raise SandboxError("ATTACH_FAILED")
        reader, writer, stderr = process.stdout, process.stdin, process.stderr
        if reader is None or writer is None or stderr is None:
            await self.terminate()
            await self.rm()
            raise SandboxError("ATTACH_STREAM_UNAVAILABLE")
        session = _InteractiveSession(self, process, reader, writer, stderr)
        try:
            return session
        except BaseException:
            await session.cleanup()
            raise

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
            ["tar", "--no-same-owner", "-xf", "-", "-C", destination],
            30,
            archive_for_copy(source),
        )
        if result.returncode:
            raise SandboxError("COPY_IN_FAILED")

    async def copy_archive_in(self, payload: bytes, destination: str) -> None:
        target = PurePosixPath(destination)
        if not target.is_absolute() or ".." in target.parts:
            raise SandboxError("COPY_DESTINATION_INVALID")
        if not payload or len(payload) > 32 * 1024 * 1024:
            raise SandboxError("DECOY_ARCHIVE_INVALID")
        result = await self.exec(
            ["tar", "--no-same-owner", "-xf", "-", "-C", destination],
            30,
            payload,
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
