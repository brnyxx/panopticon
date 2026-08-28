"""Deterministic synthetic decoy material for sandbox runs."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath


class DecoySource(StrEnum):
    FILE = "file"
    ENVIRONMENT = "environment"
    CONTENT = "content"


class DecoySensitivity(StrEnum):
    PUBLIC = "public"
    SECRET = "secret"


@dataclass(frozen=True, slots=True)
class DecoyMarker:
    key: str
    value: bytes
    source: DecoySource
    decoy: bool
    sensitivity: DecoySensitivity

    @property
    def source_identity(self) -> DecoySource:
        return self.source

    @property
    def decoy_identity(self) -> str:
        return self.key

    @property
    def text(self) -> str:
        return self.value.decode("ascii")


@dataclass(frozen=True, slots=True)
class DecoyManifest:
    identity: str
    seed: str
    files: Mapping[str, bytes]
    markers: tuple[DecoyMarker, ...]

    @property
    def env(self) -> Mapping[str, str]:
        return {
            marker.key.rsplit(":", 1)[-1].upper(): marker.text
            for marker in self.markers
            if marker.source is DecoySource.ENVIRONMENT
        }

    @property
    def bytes(self) -> bytes:
        return b"".join(self.files[path] for path in sorted(self.files))


def _token(seed: str, identity: str, key: str, length: int = 32) -> bytes:
    # Hex is deliberately boring, portable, and cannot contain real credentials.
    digest = hashlib.sha256(f"panopticon:{seed}:{identity}:{key}".encode()).hexdigest()
    return (f"PANO_DECOY_{identity}_{digest}"[:length]).encode("ascii")


def generate_decoy_home(
    seed: str, identity: str = "run", *, max_bytes: int = 1_048_576
) -> DecoyManifest:
    """Build a deterministic, entirely synthetic decoy manifest (without I/O)."""
    if not isinstance(seed, str) or not seed:
        raise ValueError("seed must be non-empty")
    if not isinstance(identity, str) or not identity or "/" in identity or "\\" in identity:
        raise ValueError("identity must be a non-empty path-safe string")
    if max_bytes < 0:
        raise ValueError("max_bytes must be non-negative")
    specs = (
        (".aws/credentials", "aws", DecoySource.FILE),
        (".npmrc", "npm", DecoySource.FILE),
        (".config/pano/marker", "marker", DecoySource.CONTENT),
    )
    files: dict[str, bytes] = {}
    markers: list[DecoyMarker] = []
    for path, key, source in specs:
        value = _token(seed, identity, key)
        content = value + b"\n"
        if sum(len(v) for v in files.values()) + len(content) <= max_bytes:
            files[str(PurePosixPath(path))] = content
            markers.append(
                DecoyMarker(f"{identity}:{key}", value, source, True, DecoySensitivity.SECRET)
            )
    env_value = _token(seed, identity, "env")
    markers.append(
        DecoyMarker(
            f"{identity}:env", env_value, DecoySource.ENVIRONMENT, True, DecoySensitivity.SECRET
        )
    )
    return DecoyManifest(identity, seed, dict(sorted(files.items())), tuple(markers))


def marker_encodings(marker: DecoyMarker) -> tuple[tuple[bytes, str], ...]:
    """Return stable wire representations used by the streaming matcher."""
    value = marker.value
    text = value.decode("ascii")
    return (
        (value, "RAW"),
        (json.dumps(text, ensure_ascii=True)[1:-1].encode(), "JSON_ESCAPED"),
        (
            __import__("urllib.parse", fromlist=["quote"]).quote(text, safe="").encode(),
            "URL_ENCODED",
        ),
        (
            __import__("urllib.parse", fromlist=["quote_plus"]).quote_plus(text, safe="").encode(),
            "FORM_ENCODED",
        ),
        (base64.b64encode(value), "BASE64"),
        (base64.urlsafe_b64encode(value), "BASE64_URLSAFE"),
    )


# Descriptive alias used by callers that treat generation as a service.
generate_decoys = generate_decoy_home
