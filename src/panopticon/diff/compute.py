"""Deterministic, coverage-aware baseline comparison."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TypeAlias

from panopticon.models.artifacts import Baseline, DiffEntry, DiffResult, FindingChanges
from panopticon.models.observation import Observation
from panopticon.models.state import StageStatus

Record: TypeAlias = Baseline | Observation


def _observations(record: Record) -> tuple[Observation, ...]:
    return record.observations if isinstance(record, Baseline) else (record,)


def _entries(kind: str, installation: str, values: Iterable[str]) -> tuple[DiffEntry, ...]:
    return tuple(
        DiffEntry(kind=kind, installation_id=installation, key=value, detail=kind)
        for value in sorted(set(values))
    )


def _coverage(record: Observation, category: str) -> bool:
    stage: object = getattr(record.state.coverage, category)
    return stage.status is StageStatus.COMPLETE


def _event_keys(observation: Observation, category: str) -> set[str]:
    result: set[str] = set()
    for span in observation.spans:
        for event in span.events:
            value = event.root
            if category == "behavior":
                if value.kind == "net":
                    result.add(f"host:{value.host}:{value.port or 0}")
                elif value.kind == "file":
                    result.add(f"path:{value.path}")
                elif value.kind == "proc":
                    result.add("process:" + " ".join(value.argv))
                elif value.kind in {"leak", "plaintext_http"}:
                    result.add(
                        "leak:"
                        + (value.decoy_key if value.kind == "leak" else ",".join(value.decoy_keys))
                    )
    return result


def _finding_changes(before: Sequence[Observation], after: Sequence[Observation]) -> FindingChanges:
    left = {str(f.logical_key): f for obs in before for f in obs.findings}
    right = {str(f.logical_key): f for obs in after for f in obs.findings}
    after_obs = {str(obs.installation_id): obs for obs in after}
    before_obs = {str(obs.installation_id): obs for obs in before}
    installation = lambda finding: str(finding.installation_id)
    new: list[DiffEntry] = []
    changed: list[DiffEntry] = []
    unchanged: list[DiffEntry] = []
    resolved: list[DiffEntry] = []
    unknown: list[DiffEntry] = []
    for key in sorted(set(left) | set(right)):
        old, current = left.get(key), right.get(key)
        source = current if current is not None else old
        assert source is not None
        install = installation(source)
        if old is None:
            new.append(DiffEntry(kind="NEW", installation_id=install, key=key, detail="finding"))
        elif current is None:
            observation = after_obs.get(install)
            prior = before_obs.get(install)
            complete = (
                observation is not None
                and prior is not None
                and observation.state.overall.status is StageStatus.COMPLETE
                and prior.state.overall.status is StageStatus.COMPLETE
            )
            target = unknown if not complete else resolved
            target.append(
                DiffEntry(
                    kind="UNKNOWN" if target is unknown else "RESOLVED",
                    installation_id=install,
                    key=key,
                    detail="finding",
                )
            )
        elif old.model_dump(mode="json") == current.model_dump(mode="json"):
            unchanged.append(
                DiffEntry(kind="UNCHANGED", installation_id=install, key=key, detail="finding")
            )
        else:
            changed.append(
                DiffEntry(kind="CHANGED", installation_id=install, key=key, detail="finding")
            )
    return FindingChanges(
        new=tuple(new),
        changed=tuple(changed),
        unchanged=tuple(unchanged),
        resolved=tuple(resolved),
        unknown=tuple(unknown),
    )


def compute_diff(before: Record, after: Record) -> DiffResult:
    """Compute a stable diff. No persistence or side effects occur."""
    old, new = _observations(before), _observations(after)
    old_by = {str(o.installation_id): o for o in old}
    new_by = {str(o.installation_id): o for o in new}
    capability: list[DiffEntry] = []
    behavior: list[DiffEntry] = []
    for installation in sorted(set(old_by) | set(new_by)):
        left, right = old_by.get(installation), new_by.get(installation)
        if left is None or right is None:
            continue
        old_tools = {tool.name: tool for tool in left.tools}
        new_tools = {tool.name: tool for tool in right.tools}
        for key in sorted(set(old_tools) | set(new_tools)):
            if key not in old_tools:
                capability.append(
                    DiffEntry(kind="NEW_TOOL", installation_id=installation, key=key, detail="tool")
                )
            elif key not in new_tools:
                if _coverage(right, "stdio"):
                    capability.append(
                        DiffEntry(
                            kind="REMOVED_TOOL",
                            installation_id=installation,
                            key=key,
                            detail="tool",
                        )
                    )
                else:
                    capability.append(
                        DiffEntry(
                            kind="UNKNOWN", installation_id=installation, key=key, detail="tool"
                        )
                    )
            elif old_tools[key].model_dump(mode="json") != new_tools[key].model_dump(mode="json"):
                old_tool, new_tool = old_tools[key], new_tools[key]
                change = (
                    "SCHEMA_CHANGED"
                    if old_tool.input_schema_hash != new_tool.input_schema_hash
                    else "ANNOTATION_CHANGED"
                )
                capability.append(
                    DiffEntry(kind=change, installation_id=installation, key=key, detail="tool")
                )
        old_events, new_events = _event_keys(left, "behavior"), _event_keys(right, "behavior")
        for key in sorted(new_events - old_events):
            behavior.append(
                DiffEntry(
                    kind="NEW_" + key.split(":", 1)[0].upper(),
                    installation_id=installation,
                    key=key,
                    detail="behavior",
                )
            )
        for key in sorted(old_events - new_events):
            prefix = key.split(":", 1)[0]
            coverage = {"host": "net", "path": "file", "process": "process", "leak": "snapshot"}[
                prefix
            ]
            kind = "REMOVED_" + prefix.upper()
            behavior.append(
                DiffEntry(
                    kind=kind if _coverage(right, coverage) and _coverage(left, coverage) else "UNKNOWN",
                    installation_id=installation,
                    key=key,
                    detail="behavior",
                )
            )
    inventory = _inventory_diff(before, after)
    meaningful = tuple(
        entry
        for entry in capability + behavior + inventory
        if entry.kind
        in {
            "NEW_LEAK",
            "NEW_HOST",
            "NEW_TOOL",
            "SCHEMA_CHANGED",
            "COMMAND_CHANGED",
            "VERSION_CHANGED",
        }
    )
    return DiffResult(
        schema_version="0.1",
        since=_label(before),
        until=_label(after),
        findings=_finding_changes(old, new),
        capability=tuple(capability),
        behavior=tuple(behavior),
        inventory=inventory,
        meaningful=meaningful,
    )


def _label(record: Record) -> str:
    return str(record.baseline_id if isinstance(record, Baseline) else record.observation_id)


def _inventory_diff(before: Record, after: Record) -> tuple[DiffEntry, ...]:
    left = {
        str(i.installation_id): i
        for i in (before.inventory if isinstance(before, Baseline) else ())
    }
    right = {
        str(i.installation_id): i for i in (after.inventory if isinstance(after, Baseline) else ())
    }
    result: list[DiffEntry] = []
    for key in sorted(set(left) | set(right)):
        if key not in left:
            result.append(DiffEntry(kind="ADDED", installation_id=key, key=key, detail="inventory"))
        elif key not in right:
            result.append(
                DiffEntry(kind="REMOVED", installation_id=key, key=key, detail="inventory")
            )
        elif left[key].command != right[key].command:
            result.append(
                DiffEntry(kind="COMMAND_CHANGED", installation_id=key, key=key, detail="inventory")
            )
        elif left[key].env_keys != right[key].env_keys:
            result.append(
                DiffEntry(kind="ENV_KEYS_CHANGED", installation_id=key, key=key, detail="inventory")
            )
        elif (
            left[key].package is not None
            and right[key].package is not None
            and left[key].package.resolved != right[key].package.resolved
        ):
            result.append(
                DiffEntry(kind="VERSION_CHANGED", installation_id=key, key=key, detail="inventory")
            )
    return tuple(result)


__all__ = ["compute_diff"]
