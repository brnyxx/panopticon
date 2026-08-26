"""Validate every schema in schemas/ against the 2020-12 metaschema and resolve $refs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1] / "schemas"


def main() -> int:
    resources = []
    for p in sorted(ROOT.glob("*.json")):
        doc = json.loads(p.read_text())
        Draft202012Validator.check_schema(doc)
        resources.append((p.name, Resource.from_contents(doc)))
    registry = Registry().with_resources(resources)
    for name, res in resources:
        Draft202012Validator(res.contents, registry=registry)
        print(f"ok  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
