"""Evidence-based probe for the official MCP server set.

Unavailable servers are recorded as blockers rather than replaced by compatible
fakes.  This keeps the acceptance result honest when upstream packages move or
require credentials.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

MANIFEST = Path(__file__).parents[2] / "fixtures" / "mcp" / "official" / "manifest.json"


def test_official_manifest_has_immutable_provenance_and_explicit_blockers() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    license_file = MANIFEST.parent / manifest["source"]["license_file"]
    assert (
        hashlib.sha256(license_file.read_bytes()).hexdigest()
        == manifest["source"]["license_sha256"]
    )
    names = {entry["name"] for entry in manifest["servers"]}
    assert names == {"filesystem", "github", "fetch", "memory", "sqlite"}
    expected_commits = {
        "filesystem": "cda92bdaacd558192fedf1a60d2bb27510792388",
        "memory": "cda92bdaacd558192fedf1a60d2bb27510792388",
        "fetch": "cda92bdaacd558192fedf1a60d2bb27510792388",
        "github": "1f705677a930ec618b7a16d87d00cee7db747ff2",
        "sqlite": "1f705677a930ec618b7a16d87d00cee7db747ff2",
    }
    for entry in manifest["servers"]:
        assert entry["status"] in {"available", "blocked"}
        assert entry["commit"] == expected_commits[entry["name"]]
        assert entry["source"].startswith("https://github.com/modelcontextprotocol/servers/tree/")
        if entry["status"] == "available":
            assert len(entry["commit"]) == 40
            assert entry["integrity"].startswith("sha512-")
            assert entry["driver"]
        else:
            assert entry["blocker"]
            assert "HTTP 404" not in entry["blocker"]
            assert "npm registry" not in entry["blocker"]


def test_available_driver_arguments_are_schema_shaped() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for entry in manifest["servers"]:
        if entry["status"] != "available":
            continue
        driver = entry["driver"]
        assert driver[0] == "node"
        assert all(isinstance(argument, str) and argument for argument in driver[1:])
        # Driver vectors are intentionally positional and contain no secret values.
        assert all("token" not in argument.lower() for argument in driver)
        assert isinstance(driver, list) and all(isinstance(item, str) for item in driver)
