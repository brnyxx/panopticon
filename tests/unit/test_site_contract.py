"""Static landing source and deployment contracts."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (ROOT / "site/template.html").read_text(encoding="utf-8")
CSS = (ROOT / "site/assets/site.css").read_text(encoding="utf-8")
JAVASCRIPT = (ROOT / "site/assets/site.js").read_text(encoding="utf-8")
KOREAN = (ROOT / "site/content/ko.json").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
FULL_SHA = re.compile(r"uses: [\w-]+/[\w-]+@[0-9a-f]{40}$", re.MULTILINE)


def test_template_has_semantic_landmarks_and_frozen_seed() -> None:
    assert "impeccable:seed d13edae8" in TEMPLATE
    for landmark in ("<header", "<nav", "<main", "<section", "<aside", "<footer"):
        assert landmark in TEMPLATE
    assert 'class="skip-link"' in TEMPLATE
    assert '<h1 id="hero-title">' in TEMPLATE
    assert '<meta name="theme-color" content="#010714">' in TEMPLATE
    assert '<meta name="color-scheme" content="dark">' in TEMPLATE
    assert '<meta property="og:image"' in TEMPLATE
    assert '<meta name="twitter:card" content="summary_large_image">' in TEMPLATE
    assert "assets/social-card.png" in TEMPLATE
    assert "assets/logo-32.png" in TEMPLATE
    assert 'rel="icon"' in TEMPLATE
    assert 'class="ledger-mark"' in TEMPLATE
    assert "▤" not in TEMPLATE


def test_commands_and_observation_contract_are_machine_visible() -> None:
    for placeholder in (
        "{{install}}",
        "{{doctor}}",
        "{{watch}}",
        "{{tool}}",
        "{{complete}}",
        "{{completed}}",
        "{{unsupported}}",
        "{{runtime_unavailable}}",
        "{{incomplete}}",
        "{{timeout}}",
        "{{unknown}}",
        "{{brand_promise}}",
        "{{target}}",
        "{{decoy_signal_rule}}",
    ):
        assert placeholder in TEMPLATE
    assert TEMPLATE.count('data-copy-target="') == 10
    assert TEMPLATE.count('aria-describedby="') == 10
    copy_labels = re.findall(r'aria-label="{{(copy_[^}]+)}}"', TEMPLATE)
    assert len(copy_labels) == len(set(copy_labels)) == 10
    assert 'class="primary-link" href="#start"' in TEMPLATE
    assert TEMPLATE.count('data-copy-target="install-command"') == 1
    assert 'id="record" class="dimension-section"' in TEMPLATE
    assert 'href="#record"' in TEMPLATE
    assert "<caption>{{example_caption}}</caption>" in TEMPLATE
    assert 'role="region" aria-label="{{table_scroll_label}}"' in TEMPLATE


def test_complete_onboarding_and_agent_routes_are_visible() -> None:
    for section in (
        'class="prerequisite-section"',
        'class="install-options-section"',
        'class="command-map-section"',
        'class="agent-section"',
        'id="guides"',
    ):
        assert section in TEMPLATE
    for command in (
        "{{install_uvx}}",
        "{{install}}",
        "{{install_pipx}}",
        "{{install_brew}}",
        "{{doctor}}",
        "{{watch}}",
        "{{command_baseline}}",
        "{{command_diff}}",
        "{{command_scan}}",
        "{{command_fix}}",
    ):
        assert command in TEMPLATE
    assert "{{getting_started_url}}" in TEMPLATE
    assert "docs/agent-guide.md" in TEMPLATE
    assert "{{footer_scope}}" in TEMPLATE
    assert "releases/tag/v1.0.1" in TEMPLATE
    assert TEMPLATE.index('id="start" class="prerequisite-section"') < TEMPLATE.index(
        'class="runway-section"'
    )
    assert " · " not in TEMPLATE


def test_copy_and_tabs_expose_keyboard_and_fallback_hooks() -> None:
    assert 'role="tablist"' in TEMPLATE
    assert TEMPLATE.count('role="tab"') == 4
    assert TEMPLATE.count('role="tabpanel"') == 4
    assert "ArrowRight" in JAVASCRIPT
    assert "ArrowLeft" in JAVASCRIPT
    assert 'event.key === "Home"' in JAVASCRIPT
    assert 'event.key === "End"' in JAVASCRIPT
    assert "navigator.clipboard.writeText" in JAVASCRIPT
    assert "setTemporaryState(button.dataset.copySuccess, button.dataset.copySuccess)" in JAVASCRIPT
    assert "selectText(target)" in JAVASCRIPT
    assert 'getElementById(button.getAttribute("aria-describedby"))' in JAVASCRIPT
    assert 'role="status" aria-live="polite"' in TEMPLATE


def test_browser_runtime_has_no_remote_resources_or_tracking_apis() -> None:
    assert 'src="http' not in TEMPLATE
    assert 'href="http' not in "\n".join(
        line for line in TEMPLATE.splitlines() if "stylesheet" in line
    )
    forbidden = (
        "fetch(",
        "XMLHttpRequest",
        "sendBeacon",
        "localStorage",
        "sessionStorage",
        "document.cookie",
    )
    assert not any(token in JAVASCRIPT for token in forbidden)


def test_accessibility_and_responsive_contracts_are_explicit() -> None:
    assert ":focus-visible" in CSS
    assert "min-height: 44px" in CSS
    assert "@media (max-width: 1279px)" in CSS
    assert "@media (max-width: 767px)" in CSS
    assert "@media (max-width: 420px)" in CSS
    assert "prefers-reduced-motion: reduce" in CSS
    assert "scroll-behavior: auto !important" in CSS
    assert "overflow-x: auto" in CSS
    assert 'class="eyebrow"' not in TEMPLATE
    assert "→" not in TEMPLATE
    assert "↗" not in TEMPLATE
    assert ".arrow-forward::before" in CSS
    assert ".arrow-external::before" in CSS
    assert "@keyframes evidence-resolve" in CSS
    assert "@keyframes signal-resolve" in CSS
    assert "animation: signal-resolve 520ms 650ms" in CSS
    assert "nth-child(4) .status { animation-delay: 580ms; }" in CSS
    assert "읽기 전용 이중 언어 규칙 문서" in KOREAN
    assert "Read-only bilingual rule document" not in KOREAN


def test_pages_workflow_is_sha_pinned_and_least_privilege() -> None:
    uses = [line.strip().removeprefix("- ") for line in WORKFLOW.splitlines() if "uses:" in line]
    assert len(uses) == 4
    assert all(FULL_SHA.fullmatch(line) for line in uses)
    assert "contents: read" in WORKFLOW
    assert "pages: write" in WORKFLOW
    assert "id-token: write" in WORKFLOW
    assert "name: github-pages" in WORKFLOW
    assert "url: ${{ steps.deployment.outputs.page_url }}" in WORKFLOW
    assert "if: github.ref == 'refs/heads/main'" in WORKFLOW
    assert "group: pages" in WORKFLOW
    assert "cancel-in-progress: false" in WORKFLOW
