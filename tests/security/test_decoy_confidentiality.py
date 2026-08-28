from __future__ import annotations

from pathlib import Path

import pytest

from panopticon.sandbox.decoy import decoy_archive, generate_decoy_home
from panopticon.util.leak_check import LeakContext, LeakError, assert_clean


def test_real_home_and_env_are_rejected_before_persistence() -> None:
    home = str(Path.home())
    real_environment_value = "real-environment-value-for-boundary-test"
    manifest = generate_decoy_home(
        "confidentiality-seed",
        "confidentiality-run",
        project_filenames=("src/server.py", ".env.example"),
    )
    archive = decoy_archive(manifest)

    assert home.encode() not in archive
    assert real_environment_value.encode() not in archive
    assert all(home not in value for value in manifest.env.values())
    with pytest.raises(LeakError):
        assert_clean(home, LeakContext(home_paths=(home,)))
    with pytest.raises(LeakError):
        assert_clean(
            real_environment_value,
            LeakContext(secrets=(real_environment_value,)),
        )
