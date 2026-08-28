"""Deterministic remediation planning with guidance-only fallbacks."""

from __future__ import annotations

from dataclasses import dataclass

from panopticon.secrets.contracts import CapabilityStatus, SecretStore
from panopticon.util.jsonc.document import SourceDocument
from panopticon.util.jsonc.patch import JsoncPatch, JsoncPatchError
from panopticon.util.jsonc.pointer import decode_pointer, value_at

from .cli_model import FixChoice, FixOutcome, FixOutcomeStatus, FixSelection
from .https import HttpTransport, check_initialize
from .model import FixPlan
from .plan import make_plan
from .rules import (
    narrow_path,
    pin_version,
    pinned_package_spec,
    remove_disabled,
    secret_reference,
    unify_version,
    upgrade_https,
)


@dataclass(frozen=True, slots=True)
class Remediation:
    plan: FixPlan | None
    outcome: FixOutcome


def _outcome(
    selection: FixSelection,
    status: FixOutcomeStatus,
    reason_code: str,
    patches: tuple[JsoncPatch, ...] = (),
) -> Remediation:
    return Remediation(
        None,
        FixOutcome(selection.fix_id, status, reason_code, patches),
    )


def _store_available(store: SecretStore | None) -> bool:
    return store is not None and store.capability().status is CapabilityStatus.COMPLETE


def _patches(
    selection: FixSelection,
    document: SourceDocument,
    secure_store: SecretStore | None,
    https_transport: HttpTransport | None,
) -> tuple[JsoncPatch, ...] | Remediation:
    if selection.fix_id == "FIX-001":
        if selection.client == "claude-desktop":
            return _outcome(selection, FixOutcomeStatus.GUIDANCE, "WRAP_INSTALL_REQUIRED")
        if not _store_available(secure_store):
            return _outcome(
                selection,
                FixOutcomeStatus.GUIDANCE,
                "SECURE_STORE_UNAVAILABLE",
            )
        if selection.value is None:
            return _outcome(selection, FixOutcomeStatus.GUIDANCE, "ENV_KEY_REQUIRED")
        return (secret_reference(selection.pointer, selection.value),)
    if selection.fix_id == "FIX-002":
        current = value_at(document.value, decode_pointer(selection.pointer))
        if not isinstance(current, str):
            raise ValueError("PACKAGE_VALUE_REQUIRED")
        replacement = pinned_package_spec(current, selection.version or "")
        return (pin_version(selection.pointer, replacement),)
    if selection.fix_id == "FIX-004":
        return (narrow_path(selection.pointer, selection.value or ""),)
    if selection.fix_id == "FIX-005":
        current = value_at(document.value, decode_pointer(selection.pointer))
        if not isinstance(current, str):
            raise ValueError("PACKAGE_VALUE_REQUIRED")
        replacement = pinned_package_spec(current, selection.version or "")
        return (unify_version(selection.pointer, replacement),)
    if selection.fix_id == "FIX-008":
        current = value_at(document.value, decode_pointer(selection.pointer))
        if https_transport is None or not isinstance(current, str):
            return _outcome(selection, FixOutcomeStatus.GUIDANCE, "HTTPS_CHECK_UNAVAILABLE")
        checked = check_initialize(current, https_transport)
        if not checked.ok:
            return _outcome(selection, FixOutcomeStatus.GUIDANCE, checked.code)
        return (upgrade_https(selection.pointer, checked.url),)
    if selection.fix_id == "FIX-010":
        return (remove_disabled(selection.pointer),)
    return _outcome(selection, FixOutcomeStatus.GUIDANCE, "UNKNOWN_FIX_ID")


def plan_remediation(
    selection: FixSelection,
    document: SourceDocument,
    *,
    secure_store: SecretStore | None = None,
    https_transport: HttpTransport | None = None,
) -> Remediation:
    if selection.choice is FixChoice.DECLINE:
        return _outcome(selection, FixOutcomeStatus.DECLINED, "USER_DECLINED")
    if selection.choice is FixChoice.GUIDANCE:
        return _outcome(selection, FixOutcomeStatus.GUIDANCE, "GUIDANCE_REQUESTED")
    try:
        result = _patches(selection, document, secure_store, https_transport)
    except (JsoncPatchError, ValueError) as error:
        return _outcome(selection, FixOutcomeStatus.GUIDANCE, str(error))
    if isinstance(result, Remediation):
        return result
    plan = make_plan(document.path, document, result)
    return Remediation(
        plan,
        FixOutcome(selection.fix_id, FixOutcomeStatus.PLANNED, "PLAN_READY", result),
    )


__all__ = ["Remediation", "plan_remediation"]
