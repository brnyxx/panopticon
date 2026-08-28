from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import release_preflight

SHA = "a" * 40


def _root(tmp_path: Path) -> Path:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    content = f"steps:\n  - uses: actions/checkout@{SHA}\n"
    for name in ("release.yml", "images.yml", "platform.yml", "ci.yml", "audit.yml"):
        (workflows / name).write_text(content, encoding="utf-8")
    return tmp_path


def _responses(conclusion: str) -> Any:
    def command(arguments: list[str]) -> Any:
        key = arguments[-1]
        if key == "repos/brnyxx/panopticon":
            return {"visibility": "public"}
        if key.endswith("private-vulnerability-reporting"):
            return {"enabled": True}
        if key.endswith("environments"):
            return {"environments": [{"name": name} for name in ("pypi", "release", "testpypi")]}
        if key == "repos/brnyxx/homebrew-tap":
            return {"visibility": "public"}
        if key.endswith("rulesets"):
            return [{"enforcement": "active", "_links": {"self": {"href": "ruleset"}}}]
        if key == "ruleset":
            return {
                "rules": [
                    {
                        "type": "required_status_checks",
                        "parameters": {
                            "required_status_checks": [
                                {"context": item} for item in release_preflight._REQUIRED_CHECKS
                            ]
                        },
                    }
                ]
            }
        if "--json" in arguments:
            return {"conclusion": conclusion, "headSha": SHA}
        raise AssertionError(arguments)

    return command


def test_preflight_accepts_exact_governance_and_rehearsal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(release_preflight, "_json_command", _responses("success"))

    result = release_preflight.evaluate("brnyxx/panopticon", 42, _root(tmp_path))

    assert result["status"] == "PASS"
    assert result["problems"] == []


def test_preflight_preserves_missing_publisher_as_blocker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(release_preflight, "_json_command", _responses("failure"))

    result = release_preflight.evaluate("brnyxx/panopticon", 42, _root(tmp_path))

    assert result["status"] == "BLOCKED"
    assert result["problems"] == ["TESTPYPI_TRUSTED_PUBLISHER_UNVERIFIED"]
