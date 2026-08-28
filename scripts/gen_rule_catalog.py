"""Generate docs/rules/CATALOG.md from the registry."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from panopticon.i18n.catalog import CATALOG  # noqa: E402


def main() -> int:
    lines = [
        "# Rule catalog (generated)",
        "",
        "| ID | line | severity | kind | fix |",
        "|---|---|---|---|---|",
    ]
    for meta in CATALOG:
        severity = meta.severity or "—"
        kind = meta.kind or "—"
        fix_id = meta.fix_id or "—"
        lines.append(f"| {meta.rule_id} | {meta.line} | {severity} | {kind} | {fix_id} |")
    out = ROOT / "docs" / "rules" / "CATALOG.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
