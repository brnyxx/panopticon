from __future__ import annotations

from pathlib import Path

from panopticon.analyzers.dependency.model import DependencyStatus
from panopticon.analyzers.dependency.scan import (
    AdvisoryResult,
    AdvisoryStatus,
    DependencyFinding,
    run_dependency_scan,
)


class FakeAdvisory:
    def __init__(self, result: AdvisoryResult) -> None:
        self.result = result
        self.calls = 0

    def check(self, requirements):
        self.calls += 1
        return self.result


def test_dependency_scan_uses_typed_advisory_and_preserves_input(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("Requests==2.31.0\n", encoding="utf-8")
    advisory = FakeAdvisory(
        AdvisoryResult(
            AdvisoryStatus.COMPLETE,
            "COMPLETE",
            (DependencyFinding("PYSEC-1", "requests", "HIGH", "known issue"),),
        )
    )

    result = run_dependency_scan(tmp_path, advisory)

    assert result.input.status is DependencyStatus.COMPLETE
    assert result.input.requirements[0].name == "requests"
    assert result.input.source_paths == ("requirements.txt",)
    assert result.advisory.status is AdvisoryStatus.COMPLETE
    assert result.advisory.findings[0].advisory_id == "PYSEC-1"
    assert advisory.calls == 1


def test_dependency_scan_missing_cache_and_offline_are_typed_without_provider_call(
    tmp_path: Path,
) -> None:
    (tmp_path / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")
    advisory = FakeAdvisory(AdvisoryResult(AdvisoryStatus.COMPLETE, "COMPLETE"))

    missing_cache = run_dependency_scan(tmp_path, advisory, cache_available=False)
    offline = run_dependency_scan(tmp_path, advisory, offline=True)
    missing_provider = run_dependency_scan(tmp_path, None)

    assert missing_cache.advisory.status is AdvisoryStatus.INCOMPLETE
    assert missing_cache.advisory.reason_code == "ADVISORY_CACHE_UNAVAILABLE"
    assert offline.advisory.status is AdvisoryStatus.UNSUPPORTED
    assert offline.advisory.reason_code == "OFFLINE"
    assert missing_provider.advisory.status is AdvisoryStatus.INCOMPLETE
    assert missing_provider.advisory.reason_code == "ADVISORY_PROVIDER_UNAVAILABLE"
    assert advisory.calls == 0
