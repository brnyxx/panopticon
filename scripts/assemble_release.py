"""CLI for validating the exact build-once release asset set."""

from __future__ import annotations

import argparse
from pathlib import Path

from panopticon.release import assemble_release


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    assembly = assemble_release(args.assets, args.commit)
    (args.assets / "SHA256SUMS").write_text(
        assembly.checksums,
        encoding="utf-8",
        newline="\n",
    )
    (args.assets / "release-manifest.json").write_bytes(assembly.manifest_bytes)


if __name__ == "__main__":
    main()
