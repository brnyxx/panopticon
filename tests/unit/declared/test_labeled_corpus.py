from panopticon.declared import (
    Authority,
    ScopeGrant,
    ScopeStatus,
    SourceKind,
    compose,
    match_host,
    match_path,
)


def _precision_recall(expected: set[str], predicted: set[str]) -> tuple[float, float]:
    true_positive = len(expected & predicted)
    precision = true_positive / len(predicted) if predicted else 1.0
    recall = true_positive / len(expected) if expected else 1.0
    return precision, recall


def test_labeled_host_corpus_precision_and_recall_are_separate() -> None:
    scope = compose(
        [
            ScopeGrant(
                hosts=("api.example.com", "*.trusted.example"),
                source=SourceKind.REGISTRY,
                authority=Authority.AUTHORITATIVE,
                complete=True,
            )
        ],
        {},
    )
    corpus = {
        "api.example.com": True,
        "v1.trusted.example": True,
        "trusted.example": False,
        "evil.example": False,
        "api.example.net": False,
    }
    predicted = {host for host in corpus if match_host(scope, host).status is ScopeStatus.COMPLETE}
    expected = {host for host, label in corpus.items() if label}
    precision, recall = _precision_recall(expected, predicted)
    assert precision == 1.0
    assert recall == 1.0


def test_labeled_path_corpus_precision_and_recall_are_separate() -> None:
    scope = compose(
        [
            ScopeGrant(
                paths=("/workspace/project/*",),
                source=SourceKind.SELF_DECL,
                authority=Authority.AUTHORITATIVE,
                complete=True,
            )
        ],
        {},
    )
    corpus = {
        "/workspace/project/main.py": True,
        "/workspace/project/pkg/mod.py": True,
        "/workspace/project/../secret.txt": False,
        "/workspace/other.txt": False,
    }
    predicted = {path for path in corpus if match_path(scope, path).status is ScopeStatus.COMPLETE}
    expected = {path for path, label in corpus.items() if label}
    precision, recall = _precision_recall(expected, predicted)
    assert precision == 1.0
    assert recall == 1.0


def test_partial_and_unknown_labels_are_not_counted_as_authorized() -> None:
    scope = compose(
        [
            ScopeGrant(
                hosts=("known.example",),
                source=SourceKind.TOOL_DESCRIPTION,
                authority=Authority.PARTIAL,
            )
        ],
        {},
    )
    labels = {"known.example": True, "unmatched.example": False}
    statuses = {host: match_host(scope, host).status for host in labels}
    assert statuses["known.example"] is ScopeStatus.PARTIAL
    assert statuses["unmatched.example"] is ScopeStatus.UNKNOWN
    predicted = {host for host, status in statuses.items() if status is ScopeStatus.COMPLETE}
    precision, recall = _precision_recall(set(), predicted)
    assert precision == 1.0
    assert recall == 1.0
