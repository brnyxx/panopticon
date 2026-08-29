"""Local, vendored official-example-compatible MCP servers.

This fixture intentionally never accesses public services.  It provides the five
example tool surfaces used by the probe acceptance tests plus protocol failure
modes for deterministic reason-code checks.
"""

from __future__ import annotations

import json
import sys
from typing import Any

MODERN = "2026-07-28"
LEGACY = "2024-11-05"


def _tools(mode: str) -> list[dict[str, Any]]:
    if mode in {"no-response", "crash", "mismatch"}:
        mode = "filesystem"
    common: dict[str, list[dict[str, Any]]] = {
        "filesystem": [
            {
                "name": "read_file",
                "description": "Read a file",
                "inputSchema": {
                    "type": "object",
                    "required": ["path"],
                    "properties": {"path": {"type": "string"}},
                },
            }
        ],
        "github": [
            {
                "name": "search_repositories",
                "inputSchema": {
                    "type": "object",
                    "required": ["query"],
                    "properties": {"query": {"type": "string"}},
                },
            }
        ],
        "fetch": [
            {
                "name": "fetch",
                "inputSchema": {
                    "type": "object",
                    "required": ["url"],
                    "properties": {"url": {"type": "string", "format": "uri"}},
                },
            }
        ],
        "memory": [
            {
                "name": "store",
                "inputSchema": {
                    "type": "object",
                    "required": ["key", "value"],
                    "properties": {"key": {"type": "string"}, "value": {"type": "string"}},
                },
            }
        ],
        "sqlite": [
            {
                "name": "query",
                "inputSchema": {
                    "type": "object",
                    "required": ["sql"],
                    "properties": {"sql": {"type": "string"}},
                },
            }
        ],
    }
    return common.get(mode, [])


def _send(message: dict[str, Any]) -> None:
    body = json.dumps(message, separators=(",", ":")).encode()
    sys.stdout.buffer.write(b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
    sys.stdout.buffer.flush()


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "filesystem"
    while True:
        header = sys.stdin.buffer.readline()
        if not header:
            return
        if header.lower().startswith(b"content-length:"):
            length = int(header.split(b":", 1)[1])
            if sys.stdin.buffer.readline() != b"\r\n":
                return
            request = json.loads(sys.stdin.buffer.read(length))
        else:
            request = json.loads(header)
        if "id" not in request:
            continue
        identifier = request["id"]
        method = request.get("method")
        params = request.get("params") or {}
        if mode == "crash":
            return
        if mode == "no-response" and method == "tools/call":
            continue
        if method == "initialize":
            requested = params.get("protocolVersion")
            if mode == "mismatch":
                selected = "2099-01-01"
            else:
                selected = requested if requested in {MODERN, LEGACY} else LEGACY
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": identifier,
                    "result": {
                        "protocolVersion": selected,
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": mode, "version": "fixture"},
                    },
                }
            )
        elif method == "tools/list":
            _send({"jsonrpc": "2.0", "id": identifier, "result": {"tools": _tools(mode)}})
        elif method == "tools/call":
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": identifier,
                    "result": {
                        "content": [{"type": "text", "text": "local-fixture"}],
                        "isError": False,
                    },
                }
            )
        else:
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": identifier,
                    "error": {"code": -32601, "message": "method not found"},
                }
            )


if __name__ == "__main__":
    main()
