"""Deterministic command and URL parsers for inventory entries."""

from __future__ import annotations

import hashlib
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import SplitResult, urlsplit, urlunsplit

from panopticon.models.ids import ServerId
from panopticon.models.inventory import (
    IdentityConfidence,
    PackageEcosystem,
    PackageIdentity,
    SourceKind,
)

_VALUE_FLAGS = {
    "--cache",
    "--package",
    "--registry",
    "--userconfig",
    "-c",
    "-p",
}
_DOCKER_VALUE_FLAGS = {
    "--add-host",
    "--env",
    "--env-file",
    "--mount",
    "--name",
    "--network",
    "--platform",
    "--publish",
    "--user",
    "--volume",
    "-e",
    "-p",
    "-u",
    "-v",
}


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    server_id: ServerId
    package: PackageIdentity | None
    source: SourceKind
    confidence: IdentityConfidence


def _pkg_name(value: str) -> tuple[str, str | None]:
    value = value.strip()
    if "@" in value[1:]:
        name, version = value.rsplit("@", 1)
        if version:
            return name, version
    return value, None


def _npm(value: str) -> ParsedCommand:
    name, version = _pkg_name(value)
    return ParsedCommand(
        ServerId(f"npm:{name}"),
        PackageIdentity(ecosystem=PackageEcosystem.NPM, name=name, pinned=version, resolved=None),
        SourceKind.REGISTRY,
        IdentityConfidence.MEDIUM,
    )


def _local(argv: list[str]) -> ParsedCommand:
    digest = hashlib.sha256("\0".join(argv).encode()).hexdigest()[:12]
    return ParsedCommand(
        ServerId(f"local:{digest}"),
        None,
        SourceKind.LOCAL,
        IdentityConfidence.LOW,
    )


def _first_package(args: tuple[str, ...] | list[str]) -> str | None:
    values = list(args)
    explicit: list[str] = []
    index = 0
    while index < len(values):
        value = values[index]
        if value == "--":
            break
        if value.startswith(("--package=", "-p=")):
            explicit.append(value.split("=", 1)[1])
        elif value in {"--package", "-p"} and index + 1 < len(values):
            explicit.append(values[index + 1])
            index += 1
        elif value in _VALUE_FLAGS and index + 1 < len(values):
            index += 1
        elif value.startswith("-"):
            pass
        else:
            return value
        index += 1
    return explicit[0] if explicit else None


