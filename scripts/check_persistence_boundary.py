# /// script
# requires-python = ">=3.11"
# ///
# ─── How to run ───
# uv run python scripts/check_persistence_boundary.py [paths...]
"""CLI wrapper for the direct-persistence machine checker."""

from panopticon.checks.persistence_boundary import ROOT, scan

violations = scan()
for violation in violations:
    display = (
        violation.path.relative_to(ROOT) if violation.path.is_relative_to(ROOT) else violation.path
    )
    print(f"DIRECT_PERSISTENCE {display}:{violation.line}: {violation.call}")
raise SystemExit(1 if violations else 0)
