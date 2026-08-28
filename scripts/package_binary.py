"""CLI for deterministic native executable archives."""

from __future__ import annotations

import argparse
from pathlib import Path

from panopticon.release import build_binary_archive


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    archive = build_binary_archive(Path.cwd(), args.binary, args.target)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(archive)


if __name__ == "__main__":
    main()
