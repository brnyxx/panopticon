"""Compose tool-specific declarations from local MCP metadata and config."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from panopticon.declared.authority import compose
from panopticon.declared.extract import (
    ConfigExtractor,
    ManifestExtractor,
    ReadmeExtractor,
    RegistryExtractor,
    SelfDeclExtractor,
    ToolDescExtractor,
)
from panopticon.declared.model import Authority, DeclaredScope, Diagnostic, ScopeGrant, SourceKind
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
    raw = result.context.raw_entry.raw

    # Discovery adapters are the sole boundary for repository/config reads.  They
    # may provide typed metadata under these keys; this function only consumes it.
    def value(*keys: str) -> object:
        for key in keys:
            if key in raw:
                return raw[key]
        return None

    server_grants: list[ScopeGrant] = [
        ConfigExtractor().extract({"env_keys": target.env_keys, "args": target.args})
    ]
    config = _mapping(value("config", "panopticon_config"))
    if config is not None:
        server_grants.append(ConfigExtractor().extract(config))
    elif value("config", "panopticon_config") is not None:
        server_grants.append(
            ScopeGrant(
                source=SourceKind.CONFIG,
                diagnostics=(
                    Diagnostic("MALFORMED_VALUE", "config must be an object", SourceKind.CONFIG),
                ),
            )
        )
    readme = value("readme", "readme_text", "README")
    if isinstance(readme, str):
        server_grants.append(ReadmeExtractor().extract(readme))
    elif readme is not None:
        server_grants.append(
            ScopeGrant(
                source=SourceKind.README,
                diagnostics=(
                    Diagnostic("MALFORMED_VALUE", "readme must be text", SourceKind.README),
                ),
            )
        )
    manifest = value("manifest", "package_manifest")
    if isinstance(manifest, (Mapping, str)):
        server_grants.append(ManifestExtractor().extract(manifest))
    registry = _mapping(value("registry", "registry_metadata"))
    # A supplied registry value is already acquired evidence (for example a
    # cache entry), so offline mode may consume it without performing I/O.
    if registry is not None:
        server_grants.append(RegistryExtractor().extract(registry))
    elif value("registry", "registry_metadata") is not None:
        server_grants.append(
            ScopeGrant(
                source=SourceKind.REGISTRY,
                diagnostics=(
                    Diagnostic(
                        "MALFORMED_VALUE", "registry must be an object", SourceKind.REGISTRY
                    ),
                ),
            )
        )
    self_decl = _mapping(value("self_decl", "panopticon", "declaration"))
    if self_decl is not None:
        server_grants.append(SelfDeclExtractor().extract(self_decl))
    tool_grants: dict[str, tuple[ScopeGrant, ...]] = {}
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
        tool_grants[name] = tuple(grants)
    scope = compose(server_grants, tool_grants)
    all_grants = (scope.server, *scope.tools.values())
    # `sources` records acquisition provenance, not only the winning
    # precedence tier. This keeps lower-priority evidence visible when a
    # maintainer declaration masks it.
    acquired_grants = (
        *server_grants,
        *(grant for grants in tool_grants.values() for grant in grants),
    )
    sources = tuple(
        sorted(
            {DeclaredSource(grant.source.value) for grant in acquired_grants},
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
    complete = any(
        grant.authority is Authority.AUTHORITATIVE and grant.complete for grant in acquired_grants
    )
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
