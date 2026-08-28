"""Configuration rule catalog acceptance tests."""

from __future__ import annotations

import json
from pathlib import Path

from panopticon.analyzers.config import RULE_IDS, ConfigInput, analyze
from panopticon.models.ids import ClientName, ConfigScope
from panopticon.models.inventory import (
    IdentityConfidence,
    InstalledServer,
    PackageEcosystem,
    SourceKind,
    Transport,
)

_CASES = json.loads(
    (Path(__file__).parents[4] / "tests/fixtures/rules/config/cases.json").read_text()
)


def _sid(value: str) -> str:
    return value if ":" in value else f"local:{value}"


def _iid(value: str) -> str:
    return (
        value
        if value.startswith("inst_")
        else f"inst_{value.split('-', 1)[-1].encode().hex()[:16]:0<16}"
    )


def _input(payload: dict) -> ConfigInput:
    servers = []
    for raw in payload["servers"]:
        server = dict(raw)
        server["server_id"] = _sid(server["server_id"])
        server["installation_id"] = _iid(server["installation_id"])
        server["client"] = ClientName.CLAUDE_DESKTOP
        server["config_path"] = f"~/{server['name']}"
        server["config_pointer"] = f"/servers/{server['name']}"
        server["scope"] = ConfigScope.GLOBAL
        server["transport"] = Transport(server["transport"])
        server["args"] = tuple(server["args"])
        server["env_keys"] = tuple(server["env_keys"])
        server["headers_keys"] = tuple(server["headers_keys"])
        server["source"] = {**server["source"], "kind": SourceKind(server["source"]["kind"])}
        server["identity_confidence"] = IdentityConfidence.HIGH
        if server["package"]:
            server["package"] = {
                **server["package"],
                "ecosystem": PackageEcosystem(server["package"]["ecosystem"]),
            }
        servers.append(InstalledServer.model_validate(server))
    return ConfigInput(
        servers=tuple(servers),
        env_values={_iid(key): tuple(values) for key, values in payload["env_values"].items()},
        allowed_paths={
            _iid(key): tuple(values) for key, values in payload["allowed_paths"].items()
        },
        filesystem_servers=frozenset(_iid(value) for value in payload["filesystem_servers"]),
        token_header_keys={
            _iid(key): tuple(values) for key, values in payload["token_header_keys"].items()
        },
    )


def test_mixed_config_yields_exact_cfg_set() -> None:
    assert set(_CASES["coverage"]["positive"]) == set(RULE_IDS)
    assert set(_CASES["coverage"]["negative"]) == set(RULE_IDS)
    matches = analyze(_input(_CASES["positive"]))
    assert [(m.rule_id, m.server_id, m.installation_id) for m in matches] == [
        ("CFG-001", _sid("cfg-token"), _iid("i-token")),
        ("CFG-002", _sid("cfg-unpinned"), _iid("i-unpinned")),
        ("CFG-003", _sid("cfg-command"), _iid("i-command")),
        ("CFG-004", _sid("filesystem"), _iid("i-path")),
        ("CFG-005", _sid("cfg-dup"), _iid("i-dup-a")),
        ("CFG-005", _sid("cfg-dup"), _iid("i-dup-b")),
        ("CFG-006", _sid("cfg-source"), _iid("i-source")),
        ("CFG-007", _sid("cfg-entropy"), _iid("i-entropy")),
        ("CFG-008", _sid("cfg-http"), _iid("i-http")),
        ("CFG-009", _sid("cfg-disabled"), _iid("i-disabled")),
        ("CFG-010", _sid("cfg-arg"), _iid("i-arg")),
        ("CFG-011", _sid("cfg-header"), _iid("i-header")),
        ("CFG-012", _sid("cfg-wrap"), _iid("i-wrap")),
    ]
    expected = {
        "CFG-001": ("HIGH", "confirmed", "FIX-001", [("API_KEY", "ghp")]),
        "CFG-002": ("MEDIUM", "confirmed", "FIX-002", [("package", "unpinned")]),
        "CFG-003": ("MEDIUM", "review", None, [("command", "sh -c")]),
        "CFG-004": ("HIGH", "confirmed", "FIX-004", [("allowed_path", "broad")]),
        "CFG-006": ("MEDIUM", "review", None, [("source", "unverifiable")]),
        "CFG-007": ("LOW", "review", "FIX-001", [("SECRET", "high_entropy")]),
        "CFG-008": ("MEDIUM", "confirmed", "FIX-008", [("url", "plaintext")]),
        "CFG-009": ("INFO", "info", "FIX-010", [("server", "disabled")]),
        "CFG-010": ("MEDIUM", "review", None, [("arg", "absolute_system_path")]),
        "CFG-011": ("LOW", "review", "FIX-001", [("header", "token")]),
        "CFG-012": ("INFO", "info", None, [("transport", "unwrapped_stdio")]),
    }
    for match in matches:
        if match.rule_id == "CFG-005":
            assert (match.severity.value, match.kind.value, match.fix_id) == (
                "LOW",
                "info",
                "FIX-005",
            )
            assert [(e.subject, e.classification) for e in match.evidence] == [
                ("server_id", "version_mismatch")
            ]
        else:
            severity, kind, fix_id, evidence = expected[match.rule_id]
            assert (match.severity.value, match.kind.value, match.fix_id) == (
                severity,
                kind,
                fix_id,
            )
            assert [(e.subject, e.classification) for e in match.evidence] == evidence
    assert "ghp_TEST_TOKEN_VALUE" not in repr(matches)


def test_near_misses_produce_no_false_confirmed_findings() -> None:
    matches = analyze(_input(_CASES["near_miss"]))
    assert matches == ()
    assert all(match.kind.value != "confirmed" for match in matches)
