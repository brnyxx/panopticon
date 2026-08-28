from __future__ import annotations

import re
from pathlib import Path

LOCK = Path(__file__).parents[2] / "src/panopticon/sandbox/images.lock"
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
OUTPUTS = {
    "ghcr.io/brnyxx/pano-sandbox-base:0.1",
    "ghcr.io/brnyxx/pano-sandbox-node:20",
    "ghcr.io/brnyxx/pano-sandbox-node:22",
    "ghcr.io/brnyxx/pano-sandbox-python:3.12",
}


def test_published_image_lock_has_exact_immutable_outputs() -> None:
    text = LOCK.read_text(encoding="utf-8")
    entries = {
        key.strip(): value.strip()
        for line in text.splitlines()
        if line and not line.startswith("#") and "=" in line
        for key, value in (line.split("=", 1),)
    }

    assert entries.pop("version") == "1"
    outputs = {key for key in entries if key.startswith("ghcr.io/")}
    assert outputs == OUTPUTS
    assert all(DIGEST.fullmatch(entries[key]) for key in outputs)
    assert len({entries[key] for key in outputs}) == len(OUTPUTS)
    assert "UNBUILT" not in text and "TODO" not in text


def test_every_source_image_is_content_pinned() -> None:
    entries = [
        line.split("=", 1)[1].strip()
        for line in LOCK.read_text(encoding="utf-8").splitlines()
        if line.startswith("source.")
    ]
    assert len(entries) == 5
    assert all(DIGEST.fullmatch(value) for value in entries)
