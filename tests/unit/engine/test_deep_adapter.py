from pathlib import Path

from panopticon.analyzers.semantic.reviewer import ReviewOutcome, SemanticStatus
from panopticon.engine.deep import SemanticDeepPort
from panopticon.engine.scan import DeepDimensionStatus, ScanFinding
from panopticon.models.finding import Finding


class Reviewer:
    def __init__(self, root: Path, outcome: ReviewOutcome) -> None:
        self.root = root
        self.outcome = outcome
        self.seen: tuple[Finding, ...] | None = None

    async def review(self, findings: tuple[Finding, ...]) -> ReviewOutcome:
        self.seen = findings
        return self.outcome


def finding(
    rule: str = "SENT-001",
    path: str | None = "src/a.py",
    line: int | None = 0,
    column: int | None = 0,
    severity: str = "high",
) -> ScanFinding:
    return ScanFinding(rule, "title", severity, "fp", path, line, column)


def test_root_mismatch_is_deterministic_and_does_not_review(tmp_path: Path) -> None:
    reviewer = Reviewer(tmp_path, ReviewOutcome(SemanticStatus.COMPLETE, "ok", ()))
    result = SemanticDeepPort(reviewer).analyze(tmp_path / "other", (finding(),))
    assert (result.status, result.reason_code) == (
        DeepDimensionStatus.INCOMPLETE,
        "SEMANTIC_ROOT_MISMATCH",
    )
    assert reviewer.seen is None


def test_converts_only_semantic_findings_and_maps_complete(tmp_path: Path) -> None:
    outcome = ReviewOutcome(SemanticStatus.COMPLETE, "REVIEWED", ())
    reviewer = Reviewer(tmp_path, outcome)
    result = SemanticDeepPort(reviewer).analyze(
        tmp_path,
        (
            finding(),
            finding("OTHER"),
            finding("SENT-002", None, None, None, "unknown"),
        ),
    )
    assert result.status is DeepDimensionStatus.COMPLETE
    assert result.reason_code == "REVIEWED"
    assert reviewer.seen is not None
    assert len(reviewer.seen) == 2
    converted = reviewer.seen[0]
    assert converted.location is not None
    assert converted.location.path == "src/a.py"
    assert converted.location.line == 1 and converted.location.column == 1
    assert converted.severity is not None
    assert converted.severity.value == "HIGH"
    first_id = converted.id
    assert reviewer.seen[1].location is None
    SemanticDeepPort(reviewer).analyze(tmp_path, (finding(),))
    assert reviewer.seen is not None
    assert reviewer.seen[0].id == first_id


def test_maps_incomplete_and_unsupported_statuses(tmp_path: Path) -> None:
    for semantic, expected in (
        (SemanticStatus.INCOMPLETE, DeepDimensionStatus.INCOMPLETE),
        (SemanticStatus.UNSUPPORTED, DeepDimensionStatus.UNSUPPORTED),
    ):
        reviewer = Reviewer(tmp_path, ReviewOutcome(semantic, "WHY", ()))
        result = SemanticDeepPort(reviewer).analyze(tmp_path, ())
        assert result.status is expected
        assert result.reason_code == "WHY"
