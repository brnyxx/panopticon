"""Fail if i18n/ko/rules and i18n/en/rules have different rule-doc sets or section structures."""

from __future__ import annotations

import re
import sys
from pathlib import Path

I18N = Path(__file__).resolve().parents[1] / "src" / "panopticon" / "i18n"
SECTIONS_EN = ["Problem", "Impact", "Evidence", "Recommended action", "How to verify", "Limits"]
SECTIONS_KO = ["문제", "영향", "근거", "권장 조치", "확인 방법", "제한"]


def sections(text: str) -> list[str]:
    return re.findall(r"^## (.+)$", text, flags=re.M)


def main() -> int:
    ko = {p.stem: p for p in (I18N / "ko" / "rules").glob("*.md")}
    en = {p.stem: p for p in (I18N / "en" / "rules").glob("*.md")}
    bad = 0
    if ko.keys() != en.keys():
        print(
            f"rule doc mismatch: only-ko={sorted(ko.keys() - en.keys())} "
            f"only-en={sorted(en.keys() - ko.keys())}"
        )
        bad += 1
    for rid in ko.keys() & en.keys():
        if sections(en[rid].read_text()) != SECTIONS_EN:
            print(f"{rid}: en sections must be {SECTIONS_EN}")
            bad += 1
        if sections(ko[rid].read_text()) != SECTIONS_KO:
            print(f"{rid}: ko sections must be {SECTIONS_KO}")
            bad += 1
    print(f"checked {len(ko.keys() & en.keys())} rule docs")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
