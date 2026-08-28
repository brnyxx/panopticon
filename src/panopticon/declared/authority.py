"""Precedence-aware merge and matching of declared scope."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .model import (
    Coverage,
    DeclaredScope,
    Match,
    ScopeGrant,
    ScopeReason,
    ScopeStatus,
    SourceKind,
)
from .normalize import host_matches, path_matches

_PRIORITY = {
    SourceKind.SELF_DECL: 60,
    SourceKind.REGISTRY: 50,
    SourceKind.CONFIG: 40,
    SourceKind.TOOL_DESCRIPTION: 30,
    SourceKind.README: 20,
    SourceKind.MANIFEST: 10,
}


def _merge(grants: Iterable[ScopeGrant]) -> ScopeGrant:
    items = tuple(grants)
    if not items:
        return ScopeGrant()
    best = max(items, key=lambda g: _PRIORITY[g.source])
    # Fields are merged only among same authority tier; low-confidence README cannot mask tool-specific data.
    tier = _PRIORITY[best.source]
    peers = tuple(g for g in items if _PRIORITY[g.source] == tier)
    return ScopeGrant(
        paths=tuple(sorted({x for g in peers for x in g.paths})),
        hosts=tuple(sorted({x for g in peers for x in g.hosts})),
        ports=tuple(sorted({x for g in peers for x in g.ports})),
        env=tuple(sorted({x for g in peers for x in g.env})),
        processes=tuple(sorted({x for g in peers for x in g.processes})),
        capabilities=tuple(
            sorted({x for g in peers for x in g.capabilities}, key=lambda x: x.value)
        ),
        source=best.source,
        confidence=max(g.confidence for g in peers),
        authority=best.authority,
        maintainer=any(g.maintainer for g in peers),
        complete=any(g.complete for g in peers),
        diagnostics=tuple(d for g in peers for d in g.diagnostics),
    )


def compose(
    server_grants: Iterable[ScopeGrant], tool_grants: Mapping[str, Iterable[ScopeGrant]]
) -> DeclaredScope:
    server = _merge(server_grants)
    tools = {name: _merge(grants) for name, grants in sorted(tool_grants.items())}
    grants = (server, *tools.values())
    coverage = Coverage(
        paths=ScopeStatus.COMPLETE if any(g.paths for g in grants) else ScopeStatus.UNKNOWN,
        hosts=ScopeStatus.COMPLETE if any(g.hosts for g in grants) else ScopeStatus.UNKNOWN,
        env=ScopeStatus.COMPLETE if any(g.env for g in grants) else ScopeStatus.UNKNOWN,
        processes=ScopeStatus.COMPLETE if any(g.processes for g in grants) else ScopeStatus.UNKNOWN,
    )
    return DeclaredScope(server=server, tools=tools, coverage=coverage)


def _grant_for(scope: DeclaredScope, tool: str | None) -> ScopeGrant:
    # A tool grant is isolated; server grants supplement only missing fields.
    if tool is None or tool not in scope.tools:
        return scope.server
    t = scope.tools[tool]
    s = scope.server
    return ScopeGrant(
        paths=t.paths or s.paths,
        hosts=t.hosts or s.hosts,
        ports=t.ports or s.ports,
        env=t.env or s.env,
        processes=t.processes or s.processes,
        capabilities=t.capabilities or s.capabilities,
        source=t.source,
        confidence=t.confidence,
        authority=t.authority,
        maintainer=t.maintainer,
        complete=t.complete,
        diagnostics=t.diagnostics,
    )


def match_host(scope: DeclaredScope, host: str, tool: str | None = None) -> Match:
    g = _grant_for(scope, tool)
    if not g.hosts:
        return Match(ScopeStatus.UNKNOWN, ScopeReason.MISSING, "host", host, g.source)
    ok = any(host_matches(p, host) for p in g.hosts)
    return Match(
        ScopeStatus.COMPLETE if ok else ScopeStatus.INVALID,
        ScopeReason.DECLARED if ok else ScopeReason.CONFLICT,
        "host",
        host,
        g.source,
    )


def match_network(
    scope: DeclaredScope, host: str, port: int | None = None, tool: str | None = None
) -> Match:
    result = match_host(scope, host, tool)
    if result.status is not ScopeStatus.COMPLETE or port is None:
        return result
    grant = _grant_for(scope, tool)
    if grant.ports and port not in grant.ports:
        return Match(ScopeStatus.INVALID, ScopeReason.CONFLICT, "port", str(port), grant.source)
    return Match(
        ScopeStatus.COMPLETE, ScopeReason.DECLARED, "network", f"{host}:{port}", grant.source
    )


def match_path(scope: DeclaredScope, path: str, tool: str | None = None) -> Match:
    g = _grant_for(scope, tool)
    if not g.paths:
        return Match(ScopeStatus.UNKNOWN, ScopeReason.MISSING, "path", path, g.source)
    ok = any(path_matches(p, path) for p in g.paths)
    return Match(
        ScopeStatus.COMPLETE if ok else ScopeStatus.INVALID,
        ScopeReason.DECLARED if ok else ScopeReason.CONFLICT,
        "path",
        path,
        g.source,
    )


def match_env(scope: DeclaredScope, name: str, tool: str | None = None) -> Match:
    g = _grant_for(scope, tool)
    if not g.env:
        return Match(ScopeStatus.UNKNOWN, ScopeReason.MISSING, "env", name, g.source)
    ok = name in g.env
    return Match(
        ScopeStatus.COMPLETE if ok else ScopeStatus.INVALID,
        ScopeReason.DECLARED if ok else ScopeReason.CONFLICT,
        "env",
        name,
        g.source,
    )


def match_process(scope: DeclaredScope, name: str, tool: str | None = None) -> Match:
    g = _grant_for(scope, tool)
    if not g.processes:
        return Match(ScopeStatus.UNKNOWN, ScopeReason.MISSING, "process", name, g.source)
    ok = name.rsplit("/", 1)[-1].lower() in g.processes
    return Match(
        ScopeStatus.COMPLETE if ok else ScopeStatus.INVALID,
        ScopeReason.DECLARED if ok else ScopeReason.CONFLICT,
        "process",
        name,
        g.source,
    )
