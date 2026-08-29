"""End-to-end contract tests for the composite GitHub action."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _action_run() -> str:
    action = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
    return action["runs"]["steps"][1]["run"]


def test_clean_checkout_action_uploads_valid_sarif() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    self_scan = workflow["jobs"]["self-scan"]
    steps = self_scan["steps"]
    assert steps[0]["uses"] == "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803"
    assert steps[1]["uses"] == "./"
    assert steps[1]["with"]["sarif"] == "pano.sarif"
    assert steps[2]["uses"] == (
        "github/codeql-action/upload-sarif@cdf488f595d80d6e07e03d4674febd5ab45fa938"
    )
    assert steps[2]["if"] == "always()"
    assert steps[2]["with"]["sarif_file"] == "pano.sarif"
    assert steps[1]["with"]["mode"] == "standard"


@pytest.mark.parametrize(
    ("mode", "extras"),
    [
        ("quick", []),
        ("standard", ["--extra", "static"]),
        ("deep", ["--extra", "static", "--extra", "semantic"]),
    ],
)
def test_action_selects_extras_for_scan_mode(tmp_path: Path, mode: str, extras: list[str]) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "uv").write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$@" > "$PANO_ARGS"\n', encoding="utf-8"
    )
    (fake_bin / "uv").chmod(0o755)
    output = tmp_path / "output"
    args = tmp_path / "args"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "GITHUB_ACTION_PATH": str(ROOT),
        "GITHUB_OUTPUT": str(output),
        "PANO_ARGS": str(args),
        "PANO_INPUT_PATH": ".",
        "PANO_INPUT_MODE": mode,
        "PANO_INPUT_SARIF": str(tmp_path / "report.sarif"),
        "PANO_INPUT_FAIL_ON": "high",
        "PANO_INPUT_CONFIG": "panopticon.toml",
    }

    completed = subprocess.run(["bash", "-c", _action_run()], env=env, check=False)

    assert completed.returncode == 0
    assert args.read_text(encoding="utf-8").splitlines() == [
        "run",
        "--directory",
        str(ROOT),
        *extras,
        "pano",
        "ci",
        ".",
        "--mode",
        mode,
        "--sarif",
        str(tmp_path / "report.sarif"),
        "--fail-on",
        "high",
        "--config",
        "panopticon.toml",
    ]


def test_malicious_action_input_cannot_execute_shell(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "uv").write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$@" > "$PANO_ARGS"\nexit 1\n', encoding="utf-8"
    )
    (fake_bin / "uv").chmod(0o755)
    output = tmp_path / "output"
    args = tmp_path / "args"
    marker = tmp_path / "injected"
    run = _action_run()
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "GITHUB_ACTION_PATH": str(ROOT),
        "GITHUB_OUTPUT": str(output),
        "PANO_ARGS": str(args),
        "PANO_INPUT_PATH": ".",
        "PANO_INPUT_MODE": f"standard; touch {marker}",
        "PANO_INPUT_SARIF": str(tmp_path / "report.sarif"),
        "PANO_INPUT_FAIL_ON": "high",
        "PANO_INPUT_CONFIG": "panopticon.toml",
    }
    completed = subprocess.run(["bash", "-c", run], env=env, check=False)
    assert completed.returncode == 1
    assert not marker.exists()
    assert output.read_text(encoding="utf-8") == f"sarif={tmp_path / 'report.sarif'}\n"
    assert f"standard; touch {marker}" in args.read_text(encoding="utf-8")
