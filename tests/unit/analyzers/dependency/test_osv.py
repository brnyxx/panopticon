from __future__ import annotations

from pathlib import Path

import httpx

from panopticon.analyzers.dependency.model import (
    DependencyInput,
    DependencyReason,
    DependencyStatus,
    RequirementRecord,
)
from panopticon.analyzers.dependency.osv import (
    OSV_BATCH_LIMIT,
    OSV_QUERY_BATCH_URL,
    OSV_TIMEOUT_SECONDS,
    OsvAdvisory,
)
from panopticon.analyzers.dependency.scan import AdvisoryStatus


class Response:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def json(self) -> object:
        return self.payload


def _requirements(*items: tuple[str, str]) -> DependencyInput:
    return DependencyInput(
        DependencyStatus.COMPLETE,
        DependencyReason.COMPLETED,
        tuple(RequirementRecord(name, specifier) for name, specifier in items),
    )


def test_osv_uses_exact_requirements_without_lock_and_sorts_findings(tmp_path: Path) -> None:
    calls: list[tuple[str, object, float, bool]] = []

    def post(url: str, *, json: object, timeout: float, follow_redirects: bool) -> Response:
        calls.append((url, json, timeout, follow_redirects))
        return Response(
            {
                "results": [
                    {
                        "vulns": [
                            {
                                "id": "OSV-2",
                                "summary": "second",
                                "database_specific": {"severity": "high"},
                            },
                            {
                                "id": "OSV-1",
                                "summary": "first",
                                "ecosystem_specific": {"severity": "LOW"},
                            },
                        ]
                    }
                ]
            }
        )

    result = OsvAdvisory(tmp_path, post=post).check(_requirements(("requests", "==2.31.0")))

    assert result.status is AdvisoryStatus.COMPLETE
    assert [(item.advisory_id, item.severity) for item in result.findings] == [
        ("OSV-1", "LOW"),
        ("OSV-2", "HIGH"),
    ]
    assert calls == [
        (
            OSV_QUERY_BATCH_URL,
            {
                "queries": [
                    {
                        "package": {"name": "requests", "ecosystem": "PyPI"},
                        "version": "2.31.0",
                    }
                ]
            },
            OSV_TIMEOUT_SECONDS,
            False,
        )
    ]


def test_osv_resolves_versions_from_uv_lock(tmp_path: Path) -> None:
    (tmp_path / "uv.lock").write_text(
        "[[package]]\nname = 'requests'\nversion = '2.32.3'\n", encoding="utf-8"
    )
    payloads: list[object] = []

    def post(_url: str, *, json: object, **_kwargs: object) -> Response:
        payloads.append(json)
        return Response({"results": [{}]})

    result = OsvAdvisory(tmp_path, post=post).check(_requirements(("requests", ">=2")))

    assert result.status is AdvisoryStatus.COMPLETE
    assert payloads[0] == {
        "queries": [{
                "package": {"name": "requests", "ecosystem": "PyPI"},
                "version": "2.32.3",
            }]
    }


def test_osv_rejects_ambiguous_or_missing_versions_without_request(tmp_path: Path) -> None:
    calls = 0

    def post(*_args: object, **_kwargs: object) -> Response:
        nonlocal calls
        calls += 1
        return Response({"results": []})

    wildcard = OsvAdvisory(tmp_path, post=post).check(_requirements(("requests", "==2.*")))
    missing = OsvAdvisory(tmp_path, post=post).check(_requirements(("requests", ">=2")))
    (tmp_path / "uv.lock").write_text(
        "[[package]]\nname = 'requests'\nversion = '2.31.0'\n"
        "[[package]]\nname = 'requests'\nversion = '2.32.0'\n",
        encoding="utf-8",
    )
    ambiguous = OsvAdvisory(tmp_path, post=post).check(_requirements(("requests", ">=2")))

    assert [item.reason_code for item in (wildcard, missing, ambiguous)] == [
        "ADVISORY_VERSION_UNRESOLVED",
        "ADVISORY_VERSION_UNRESOLVED",
        "ADVISORY_VERSION_UNRESOLVED",
    ]
    assert calls == 0


def test_osv_bounds_requests_and_converts_network_and_shape_failures(tmp_path: Path) -> None:
    requirements = _requirements(
        *((f"pkg{number}", "==1.0") for number in range(OSV_BATCH_LIMIT + 1))
    )
    bounded = OsvAdvisory(tmp_path, post=lambda *_args, **_kwargs: Response({"results": []})).check(
        requirements
    )

    def failing(*_args: object, **_kwargs: object) -> Response:
        raise httpx.ConnectError("offline")

    network = OsvAdvisory(tmp_path, post=failing).check(_requirements(("requests", "==2.31.0")))
    malformed = OsvAdvisory(
        tmp_path, post=lambda *_args, **_kwargs: Response({"results": []})
    ).check(_requirements(("requests", "==2.31.0")))

    assert bounded.reason_code == "ADVISORY_BATCH_TOO_LARGE"
    assert network.reason_code == "ADVISORY_NETWORK_ERROR"
    assert malformed.reason_code == "ADVISORY_RESPONSE_INVALID"
