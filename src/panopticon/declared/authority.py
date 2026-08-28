"""Precedence-aware merge and matching of declared scope."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .model import (
    Authority,
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
    SourceKind.CONFIG: 50,
    SourceKind.REGISTRY: 40,
    SourceKind.TOOL_DESCRIPTION: 30,
    SourceKind.README: 20,
    SourceKind.MANIFEST: 10,
}


def _merge(grants: Iterable[ScopeGrant]) -> ScopeGrant:
    items = tuple(grants)
    if not items:
        return ScopeGrant()
    best = max(items, key=lambda grant: _PRIORITY[grant.source])
    tier = _PRIORITY[best.source]
    peers = tuple(grant for grant in items if _PRIORITY[grant.source] == tier)
    return ScopeGrant(
        paths=tuple(sorted({value for grant in peers for value in grant.paths})),
        hosts=tuple(sorted({value for grant in peers for value in grant.hosts})),
        ports=tuple(sorted({value for grant in peers for value in grant.ports})),
        env=tuple(sorted({value for grant in peers for value in grant.env})),
        processes=tuple(sorted({value for grant in peers for value in grant.processes})),
        capabilities=tuple(
            sorted(
                {value for grant in peers for value in grant.capabilities},
                key=lambda value: value.value,
            )
        ),
        source=best.source,
        confidence=max(grant.confidence for grant in peers),
        authority=best.authority,
        maintainer=any(grant.maintainer for grant in peers),
        complete=any(grant.complete for grant in peers),
        diagnostics=tuple(diagnostic for grant in peers for diagnostic in grant.diagnostics),
    )


def _dimension(grants: tuple[ScopeGrant, ...], field: str) -> ScopeStatus:
    if any(grant.authority is Authority.AUTHORITATIVE and grant.complete for grant in grants):
        return ScopeStatus.COMPLETE
    if any(bool(getattr(grant, field)) for grant in grants):
        return ScopeStatus.PARTIAL
    return ScopeStatus.UNKNOWN


def compose(
    server_grants: Iterable[ScopeGrant],
    tool_grants: Mapping[str, Iterable[ScopeGrant]],
) -> DeclaredScope:
    server = _merge(server_grants)
    tools = {name: _merge(grants) for name, grants in sorted(tool_grants.items())}
    grants = (server, *tools.values())
    diagnostics = tuple(diagnostic for grant in grants for diagnostic in grant.diagnostics)
    return DeclaredScope(
        server=server,
        tools=tools,
        diagnostics=diagnostics,
        coverage=Coverage(
            paths=_dimension(grants, "paths"),
            hosts=_dimension(grants, "hosts"),
            env=_dimension(grants, "env"),
            processes=_dimension(grants, "processes"),
        ),
    )


def _field_grant(scope: DeclaredScope, tool: str | None, field: str) -> ScopeGrant:
    if tool is None:
        return scope.server
    grant = scope.tools.get(tool)
    if grant is None:
        return scope.server
    if getattr(grant, field) or (grant.authority is Authority.AUTHORITATIVE and grant.complete):
        return grant
    return scope.server


def _result(grant: ScopeGrant, matched: bool, field: str, value: str) -> Match:
    authoritative = grant.authority is Authority.AUTHORITATIVE and grant.complete
    if matched:
        if grant.authority is Authority.NONE:
            return Match(
                ScopeStatus.UNKNOWN,
                ScopeReason.INFERRED,
                field,
                value,
                grant.source,
            )
        return Match(
            ScopeStatus.COMPLETE if authoritative else ScopeStatus.PARTIAL,
            ScopeReason.DECLARED if authoritative else ScopeReason.INFERRED,
            field,
            value,
            grant.source,
        )
    return Match(
        ScopeStatus.INVALID if authoritative else ScopeStatus.UNKNOWN,
        ScopeReason.CONFLICT if authoritative else ScopeReason.MISSING,
        field,
        value,
        grant.source,
    )


def match_host(scope: DeclaredScope, host: str, tool: str | None = None) -> Match:
    grant = _field_grant(scope, tool, "hosts")
    return _result(
        grant,
        any(host_matches(pattern, host) for pattern in grant.hosts),
        "host",
        host,
    )


def match_network(
    scope: DeclaredScope,
    host: str,
    port: int | None = None,
    tool: str | None = None,
) -> Match:
    host_result = match_host(scope, host, tool)
    if host_result.status not in {ScopeStatus.COMPLETE, ScopeStatus.PARTIAL} or port is None:
        return host_result
    grant = _field_grant(scope, tool, "ports")
    matched = not grant.ports or port in grant.ports
    return _result(grant, matched, "network", f"{host}:{port}")


def match_path(scope: DeclaredScope, path: str, tool: str | None = None) -> Match:
    grant = _field_grant(scope, tool, "paths")
    return _result(
        grant,
        any(path_matches(pattern, path) for pattern in grant.paths),
        "path",
        path,
    )


def match_env(scope: DeclaredScope, name: str, tool: str | None = None) -> Match:
    grant = _field_grant(scope, tool, "env")
    return _result(grant, name in grant.env, "env", name)


def match_process(scope: DeclaredScope, name: str, tool: str | None = None) -> Match:
    grant = _field_grant(scope, tool, "processes")
    normalized = name.replace("\\", "/").rsplit("/", 1)[-1].casefold()
    return _result(grant, normalized in grant.processes, "process", name)
