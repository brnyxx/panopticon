"""Write the canonical release version to GitHub Actions outputs."""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path
from typing import Any

from panopticon.release import validate_version


def release_version() -> str:
    project_file = Path(__file__).resolve().parents[1] / "pyproject.toml"
    with project_file.open("rb") as stream:
        document: Any = tomllib.load(stream)
    project = document.get("project") if isinstance(document, dict) else None
    version = project.get("version") if isinstance(project, dict) else None
    if not isinstance(version, str):
        raise ValueError("INVALID_RELEASE_VERSION")
    return validate_version(version)


def main_for_output(github_output: Path) -> None:
    if not github_output.parent.is_dir():
        raise ValueError("GITHUB_OUTPUT_PARENT_MISSING")
    version = release_version()
    existing = github_output.read_bytes() if github_output.exists() else b""
    with github_output.open("ab") as output:
        if existing and not existing.endswith(b"\n"):
            output.write(b"\n")
        output.write(
            f"version={version}\ntag=v{version}\nbundle_name=release-bundle-{version}\n".encode()
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args()
    main_for_output(args.github_output)


if __name__ == "__main__":
    main()
