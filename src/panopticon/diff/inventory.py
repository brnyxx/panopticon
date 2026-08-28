"""Deterministic inventory deltas for baseline comparison."""

from __future__ import annotations

from panopticon.models.artifacts import Baseline, DiffEntry


def inventory_diff(before: Baseline, after: Baseline) -> tuple[DiffEntry, ...]:
    left = {item.installation_id: item for item in before.inventory}
    right = {item.installation_id: item for item in after.inventory}
    result: list[DiffEntry] = []
    for key in sorted(set(left) | set(right), key=str):
        if key not in left:
            kind = "ADDED"
        elif key not in right:
            kind = "REMOVED"
        elif left[key].command != right[key].command:
            kind = "COMMAND_CHANGED"
        elif left[key].env_keys != right[key].env_keys:
            kind = "ENV_KEYS_CHANGED"
        else:
            left_package = left[key].package
            right_package = right[key].package
            if (
                left_package is None
                or right_package is None
                or left_package.resolved == right_package.resolved
            ):
                continue
            kind = "VERSION_CHANGED"
        result.append(
            DiffEntry(
                kind=kind,
                installation_id=key,
                key=str(key),
                detail="inventory",
            )
        )
    return tuple(result)
