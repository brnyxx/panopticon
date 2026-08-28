from datetime import UTC, datetime

import pytest

from panopticon.rules.context import RuleContext, SourceState, SourceStatus
from panopticon.rules.registry import Suppression, all_rules, rule, run_rules


def test_context_distinguishes_source_states() -> None:
    context = RuleContext(inventory=SourceState.incomplete("timeout"))
    assert context.inventory.status is SourceStatus.INCOMPLETE
    assert context.observation.status is SourceStatus.UNKNOWN


def test_registry_order_and_duplicate_rejection() -> None:
    rule_id = "CFG-999"
    decorated = rule(rule_id=rule_id, severity="INFO", kind="info", line="config")
    decorated(lambda _ctx: ())
    with pytest.raises(ValueError):
        decorated(lambda _ctx: ())
    with pytest.raises(ValueError):
        rule(rule_id="CFG-ZZZ", severity="INFO", kind="info", line="config")(lambda _ctx: ())
    assert list(all_rules()) == sorted(all_rules())


def test_rule_exception_becomes_diagnostic() -> None:
    rule_id = "CFG-998"

    @rule(rule_id=rule_id, severity="LOW", kind="review", line="config")
    def broken(_ctx):
        raise RuntimeError("secret\nmessage")

    findings, diagnostics = run_rules(
        RuleContext(),
        at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    diagnostic = next(item for item in diagnostics if item.rule_id == rule_id)
    assert not findings
    assert diagnostic.code == "RULE_EXCEPTION"
    assert "\n" not in diagnostic.detail


def test_expired_suppression_is_not_active() -> None:
    suppression = Suppression(
        "CFG-998",
        "local:test",
        "old",
        datetime(2020, 1, 1, tzinfo=UTC),
    )
    assert not suppression.active(datetime(2026, 1, 1, tzinfo=UTC))
