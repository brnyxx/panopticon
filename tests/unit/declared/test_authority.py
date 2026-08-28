import os

from panopticon.declared import (
    Authority,
    Completeness,
    ConfigExtractor,
    DeclaredScope,
    ScopeGrant,
    ScopeStatus,
    SelfDeclExtractor,
    SourceKind,
    compose,
    host_matches,
    host_port,
    match_env,
    match_host,
    match_network,
    match_process,
    normalize_env,
    normalize_host,
    normalize_path,
    normalize_port,
    normalize_process,
    path_matches,
)


def test_authoritative_scope_is_tool_specific() -> None:
    scope = compose(
        [
            ScopeGrant(
                hosts=("server.example",),
                source=SourceKind.REGISTRY,
                authority=Authority.AUTHORITATIVE,
                complete=True,
            )
        ],
        {
            "read": [
                ScopeGrant(
                    hosts=("read.example",),
                    source=SourceKind.SELF_DECL,
                    authority=Authority.AUTHORITATIVE,
                    complete=True,
                )
            ]
        },
    )
    assert match_host(scope, "read.example", "read").status is ScopeStatus.COMPLETE
    assert match_host(scope, "server.example", "read").status is ScopeStatus.INVALID
    assert match_host(scope, "server.example", "other").status is ScopeStatus.COMPLETE


def test_readme_cannot_mask_other_tool_or_upgrade_completeness() -> None:
    scope = compose(
        [
            ScopeGrant(
                hosts=("registry.example",),
                source=SourceKind.REGISTRY,
                authority=Authority.AUTHORITATIVE,
                complete=True,
            )
        ],
        {
            "tool": [
                ScopeGrant(
                    hosts=("tool.example",),
                    source=SourceKind.TOOL_DESCRIPTION,
                    authority=Authority.PARTIAL,
                ),
                ScopeGrant(
                    hosts=("readme.example",), source=SourceKind.README, authority=Authority.PARTIAL
                ),
            ]
        },
    )
    assert match_host(scope, "tool.example", "tool").status is ScopeStatus.PARTIAL
    assert match_host(scope, "readme.example", "tool").status is ScopeStatus.UNKNOWN
    assert scope.completeness is Completeness.COMPLETE


def test_authoritative_completeness_is_explicit() -> None:
    partial = DeclaredScope(
        server=ScopeGrant(authority=Authority.AUTHORITATIVE, complete=False, hosts=("x.example",))
    )
    complete = DeclaredScope(
        server=ScopeGrant(authority=Authority.AUTHORITATIVE, complete=True, hosts=("x.example",))
    )
    assert partial.completeness is Completeness.PARTIAL
    assert complete.completeness is Completeness.COMPLETE


def test_user_config_does_not_make_maintainer_claim() -> None:
    config = ConfigExtractor().extract({"env_keys": ["TOKEN"]})
    claim = SelfDeclExtractor().extract({"env": ["TOKEN"]})
    assert config.source is SourceKind.CONFIG and not config.maintainer
    assert claim.source is SourceKind.SELF_DECL and claim.maintainer


def test_authority_precedence_and_unmatched_partial_unknown() -> None:
    scope = compose(
        [
            ScopeGrant(
                hosts=("none.example",), source=SourceKind.MANIFEST, authority=Authority.NONE
            ),
            ScopeGrant(
                hosts=("partial.example",),
                source=SourceKind.TOOL_DESCRIPTION,
                authority=Authority.PARTIAL,
            ),
            ScopeGrant(
                hosts=("auth.example",),
                source=SourceKind.REGISTRY,
                authority=Authority.AUTHORITATIVE,
                complete=True,
            ),
        ],
        {},
    )
    assert match_host(scope, "auth.example").status is ScopeStatus.COMPLETE
    partial_scope = compose(
        [],
        {
            "tool": [
                ScopeGrant(
                    hosts=("partial.example",),
                    source=SourceKind.TOOL_DESCRIPTION,
                    authority=Authority.PARTIAL,
                )
            ]
        },
    )
    assert match_host(partial_scope, "partial.example", "tool").status is ScopeStatus.PARTIAL
    assert match_host(partial_scope, "unknown.example", "tool").status is ScopeStatus.UNKNOWN
    none_scope = compose(
        [ScopeGrant(hosts=("none.example",), source=SourceKind.MANIFEST, authority=Authority.NONE)],
        {},
    )
    assert match_host(none_scope, "none.example").status is ScopeStatus.UNKNOWN


def test_network_port_and_default_boundaries() -> None:
    scope = compose(
        [
            ScopeGrant(
                hosts=("api.example",),
                ports=(443,),
                source=SourceKind.REGISTRY,
                authority=Authority.AUTHORITATIVE,
                complete=True,
            )
        ],
        {},
    )
    assert match_network(scope, "api.example", 443).status is ScopeStatus.COMPLETE
    assert match_network(scope, "api.example", 80).status is ScopeStatus.INVALID
    assert normalize_port("https", "https") == 443
    assert normalize_port("bad", "https") == 443


def test_path_parent_and_symlink_shaped_escape() -> None:
    home = "/tmp/panopticon-test-home"
    assert normalize_path("~/project/../other", home) == "~/other"
    assert normalize_path("~/../../etc", home) is None
    assert path_matches("/tmp/project/*", "/tmp/project/file")
    assert not path_matches("/tmp/project/*", "/tmp/project/../secret")
    assert path_matches("/tmp/Case/*", "/tmp/Case/file")
    assert path_matches("/tmp/Case/*", "/tmp/case/file") is (os.name == "nt")


def test_environment_and_process_normalization() -> None:
    assert normalize_env(" TOKEN ") == "TOKEN"
    assert normalize_env("TOKEN-NAME") is None
    assert normalize_process("/usr/bin/Python3") == "python3"
    assert normalize_process("bad name") is None
    scope = compose(
        [
            ScopeGrant(
                env=("TOKEN",),
                processes=("python3",),
                source=SourceKind.SELF_DECL,
                authority=Authority.AUTHORITATIVE,
                complete=True,
            )
        ],
        {},
    )
    assert match_env(scope, "TOKEN").status is ScopeStatus.COMPLETE
    assert match_process(scope, "/opt/PYTHON3").status is ScopeStatus.COMPLETE


def test_malformed_declarations_are_diagnostic() -> None:
    grant = SelfDeclExtractor().extract({"paths": ["~/../../etc"], "env": ["not-valid"]})
    assert grant.complete is False
    assert grant.authority is Authority.AUTHORITATIVE
    assert grant.diagnostics and grant.diagnostics[0].code == "MALFORMED_VALUE"


def test_host_wildcard_public_suffix_port_idna_ipv6_and_case() -> None:
    assert host_matches("*.example.com", "a.example.com")
    assert not host_matches("*.example.com", "example.com")
    assert not host_matches("*.co.uk", "example.co.uk")
    assert host_matches("BÜCHER.example", "xn--bcher-kva.example")
    assert host_matches("[2001:db8::1]", "2001:0db8:0:0:0:0:0:1")
    assert normalize_host("Example.COM.") == "example.com"
    assert host_port("https://api.example")[1] == 443
    assert host_port("[2001:db8::1]:8443")[1] == 8443
    assert normalize_port("443") == 443
    assert normalize_port(0) is None
    assert normalize_port(70000) is None
