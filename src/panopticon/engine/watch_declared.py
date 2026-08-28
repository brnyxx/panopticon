"""Compose tool-specific declarations from local MCP metadata and config."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from panopticon.declared.authority import compose
from panopticon.declared.extract import ConfigExtractor, SelfDeclExtractor, ToolDescExtractor
from panopticon.declared.model import Authority, DeclaredScope, ScopeGrant
from panopticon.models.common import Host, PersistedPath
from panopticon.models.observation import (
    Declared,
    DeclaredCapability,
    DeclaredCompleteness,
    DeclaredSource,
)
from panopticon.probe.argument_schema import JsonValue

from .watch_local_model import LocalWatchResult


@dataclass(frozen=True, slots=True)
class DeclaredBuild:
    persisted: Declared
    scope: DeclaredScope


def _mapping(value: JsonValue | object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def build_declared(result: LocalWatchResult) -> DeclaredBuild:
    target = result.context.target
    server_grants = (ConfigExtractor().extract({"env_keys": target.env_keys, "args": target.args}),)
    tool_grants: dict[str, tuple[ScopeGrant, ...]] = {}
    self_complete: list[bool] = []
    for raw in result.raw_tools:
        name = raw.get("name")
        if not isinstance(name, str) or not name:
            continue
        description = raw.get("description")
        annotations = _mapping(raw.get("annotations"))
        grants: list[ScopeGrant] = [
            ToolDescExtractor().extract(
                description if isinstance(description, str) else None,
                annotations,
            )
        ]
        metadata = _mapping(raw.get("_meta"))
        declaration = _mapping(metadata.get("panopticon")) if metadata is not None else None
        if declaration is not None:
            grant = SelfDeclExtractor().extract(declaration)
            grants.insert(0, grant)
            self_complete.append(grant.authority is Authority.AUTHORITATIVE and grant.complete)
        else:
            self_complete.append(False)
        tool_grants[name] = tuple(grants)
    scope = compose(server_grants, tool_grants)
    all_grants = (scope.server, *scope.tools.values())
    sources = tuple(
        sorted(
            {DeclaredSource(grant.source.value) for grant in all_grants},
            key=lambda source: source.value,
        )
    )
    capabilities = tuple(
        sorted(
            {
                DeclaredCapability(capability.value)
                for grant in all_grants
                for capability in grant.capabilities
            },
            key=lambda capability: capability.value,
        )
    )
    complete = bool(self_complete) and all(self_complete)
    partial = any(
        grant.paths or grant.hosts or grant.env or grant.processes or grant.capabilities
        for grant in all_grants
    )
    completeness = (
        DeclaredCompleteness.COMPLETE
        if complete
        else DeclaredCompleteness.PARTIAL
        if partial
        else DeclaredCompleteness.NONE
    )
    persisted = Declared(
        hosts=tuple(
            Host(host) for host in sorted({host for grant in all_grants for host in grant.hosts})
        ),
        paths=tuple(
            PersistedPath(path)
            for path in sorted({path for grant in all_grants for path in grant.paths})
        ),
        env=tuple(sorted({name for grant in all_grants for name in grant.env})),
        processes=tuple(sorted({name for grant in all_grants for name in grant.processes})),
        capabilities=capabilities,
        sources=sources,
        completeness=completeness,
    )
    return DeclaredBuild(persisted, scope)


__all__ = ["DeclaredBuild", "build_declared"]
