from __future__ import annotations

import gzip
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("package_npm", ROOT / "scripts" / "package_npm.py")
assert SPEC is not None and SPEC.loader is not None
package_npm = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = package_npm
SPEC.loader.exec_module(package_npm)


def _archive(path: Path, root: str, *, duplicate: bool = False, traversal: bool = False) -> bytes:
    output = io.BytesIO()
    with (
        gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.GNU_FORMAT) as archive,
    ):
        files = {
            f"{root}/pano": (b"native executable", 0o755),
            f"{root}/LICENSE": (b"MIT\n", 0o644),
            f"{root}/THIRD_PARTY_NOTICES.md": (b"notice\n", 0o644),
        }
        if traversal:
            files[f"{root}/../pano"] = (b"bad", 0o755)
        for name, (contents, mode) in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(contents)
            member.mode = mode
            member.mtime = 0
            archive.addfile(member, io.BytesIO(contents))
        if duplicate:
            member = tarfile.TarInfo(f"{root}/pano")
            member.size = 3
            member.mode = 0o755
            archive.addfile(member, io.BytesIO(b"bad"))
    path.write_bytes(output.getvalue())
    return files[f"{root}/pano"][0]


def _project(tmp_path: Path) -> tuple[Path, Path, dict[str, bytes]]:
    project = tmp_path / "project"
    (project / "npm" / "bin").mkdir(parents=True)
    (project / "pyproject.toml").write_text("[project]\nversion = '2.3.4'\n", encoding="utf-8")
    (project / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (project / "THIRD_PARTY_NOTICES.md").write_text("notice\n", encoding="utf-8")
    shutil.copy(ROOT / "npm" / "packages.json", project / "npm" / "packages.json")
    shutil.copy(ROOT / "npm" / "README.md", project / "npm" / "README.md")
    shutil.copy(ROOT / "npm" / "bin" / "pano.cjs", project / "npm" / "bin" / "pano.cjs")
    archives = tmp_path / "archives"
    archives.mkdir()
    binaries: dict[str, bytes] = {}
    for package in package_npm.native_packages(project / "npm" / "packages.json"):
        root = f"panopticon-2.3.4-{package.target}"
        binaries[package.name] = _archive(archives / f"{root}.tar.gz", root)
    return project, archives, binaries


def _members(path: Path) -> dict[str, tarfile.TarInfo]:
    with tarfile.open(path, mode="r:gz") as archive:
        return {member.name: member for member in archive.getmembers()}


def test_public_package_names_and_version_come_only_from_pyproject(tmp_path: Path) -> None:
    project, archives, _ = _project(tmp_path)
    assert package_npm.PACKAGE_NAMES == (
        "@brnyxx/panopticon",
        "@brnyxx/panopticon-linux-x64-gnu",
        "@brnyxx/panopticon-linux-arm64-gnu",
        "@brnyxx/panopticon-darwin-x64",
        "@brnyxx/panopticon-darwin-arm64",
    )
    assert package_npm.release_version(project) == "2.3.4"
    artifacts = package_npm.build_npm_packages(project, archives, tmp_path / "npm")
    assert [artifact.name for artifact in artifacts] == [
        "brnyxx-panopticon-2.3.4.tgz",
        "brnyxx-panopticon-linux-x64-gnu-2.3.4.tgz",
        "brnyxx-panopticon-linux-arm64-gnu-2.3.4.tgz",
        "brnyxx-panopticon-darwin-x64-2.3.4.tgz",
        "brnyxx-panopticon-darwin-arm64-2.3.4.tgz",
    ]
    with tarfile.open(artifacts[0], "r:gz") as archive:
        manifest_file = archive.extractfile("package/package.json")
        assert manifest_file is not None
        root_manifest = json.loads(manifest_file.read())
    assert root_manifest["version"] == "2.3.4"
    assert root_manifest["optionalDependencies"] == dict.fromkeys(
        package_npm.PACKAGE_NAMES[1:], "2.3.4"
    )


def test_tarballs_are_deterministic_and_preserve_native_executables(tmp_path: Path) -> None:
    project, archives, binaries = _project(tmp_path)
    first = package_npm.build_npm_packages(project, archives, tmp_path / "one")
    second = package_npm.build_npm_packages(project, archives, tmp_path / "two")
    assert [item.read_bytes() for item in first] == [item.read_bytes() for item in second]
    for artifact, package in zip(
        first[1:],
        package_npm.native_packages(project / "npm" / "packages.json"),
        strict=True,
    ):
        with tarfile.open(artifact, "r:gz") as archive:
            binary = archive.extractfile("package/bin/pano")
            assert binary is not None
            assert binary.read() == binaries[package.name]
        members = _members(artifact)
        assert set(members) == {
            "package/LICENSE",
            "package/README.md",
            "package/THIRD_PARTY_NOTICES.md",
            "package/bin/pano",
            "package/package.json",
        }
        assert members["package/bin/pano"].mode == 0o755
        assert all(member.mtime == 0 for member in members.values())


@pytest.mark.parametrize("kind", ("duplicate", "traversal", "malformed"))
def test_rejects_malformed_native_archive_shapes(tmp_path: Path, kind: str) -> None:
    project, archives, _ = _project(tmp_path)
    package = package_npm.native_packages(project / "npm" / "packages.json")[0]
    path = archives / f"panopticon-2.3.4-{package.target}.tar.gz"
    if kind == "malformed":
        path.write_bytes(b"not a gzip archive")
    else:
        _archive(path, f"panopticon-2.3.4-{package.target}", **{kind: True})
    with pytest.raises(ValueError, match="INVALID_NPM_NATIVE_ARCHIVE"):
        package_npm.build_npm_packages(project, archives, tmp_path / "output")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")
def test_launcher_reports_unsupported_and_missing_payload() -> None:
    launcher = ROOT / "npm" / "bin" / "pano.cjs"
    unsupported = subprocess.run(
        [
            "node",
            "-e",
            (
                "Object.defineProperty(process, 'platform', {value: 'freebsd'}); "
                "require(process.argv[1]);"
            ),
            str(launcher),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert unsupported.returncode == 1
    assert "does not provide a native package for freebsd/" in unsupported.stderr
    missing = subprocess.run(["node", str(launcher)], capture_output=True, text=True, check=False)
    assert missing.returncode == 1
    assert "native package @brnyxx/panopticon-" in missing.stderr
    assert "is not installed" in missing.stderr
