"""Generate Formula/panopticon.rb from a verified release manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from panopticon.release import render_formula


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document: Any = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("version") != "1.0.0":
        raise ValueError("INVALID_RELEASE_MANIFEST")
    hashes = document.get("assets")
    if not isinstance(hashes, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in hashes.items()
    ):
        raise ValueError("INVALID_RELEASE_MANIFEST")
    formula = render_formula(
        hashes,
        "https://github.com/brnyxx/panopticon/releases/download/v1.0.0/",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(formula, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
