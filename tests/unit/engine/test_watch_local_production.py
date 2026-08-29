from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, cast

import pytest

from panopticon.discovery.base import DiscoveryEnv
from panopticon.engine.watch_inventory import ProductionWatchInventory, WatchTargetContext
from panopticon.engine.watch_local_evidence import image_reference, target_environment
from panopticon.engine.watch_local_production import LocalRuntime, run_local_production
from panopticon.engine.watch_model import TargetMode, TargetSelection, WatchOptions
from panopticon.probe.protocol import encode_message
from panopticon.sandbox.base import ContainerSpec, StreamResult
from panopticon.sandbox.decoy import generate_decoy_home
from panopticon.sandbox.image_catalog import DEFAULT_IMAGE_CATALOG


class ReactiveStream:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.closed = False

    async def read(self, size: int) -> bytes:
        return await self.queue.get()

    def write(self, data: bytes) -> None:
        payload: Any = json.loads(data)
        identifier = payload.get("id")
        method = payload["method"]
        if identifier is None:
            return
        result: Any
        if method == "initialize":
            result = {
                "protocolVersion": "2026-07-28",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fixture", "version": "1.0"},
            }
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "read_data",
                        "inputSchema": {"type": "object"},
                        "annotations": {"readOnlyHint": True},
                    }
                ]
            }
        else:
            result = {"content": []}
        message = {"jsonrpc": "2.0", "id": identifier, "result": result}
        self.queue.put_nowait(encode_message(message))

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class Session:
    def __init__(self) -> None:
        self.reader = self.writer = ReactiveStream()
        self.cleaned = 0

    async def read_stderr(self, max_bytes: int = 1_048_576) -> StreamResult:
        return StreamResult(b"PANO_CLOCK 1")

    async def wait(self, timeout: float | None = None) -> int:
        return 0

    def close_stdin(self) -> None:
        self.writer.close()

    async def terminate(self) -> None:
        return None

    async def cleanup(self) -> None:
        self.cleaned += 1


class Container:
    id = "fixture"

    def __init__(self) -> None:
        self.session = Session()

    async def open_stdio(self) -> Session:
        return self.session

    async def trace(self, max_bytes: int = 1_048_576) -> StreamResult:
        return StreamResult(
            b'10 1700000000.100 openat(AT_FDCWD</home/pano>, "/home/pano/file", '
            b"O_RDONLY) = 3</home/pano/file>"
        )

    async def stop(self) -> None:
        return None

    async def rm(self) -> None:
        return None


class FakeRuntime:
    name = "docker"
    executable = "docker"

    def __init__(self) -> None:
        self.pulls: list[str] = []
        self.specs: list[ContainerSpec] = []
        self.container = Container()

    def available(self) -> bool:
        return True

    async def pull(self, image_ref: str) -> None:
        self.pulls.append(image_ref)

    async def run(self, spec: ContainerSpec) -> Container:
        self.specs.append(spec)
        return self.container


def _context(tmp_path: Path) -> WatchTargetContext:
    inventory = ProductionWatchInventory(
        DiscoveryEnv(tmp_path, tmp_path, "darwin"),
        self_command=("python3", "server.py"),
    )
    return inventory.select(TargetSelection(TargetMode.SELF)).contexts[0]


@pytest.mark.asyncio
async def test_offline_local_watch_calls_real_transport_without_pull(tmp_path: Path) -> None:
    runtime = FakeRuntime()

    result = await run_local_production(
        _context(tmp_path),
        WatchOptions(offline=True),
        runtime=cast(LocalRuntime, runtime),
    )

    assert result.status.value == "COMPLETE"
    assert result.protocol is not None and result.protocol.server_name == "fixture"
    assert result.calls is not None and result.calls.reason_code == "OK"
    assert [span.tool for span in result.spans] == ["session", "startup", "read_data"]
    assert result.trace is not None and result.trace.events
    assert runtime.pulls == []
    assert runtime.container.session.cleaned == 1
    assert runtime.specs[0].network == "pano-net"


@pytest.mark.asyncio
async def test_local_watch_regenerates_decoys_per_run(tmp_path: Path) -> None:
    first = FakeRuntime()
    second = FakeRuntime()

    await run_local_production(
        _context(tmp_path),
        WatchOptions(offline=True),
        runtime=cast(LocalRuntime, first),
        run_identity="run-one",
    )
    await run_local_production(
        _context(tmp_path),
        WatchOptions(offline=True),
        runtime=cast(LocalRuntime, second),
        run_identity="run-two",
    )

    assert first.specs[0].decoy_archive != second.specs[0].decoy_archive


def test_image_and_environment_selection_do_not_expose_real_values(tmp_path: Path) -> None:
    original = _context(tmp_path)
    context = WatchTargetContext(
        original.target.model_copy(update={"env_keys": ("GITHUB_TOKEN",)}),
        original.raw_entry,
    )
    manifest = generate_decoy_home("seed")

    decoyed = target_environment(
        context, manifest.env, WatchOptions(), {"GITHUB_TOKEN": "real-value"}
    )
    authorized = target_environment(
        context,
        manifest.env,
        WatchOptions(real_env=("GITHUB_TOKEN",)),
        {"GITHUB_TOKEN": "real-value"},
    )

    assert image_reference(context, DEFAULT_IMAGE_CATALOG, None) is not None
    assert decoyed["GITHUB_TOKEN"] != "real-value"
    assert authorized["GITHUB_TOKEN"] == "real-value"
    assert "real-value" not in repr(context)
