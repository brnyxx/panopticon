"""Every schema validates its own minimal example, and refs resolve."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource

SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"


def _registry() -> Registry:
    res = [
        (p.name, Resource.from_contents(json.loads(p.read_text()))) for p in SCHEMAS.glob("*.json")
    ]
    return Registry().with_resources(res)


def _validator(name: str) -> Draft202012Validator:
    doc = json.loads((SCHEMAS / f"{name}.json").read_text())
    return Draft202012Validator(doc, registry=_registry())


MINIMAL = {
    "installed_server": {
        "schema_version": "1.0",
        "server_id": "npm:@modelcontextprotocol/server-github",
        "name": "github",
        "client": "claude-desktop",
        "config_path": "~/Library/Application Support/Claude/claude_desktop_config.json",
        "scope": "global",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env_keys": ["GITHUB_TOKEN"],
        "identity_confidence": "high",
    },
    "event": {
        "kind": "net",
        "op": "connect",
        "host": "api.github.com",
        "port": 443,
        "via": "proxy",
    },
    "finding": {
        "id": "0123456789abcdef",
        "rule_id": "WATCH-001",
        "severity": "HIGH",
        "kind": "confirmed",
        "title": "Decoy value exfiltrated",
        "evidence": [],
    },
    "observation": {
        "schema_version": "1.0",
        "observation_id": "obs_x",
        "server_id": "npm:x",
        "observed_at": "2026-08-26T00:00:00Z",
        "pano_version": "0.0.1",
        "spans": [
            {
                "tool": "list_issues",
                "result": "ok",
                "events": [{"kind": "file", "op": "read", "path": "~/.ssh/config", "decoy": True}],
            }
        ],
        "declared": {"completeness": "PARTIAL", "sources": ["readme"]},
        "findings": [],
        "state": {"overall": "PARTIAL", "stages": {"probe": "COMPLETE", "file": "COMPLETE"}},
    },
    "baseline": {
        "schema_version": "1.0",
        "baseline_id": "bl_x",
        "created_at": "2026-08-26T00:00:00Z",
        "kind": "explicit",
        "inventory": [],
        "observations": [],
        "findings": [],
    },
    "diff_result": {
        "schema_version": "1.0",
        "since": "bl_x",
        "until": "now",
        "findings": {"new": [], "changed": [], "unchanged": [], "resolved": [], "unknown": []},
        "capability": [],
        "behavior": [],
        "inventory": [],
        "meaningful": [],
    },
    "wrap_record": {
        "ts": "2026-08-26T00:00:00Z",
        "server_id": "npm:x",
        "span": {"tool": "x"},
        "events": [],
    },
}


@pytest.mark.parametrize("name", sorted(MINIMAL))
def test_minimal_example_validates(name: str) -> None:
    _validator(name).validate(MINIMAL[name])


def test_absolute_home_path_rejected_in_event() -> None:
    v = _validator("event")
    with pytest.raises(ValidationError):
        v.validate({"kind": "file", "op": "read", "path": "/Users/alice/.ssh/config"})
