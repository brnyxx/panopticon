"""Fail if user-facing text contains forbidden verdict phrases (glossary.yaml `forbidden`)."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1] / "src" / "panopticon"
GLOSSARY = yaml.safe_load((ROOT / "i18n" / "glossary.yaml").read_text())
SCAN_DIRS = [ROOT / "i18n", ROOT / "reporters", ROOT / "cli"]


def main() -> int:
    forbidden = GLOSSARY["forbidden"]["en"] + GLOSSARY["forbidden"]["ko"]
    bad = 0
    for d in SCAN_DIRS:
        for p in d.rglob("*"):
            if p.suffix not in {".md", ".py", ".yaml"} or p.name == "glossary.yaml":
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
