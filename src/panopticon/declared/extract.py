"""Pure extractors; inputs are supplied in memory by callers."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence

from .model import Authority, Capability, Diagnostic, ScopeGrant, SourceKind
from .normalize import (
    host_port,
    normalize_env,
    normalize_host,
    normalize_path,
    normalize_process,
)


def _seq(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return tuple(item for item in value if isinstance(item, str))
    return ()


def _grant(
    source: SourceKind,
    *,
    paths: Iterable[str] = (),
    hosts: Iterable[str] = (),
    ports: Iterable[int] = (),
    env: Iterable[str] = (),
    processes: Iterable[str] = (),
    caps: Iterable[Capability] = (),
    maintainer: bool = False,
    complete: bool = False,
    authority: Authority = Authority.PARTIAL,
    diagnostics: Iterable[Diagnostic] = (),
) -> ScopeGrant:
    return ScopeGrant(
        tuple(sorted(set(paths))),
        tuple(sorted(set(hosts))),
        tuple(sorted(set(ports))),
        tuple(sorted(set(env))),
        tuple(sorted(set(processes))),
        tuple(sorted(set(caps), key=lambda x: x.value)),
        source,
        1.0,
        authority,
        maintainer,
        complete,
        tuple(diagnostics),
    )


class ToolDescExtractor:
    def extract(
        self, description: str | None = None, annotations: Mapping[str, object] | None = None
    ) -> ScopeGrant:
        text = description or ""
        ann = annotations or {}
        hosts = tuple(
            normalize_host(x)
            for x in re.findall(
                r"(?:https?://|www\.)?([A-Za-z0-9][A-Za-z0-9.-]+\.[A-Za-z]{2,})", text
            )
        )
        paths = tuple(
            x for x in (normalize_path(v) for v in re.findall(r"(?:~?/|/)[\w.\-/]+", text)) if x
        )
        caps = [Capability.READ]
        if ann.get("readOnlyHint") is False or re.search(
            r"\b(write|save|update|create)\b", text, re.I
        ):
            caps.append(Capability.WRITE)
        if ann.get("destructiveHint") is True:
            caps.append(Capability.DESTRUCTIVE)
        if ann.get("openWorldHint") is True:
            caps.append(Capability.OPEN_WORLD)
        return _grant(
            SourceKind.TOOL_DESCRIPTION,
            paths=paths,
            hosts=hosts,
            caps=caps,
            complete=False,
            authority=Authority.PARTIAL,
        )


class ReadmeExtractor:
    def extract(self, text: str) -> ScopeGrant:
        code = "\n".join(re.findall(r"```(?:\w+)?\n(.*?)```", text, re.S)) or text
        hosts = tuple(
            normalize_host(x)
            for x in re.findall(r"(?:https?://)?([A-Za-z0-9][A-Za-z0-9.-]+\.[A-Za-z]{2,})", code)
        )
        paths = tuple(
            x for x in (normalize_path(v) for v in re.findall(r"(?:~?/|/)[\w.\-/]+", code)) if x
        )
        env = tuple(
            x for x in (normalize_env(v) for v in re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", code)) if x
        )
        return _grant(
            SourceKind.README, paths=paths, hosts=hosts, env=env, authority=Authority.PARTIAL
        )


class ManifestExtractor:
    def extract(self, manifest: Mapping[str, object] | str) -> ScopeGrant:
        if isinstance(manifest, str):
            try:
                parsed: object = json.loads(manifest)
            except json.JSONDecodeError:
                parsed = None
        else:
            parsed = manifest
        if not isinstance(parsed, Mapping):
            return _grant(
                SourceKind.MANIFEST,
                authority=Authority.NONE,
                diagnostics=(Diagnostic("MALFORMED_VALUE", "manifest must be an object"),),
            )
        data = {str(key): value for key, value in parsed.items()}
        vals = []
        for key in ("homepage", "repository", "bugs"):
            v = data.get(key)
            if isinstance(v, str):
                vals.append(v)
            elif isinstance(v, Mapping) and isinstance(v.get("url"), str):
                vals.append(str(v["url"]))
        hosts = tuple(host_port(v)[0] for v in vals if host_port(v)[0])
        bins = data.get("bin", ())
        return _grant(
            SourceKind.MANIFEST,
            hosts=hosts,
            processes=tuple(
                normalized
                for item in _seq(bins)
                if (normalized := normalize_process(item)) is not None
            ),
            authority=Authority.PARTIAL,
        )


class ConfigExtractor:
    def extract(self, config: Mapping[str, object]) -> ScopeGrant:
        env = tuple(x for x in (normalize_env(v) for v in _seq(config.get("env_keys", ()))) if x)
        paths = tuple(x for x in (normalize_path(v) for v in _seq(config.get("args", ()))) if x)
        return _grant(SourceKind.CONFIG, env=env, paths=paths, authority=Authority.PARTIAL)


class RegistryExtractor:
    def extract(self, data: Mapping[str, object]) -> ScopeGrant:
        hosts = []
        for item in _seq(data.get("remotes", ())):
            h, _port = host_port(item)
            hosts.append(h)
        env = tuple(
            x for x in (normalize_env(v) for v in _seq(data.get("environment_variables", ()))) if x
        )
        complete = data.get("complete") is True
        return _grant(
            SourceKind.REGISTRY,
            hosts=hosts,
            env=env,
            authority=Authority.AUTHORITATIVE if complete else Authority.PARTIAL,
            complete=complete,
            maintainer=True,
        )


class SelfDeclExtractor:
    def extract(self, data: Mapping[str, object]) -> ScopeGrant:
        if data.get("version") not in (None, 1):
            return _grant(
                SourceKind.SELF_DECL,
                maintainer=True,
                authority=Authority.NONE,
                diagnostics=(
                    Diagnostic(
                        "UNSUPPORTED_VERSION",
                        "self declaration version is unsupported",
                        SourceKind.SELF_DECL,
                    ),
                ),
            )
        raw_paths, raw_hosts = _seq(data.get("paths", ())), _seq(data.get("hosts", ()))
        raw_env, raw_proc = _seq(data.get("env", ())), _seq(data.get("processes", ()))
        paths = tuple(x for x in (normalize_path(v) for v in raw_paths) if x)
        hosts = tuple(normalize_host(v) for v in raw_hosts)
        env = tuple(x for x in (normalize_env(v) for v in raw_env) if x)
        proc = tuple(x for x in (normalize_process(v) for v in raw_proc) if x)
        bad = len(paths) != len(raw_paths) or len(env) != len(raw_env) or len(proc) != len(raw_proc)
        diagnostics = (
            (
                Diagnostic(
                    "MALFORMED_VALUE",
                    "self declaration contains invalid values",
                    SourceKind.SELF_DECL,
                ),
            )
            if bad
            else ()
        )
        complete = data.get("complete") is True and not bad
        return _grant(
            SourceKind.SELF_DECL,
            paths=paths,
            hosts=hosts,
            env=env,
            processes=proc,
            maintainer=True,
            authority=Authority.AUTHORITATIVE,
            complete=complete,
            diagnostics=diagnostics,
        )
