"""Immutable provenance contract for the official MCP acceptance verifier."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

MANIFEST = Path(__file__).parents[2] / "fixtures" / "mcp" / "official" / "manifest.json"


def test_official_manifest_has_immutable_provenance_and_drivers() -> None:
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
        assert entry["status"] in {"available", "verified"}
        assert entry["commit"] == expected_commits[entry["name"]]
        assert entry["source"].startswith("https://github.com/modelcontextprotocol/servers/tree/")
        assert len(entry["commit"]) == 40
        assert entry["driver"]
        if entry["package"] is not None:
            assert entry["integrity"].startswith("sha512-")


def test_official_driver_arguments_are_schema_shaped() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for entry in manifest["servers"]:
        driver = entry["driver"]
        assert isinstance(driver, list) and driver
        assert driver[0] == "node" or driver[0].startswith(".venv/bin/")
        assert all(isinstance(argument, str) and argument for argument in driver[1:])
        # Driver vectors are intentionally positional and contain no secret values.
        assert all("token" not in argument.lower() for argument in driver)
        assert all(isinstance(item, str) for item in driver)
