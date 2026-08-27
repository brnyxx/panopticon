"""OS credential-store adapters with injected platform backends."""

from __future__ import annotations

import sys
from typing import Final, Literal

from panopticon.secrets.contracts import (
    BackendResult,
    CapabilityResult,
    CapabilityStatus,
    KeyResult,
    OperationResult,
    PlatformBackend,
    SecretHandle,
    SecretMaterialBackend,
)
from panopticon.secrets.keyring_backend import KeyringBridge

_ALLOWED_CODES: Final[frozenset[str]] = frozenset(
    {
        "BACKEND_AVAILABLE",
        "BACKEND_UNAVAILABLE",
        "BACKEND_FAILED",
        "BACKEND_ROLLBACK_FAILED",
        "KEY_CREATED",
        "KEY_AVAILABLE",
        "KEY_ROTATED",
        "KEY_DELETED",
        "KEY_NOT_FOUND",
        "INVALID_KEY",
        "INVALID_KEY_NAME",
    }
)


_PLATFORM_UNAVAILABLE: Final = BackendResult(
    CapabilityStatus.UNAVAILABLE,
    "BACKEND_UNAVAILABLE",
)


class _UnavailablePlatformBackend:
    """Typed no-op backend selected when a native adapter targets another host."""

    __slots__ = ()

    def probe(self) -> BackendResult:
        return _PLATFORM_UNAVAILABLE

    def get_or_create(self, name: str) -> BackendResult:
        del name
        return _PLATFORM_UNAVAILABLE

    def read(self, key_id: str) -> BackendResult:
        del key_id
        return _PLATFORM_UNAVAILABLE

    def rotate(self, name: str) -> BackendResult:
        del name
        return _PLATFORM_UNAVAILABLE

    def delete(self, key_id: str) -> BackendResult:
        del key_id
        return _PLATFORM_UNAVAILABLE


def _default_backend(
    expected_platform: Literal["darwin", "linux", "win32"], service: str
) -> PlatformBackend:
    if sys.platform != expected_platform:
        return _UnavailablePlatformBackend()
    return KeyringBridge(service)


class _PlatformAdapter:
    """Shared lifecycle translation from a platform bridge to typed store results."""

    __slots__ = ("_backend",)

    def __init__(self, backend: PlatformBackend) -> None:
        self._backend = backend

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted>)"

    def __str__(self) -> str:
        return self.__repr__()

    @staticmethod
    def _status(value: CapabilityStatus | str) -> CapabilityStatus:
        try:
            return CapabilityStatus(value)
        except ValueError:
            return CapabilityStatus.FAILED

    @staticmethod
    def _code(value: str) -> str:
        return value if value in _ALLOWED_CODES else "BACKEND_FAILED"

    def _handle(self, key_id: str | None) -> SecretHandle | None:
        if key_id is None or not isinstance(self._backend, SecretMaterialBackend):
            return None
        backend = self._backend
        return SecretHandle(key_id, lambda: backend.read_material(key_id))

    def _key_result(self, result: BackendResult) -> KeyResult:
        status = self._status(result.status)
        code = self._code(result.code)
        key_id = result.key_id if isinstance(result.key_id, str) else None
        handle = self._handle(key_id) if status is CapabilityStatus.COMPLETE else None
        return KeyResult(status, code, key_id, handle)

    def capability(self) -> CapabilityResult:
        """Probe the injected platform backend."""
        result = self._backend.probe()
        return CapabilityResult(self._status(result.status), self._code(result.code))

    def probe(self) -> CapabilityResult:
        """Expose the platform capability probe for adapter diagnostics."""
        return self.capability()

    def create_key(self, name: str) -> KeyResult:
        """Get or create the current named credential."""
        return self._key_result(self._backend.get_or_create(name))

    def get_key(self, key_id: str) -> KeyResult:
        """Read one opaque credential identifier."""
        return self._key_result(self._backend.read(key_id))

    def rotate_key(self, name: str) -> KeyResult:
        """Rotate the current credential while leaving old identifiers retained."""
        return self._key_result(self._backend.rotate(name))

    def delete_key(self, key_id: str) -> OperationResult:
        """Delete one credential through the injected platform backend."""
        result = self._backend.delete(key_id)
        return OperationResult(self._status(result.status), self._code(result.code))


class MacOSKeychainAdapter(_PlatformAdapter):
    """Adapter for the macOS Keychain keyring backend."""

    def __init__(self, backend: PlatformBackend | None = None) -> None:
        super().__init__(
            backend
            if backend is not None
            else _default_backend("darwin", "panopticon.macos-keychain.v1")
        )


class LinuxSecretServiceAdapter(_PlatformAdapter):
    """Adapter for the Linux Secret Service keyring backend."""

    def __init__(self, backend: PlatformBackend | None = None) -> None:
        super().__init__(
            backend
            if backend is not None
            else _default_backend("linux", "panopticon.linux-secret-service.v1")
        )


class WindowsCredentialAdapter(_PlatformAdapter):
    """Adapter for the Windows native credential-manager keyring backend."""

    def __init__(self, backend: PlatformBackend | None = None) -> None:
        super().__init__(
            backend
            if backend is not None
            else _default_backend("win32", "panopticon.windows-credential-manager.v1")
        )
