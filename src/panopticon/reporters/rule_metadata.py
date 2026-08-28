"""Stable metadata for findings rendered to machine formats."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RuleMetadata:
    id: str
    name: str
    description: str
    help_uri: str | None = None


def metadata_for(rule_id: str, title: str | None = None) -> RuleMetadata:
    rid = str(rule_id)
    help_uri = f"https://github.com/brnyxx/panopticon/blob/main/docs/rules/{rid}.md"
    return RuleMetadata(rid, title or rid, f"Panopticon policy rule {rid}.", help_uri)


def metadata_map(rule_ids: list[str] | tuple[str, ...]) -> tuple[RuleMetadata, ...]:
    return tuple(metadata_for(rid) for rid in sorted(set(map(str, rule_ids))))


__all__ = ["RuleMetadata", "metadata_for", "metadata_map"]
