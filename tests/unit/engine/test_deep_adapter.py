from panopticon.analyzers.semantic.reviewer import ReviewOutcome, SemanticStatus
from panopticon.engine.deep import SemanticDeepPort
from panopticon.engine.scan import DeepDimensionStatus, ScanFinding


class Reviewer:
    def __init__(self, root, outcome):
        self.root = root
        self.outcome = outcome
        self.seen = None

    async def review(self, findings):
        self.seen = findings
        return self.outcome


def finding(rule="SENT-001", path="src/a.py", line=0, column=0, severity="high"):
    return ScanFinding(rule, "title", severity, "fp", path, line, column)


def test_root_mismatch_is_deterministic_and_does_not_review(tmp_path):
    reviewer = Reviewer(tmp_path, ReviewOutcome(SemanticStatus.COMPLETE, "ok", ()))
    result = SemanticDeepPort(reviewer).analyze(tmp_path / "other", (finding(),))
    assert (result.status, result.reason_code) == (
        DeepDimensionStatus.INCOMPLETE,
        "SEMANTIC_ROOT_MISMATCH",
    )
    assert reviewer.seen is None


def test_converts_only_semantic_findings_and_maps_complete(tmp_path):
    outcome = ReviewOutcome(SemanticStatus.COMPLETE, "REVIEWED", ())
    reviewer = Reviewer(tmp_path, outcome)
    result = SemanticDeepPort(reviewer).analyze(
        tmp_path, (finding(), finding("OTHER"), finding("SENT-002", None, None, None, "unknown"))
    )
    assert result.status is DeepDimensionStatus.COMPLETE
    assert result.reason_code == "REVIEWED"
    assert len(reviewer.seen) == 2
    converted = reviewer.seen[0]
    assert converted.location.path == "src/a.py"
    assert converted.location.line == 1 and converted.location.column == 1
    assert converted.severity.value == "HIGH"
    first_id = converted.id
    assert reviewer.seen[1].location is None
    SemanticDeepPort(reviewer).analyze(tmp_path, (finding(),))
    assert reviewer.seen[0].id == first_id


def test_maps_incomplete_and_unsupported_statuses(tmp_path):
    for semantic, expected in (
        (SemanticStatus.INCOMPLETE, DeepDimensionStatus.INCOMPLETE),
        (SemanticStatus.UNSUPPORTED, DeepDimensionStatus.UNSUPPORTED),
    ):
        reviewer = Reviewer(tmp_path, ReviewOutcome(semantic, "WHY", ()))
        result = SemanticDeepPort(reviewer).analyze(tmp_path, ())
        assert result.status is expected
        assert result.reason_code == "WHY"
