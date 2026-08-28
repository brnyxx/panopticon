"""Executable deterministic conditions for CFG-001 through CFG-012."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

from panopticon.models.inventory import SourceKind, Transport

from .catalog import RULE_BY_ID
from .entropy import high_entropy, token_classification
from .model import ConfigEvidence, ConfigInput, ConfigMatch, ConfigRule

_SHELL_SHAPES = ("sh -c", "bash -c", "curl|sh", "curl | sh", "powershell", "eval")
_BROAD_PATHS = ("~", "/", "$HOME")
_SYSTEM_PREFIXES = ("/etc", "/var", "/usr")


def _facts(mapping: object, key: str) -> tuple[str, ...]:
    return tuple(mapping.get(key, ())) if hasattr(mapping, "get") else ()


def _match(rule: ConfigRule, server, evidence: tuple[ConfigEvidence, ...]) -> ConfigMatch:
    return ConfigMatch(
        rule.rule_id,
        rule.severity,
        rule.kind,
        rule.fix_id,
        str(server.server_id),
        str(server.installation_id),
        evidence,
    )


def _per_server(
    context: ConfigInput,
    rule: ConfigRule,
    predicate: Callable[[object], tuple[ConfigEvidence, ...]],
) -> list[ConfigMatch]:
    out: list[ConfigMatch] = []
    for server in context.servers:
        evidence = predicate(server)
        if evidence:
            out.append(_match(rule, server, evidence))
    return out


def _rule001(context: ConfigInput) -> list[ConfigMatch]:
    rule = RULE_BY_ID["CFG-001"]

    def check(server):
        found = tuple(
            ConfigEvidence(key, token_classification(value) or "token")
            for key in server.env_keys
            for value in _facts(context.env_values, str(server.installation_id))
            if token_classification(value)
        )
        return found

    return _per_server(context, rule, check)


def _rule002(context: ConfigInput) -> list[ConfigMatch]:
    rule = RULE_BY_ID["CFG-002"]

    def check(server):
        package = server.package
        if package is not None and (package.pinned is None or package.pinned == "@latest"):
            return (ConfigEvidence("package", "unpinned"),)
        return ()

    return _per_server(context, rule, check)


def _rule003(context: ConfigInput) -> list[ConfigMatch]:
    rule = RULE_BY_ID["CFG-003"]

    def check(server):
        command = server.command or ""
        return (
            (ConfigEvidence("command", next(shape for shape in _SHELL_SHAPES if shape in command)),)
            if any(shape in command for shape in _SHELL_SHAPES)
            else ()
        )

    return _per_server(context, rule, check)


def _rule004(context: ConfigInput) -> list[ConfigMatch]:
    rule = RULE_BY_ID["CFG-004"]

    def check(server):
        if str(server.installation_id) not in context.filesystem_servers:
            return ()
        paths = _facts(context.allowed_paths, str(server.installation_id))
        broad = next(
            (
                path
                for path in paths
                if path in _BROAD_PATHS or (len(path) == 3 and path[1:] in (":\\", ":/"))
            ),
            None,
        )
        return (ConfigEvidence("allowed_path", "broad"),) if broad else ()

    return _per_server(context, rule, check)


def _rule005(context: ConfigInput) -> list[ConfigMatch]:
    rule = RULE_BY_ID["CFG-005"]
    groups: dict[str, list] = defaultdict(list)
    for server in context.servers:
        groups[str(server.server_id)].append(server)
    out = []
    for servers in groups.values():
        versions = {
            s.package.resolved or s.package.pinned for s in servers if s.package is not None
        }
        if len(servers) > 1 and len(versions) > 1:
            out.extend(
                _match(rule, s, (ConfigEvidence("server_id", "version_mismatch"),)) for s in servers
            )
    return out


def _rule006(context: ConfigInput) -> list[ConfigMatch]:
    rule = RULE_BY_ID["CFG-006"]
    return _per_server(
        context,
        rule,
        lambda s: (
            (ConfigEvidence("source", "unverifiable"),)
            if s.source.kind in (SourceKind.LOCAL, SourceKind.REMOTE)
            else ()
        ),
    )


def _rule007(context: ConfigInput) -> list[ConfigMatch]:
    rule = RULE_BY_ID["CFG-007"]

    def check(server):
        return tuple(
            ConfigEvidence(key, "high_entropy")
            for key in server.env_keys
            for value in _facts(context.env_values, str(server.installation_id))
            if high_entropy(value)
        )

    return _per_server(context, rule, check)


def _rule008(context: ConfigInput) -> list[ConfigMatch]:
    rule = RULE_BY_ID["CFG-008"]
    return _per_server(
        context,
        rule,
        lambda s: (
            (ConfigEvidence("url", "plaintext"),)
            if s.url is not None and str(s.url).startswith("http://")
            else ()
        ),
    )


def _rule009(context: ConfigInput) -> list[ConfigMatch]:
    rule = RULE_BY_ID["CFG-009"]
    return _per_server(
        context, rule, lambda s: (ConfigEvidence("server", "disabled"),) if s.disabled else ()
    )


def _rule010(context: ConfigInput) -> list[ConfigMatch]:
    rule = RULE_BY_ID["CFG-010"]
    return _per_server(
        context,
        rule,
        lambda s: (
            (ConfigEvidence("arg", "absolute_system_path"),)
            if any(arg.startswith(_SYSTEM_PREFIXES) for arg in s.args)
            else ()
        ),
    )


def _rule011(context: ConfigInput) -> list[ConfigMatch]:
    rule = RULE_BY_ID["CFG-011"]
    return _per_server(
        context,
        rule,
        lambda s: (
            (ConfigEvidence("header", "token"),)
            if s.transport in (Transport.HTTP, Transport.SSE)
            and _facts(context.token_header_keys, str(s.installation_id))
            else ()
        ),
    )


def _rule012(context: ConfigInput) -> list[ConfigMatch]:
    rule = RULE_BY_ID["CFG-012"]
    return _per_server(
        context,
        rule,
        lambda s: (
            (ConfigEvidence("transport", "unwrapped_stdio"),)
            if s.transport is Transport.STDIO and not s.wrapped
            else ()
        ),
    )


_HANDLERS = (
    _rule001,
    _rule002,
    _rule003,
    _rule004,
    _rule005,
    _rule006,
    _rule007,
    _rule008,
    _rule009,
    _rule010,
    _rule011,
    _rule012,
)


def analyze(context: ConfigInput) -> tuple[ConfigMatch, ...]:
    matches = [match for handler in _HANDLERS for match in handler(context)]
    return tuple(sorted(matches, key=lambda m: (m.rule_id, m.server_id, m.installation_id)))
