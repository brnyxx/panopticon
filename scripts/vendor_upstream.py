"""Copy the approved MCP-Sentinel replay corpus from its pinned clean clone."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

COMMIT = "e717e955210b1d2a3e9fb1cdc266587c77ffebf3"
OFFICIAL_CURRENT_COMMIT = "cda92bdaacd558192fedf1a60d2bb27510792388"
OFFICIAL_ARCHIVE_COMMIT = "1f705677a930ec618b7a16d87d00cee7db747ff2"
OFFICIAL_MANIFEST = Path("tests/fixtures/mcp/official/manifest.json")


def _git(clone: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(clone), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _selected_files(clone: Path) -> tuple[Path, ...]:
    selected: list[Path] = []
    source = clone / "src" / "sentinel"
    selected.extend(
        path
        for path in source.rglob("*")
        if path.is_file()
        and (path.suffix == ".py" or path.suffix == ".yaml" or "_cassettes/demo" in path.as_posix())
        and path.name != "__main__.py"
    )
    tests = clone / "tests"
    selected.extend(
        path
        for path in tests.rglob("*")
        if path.is_file()
        and "tests/evals/" not in path.as_posix()
        and "__pycache__" not in path.parts
    )
    selected.extend(
        clone / "scripts" / name
        for name in ("__init__.py", "capture_gpt_reviews.py", "run_github_action.py")
    )
    selected.extend((clone / "schemas").glob("*.json"))
    selected.extend((clone / name) for name in ("LICENSE", "action.yml"))
    return tuple(sorted(set(selected)))


def vendor(clone: Path, destination: Path) -> tuple[Path, ...]:
    if _git(clone, "rev-parse", "HEAD") != COMMIT:
        raise ValueError("upstream clone is not at the approved commit")
    if _git(clone, "status", "--porcelain"):
        raise ValueError("upstream clone must be clean")
    if destination.exists():
        shutil.rmtree(destination)
    copied: list[Path] = []
    for source in _selected_files(clone):
        relative = source.relative_to(clone)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied.append(target)
    return tuple(copied)


def official_manifest(path: Path = OFFICIAL_MANIFEST) -> dict[str, object]:
    """Read the separately audited official-server provenance manifest."""
    import json

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("official manifest schema unsupported")
    servers = value.get("servers")
    if not isinstance(servers, list):
        raise ValueError("official manifest servers must be an array")
    names = {item.get("name") for item in servers if isinstance(item, dict)}
    if len(servers) != 5 or names != {"filesystem", "github", "fetch", "memory", "sqlite"}:
        raise ValueError("official manifest must describe exactly five servers")
    return value


def vendor_official_sources(
    current_clone: Path, archive_clone: Path, destination: Path
) -> tuple[Path, ...]:
    """Explicitly acquire the five official source trees into an offline cache.

    The clones must already have been fetched by the caller. This function never
    performs network access and accepts only the two audited repository commits.
    """
    if _git(current_clone, "rev-parse", "HEAD") != OFFICIAL_CURRENT_COMMIT:
        raise ValueError("current official clone is not at the audited commit")
    if _git(archive_clone, "rev-parse", "HEAD") != OFFICIAL_ARCHIVE_COMMIT:
        raise ValueError("archived official clone is not at the audited commit")
    for clone in (current_clone, archive_clone):
        if _git(clone, "status", "--porcelain"):
            raise ValueError("official clone must be clean")
    destination.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for name, clone in (
        *((name, current_clone) for name in ("filesystem", "memory", "fetch")),
        *((name, archive_clone) for name in ("github", "sqlite")),
    ):
        source = clone / "src" / name
        if not source.exists():
            continue
        target = destination / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
        copied.extend(path for path in target.rglob("*") if path.is_file())
    return tuple(copied)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-clone", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=Path("tests/upstream"))
    parser.add_argument("--official-current-clone", type=Path)
    parser.add_argument("--official-archive-clone", type=Path)
    parser.add_argument(
        "--official-destination", type=Path, default=Path("tests/fixtures/mcp/official/cache")
    )
    args = parser.parse_args()
    official_manifest()
    copied = vendor(args.source_clone.resolve(), args.destination.resolve())
    print(f"vendored {len(copied)} exact files from {COMMIT}")
    if args.official_current_clone is not None or args.official_archive_clone is not None:
        if args.official_current_clone is None or args.official_archive_clone is None:
            parser.error("--official-current-clone and --official-archive-clone are paired")
        official = vendor_official_sources(
            args.official_current_clone.resolve(),
            args.official_archive_clone.resolve(),
            args.official_destination.resolve(),
        )
        print(f"vendored {len(official)} official source files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
