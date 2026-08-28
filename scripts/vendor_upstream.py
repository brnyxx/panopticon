"""Copy the approved MCP-Sentinel replay corpus from its pinned clean clone."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

COMMIT = "e717e955210b1d2a3e9fb1cdc266587c77ffebf3"
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-clone", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=Path("tests/upstream"))
    args = parser.parse_args()
    official_manifest()
    copied = vendor(args.source_clone.resolve(), args.destination.resolve())
    print(f"vendored {len(copied)} exact files from {COMMIT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
