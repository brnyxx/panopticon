from __future__ import annotations

from pathlib import Path

from panopticon.fix.cli_model import FixOutcomeStatus, FixSelection
from panopticon.fix.remediations import plan_remediation
from panopticon.fix.rules import RULES
from panopticon.models.ids import ConfigPath, JsonPointer
from panopticon.secrets import InMemorySecretStore
from panopticon.util.jsonc.parser import parse_document
from panopticon.util.jsonc.patch import patch_document


class HttpsTransport:
    def __init__(self, valid: bool = True) -> None:
        self.valid = valid
        self.methods: list[str] = []

    def request(self, method, url, headers, body=None):
        self.methods.append(method)
        if not self.valid:
            return 404, {}, b"{}"
        return (
            200,
            {"content-type": "application/json"},
            b'{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2026-07-28"}}',
        )


def _document():
    source = (
        b"// retained\n"
        b'{"mcpServers":{"one":{"command":"npx","args":["fixture@latest","/"],'
        b'"env":{"TOKEN":"ghp_fixture_secret_value_123456"}},'
        b'"remote":{"url":"http://example.com/mcp"},'
        b'"disabled":{"command":"node","args":["server.js"],"disabled":true},'
        b'"duplicate":{"command":"npx","args":["fixture@2.0.0"]}},"other":7}\n'
    )
    return parse_document(
        source,
        path=Path("config.jsonc"),
        logical_path=ConfigPath("~/config.jsonc"),
    )


def test_all_six_fix_rules_plan_exact_non_overlapping_patches() -> None:
    document = _document()
    store = InMemorySecretStore()
    https = HttpsTransport()
    selections = (
        FixSelection(
            "FIX-001", document.path, JsonPointer("/mcpServers/one/env/TOKEN"), value="TOKEN"
        ),
        FixSelection(
            "FIX-002", document.path, JsonPointer("/mcpServers/one/args/0"), version="1.2.3"
        ),
        FixSelection(
            "FIX-004", document.path, JsonPointer("/mcpServers/one/args/1"), value="~/project"
        ),
        FixSelection(
            "FIX-005", document.path, JsonPointer("/mcpServers/duplicate/args/0"), version="1.2.3"
        ),
        FixSelection("FIX-008", document.path, JsonPointer("/mcpServers/remote/url")),
        FixSelection("FIX-010", document.path, JsonPointer("/mcpServers/disabled")),
    )
    plans = [
        plan_remediation(
            selection,
            document,
            secure_store=store,
            https_transport=https,
        )
        for selection in selections
    ]
    assert [rule.fix_id for rule in RULES] == [selection.fix_id for selection in selections]
    assert all(remediation.outcome.status is FixOutcomeStatus.PLANNED for remediation in plans)
    rendered = [
        patch_document(document, remediation.plan.patches)
        for remediation in plans
        if remediation.plan is not None
    ]
    assert b'"${TOKEN}"' in rendered[0]
    assert b'"fixture@1.2.3"' in rendered[1]
    assert b'"~/project"' in rendered[2]
    assert b'"fixture@1.2.3"' in rendered[3]
    assert b'"https://example.com/mcp"' in rendered[4]
    assert b'"disabled"' not in rendered[5]
    assert all(b'"other":7' in value and b"// retained" in value for value in rendered)
    assert https.methods == ["POST"]


def test_secret_and_https_without_required_capability_are_guidance_only() -> None:
    document = _document()
    secret = plan_remediation(
        FixSelection(
            "FIX-001",
            document.path,
            JsonPointer("/mcpServers/one/env/TOKEN"),
            value="TOKEN",
        ),
        document,
    )
    remote = plan_remediation(
        FixSelection("FIX-008", document.path, JsonPointer("/mcpServers/remote/url")),
        document,
        https_transport=HttpsTransport(valid=False),
    )
    assert secret.plan is None and secret.outcome.status is FixOutcomeStatus.GUIDANCE
    assert remote.plan is None and remote.outcome.status is FixOutcomeStatus.GUIDANCE
    assert secret.outcome.written_paths == remote.outcome.written_paths == ()
