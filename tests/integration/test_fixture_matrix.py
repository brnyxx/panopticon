"""Real-process MCP fixture matrix checks."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

import pytest

JsonValue: TypeAlias = str | int | float | bool | list["JsonValue"] | dict[str, "JsonValue"] | None
JsonObject: TypeAlias = dict[str, JsonValue]
ROOT = Path(__file__).parents[1] / "fixtures" / "mcp"
EVIL = ("file_read", "host_connect", "decoy_leak", "idle_beacon", "proc_exec")


@dataclass(frozen=True, slots=True)
class SessionOutcome:
    initialized: JsonObject
    listed: JsonObject
    called: JsonObject
    ready: JsonObject | None


async def _read_message(reader: asyncio.StreamReader, timeout: float = 1.0) -> JsonObject:
    length: int | None = None
    while length is None:
        line = await asyncio.wait_for(reader.readline(), timeout)
        if not line:
            raise EOFError("fixture exited before response")
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":", 1)[1].strip())
    separator = await asyncio.wait_for(reader.readline(), timeout)
    if separator not in (b"\r\n", b"\n"):
        raise ValueError("invalid fixture frame separator")
    value = json.loads(await asyncio.wait_for(reader.readexactly(length), timeout))
    if not isinstance(value, dict):
        raise TypeError("fixture response must be an object")
    return value


def _command(kind: str, mode: str) -> list[str]:
    if kind == "python":
        return [sys.executable, str(ROOT / "python_server.py"), mode]
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node fixture runtime is required")
    return [node, str(ROOT / "node_server.mjs"), mode]


async def _session(
    kind: str,
    mode: str,
    *flags: str,
    namespace: Path,
    host: str,
    port: int,
) -> SessionOutcome:
    command = _command(kind, mode)
    command.extend(flags)
    namespace.mkdir(parents=True, exist_ok=True)
    cache = namespace / "cache"
    cache.mkdir()
    decoy = namespace / "credential.txt"
    decoy.write_text("fixture-decoy", encoding="utf-8")
    env = dict(os.environ)
    env.update(
        TMPDIR=str(namespace),
        PANO_CACHE_DIR=str(cache),
        PANO_PORT_NAMESPACE=namespace.name,
        PANO_DECOY_FILE=str(decoy),
        PANO_DECOY_VALUE="fixture-decoy-value",
        PANO_FIXTURE_HOST=host,
        PANO_FIXTURE_PORT=str(port),
    )
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        env=env,
    )
    if process.stdin is None or process.stdout is None:
        process.kill()
        await process.wait()
        raise RuntimeError("fixture pipes unavailable")
    counter = 0

    async def request(
        method: str,
        params: JsonObject | None = None,
        *,
        expect_response: bool = True,
    ) -> JsonObject:
        nonlocal counter
        counter += 1
        payload: JsonObject = {"jsonrpc": "2.0", "id": counter, "method": method}
        if params is not None:
            payload["params"] = params
        body = json.dumps(payload, separators=(",", ":")).encode()
        process.stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
        await process.stdin.drain()
        if not expect_response:
            return {}
        while True:
            message = await _read_message(process.stdout)
            if message.get("id") == counter:
                return message

    try:
        initialized = await request(
            "initialize",
            {"_meta": {"protocolVersion": "2026-07-28"}},
        )
        ready = None if "--omit-ready" in flags else await _read_message(process.stdout)
        await request("notifications/initialized", expect_response=False)
        listed = await request("tools/list")
        called = await request("tools/call", {"name": mode, "arguments": {}})
        return SessionOutcome(initialized, listed, called, ready)
    finally:
        process.stdin.close()
        await asyncio.wait_for(process.wait(), 1.0)


async def _listener() -> tuple[asyncio.AbstractServer, str, int, asyncio.Event]:
    connected = asyncio.Event()

    async def accept(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        connected.set()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(accept, "127.0.0.1", 0)
    address = server.sockets[0].getsockname()
    return server, str(address[0]), int(address[1]), connected


@pytest.mark.docker
@pytest.mark.asyncio
async def test_parallel_repeat_runs_are_semantically_identical(tmp_path: Path) -> None:
    server, host, port, _ = await _listener()
    try:
        runs = await asyncio.gather(
            *(
                _session(
                    "python",
                    "file_read",
                    "--era=modern",
                    namespace=tmp_path / f"run-{index}",
                    host=host,
                    port=port,
                )
                for index in range(2)
            )
        )
        clean = await _session(
            "node",
            "clean_file_read",
            "--era=legacy",
            namespace=tmp_path / "node",
            host=host,
            port=port,
        )
    finally:
        server.close()
        await server.wait_closed()
    semantic = [(run.listed["result"], run.called["result"]) for run in runs]
    assert semantic[0] == semantic[1]
    assert runs[0].ready and runs[0].ready["method"] == "notifications/fixture/ready"
    assert clean.initialized["result"]["protocolVersion"] == "2024-11-05"
    assert clean.listed["result"]["tools"][0]["_meta"]["panopticon"]["complete"] is True


@pytest.mark.asyncio
async def test_missing_ready_or_declaration_is_bounded_partial(tmp_path: Path) -> None:
    server, host, port, _ = await _listener()
    try:
        outcome = await _session(
            "python",
            "host_connect",
            "--omit-ready",
            "--omit-declaration",
            namespace=tmp_path / "partial",
            host=host,
            port=port,
        )
    finally:
        server.close()
        await server.wait_closed()
    assert outcome.ready is None
    assert outcome.listed["result"]["tools"] == []


@pytest.mark.docker
@pytest.mark.asyncio
async def test_each_evil_mode_exhibits_one_behavior_and_clean_modes_none(tmp_path: Path) -> None:
    server, host, port, connected = await _listener()
    try:
        evil = []
        for index, mode in enumerate(EVIL):
            evil.append(
                await _session(
                    "python",
                    mode,
                    namespace=tmp_path / f"evil-{index}",
                    host=host,
                    port=port,
                )
            )
        clean = await asyncio.gather(
            *(
                _session(
                    "node",
                    f"clean_{mode}",
                    namespace=tmp_path / f"clean-{index}",
                    host=host,
                    port=port,
                )
                for index, mode in enumerate(EVIL)
            )
        )
        await asyncio.wait_for(connected.wait(), 1.0)
    finally:
        server.close()
        await server.wait_closed()
    assert [
        json.loads(item.called["result"]["content"][0]["text"])["mode"] for item in evil
    ] == list(EVIL)
    assert all(
        json.loads(item.called["result"]["content"][0]["text"])["observed"] == "none"
        for item in clean
    )


def test_pinned_official_example_archive_matches_manifest() -> None:
    archive = ROOT / "official" / "server-everything-2026.8.18.tgz"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == (
        "bd11de97a2413c7083f7a9252be55d0d9bfbdb67b2531dbe4217a6517226d36d"
    )
    with tarfile.open(archive, mode="r:gz") as package:
        metadata = json.load(package.extractfile("package/package.json"))
    assert metadata["name"] == "@modelcontextprotocol/server-everything"
    assert metadata["version"] == "2026.8.18"
    assert (ROOT / "official" / "LICENSE").is_file()