def parse_command(command: str, args: tuple[str, ...] | list[str] = ()) -> ParsedCommand:
    """Classify a stdio command using the fixed E03 extraction rules."""
    argv = [command, *args]
    exe = posixpath.basename(command.replace("\\", "/")).casefold()
    if exe in {"npx", "npx.cmd", "bunx", "bunx.cmd"}:
        package = _first_package(args)
        if package is not None and "${" not in package:
            return _npm(package)
    if exe == "node" and len(args) > 0:
        match = re.search(
            r"(?:^|/)node_modules/(?:@([^/]+)/)?([^/]+)",
            args[0].replace("\\", "/"),
        )
        if match:
            name = f"@{match.group(1)}/{match.group(2)}" if match.group(1) else match.group(2)
            return _npm(name)
    if exe in {"uvx", "pipx"}:
        vals = list(args)
        explicit: str | None = None
        if exe == "uvx" and len(vals) >= 2 and vals[0] == "--from":
            explicit = vals[1]
            vals = vals[2:]
        elif exe == "uvx" and vals and vals[0].startswith("--from="):
            explicit = vals.pop(0).split("=", 1)[1]
        if exe == "pipx" and vals and vals[0] == "run":
            vals = vals[1:]
        package = explicit or next((value for value in vals if not value.startswith("-")), None)
        if package is not None and "${" not in package:
            name, version = _pkg_name(package)
            return ParsedCommand(
                ServerId(f"pypi:{name}"),
                PackageIdentity(
                    ecosystem=PackageEcosystem.PYPI, name=name, pinned=version, resolved=None
                ),
                SourceKind.REGISTRY,
                IdentityConfidence.MEDIUM,
            )
    if exe in {"python", "python3"} and len(args) >= 2 and args[0] == "-m":
        mod = args[1].replace("_", "-")
        return ParsedCommand(
            ServerId(f"pypi:{mod}"),
            PackageIdentity(ecosystem=PackageEcosystem.PYPI, name=mod, pinned=None, resolved=None),
            SourceKind.REGISTRY,
            IdentityConfidence.LOW,
        )
    if exe == "docker" and args:
        vals = list(args)
        while vals and vals[0] != "run":
            flag = vals.pop(0)
            if flag in _DOCKER_VALUE_FLAGS and vals:
                vals.pop(0)
        if vals and vals[0] == "run":
            vals.pop(0)
        while vals and vals[0].startswith("-"):
            flag = vals.pop(0)
            if flag in _DOCKER_VALUE_FLAGS and vals:
                vals.pop(0)
        if vals:
            image = vals[0].casefold()
            return ParsedCommand(
                ServerId(f"docker:{image}"),
                PackageIdentity(
                    ecosystem=PackageEcosystem.DOCKER, name=image, pinned=None, resolved=None
                ),
                SourceKind.REGISTRY,
                IdentityConfidence.MEDIUM,
            )
    for value in argv:
        match = re.search(r"https?://github\.com/([^/\s]+)/([^/#\s]+)", value, re.I)
        if match:
            repo = match.group(2).removesuffix(".git")
            return ParsedCommand(
                ServerId(f"github:{match.group(1).casefold()}/{repo.casefold()}"),
                None,
                SourceKind.GIT,
                IdentityConfidence.HIGH,
            )
    if args and (args[0].startswith(("http://", "https://"))):
        host = normalize_url(args[0])
        parsed = urlsplit(host)
        path = parsed.path.rstrip("/")
        return ParsedCommand(
            ServerId(f"remote:{parsed.netloc}{path}"),
            None,
            SourceKind.REMOTE,
            IdentityConfidence.HIGH,
        )
    return _local(argv)


def resolve_cached_version(package: PackageIdentity, home: Path) -> str | None:
    """Read only normalized version fields from deterministic local package caches."""
    if package.ecosystem is PackageEcosystem.NPM:
        package_path = Path(*package.name.split("/"))
        roots = sorted((home / ".npm/_npx").glob("*"), key=lambda path: path.as_posix())
        for root in roots:
            metadata = root / "node_modules" / package_path / "package.json"
            try:
                match = re.search(r'"version"\s*:\s*"([^"]+)"', metadata.read_text())
            except OSError:
                continue
            if match is not None:
                return match.group(1)
    elif package.ecosystem is PackageEcosystem.PYPI:
        cache = home / ".cache/uv/archive-v0"
        for metadata in sorted(
            cache.glob("*/*.dist-info/METADATA"), key=lambda path: path.as_posix()
        ):
            try:
                fields = dict(
                    line.split(":", 1) for line in metadata.read_text().splitlines() if ":" in line
                )
            except OSError:
                continue
            if fields.get("Name", "").strip().casefold() == package.name.casefold():
                version = fields.get("Version", "").strip()
                return version or None
    return None


def normalize_url(value: str) -> str:
    """Drop credentials and query/fragment; canonicalize IDNA host and IPv6."""
    parts = urlsplit(value)
    host = parts.hostname or ""
    try:
        host = host.encode("idna").decode("ascii").casefold()
    except UnicodeError:
        host = host.casefold()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = host
    if parts.port is not None and not (
        (parts.scheme == "http" and parts.port == 80)
        or (parts.scheme == "https" and parts.port == 443)
    ):
        netloc += f":{parts.port}"
    return urlunsplit(SplitResult(parts.scheme.casefold(), netloc, parts.path or "/", "", ""))
