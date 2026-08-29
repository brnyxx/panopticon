"""Execute every tool on the five commit-pinned official MCP implementations."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

from panopticon.probe.argument_schema import JsonValue
from panopticon.probe.client import McpClient
from panopticon.probe.driver import CallDriver, DriverStatus
from panopticon.probe.protocol import ProbeStatus

REPOSITORY = "https://github.com/modelcontextprotocol/servers.git"
CURRENT_COMMIT = "cda92bdaacd558192fedf1a60d2bb27510792388"
ARCHIVE_COMMIT = "1f705677a930ec618b7a16d87d00cee7db747ff2"


@dataclass(frozen=True, slots=True)
class ServerCase:
    name: str
    commit: str
    argv: tuple[str, ...]
    cwd: Path
    environment: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class ServerReceipt:
    name: str
    commit: str
    tool_count: int
    complete_calls: int
    status: str


async def command(argv: tuple[str, ...], cwd: Path) -> None:
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env={**os.environ, "PUPPETEER_SKIP_DOWNLOAD": "true"},
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode:
        detail = stderr.decode(errors="replace")[-1000:]
        raise RuntimeError(f"command failed ({process.returncode}): {argv[0]}: {detail}")


async def acquire(root: Path) -> tuple[Path, Path]:
    current = root / "current"
    archive = root / "archive"
    for path, commit in ((current, CURRENT_COMMIT), (archive, ARCHIVE_COMMIT)):
        await command(
            ("git", "clone", "--filter=blob:none", "--no-checkout", REPOSITORY, str(path)),
            root,
        )
        await command(("git", "checkout", "--detach", commit), path)
    await command(("npm", "ci"), current)
    await command(
        ("npm", "run", "build", "--workspace=@modelcontextprotocol/server-filesystem"),
        current,
    )
    await command(
        ("npm", "run", "build", "--workspace=@modelcontextprotocol/server-memory"),
        current,
    )
    await command(("npm", "ci"), archive)
    await command(
        ("npm", "run", "build", "--workspace=@modelcontextprotocol/server-github"),
        archive,
    )
    await command(("uv", "sync"), current / "src" / "fetch")
    await command(("uv", "sync"), archive / "src" / "sqlite")
    return current, archive


async def execute(case: ServerCase, home: Path) -> ServerReceipt:
    environment = {
        "HOME": str(home),
        "PATH": os.environ["PATH"],
        **dict(case.environment),
    }
    process = await asyncio.create_subprocess_exec(
        *case.argv,
        cwd=case.cwd,
        env=environment,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    if process.stdin is None or process.stdout is None:
        raise RuntimeError(f"{case.name}: stdio unavailable")
    client = McpClient(process.stdout, process.stdin, timeout=15)
    try:
        initialized = await client.initialize()
        if initialized.status is not ProbeStatus.COMPLETE:
            raise RuntimeError(f"{case.name}: initialize {initialized.reason_code}")
        listed = await client.list_paginated("tools/list", timeout=15)
        if listed.status is not ProbeStatus.COMPLETE or not isinstance(listed.result, dict):
            raise RuntimeError(f"{case.name}: tools/list {listed.reason_code}")
        raw_tools = listed.result.get("tools")
        if not isinstance(raw_tools, list):
            raise RuntimeError(f"{case.name}: tools/list malformed")
        tools = cast(list[dict[str, JsonValue]], raw_tools)
        driven = await CallDriver(
            client,
            calls=1,
            allow_destructive=True,
            stage_timeout=15,
            total_timeout=300,
        ).run(tools)
        complete = sum(
            call.response is not None and call.response.status is ProbeStatus.COMPLETE
            for call in driven.calls
        )
        if driven.status is not DriverStatus.COMPLETE or complete != len(tools):
            failures = [
                f"{call.tool}:{call.reason_code}"
                for call in driven.calls
                if call.response is None or call.response.status is not ProbeStatus.COMPLETE
            ]
            raise RuntimeError(f"{case.name}: incomplete calls: {failures}")
        return ServerReceipt(case.name, case.commit, len(tools), complete, driven.status.value)
    finally:
        await client.close()
        if process.returncode is None:
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 5)
        except TimeoutError:
            process.kill()
            await process.wait()


async def main() -> int:
    repository_root = Path(__file__).resolve().parents[1]
    mock = repository_root / "tests" / "fixtures" / "mcp" / "official" / "github_fetch_mock.mjs"
    with tempfile.TemporaryDirectory(prefix="pano-official-") as temporary:
        root = Path(temporary)
        current, archive = await acquire(root)
        home = root / "home"
        allowed = root / "filesystem"
        home.mkdir()
        allowed.mkdir()
        node = shutil.which("node")
        if node is None:
            raise RuntimeError("node is unavailable")
        cases = (
            ServerCase(
                "filesystem",
                CURRENT_COMMIT,
                (node, str(current / "src/filesystem/dist/index.js"), str(allowed)),
                current,
            ),
            ServerCase(
                "memory",
                CURRENT_COMMIT,
                (node, str(current / "src/memory/dist/index.js")),
                current,
            ),
            ServerCase(
                "github",
                ARCHIVE_COMMIT,
                (node, str(archive / "src/github/dist/index.js")),
                archive,
                (
                    ("GITHUB_PERSONAL_ACCESS_TOKEN", "synthetic-token"),
                    ("NODE_OPTIONS", f"--import={mock}"),
                ),
            ),
            ServerCase(
                "fetch",
                CURRENT_COMMIT,
                (str(current / "src/fetch/.venv/bin/mcp-server-fetch"),),
                current / "src/fetch",
            ),
            ServerCase(
                "sqlite",
                ARCHIVE_COMMIT,
                (
                    str(archive / "src/sqlite/.venv/bin/mcp-server-sqlite"),
                    "--db-path",
                    str(root / "official.sqlite"),
                ),
                archive / "src/sqlite",
            ),
        )
        receipts = [asdict(await execute(case, home)) for case in cases]
    payload = {
        "schema": "panopticon.official-examples.v1",
        "mock_sha256": hashlib.sha256(mock.read_bytes()).hexdigest(),
        "servers": receipts,
        "status": "PASS",
    }
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
