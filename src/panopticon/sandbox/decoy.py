"""Deterministic synthetic decoy material for sandbox runs."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import tarfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from types import MappingProxyType
from urllib.parse import quote, quote_plus

from .decoy_specs import ENVIRONMENT_KEYS, FILE_SPECS, formatted_content


class DecoySource(StrEnum):
    FILE = "file"
    ENVIRONMENT = "environment"
    CONTENT = "content"


class DecoySensitivity(StrEnum):
    PUBLIC = "public"
    SENSITIVE = "sensitive"


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
        return MappingProxyType(
            {
                marker.key.rsplit(":", 1)[-1]: marker.text
                for marker in self.markers
                if marker.source is DecoySource.ENVIRONMENT
            }
        )

    @property
    def bytes(self) -> bytes:
        return b"".join(self.files[path] for path in sorted(self.files))


def _token(seed: str, identity: str, key: str) -> bytes:
    digest = hashlib.sha256(f"panopticon:{seed}:{identity}:{key}".encode()).hexdigest()
    identity_digest = hashlib.sha256(identity.encode()).hexdigest()[:8]
    return f'PANO_DECOY_{identity_digest}_{digest[:16]} +/="'.encode()


def _environment_token(seed: str, identity: str, key: str) -> bytes:
    digest = hashlib.sha256(f"panopticon:env:{seed}:{identity}:{key}".encode()).hexdigest()
    marker = f"PANO_DECOY_{digest[:12]}"
    if key == "AWS_ACCESS_KEY_ID":
        return f"AKIA{digest[:4].upper()}{marker}".encode()
    if key in {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}:
        return f"sk-{marker}-{digest[12:24]}".encode()
    if key.endswith("_URL") or key in {"DATABASE_URL", "MONGODB_URI"}:
        return f"https://{marker}:synthetic@decoy.invalid/{digest[:8]}".encode()
    return f"{marker}_{digest[12:28]}".encode()


def generate_decoy_home(
    seed: str,
    identity: str = "run",
    *,
    max_bytes: int = 1_048_576,
    project_filenames: Iterable[str] = (),
) -> DecoyManifest:
    """Build a deterministic, entirely synthetic decoy manifest without I/O."""
    if not seed:
        raise ValueError("seed must be non-empty")
    if not identity or "/" in identity or "\\" in identity:
        raise ValueError("identity must be a non-empty path-safe string")
    if max_bytes < 0:
        raise ValueError("max_bytes must be non-negative")
    files: dict[str, bytes] = {}
    markers: list[DecoyMarker] = []
    retained = 0
    for spec in FILE_SPECS:
        value = _token(seed, identity, spec.key)
        content = formatted_content(spec, value)
        if retained + len(content) > max_bytes:
            continue
        files[spec.path] = content
        retained += len(content)
        source = (
            DecoySource.CONTENT
            if spec.path.startswith(("Documents/", "Desktop/", "Downloads/"))
            or spec.format == "history"
            else DecoySource.FILE
        )
        markers.append(_marker(identity, f"file:{spec.key}", value, source))
    for raw_name in sorted(set(project_filenames)):
        name = _project_name(raw_name)
        value = _token(seed, identity, f"project:{name}")
        is_environment = PurePosixPath(name).name.startswith(".env")
        content = value + b"\n" if is_environment else b""
        if retained + len(content) > max_bytes:
            continue
        files[f"project/{name}"] = content
        retained += len(content)
        if content:
            markers.append(_marker(identity, f"project:{name}", value, DecoySource.CONTENT))
    for key in ENVIRONMENT_KEYS:
        value = _environment_token(seed, identity, key)
        markers.append(_marker(identity, f"env:{key}", value, DecoySource.ENVIRONMENT))
    return DecoyManifest(
        identity,
        seed,
        MappingProxyType(dict(sorted(files.items()))),
        tuple(markers),
    )


def _marker(identity: str, key: str, value: bytes, source: DecoySource) -> DecoyMarker:
    return DecoyMarker(
        f"{identity}:{key}",
        value,
        source,
        True,
        DecoySensitivity.SENSITIVE,
    )


def _project_name(value: str) -> str:
    original = value.replace("\\", "/")
    if PurePosixPath(original).is_absolute() or (len(original) >= 2 and original[1] == ":"):
        raise ValueError("project filename must be repository-relative")
    normalized = original.strip("/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts:
        raise ValueError("project filename must be repository-relative")
    return path.as_posix()


def decoy_archive(manifest: DecoyManifest, *, max_bytes: int = 32 * 1024 * 1024) -> bytes:
    """Create a canonical in-memory tar suitable for container copy-in."""
    if max_bytes < 1:
        raise ValueError("archive bound must be positive")
    output = io.BytesIO()
    directories = {
        parent.as_posix()
        for name in manifest.files
        for parent in PurePosixPath(name).parents
        if parent.as_posix() != "."
    }
    with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for directory in sorted(directories, key=lambda item: (item.count("/"), item)):
            info = _tar_info(f"{directory}/", directory=True)
            archive.addfile(info)
        for name, content in sorted(manifest.files.items()):
            info = _tar_info(name, directory=False)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
            if output.tell() > max_bytes:
                raise ValueError("decoy archive exceeded its bound")
    payload = output.getvalue()
    if len(payload) > max_bytes:
        raise ValueError("decoy archive exceeded its bound")
    return payload


def _tar_info(name: str, *, directory: bool) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.DIRTYPE if directory else tarfile.REGTYPE
    info.mode = 0o700 if directory else 0o600
    info.uid = info.gid = 1000
    info.uname = info.gname = "pano"
    info.mtime = 0
    return info


def marker_encodings(marker: DecoyMarker) -> tuple[tuple[bytes, str], ...]:
    value = marker.value
    text = value.decode("ascii")
    json_escaped = json.dumps(text, ensure_ascii=True)[1:-1]
    return (
        (value, "RAW"),
        (json_escaped.encode(), "JSON_ESCAPED"),
        (
            json.dumps(json_escaped, ensure_ascii=True)[1:-1].encode(),
            "JSON_NESTED_ESCAPED",
        ),
        (quote(text, safe="").encode(), "URL_ENCODED"),
        (quote_plus(text, safe="").encode(), "FORM_ENCODED"),
        (base64.b64encode(value), "BASE64"),
        (base64.urlsafe_b64encode(value), "BASE64_URLSAFE"),
    )


generate_decoys = generate_decoy_home
