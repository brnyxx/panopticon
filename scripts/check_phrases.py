"""Fail if user-facing text contains forbidden verdict phrases (glossary.yaml `forbidden`)."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "src" / "panopticon"
GLOSSARY = yaml.safe_load((PACKAGE_ROOT / "i18n" / "glossary.yaml").read_text())
SCAN_PATHS = [
    PACKAGE_ROOT / "i18n",
    PACKAGE_ROOT / "reporters",
    PACKAGE_ROOT / "cli",
    REPO_ROOT / "site" / "content",
    REPO_ROOT / "site" / "template.html",
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "README.ko.md",
]


def _files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(candidate for candidate in path.rglob("*") if candidate.is_file())


def main() -> int:
    forbidden = GLOSSARY["forbidden"]["en"] + GLOSSARY["forbidden"]["ko"]
    bad = 0
    for path in SCAN_PATHS:
        for p in _files(path):
            if p.suffix not in {".html", ".json", ".md", ".py", ".yaml"}:
                continue
            if p.name == "glossary.yaml":
                continue
            text = p.read_text(encoding="utf-8")
            for phrase in forbidden:
                if phrase in text:
                    print(f"{p}: forbidden phrase {phrase!r}")
                    bad += 1
    print(f"scanned for {len(forbidden)} forbidden phrases, {bad} hit(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
