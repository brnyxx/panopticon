"""Deterministic host allowlist for install and network WATCH rules."""

from __future__ import annotations

import fnmatch

INSTALL_HOSTS: tuple[str, ...] = (
    "registry.npmjs.org",
    "registry.yarnpkg.com",
    "pypi.org",
    "files.pythonhosted.org",
    "github.com",
    "objects.githubusercontent.com",
    "*.cloudfront.net",
)
ALWAYS_HOSTS: tuple[str, ...] = ()


def normalize_host(host: str) -> str:
    return host.strip().rstrip(".").lower()


def host_allowed(host: str, *, install: bool = False) -> bool:
    value = normalize_host(host)
    patterns = (*ALWAYS_HOSTS, *(INSTALL_HOSTS if install else ()))
    return any(fnmatch.fnmatchcase(value, pattern) for pattern in patterns)


def excluded(host: str, *, install: bool = False) -> bool:
    return host_allowed(host, install=install)
