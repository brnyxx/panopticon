"""The docs contract checker must reject a corrupted doc tree and accept the real one.

Tests assert machine-consumed diagnostics and exit codes only, never prose wording.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from check_docs import CHECKED_FILES, CONTRACT_TOKENS, check, main

ROOT = Path(__file__).resolve().parents[2]

# README joined the authoritative surface once its visuals and contract copy landed.
EXPECTED_AUTHORITATIVE_FILES = 10

# Every README contract token must be a machine-consumed identifier: a state name the
# renderer emits, a command a user types, or the pinned upstream hash. Natural-language
# tokens pin prose, so a legitimate rewording breaks the checker instead of the contract.
README_CONTRACT_TOKENS = (
    "UNKNOWN",
    "INCOMPLETE",
    "scan --mode deep",
    "--offline",
    "e717e955",
)

README_ASSETS = (
    ".github/assets/hero.svg",
    ".github/assets/logo.svg",
    ".github/assets/panopticon.png",
)

# Paths README links to or embeds that are not themselves authoritative documents.
# The checker only resolves these paths, so the fixture stands them up empty rather
# than copying 2 MB of artwork into every test.
README_LINKED_PATHS = (*README_ASSETS, "LICENSE", "THIRD_PARTY_NOTICES.md")


@pytest.fixture
def doc_tree(tmp_path: Path) -> Path:
    """A copy of the authoritative doc surface plus the exact paths README references."""
    for rel in CHECKED_FILES:
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, dst)
    for rel in README_LINKED_PATHS:
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.touch()
    return tmp_path


def test_docs_checker_accepts_the_repository() -> None:
    # Given: the authoritative docs in this repository
    # When: the checker runs over them
    problems = check(ROOT)
    # Then: it reports no problem
    assert problems == []


def test_temporary_fixture_starts_clean(doc_tree: Path) -> None:
    # Given: the fixture tree before any defect is injected
    # When: the checker runs over it
    problems = check(doc_tree)
    # Then: it is clean, so every other test's finding is caused by its own injection
    assert problems == []


def test_readme_contract_tokens_are_machine_consumed_only() -> None:
    # Given: the checker's frozen README contract-token set
    # When/Then: it is exactly the stable identifiers, commands, and hash - no prose
    assert CONTRACT_TOKENS["README.md"] == README_CONTRACT_TOKENS


def test_readme_is_part_of_the_authoritative_surface() -> None:
    # Given: the checker's declared authoritative file set
    # When/Then: README is in it and the surface is exactly ten files
    assert "README.md" in CHECKED_FILES
    assert len(CHECKED_FILES) == EXPECTED_AUTHORITATIVE_FILES


def test_docs_checker_rejects_forbidden_phrase_and_owner_placeholder(doc_tree: Path) -> None:
    # Given: a doc tree carrying a forbidden verdict phrase and an unresolved OWNER placeholder
    security = doc_tree / "SECURITY.md"
    security.write_text(
        security.read_text(encoding="utf-8")
        + "\nThis release is certified and the server is 100% secure.\n"
        + "Homepage: https://github.com/OWNER/panopticon\n",
        encoding="utf-8",
    )
    # When: the checker runs over the corrupted tree
    problems = check(doc_tree)
    # Then: it names both defect classes against that exact file, deterministically ordered
    assert any(p.startswith("SECURITY.md: forbidden verdict phrase") for p in problems), problems
    assert any(p.startswith("SECURITY.md: unresolved placeholder") for p in problems), problems
    assert problems == sorted(problems)


def test_exit_code_is_nonzero_when_a_doc_is_missing(doc_tree: Path) -> None:
    # Given: an authoritative file removed from the tree
    (doc_tree / "ARCHITECTURE.md").unlink()
    # When: the checker's process entry point runs
    code = main(doc_tree)
    # Then: it exits nonzero and names the missing path
    assert code == 1
    assert any(p.startswith("ARCHITECTURE.md: missing") for p in check(doc_tree))


def test_unresolved_decision_is_rejected(doc_tree: Path) -> None:
    # Given: an accepted decision reverted to an unresolved marker
    decisions = doc_tree / "docs/DECISIONS.md"
    decisions.write_text(
        decisions.read_text(encoding="utf-8").replace(
            "- Chosen: **`ghcr.io/brnyxx`**", "- Chosen: **TBD**"
        ),
        encoding="utf-8",
    )
    # When: the checker runs
    problems = check(doc_tree)
    # Then: it reports the unresolved decision
    assert any("unresolved decision" in p for p in problems), problems


def test_wrong_namespace_is_rejected(doc_tree: Path) -> None:
    # Given: a release URL pointing at a namespace that is not the authorized one
    pyproject = doc_tree / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8").replace(
            "https://github.com/brnyxx/panopticon", "https://github.com/someone-else/panopticon"
        ),
        encoding="utf-8",
    )
    # When: the checker runs
    problems = check(doc_tree)
    # Then: it reports the missing authorized namespace
    assert any("brnyxx" in p for p in problems), problems


def test_missing_epic_section_marker_is_rejected(doc_tree: Path) -> None:
    # Given: E19 stripped of its definition-of-done marker
    plan = doc_tree / "panopticon-buildplan.md"
    body = plan.read_text(encoding="utf-8")
    head, _, tail = body.rpartition("### Definition of done")
    plan.write_text(head + "### Closing notes" + tail, encoding="utf-8")
    # When: the checker runs
    problems = check(doc_tree)
    # Then: it reports the epic missing its required marker
    assert any(p.startswith("panopticon-buildplan.md: E19 missing") for p in problems), problems


def test_wrong_rule_inventory_total_is_rejected(doc_tree: Path) -> None:
    # Given: the observe subtotal changed without amending the family counts
    plan = doc_tree / "panopticon-buildplan.md"
    plan.write_text(
        plan.read_text(encoding="utf-8").replace(
            "| **Observe subtotal** | **30** |", "| **Observe subtotal** | **29** |"
        ),
        encoding="utf-8",
    )
    # When: the checker runs
    problems = check(doc_tree)
    # Then: it reports the inventory mismatch
    assert any("rule inventory" in p for p in problems), problems


def test_broken_relative_link_is_rejected(doc_tree: Path) -> None:
    # Given: a Markdown relative link to a file that does not exist
    limitations = doc_tree / "docs/limitations.md"
    limitations.write_text(
        limitations.read_text(encoding="utf-8") + "\nSee [gone](./does-not-exist.md).\n",
        encoding="utf-8",
    )
    # When: the checker runs
    problems = check(doc_tree)
    # Then: it reports the unresolvable link target
    assert any("does-not-exist.md" in p for p in problems), problems


def test_broken_link_nested_inside_a_badge_is_rejected(doc_tree: Path) -> None:
    # Given: README's badge row, where the link target sits behind an image label
    readme = doc_tree / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace("](LICENSE)", "](LICENCE)"),
        encoding="utf-8",
    )
    # When: the checker runs
    problems = check(doc_tree)
    # Then: the nested target is still resolved and reported
    assert "README.md: unresolvable relative link LICENCE" in problems, problems


def test_broken_html_image_source_is_rejected(doc_tree: Path) -> None:
    # Given: a README HTML <img> pointing at an asset that does not exist
    readme = doc_tree / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace(
            ".github/assets/hero.svg", ".github/assets/missing-hero.svg"
        ),
        encoding="utf-8",
    )
    # When: the checker runs
    problems = check(doc_tree)
    # Then: it reports that image source as unresolvable
    assert "README.md: unresolvable image source .github/assets/missing-hero.svg" in problems


@pytest.mark.parametrize("asset", README_ASSETS)
def test_every_readme_asset_must_resolve(doc_tree: Path, asset: str) -> None:
    # Given: one of the three shipped README assets removed from the tree
    (doc_tree / asset).unlink()
    # When: the checker runs
    problems = check(doc_tree)
    # Then: it reports exactly that asset as unresolvable
    assert f"README.md: unresolvable image source {asset}" in problems, problems


@pytest.mark.parametrize("token", README_CONTRACT_TOKENS)
def test_readme_missing_contract_token_is_rejected(doc_tree: Path, token: str) -> None:
    # Given: README with one frozen contract token removed
    readme = doc_tree / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace(token, "..."),
        encoding="utf-8",
    )
    # When: the checker runs
    problems = check(doc_tree)
    # Then: it names that exact token
    assert f"README.md: missing contract token {token}" in problems, problems


def test_missing_contract_token_is_rejected(doc_tree: Path) -> None:
    # Given: the secret-store contract removed from the architecture document
    architecture = doc_tree / "ARCHITECTURE.md"
    architecture.write_text(
        architecture.read_text(encoding="utf-8").replace("SecretStore", "credential helper"),
        encoding="utf-8",
    )
    # When: the checker runs
    problems = check(doc_tree)
    # Then: it reports the absent contract token
    assert any("SecretStore" in p for p in problems), problems


def test_cli_surface_exits_zero_with_a_deterministic_summary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: the checker entry point aimed at the real repository
    # When: it runs twice
    codes: list[int] = []
    outputs: list[str] = []
    for _ in range(2):
        codes.append(main(ROOT))
        outputs.append(capsys.readouterr().out)
    # Then: both exit 0 with identical output stating the frozen checked-file count
    assert codes == [0, 0], outputs
    assert outputs[0] == outputs[1]
    assert outputs[0] == "checked 10 authoritative files, 0 problem(s)\n"
