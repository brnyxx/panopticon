"""Fail-closed verification for recovery-only release promotion."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_SHA = re.compile(r"[0-9a-f]{40}")
_HEX = re.compile(r"[0-9a-f]{64}")
_RUN_ID = re.compile(r"[0-9]+")
_SIGSTORE_MEDIA_TYPE = "application/vnd.dev.sigstore.bundle.v0.3+json"
WHEEL = "panopticon_mcp-1.0.0-py3-none-any.whl"
SDIST = "panopticon_mcp-1.0.0.tar.gz"
PYPI_ASSETS = frozenset((WHEEL, SDIST))
RELEASE_ASSETS = frozenset(
    {
        "panopticon-1.0.0-darwin-arm64.tar.gz",
        "panopticon-1.0.0-darwin-arm64.tar.gz.cdx.json",
        "panopticon-1.0.0-darwin-x86_64.tar.gz",
        "panopticon-1.0.0-darwin-x86_64.tar.gz.cdx.json",
        "panopticon-1.0.0-linux-arm64.tar.gz",
        "panopticon-1.0.0-linux-arm64.tar.gz.cdx.json",
        "panopticon-1.0.0-linux-x86_64.tar.gz",
        "panopticon-1.0.0-linux-x86_64.tar.gz.cdx.json",
        WHEEL,
        f"{WHEEL}.cdx.json",
        SDIST,
        f"{SDIST}.cdx.json",
    }
)
_METADATA_FILES = frozenset(("release-manifest.json", "SHA256SUMS"))
_SIGNED_FILES = RELEASE_ASSETS | _METADATA_FILES
_BUNDLE_FILES = _SIGNED_FILES | {f"{name}.sigstore.json" for name in _SIGNED_FILES}


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ValueError("RELEASE_FILE_MISSING") from exc
    return digest.hexdigest()


def _json(path: Path, reason: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(reason) from exc


def validate_inputs(source_run_id: str, source_sha: str) -> None:
    if _RUN_ID.fullmatch(source_run_id) is None:
        raise ValueError("INVALID_SOURCE_RUN_ID")
    if _SHA.fullmatch(source_sha) is None:
        raise ValueError("INVALID_SOURCE_SHA")


def verify_run_metadata(metadata: object, source_run_id: str, source_sha: str) -> None:
    if not isinstance(metadata, dict):
        raise ValueError("INVALID_RUN_METADATA")
    if str(metadata.get("id")) != source_run_id:
        raise ValueError("RUN_ID_MISMATCH")
    if metadata.get("conclusion") != "success":
        raise ValueError("RUN_NOT_SUCCESSFUL")
    if metadata.get("head_sha") != source_sha:
        raise ValueError("RUN_SHA_MISMATCH")
    if metadata.get("event") != "workflow_dispatch":
        raise ValueError("RUN_EVENT_MISMATCH")
    if metadata.get("path") != ".github/workflows/release.yml":
        raise ValueError("RUN_WORKFLOW_MISMATCH")
    if metadata.get("name") != "release":
        raise ValueError("RUN_WORKFLOW_MISMATCH")


def _checksums(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError("SHA256SUMS_MISSING") from exc
    result: dict[str, str] = {}
    for line in lines:
        fields = line.split()
        if len(fields) != 2 or _HEX.fullmatch(fields[0]) is None:
            raise ValueError("MALFORMED_SHA256SUMS")
        if Path(fields[1]).name != fields[1] or fields[1] in result:
            raise ValueError("MALFORMED_SHA256SUMS")
        result[fields[1]] = fields[0]
    return result


def _verify_sigstore_bundle(path: Path) -> None:
    value = _json(path, "INVALID_SIGSTORE_BUNDLE")
    if not isinstance(value, dict) or value.get("mediaType") != _SIGSTORE_MEDIA_TYPE:
        raise ValueError("INVALID_SIGSTORE_BUNDLE")
    if not isinstance(value.get("verificationMaterial"), dict):
        raise ValueError("INVALID_SIGSTORE_BUNDLE")
    if not isinstance(value.get("messageSignature"), dict):
        raise ValueError("INVALID_SIGSTORE_BUNDLE")


def verify_bundle(bundle: Path, source_sha: str) -> Mapping[str, str]:
    manifest = _json(bundle / "release-manifest.json", "INVALID_RELEASE_MANIFEST")
    if not isinstance(manifest, dict):
        raise ValueError("INVALID_RELEASE_MANIFEST")
    if set(manifest) != {"assets", "commit", "schema_version", "version"}:
        raise ValueError("INVALID_RELEASE_MANIFEST")
    if manifest.get("schema_version") != 1 or manifest.get("version") != "1.0.0":
        raise ValueError("INVALID_RELEASE_MANIFEST")
    if manifest.get("commit") != source_sha:
        raise ValueError("RELEASE_COMMIT_MISMATCH")
    assets = manifest.get("assets")
    if not isinstance(assets, dict) or set(assets) != RELEASE_ASSETS:
        raise ValueError("INVALID_RELEASE_ASSETS")
    expected = {str(name): str(value) for name, value in assets.items()}
    if any(_HEX.fullmatch(value) is None for value in expected.values()):
        raise ValueError("INVALID_RELEASE_ASSETS")
    if _checksums(bundle / "SHA256SUMS") != expected:
        raise ValueError("SHA256SUMS_MISMATCH")
    actual = {path.name for path in bundle.iterdir() if path.is_file()}
    if actual != _BUNDLE_FILES:
        raise ValueError("RELEASE_ASSET_SET_MISMATCH")
    for name, digest in expected.items():
        if _digest(bundle / name) != digest:
            raise ValueError(f"RELEASE_ASSET_HASH_MISMATCH:{name}")
    for name in _BUNDLE_FILES - _SIGNED_FILES:
        _verify_sigstore_bundle(bundle / name)
    return expected


def verify_dist(bundle: Path, dist: Path) -> None:
    try:
        actual = {path.name for path in dist.iterdir() if path.is_file()}
    except OSError as exc:
        raise ValueError("INVALID_DIST_ASSETS") from exc
    if actual != PYPI_ASSETS:
        raise ValueError("INVALID_DIST_ASSETS")
    for name in PYPI_ASSETS:
        if _digest(bundle / name) != _digest(dist / name):
            raise ValueError(f"DIST_MISMATCH:{name}")


def _remote_assets(value: object) -> dict[str, str]:
    if isinstance(value, dict) and "urls" in value:
        value = value["urls"]
    if isinstance(value, dict):
        result = {str(name): str(digest) for name, digest in value.items()}
    elif isinstance(value, list):
        result = {}
        for item in value:
            if not isinstance(item, dict):
                raise ValueError("INVALID_REMOTE_ASSETS")
            filename = item.get("filename", item.get("name"))
            digests = item.get("digests")
            digest = digests.get("sha256") if isinstance(digests, dict) else item.get("sha256")
            if not isinstance(filename, str) or not isinstance(digest, str):
                raise ValueError("INVALID_REMOTE_ASSETS")
            if filename in result:
                raise ValueError("INVALID_REMOTE_ASSETS")
            result[filename] = digest
    else:
        raise ValueError("INVALID_REMOTE_ASSETS")
    invalid = (
        Path(name).name != name or _HEX.fullmatch(digest) is None for name, digest in result.items()
    )
    if any(invalid):
        raise ValueError("INVALID_REMOTE_ASSETS")
    return result


def verify_index(metadata: object | Path, dist: Path) -> None:
    value = _json(metadata, "INVALID_INDEX_METADATA") if isinstance(metadata, Path) else metadata
    if missing_index_assets(value, dist):
        raise ValueError("INDEX_ASSET_MISMATCH")


def missing_index_assets(metadata: object, dist: Path) -> frozenset[str]:
    expected = {name: _digest(dist / name) for name in PYPI_ASSETS}
    observed = _remote_assets(metadata)
    if not set(observed).issubset(expected):
        raise ValueError("INDEX_ASSET_MISMATCH")
    if any(expected[name] != digest for name, digest in observed.items()):
        raise ValueError("INDEX_ASSET_MISMATCH")
    return frozenset(set(expected) - set(observed))


def stage_missing_index_assets(metadata: object, dist: Path, staged: Path) -> frozenset[str]:
    missing = missing_index_assets(metadata, dist)
    try:
        staged.mkdir()
        for name in sorted(missing):
            shutil.copyfile(dist / name, staged / name)
    except OSError as exc:
        raise ValueError("INDEX_STAGING_FAILED") from exc
    return missing


def prepare_release_metadata(
    releases: object,
) -> tuple[dict[str, object], tuple[tuple[int, str], ...]]:
    if not isinstance(releases, list):
        raise ValueError("INVALID_RELEASE_LIST")
    matches = [
        release
        for release in releases
        if isinstance(release, dict) and release.get("tag_name") == "v1.0.0"
    ]
    if len(matches) != 1:
        raise ValueError("RELEASE_NOT_UNIQUE")
    release = matches[0]
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise ValueError("INVALID_RELEASE_ASSETS")
    digests: dict[str, str] = {}
    downloads: list[tuple[int, str]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            raise ValueError("INVALID_RELEASE_ASSETS")
        name = asset.get("name")
        identifier = asset.get("id")
        digest = asset.get("digest")
        if not isinstance(name, str) or Path(name).name != name:
            raise ValueError("INVALID_RELEASE_ASSETS")
        if not isinstance(identifier, int) or identifier <= 0:
            raise ValueError("INVALID_RELEASE_ASSETS")
        if not isinstance(digest, str) or not digest.startswith("sha256:"):
            raise ValueError("INVALID_RELEASE_ASSETS")
        value = digest.removeprefix("sha256:")
        if _HEX.fullmatch(value) is None or name in digests:
            raise ValueError("INVALID_RELEASE_ASSETS")
        digests[name] = value
        downloads.append((identifier, name))
    if set(digests) != _BUNDLE_FILES:
        raise ValueError("INVALID_RELEASE_ASSETS")
    metadata = {
        "target_commitish": release.get("target_commitish"),
        "draft": release.get("draft"),
        "prerelease": release.get("prerelease"),
        "assets": digests,
    }
    return metadata, tuple(sorted(downloads, key=lambda item: item[1]))


def verify_release_state(
    metadata: object,
    bundle: Path,
    source_sha: str,
    downloaded: Path,
) -> bool:
    if not isinstance(metadata, dict):
        raise ValueError("INVALID_RELEASE_STATE")
    state = (metadata.get("draft"), metadata.get("prerelease"))
    if state not in {(True, True), (False, False)}:
        raise ValueError("RELEASE_STATE_MISMATCH")
    if metadata.get("target_commitish") != source_sha:
        raise ValueError("RELEASE_TARGET_MISMATCH")
    expected = {path.name: _digest(path) for path in bundle.iterdir() if path.is_file()}
    if _remote_assets(metadata.get("assets")) != expected:
        raise ValueError("RELEASE_ASSETS_MISMATCH")
    try:
        actual = {path.name for path in downloaded.iterdir() if path.is_file()}
    except OSError as exc:
        raise ValueError("RELEASE_DOWNLOAD_MISSING") from exc
    if actual != set(expected):
        raise ValueError("RELEASE_DOWNLOAD_SET_MISMATCH")
    if any(_digest(downloaded / name) != digest for name, digest in expected.items()):
        raise ValueError("RELEASE_DOWNLOAD_HASH_MISMATCH")
    return state == (True, True)


def verify_recovery(
    source_run_id: str,
    source_sha: str,
    bundle: Path,
    dist: Path,
    index_metadata: object,
    release_metadata: object,
    release_assets: Path,
    run_metadata: object,
) -> None:
    validate_inputs(source_run_id, source_sha)
    verify_run_metadata(run_metadata, source_run_id, source_sha)
    verify_bundle(bundle, source_sha)
    verify_dist(bundle, dist)
    verify_index(index_metadata, dist)
    verify_release_state(release_metadata, bundle, source_sha, release_assets)


def _source_command(args: argparse.Namespace) -> None:
    verify_recovery(
        args.source_run_id,
        args.source_sha,
        args.bundle,
        args.dist,
        _json(args.index, "INVALID_INDEX_METADATA"),
        _json(args.release, "INVALID_RELEASE_STATE"),
        args.release_assets,
        _json(args.run_metadata, "INVALID_RUN_METADATA"),
    )
    print("recovery verification: source-bound, byte-identical, remote checks passed")


def _release_metadata_command(args: argparse.Namespace) -> None:
    metadata, downloads = prepare_release_metadata(_json(args.releases, "INVALID_RELEASE_LIST"))
    args.metadata.write_text(
        json.dumps(metadata, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    args.downloads.write_text(
        "".join(f"{identifier}\t{name}\n" for identifier, name in downloads),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    source = subparsers.add_parser("source")
    source.add_argument("--source-run-id", required=True)
    source.add_argument("--source-sha", required=True)
    source.add_argument("--bundle", type=Path, required=True)
    source.add_argument("--dist", type=Path, required=True)
    source.add_argument("--index", type=Path, required=True)
    source.add_argument("--release", type=Path, required=True)
    source.add_argument("--release-assets", type=Path, required=True)
    source.add_argument("--run-metadata", type=Path, required=True)
    source.set_defaults(handler=_source_command)
    index = subparsers.add_parser("index")
    index.add_argument("--metadata", type=Path, required=True)
    index.add_argument("--dist", type=Path, required=True)
    index.set_defaults(handler=lambda args: verify_index(args.metadata, args.dist))
    release = subparsers.add_parser("release-metadata")
    release.add_argument("--releases", type=Path, required=True)
    release.add_argument("--metadata", type=Path, required=True)
    release.add_argument("--downloads", type=Path, required=True)
    release.set_defaults(handler=_release_metadata_command)
    args: Any = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
