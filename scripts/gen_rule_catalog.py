"""Generate docs/rules/CATALOG.md from the registry."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from check_rules import import_all_rules  # noqa: E402

from panopticon.rules.registry import all_rules  # noqa: E402


def main() -> int:
    import_all_rules()
    lines = [
        "# Rule catalog (generated)",
        "",
        "| ID | line | severity | kind | fix |",
        "|---|---|---|---|---|",
    ]
    for rid, (meta, _) in sorted(all_rules().items()):
        lines.append(
            f"| {rid} | {meta.line} | {meta.severity or '—'} | {meta.kind} | {meta.fix_id or '—'} |"
        )
    out = ROOT / "docs" / "rules" / "CATALOG.md"
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
