"""Fail if the authoritative contract docs lost a frozen decision, marker, token, or link.

Structure only. Prose wording is not this checker's business, and the forbidden verdict
phrase authority for user-facing source stays `scripts/check_phrases.py`; this script
applies the same glossary to the contract documents it owns.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GLOSSARY = ROOT / "src" / "panopticon" / "i18n" / "glossary.yaml"

CHECKED_FILES = (
    "AGENTS.md",
    "ARCHITECTURE.md",
    "DESIGN.md",
    "PRODUCT.md",
    "README.md",
    "SECURITY.md",
    "docs/DECISIONS.md",
    "docs/PRODUCT_READINESS.md",
    "docs/PROGRESS.md",
    "docs/agent-guide.md",
    "docs/getting-started.ko.md",
    "docs/getting-started.md",
    "docs/limitations.md",
    "docs/privacy.md",
    "docs/release.md",
    "docs/release-maintainers.md",
    "panopticon-buildplan.md",
    "pyproject.toml",
)

# A backticked token is being named, not claimed: `OWNER` in a rule that forbids the
# placeholder, or `certified` in the list of forbidden verdict words. Only bare
# occurrences are defects, so the contract docs can state their own rules.
CODE_SPAN = re.compile(r"`[^`\n]*`")
PLACEHOLDERS = (
    re.compile(r"\bOWNER\b"),
    re.compile(r"<domain>"),
)

NAMESPACE_TOKENS = {
    "pyproject.toml": ("https://github.com/brnyxx/panopticon",),
    "SECURITY.md": ("brnyxx/panopticon", "ghcr.io/brnyxx"),
    "docs/PROGRESS.md": ("ghcr.io/brnyxx", "brnyxx/homebrew-tap"),
    "panopticon-buildplan.md": ("ghcr.io/brnyxx", "brnyxx/homebrew-tap"),
}

EPIC_MARKERS = ("### Scope", "### Interfaces", "### Tests", "### Definition of done")
EPICS = ("E17", "E18", "E19", "E20")

RULE_INVENTORY = (
    (re.compile(r"\|\s*\*\*Observe subtotal\*\*\s*\|\s*\*\*30\*\*\s*\|"), "observe subtotal 30"),
    (re.compile(r"\|\s*CFG\s*\|\s*12\s*\|"), "CFG 12"),
    (re.compile(r"\|\s*HIST\s*\|\s*4\s*\|"), "HIST 4"),
    (re.compile(r"\|\s*WATCH\s*\|\s*14\s*\|"), "WATCH 14"),
    (re.compile(r"\|\s*FIX\s*\|\s*6\s*\|"), "FIX 6"),
    (re.compile(r"\|\s*SENT\s*\|\s*11\s*\|"), "SENT 11"),
)

# Machine-consumed contract tokens: privacy, network, secret, schema, and protocol.
CONTRACT_TOKENS = {
    "ARCHITECTURE.md": (
        "installation_id",
        "server_id",
        "logical_key",
        "reason_code",
        "NOT_REQUESTED",
        "UNSUPPORTED",
        "SecretStore",
        "leak",
        "0.x",
        "2026-07-28",
        "--offline",
    ),
    "docs/privacy.md": (
        "--offline",
        "--real-env",
        "--real-env-all",
        "scan --mode deep",
        "api.osv.dev",
        "credential store",
    ),
    "docs/release.md": ("1.0.2", "uvx", "pipx", "Homebrew", "SHA256SUMS", "Sigstore"),
    "SECURITY.md": ("--real-env", "ghcr.io/brnyxx", "sandbox/images.lock"),
    "AGENTS.md": ("installation_id", "reason_code", "SecretStore", "store/", "e717e955"),
    "docs/limitations.md": ("UNSUPPORTED", "UNKNOWN", "PARTIAL"),
    "README.md": (
        "UNKNOWN",
        "INCOMPLETE",
        "scan --mode deep",
        "--offline",
        "e717e955",
    ),
    "docs/PRODUCT_READINESS.md": (
        "standard self-scan",
        "@brnyxx/panopticon",
        "Public verification for 1.0.2",
    ),
    "docs/getting-started.md": (
        "panopticon-mcp==1.0.2",
        "pano doctor --offline",
        "pano watch SERVER_NAME --offline",
        "reason_code",
        "~/.panopticon/",
    ),
    "docs/getting-started.ko.md": (
        "panopticon-mcp==1.0.2",
        "pano doctor --offline",
        "pano watch SERVER_NAME --offline",
        "reason_code",
        "~/.panopticon/",
    ),
    "docs/agent-guide.md": (
        "installation_id",
        "reason_code",
        "--real-env-all",
        "--allow-destructive",
        "pano fix SERVER_NAME --dry-run --offline",
    ),
    "DESIGN.md": ("d13edae8", "prefers-reduced-motion", "No telemetry"),
    "PRODUCT.md": ("1.0.2", "UNKNOWN", "INCOMPLETE", "--offline"),
    "docs/release-maintainers.md": (
        "source_run_id",
        "source_sha",
        "NPM_PACKAGE_BOOTSTRAP_REQUIRED",
        "homebrew-handoff",
    ),
}

DECISION_HEADING = re.compile(r"^#{2,3} (\d+[a-z]?)\. ", re.M)
EPIC_HEADING = "^## \\d+\\. {epic} .*?(?=^## |\\Z)"
CHOSEN = re.compile(r"^- Chosen: (.+)$", re.M)
UNRESOLVED = re.compile(r"\bTBD\b|\bTODO\b|\bdecide\b", re.I)

# Match the destination directly, so a target nested behind an image label -
# GitHub's badge idiom `[![alt](badge-url)](target)` - is resolved too.
LINK = re.compile(r"\]\(([^)\s]+)")
# GitHub renders inline HTML in Markdown; README embeds its artwork that way.
HTML_IMAGE = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.I | re.S)
RAW_REPOSITORY_PREFIX = "https://raw.githubusercontent.com/brnyxx/panopticon/main/"


def _read(root: Path, rel: str) -> str | None:
    path = root / rel
    return path.read_text(encoding="utf-8") if path.is_file() else None


def _forbidden_phrases() -> list[str]:
    glossary = yaml.safe_load(GLOSSARY.read_text(encoding="utf-8"))
    forbidden: list[str] = glossary["forbidden"]["en"] + glossary["forbidden"]["ko"]
    return forbidden


def _check_decisions(text: str) -> list[str]:
    problems: list[str] = []
    ids = DECISION_HEADING.findall(text)
    if not ids:
        problems.append("docs/DECISIONS.md: no numbered decisions found")
    for number, chosen in zip(ids, CHOSEN.findall(text), strict=False):
        if UNRESOLVED.search(chosen):
            problems.append(f"docs/DECISIONS.md: unresolved decision {number}")
    if len(CHOSEN.findall(text)) != len(ids):
        problems.append("docs/DECISIONS.md: every decision needs exactly one Chosen line")
    return problems


def _check_links(root: Path, rel: str, text: str) -> list[str]:
    base = (root / rel).parent
    problems: list[str] = []
    for kind, pattern in (("relative link", LINK), ("image source", HTML_IMAGE)):
        for target in pattern.findall(text):
            href = target.split("#")[0]
            if href.startswith(RAW_REPOSITORY_PREFIX):
                display = href.removeprefix(RAW_REPOSITORY_PREFIX)
                resolved = root / display
            elif not href or "://" in href or href.startswith(("#", "mailto:", "data:")):
                continue
            else:
                display = href
                resolved = base / href
            if not resolved.exists():
                problems.append(f"{rel}: unresolvable {kind} {display}")
    return problems


def check(root: Path) -> list[str]:
    """Return every contract problem found under `root`, sorted for deterministic output."""
    problems: list[str] = []
    forbidden = _forbidden_phrases()

    for rel in CHECKED_FILES:
        text = _read(root, rel)
        if text is None:
            problems.append(f"{rel}: missing authoritative file")
            continue

        prose = CODE_SPAN.sub("``", text)
        for phrase in forbidden:
            if phrase in prose:
                problems.append(f"{rel}: forbidden verdict phrase {phrase!r}")
        for pattern in PLACEHOLDERS:
            if pattern.search(prose):
                problems.append(f"{rel}: unresolved placeholder {pattern.pattern}")
        for token in NAMESPACE_TOKENS.get(rel, ()):
            if token not in text:
                problems.append(f"{rel}: missing authorized namespace {token}")
        for token in CONTRACT_TOKENS.get(rel, ()):
            if token not in text:
                problems.append(f"{rel}: missing contract token {token}")
        if rel.endswith(".md"):
            problems.extend(_check_links(root, rel, text))

    decisions = _read(root, "docs/DECISIONS.md")
    if decisions is not None:
        problems.extend(_check_decisions(decisions))

    plan = _read(root, "panopticon-buildplan.md")
    if plan is not None:
        for epic in EPICS:
            found = re.search(EPIC_HEADING.format(epic=epic), plan, flags=re.M | re.S)
            if found is None:
                problems.append(f"panopticon-buildplan.md: {epic} has no numbered section")
                continue
            for marker in EPIC_MARKERS:
                if marker not in found.group(0):
                    problems.append(f"panopticon-buildplan.md: {epic} missing {marker}")
        for pattern, label in RULE_INVENTORY:
            if not pattern.search(plan):
                problems.append(f"panopticon-buildplan.md: rule inventory row {label} not found")

    return sorted(problems)


def main(root: Path = ROOT) -> int:
    problems = check(root)
    for problem in problems:
        print(problem)
    print(f"checked {len(CHECKED_FILES)} authoritative files, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
