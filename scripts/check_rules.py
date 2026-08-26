"""Every registered rule must have ko+en explain docs and ≥1 positive and ≥1 negative fixture.

Fixture convention: tests/fixtures/rules/<RULE-ID>/positive_*.json and negative_*.json
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import panopticon.analyzers as analyzers  # noqa: E402
from panopticon.rules.registry import all_rules  # noqa: E402


def import_all_rules() -> None:
    for m in pkgutil.walk_packages(analyzers.__path__, analyzers.__name__ + "."):
        if m.name.endswith(".rules"):
            importlib.import_module(m.name)


def main() -> int:
    import_all_rules()
    rules = all_rules()
    i18n = ROOT / "src" / "panopticon" / "i18n"
    fx = ROOT / "tests" / "fixtures" / "rules"
    bad = 0
    for rid in sorted(rules):
        for lang in ("ko", "en"):
            if not (i18n / lang / "rules" / f"{rid}.md").exists():
                print(f"{rid}: missing {lang} explain doc")
                bad += 1
        d = fx / rid
        if not list(d.glob("positive_*")) or not list(d.glob("negative_*")):
            print(f"{rid}: needs positive_* and negative_* fixtures under {d}")
            bad += 1
    print(f"{len(rules)} rules registered, {bad} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
