"""Opaque storage of MCP secret values in the selected OS credential backend."""

from __future__ import annotations

from panopticon.secrets.contracts import KeyringAPI, KeyringDataError, KeyringUnavailable
from panopticon.secrets.keyring_backend import LazyKeyringAPI


class KeyringSecretProvisioner:
    def __init__(
        self,
        api: KeyringAPI | None = None,
        *,
        service: str = "panopticon-mcp-secrets",
    ) -> None:
        self._api = api or LazyKeyringAPI()
        self._service = service

    def __repr__(self) -> str:
        return "KeyringSecretProvisioner(<redacted>)"

    def provision(self, key: str, value: str) -> bool:
        if not key or not value:
            return False
        try:
            self._api.set_password(self._service, key, value)
        except (KeyringDataError, KeyringUnavailable, RuntimeError):
            return False
        return True


__all__ = ["KeyringSecretProvisioner"]
