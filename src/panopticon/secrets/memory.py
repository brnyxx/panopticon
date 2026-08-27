"""Deterministic in-memory credential store used by tests and local composition."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

from panopticon.secrets.contracts import (
    CapabilityResult,
    CapabilityStatus,
    KeyResult,
    OperationResult,
    SecretHandle,
    SecretUseError,
)

KeyFactory = Callable[[str], bytes]


@dataclass(frozen=True, slots=True)
class _StoredKey:
    """Private key record; its representation never includes key material."""

    key_id: str
    material: bytes

    def __repr__(self) -> str:
        return "_StoredKey(<redacted>)"


class InMemorySecretStore:
    """A deterministic credential store with explicit key-retention semantics."""

    __slots__ = (
        "_available",
        "_current",
        "_deleted",
        "_failure",
        "_key_factory",
        "_keys",
        "_sequence",
    )

    def __init__(
        self,
        key_factory: KeyFactory | None = None,
        available: bool = True,
        failure: str | None = None,
    ) -> None:
        self._key_factory = key_factory or self._default_key_factory
        self._available = available
        self._failure = failure
        self._keys: dict[str, _StoredKey] = {}
        self._current: dict[str, str] = {}
        self._deleted: set[str] = set()
        self._sequence = 0

    def __repr__(self) -> str:
        return "InMemorySecretStore(<redacted>)"

    def __str__(self) -> str:
        return self.__repr__()

    @staticmethod
    def _default_key_factory(name: str) -> bytes:
        """Derive stable fixture material without making it a production secret."""
        return hashlib.sha256(name.encode("utf-8")).digest()

    def capability(self) -> CapabilityResult:
        """Report whether this deterministic store can service operations."""
        if not self._available:
            return CapabilityResult(CapabilityStatus.UNAVAILABLE, "BACKEND_UNAVAILABLE")
        return CapabilityResult(CapabilityStatus.COMPLETE, "BACKEND_AVAILABLE")

    def _store_failed(self) -> bool:
        return self._failure == "STORE"

    def _failed_key(self) -> KeyResult:
        return KeyResult(CapabilityStatus.FAILED, "STORE_FAILED")

    def _failed_operation(self) -> OperationResult:
        return OperationResult(CapabilityStatus.FAILED, "STORE_FAILED")

    def _new_key(self, name: str) -> KeyResult:
        if not name:
            return KeyResult(CapabilityStatus.FAILED, "INVALID_KEY_NAME")
        material = self._key_factory(name)
        if len(material) != 32:
            return KeyResult(CapabilityStatus.FAILED, "INVALID_KEY")
        self._sequence += 1
        key_id = f"memory-key-{self._sequence}"
        self._keys[key_id] = _StoredKey(key_id, material)
        self._current[name] = key_id
        self._deleted.discard(key_id)
        return KeyResult(
            CapabilityStatus.COMPLETE,
            "KEY_CREATED",
            key_id,
            self._handle(key_id),
        )

    def _handle(self, key_id: str) -> SecretHandle:
        return SecretHandle(key_id, lambda: self._material_for(key_id))

    def _material_for(self, key_id: str) -> bytes:
        if self._failure == "ENCRYPTION":
            raise SecretUseError("ENCRYPTION_FAILED")
        stored = self._keys.get(key_id)
        if stored is None:
            raise SecretUseError("KEY_NOT_FOUND")
        return stored.material

    def create_key(self, name: str) -> KeyResult:
        """Return the current key for a name, creating it when absent."""
        if not self._available:
            return KeyResult(CapabilityStatus.UNAVAILABLE, "BACKEND_UNAVAILABLE")
        if self._store_failed():
            return self._failed_key()
        current_id = self._current.get(name)
        if current_id is not None and current_id in self._keys:
            return KeyResult(
                CapabilityStatus.COMPLETE,
                "KEY_AVAILABLE",
                current_id,
                self._handle(current_id),
            )
        return self._new_key(name)

    def get_key(self, key_id: str) -> KeyResult:
        """Return one retained key by opaque identifier."""
        if not self._available:
            return KeyResult(CapabilityStatus.UNAVAILABLE, "BACKEND_UNAVAILABLE")
        if self._store_failed():
            return self._failed_key()
        stored = self._keys.get(key_id)
        if stored is not None:
            return KeyResult(
                CapabilityStatus.COMPLETE,
                "KEY_AVAILABLE",
                key_id,
                self._handle(key_id),
            )
        if key_id in self._deleted:
            return KeyResult(CapabilityStatus.UNAVAILABLE, "KEY_NOT_FOUND")
        return KeyResult(CapabilityStatus.UNAVAILABLE, "KEY_NOT_FOUND", key_id)

    def rotate_key(self, name: str) -> KeyResult:
        """Create a new current key while retaining all prior identifiers."""
        if not self._available:
            return KeyResult(CapabilityStatus.UNAVAILABLE, "BACKEND_UNAVAILABLE")
        if self._store_failed():
            return self._failed_key()
        if not name:
            return KeyResult(CapabilityStatus.FAILED, "INVALID_KEY_NAME")
        material = self._key_factory(name)
        if len(material) != 32:
            return KeyResult(CapabilityStatus.FAILED, "INVALID_KEY")
        self._sequence += 1
        key_id = f"memory-key-{self._sequence}"
        self._keys[key_id] = _StoredKey(key_id, material)
        self._current[name] = key_id
        return KeyResult(
            CapabilityStatus.COMPLETE,
            "KEY_ROTATED",
            key_id,
            self._handle(key_id),
        )

    def delete_key(self, key_id: str) -> OperationResult:
        """Delete exactly one key and leave all other retained keys untouched."""
        if not self._available:
            return OperationResult(CapabilityStatus.UNAVAILABLE, "BACKEND_UNAVAILABLE")
        if self._store_failed():
            return self._failed_operation()
        if key_id not in self._keys:
            return OperationResult(CapabilityStatus.UNAVAILABLE, "KEY_NOT_FOUND")
        del self._keys[key_id]
        self._deleted.add(key_id)
        for name, current_id in tuple(self._current.items()):
            if current_id == key_id:
                del self._current[name]
        return OperationResult(CapabilityStatus.COMPLETE, "KEY_DELETED")
