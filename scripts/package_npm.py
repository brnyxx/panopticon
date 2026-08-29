"""Build deterministic npm packages from retained Panopticon native archives."""

from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import tarfile
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
PACKAGE_NAMES = (
    "@brnyxx/panopticon",
    "@brnyxx/panopticon-linux-x64-gnu",
    "@brnyxx/panopticon-linux-arm64-gnu",
    "@brnyxx/panopticon-darwin-x64",
    "@brnyxx/panopticon-darwin-arm64",
)


@dataclass(frozen=True, slots=True)
class NativePackage:
    name: str
    target: str
    os: str
    cpu: str
    libc: str | None


def release_version(project_root: Path) -> str:
    """Read the only release version authority and require stable X.Y.Z."""
    with (project_root / "pyproject.toml").open("rb") as source:
        project = tomllib.load(source).get("project")
    if not isinstance(project, dict) or not isinstance(project.get("version"), str):
        raise ValueError("INVALID_RELEASE_VERSION")
    version = project["version"]
    if not VERSION_RE.fullmatch(version):
        raise ValueError("INVALID_RELEASE_VERSION")
    return version


def native_packages(config_path: Path) -> tuple[NativePackage, ...]:
    """Load the frozen platform mapping without allowing alternate package sets."""
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("packages"), list):
        raise ValueError("INVALID_NPM_PACKAGE_CONFIG")
    packages: list[NativePackage] = []
    names: list[str] = []
    for item in raw["packages"]:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise ValueError("INVALID_NPM_PACKAGE_CONFIG")
        names.append(item["name"])
        if item.get("kind") == "root":
            continue
        fields = ("target", "os", "cpu")
        if any(not isinstance(item.get(field), str) for field in fields):
            raise ValueError("INVALID_NPM_PACKAGE_CONFIG")
        libc = item.get("libc")
        if libc is not None and not isinstance(libc, str):
            raise ValueError("INVALID_NPM_PACKAGE_CONFIG")
        packages.append(
            NativePackage(
                name=item["name"],
                target=item["target"],
                os=item["os"],
                cpu=item["cpu"],
                libc=libc,
            )
        )
    if tuple(names) != PACKAGE_NAMES or len(packages) != 4:
        raise ValueError("INVALID_NPM_PACKAGE_CONFIG")
    return tuple(packages)


def _archive_binary(archive_path: Path, version: str, target: str) -> bytes:
    expected_root = f"panopticon-{version}-{target}"
    expected = {
        f"{expected_root}/pano",
        f"{expected_root}/LICENSE",
        f"{expected_root}/THIRD_PARTY_NOTICES.md",
    }
    try:
        with tarfile.open(archive_path, mode="r:gz") as archive:
            members = archive.getmembers()
            names: set[str] = set()
            binary: bytes | None = None
            for member in members:
                path = PurePosixPath(member.name)
                if (
                    member.name in names
                    or path.is_absolute()
                    or ".." in path.parts
                    or member.name not in expected
                    or not member.isreg()
                    or member.linkname
                ):
                    raise ValueError("INVALID_NPM_NATIVE_ARCHIVE")
                names.add(member.name)
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise ValueError("INVALID_NPM_NATIVE_ARCHIVE")
                contents = extracted.read()
                if member.name.endswith("/pano"):
                    if member.mode != 0o755:
                        raise ValueError("INVALID_NPM_NATIVE_ARCHIVE")
                    binary = contents
                elif member.mode & 0o111:
                    raise ValueError("INVALID_NPM_NATIVE_ARCHIVE")
            if names != expected or binary is None:
                raise ValueError("INVALID_NPM_NATIVE_ARCHIVE")
            return binary
    except (OSError, tarfile.TarError) as error:
        raise ValueError("INVALID_NPM_NATIVE_ARCHIVE") from error


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _tarball(files: dict[str, tuple[bytes, int]]) -> bytes:
    payload = io.BytesIO()
    with (
        gzip.GzipFile(filename="", mode="wb", fileobj=payload, mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.GNU_FORMAT) as archive,
    ):
        for name in sorted(files):
            contents, mode = files[name]
            member = tarfile.TarInfo(f"package/{name}")
            member.size = len(contents)
            member.mode = mode
            member.mtime = 0
            member.uid = 0
            member.gid = 0
            member.uname = ""
            member.gname = ""
            archive.addfile(member, io.BytesIO(contents))
    return payload.getvalue()


def _common_manifest(name: str, version: str) -> dict[str, Any]:
    return {
        "name": name,
        "version": version,
        "description": "Local-first MCP behavior observatory",
        "license": "MIT",
        "author": "Panopticon contributors",
        "repository": {"type": "git", "url": "git+https://github.com/brnyxx/panopticon.git"},
        "homepage": "https://github.com/brnyxx/panopticon",
        "bugs": {"url": "https://github.com/brnyxx/panopticon/issues"},
        "engines": {"node": ">=22.14.0"},
        "publishConfig": {"access": "public"},
    }


def build_npm_packages(project_root: Path, archives: Path, output: Path) -> tuple[Path, ...]:
    """Create the root launcher and four platform package tarballs."""
    version = release_version(project_root)
    config = project_root / "npm" / "packages.json"
    platforms = native_packages(config)
    license_text = (project_root / "LICENSE").read_bytes()
    notices = (project_root / "THIRD_PARTY_NOTICES.md").read_bytes()
    readme = (project_root / "npm" / "README.md").read_bytes()
    launcher = (project_root / "npm" / "bin" / "pano.cjs").read_bytes()
    payloads = {
        package.name: _archive_binary(
            archives / f"panopticon-{version}-{package.target}.tar.gz", version, package.target
        )
        for package in platforms
    }
    output.mkdir(parents=True, exist_ok=True)
    root = _common_manifest(PACKAGE_NAMES[0], version)
    root["bin"] = {"pano": "bin/pano.cjs"}
    root["optionalDependencies"] = {package.name: version for package in platforms}
    artifacts: list[Path] = []
    root_path = output / "brnyxx-panopticon.tgz"
    root_path.write_bytes(
        _tarball(
            {
                "LICENSE": (license_text, 0o644),
                "README.md": (readme, 0o644),
                "THIRD_PARTY_NOTICES.md": (notices, 0o644),
                "bin/pano.cjs": (launcher, 0o755),
                "package.json": (_json_bytes(root), 0o644),
            }
        )
    )
    artifacts.append(root_path)
    for package in platforms:
        manifest = _common_manifest(package.name, version)
        manifest["os"] = [package.os]
        manifest["cpu"] = [package.cpu]
        if package.libc is not None:
            manifest["libc"] = [package.libc]
        path = output / f"{package.name.removeprefix('@').replace('/', '-')}.tgz"
        path.write_bytes(
            _tarball(
                {
                    "LICENSE": (license_text, 0o644),
                    "README.md": (readme, 0o644),
                    "THIRD_PARTY_NOTICES.md": (notices, 0o644),
                    "bin/pano": (payloads[package.name], 0o755),
                    "package.json": (_json_bytes(manifest), 0o644),
                }
            )
        )
        artifacts.append(path)
    return tuple(artifacts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archives", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    build_npm_packages(args.project_root.resolve(), args.archives.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
