"""Typed contracts for credential-backed secret storage and encrypted backups."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum, unique
from pathlib import Path
from typing import Protocol, TypeAlias, TypeVar, runtime_checkable

from panopticon.models.common import NonEmptyStr, PersistedPathValue, StrictModel
from panopticon.store.contracts import FaultInjector, PersistRequest, PersistResult
from panopticon.util.leak_check import LeakContext

_ResultT = TypeVar("_ResultT")
SecretConsumer: TypeAlias = Callable[[bytes], _ResultT]


@unique
class CapabilityStatus(StrEnum):
    """State returned by a secure credential boundary."""

    COMPLETE = "COMPLETE"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


@dataclass(slots=True)
class SecretUseError(RuntimeError):
    """A key could not be loaded for one callback invocation."""

    code: str

    def __str__(self) -> str:
        return self.code


class SecretHandle:
    """Opaque key capability that exposes bytes only during a callback."""

    __slots__ = ("_identifier", "_load")

    def __init__(self, identifier: str, load: Callable[[], bytes]) -> None:
        self._identifier = identifier
        self._load = load

    def use(self, callback: SecretConsumer[_ResultT]) -> _ResultT:
        """Run one operation with transient key bytes and return its result."""
        return callback(self._load())

    def __repr__(self) -> str:
        return "SecretHandle(<redacted>)"

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True, slots=True)
class CapabilityResult:
    """Value-free capability result."""

    status: CapabilityStatus
    code: str

    def __repr__(self) -> str:
        return f"CapabilityResult(status={self.status.value!r}, code={self.code!r})"

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True, slots=True)
class KeyResult:
    """Key lifecycle result with an opaque handle, never raw key bytes."""

    status: CapabilityStatus
    code: str
    key_id: str | None = None
    handle: SecretHandle | None = None

    def __repr__(self) -> str:
        return (
            f"KeyResult(status={self.status.value!r}, code={self.code!r}, key_id={self.key_id!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True, slots=True)
class OperationResult:
    """Value-free result for a key deletion operation."""

    status: CapabilityStatus
    code: str

    def __repr__(self) -> str:
        return f"OperationResult(status={self.status.value!r}, code={self.code!r})"

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True, slots=True)
class BackendResult:
    """Sanitized result exchanged with a platform credential backend."""

    status: CapabilityStatus | str
    code: str
    key_id: str | None = None

    def __repr__(self) -> str:
        status = self.status.value if isinstance(self.status, CapabilityStatus) else self.status
        return f"BackendResult(status={status!r}, code={self.code!r}, key_id={self.key_id!r})"

    def __str__(self) -> str:
        return self.__repr__()


@runtime_checkable
class SecretStore(Protocol):
    """Credential-store lifecycle contract used by backup services."""

    def capability(self) -> CapabilityResult: ...

    def create_key(self, name: str) -> KeyResult: ...

    def get_key(self, key_id: str) -> KeyResult: ...

    def rotate_key(self, name: str) -> KeyResult: ...

    def delete_key(self, key_id: str) -> OperationResult: ...


@runtime_checkable
class PlatformBackend(Protocol):
    """Injected platform bridge contract; implementations never expose key bytes."""

    def probe(self) -> BackendResult: ...

    def get_or_create(self, name: str) -> BackendResult: ...

    def read(self, key_id: str) -> BackendResult: ...

    def rotate(self, name: str) -> BackendResult: ...

    def delete(self, key_id: str) -> BackendResult: ...


@runtime_checkable
class SecretMaterialBackend(Protocol):
    """Private adapter seam for loading one key only inside a handle callback."""

    def read_material(self, key_id: str) -> bytes: ...


class KeyringUnavailableError(RuntimeError):
    """The selected OS credential backend cannot service a request."""

    def __str__(self) -> str:
        return "BACKEND_UNAVAILABLE"


KeyringUnavailable: TypeAlias = KeyringUnavailableError


class KeyringDataError(RuntimeError):
    """Credential-store metadata or key material failed strict decoding."""

    def __str__(self) -> str:
        return "BACKEND_FAILED"


@runtime_checkable
class KeyringAPI(Protocol):
    """Small injectable subset of the keyring package."""

    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...

    def delete_password(self, service: str, username: str) -> None: ...


@runtime_checkable
class NonceSource(Protocol):
    """Composition-injected source for authenticated-encryption nonces."""

    def next_nonce(self) -> bytes: ...


class BackupMetadata(StrictModel):
    """Sanitized metadata authenticated alongside an encrypted backup."""

    source: NonEmptyStr
    config_path: PersistedPathValue
    config_digest: NonEmptyStr


@dataclass(frozen=True, slots=True)
class BackupWriteRequest:
    """In-memory backup input; plaintext is deliberately absent from repr output."""

    target: Path
    plaintext: bytes
    key_name: str
    metadata: BackupMetadata
    leak_context: LeakContext

    def __repr__(self) -> str:
        return "BackupWriteRequest(<redacted>)"

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True, slots=True)
class BackupDecryptRequest:
    """In-memory envelope input with redacted representation."""

    envelope: bytes

    def __repr__(self) -> str:
        return "BackupDecryptRequest(<redacted>)"

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True, slots=True)
class BackupSaved:
    """Successful backup persistence result."""

    target: Path
    bytes_written: int
    status: CapabilityStatus
    code: str
    guidance_only: bool
    written_paths: tuple[Path, ...]

    def __repr__(self) -> str:
        return f"BackupSaved(status={self.status.value!r}, code={self.code!r})"

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True, slots=True)
class BackupUnavailable:
    """Guidance-only outcome that guarantees no path was written."""

    status: CapabilityStatus
    code: str
    guidance_only: bool
    written_paths: tuple[Path, ...]

    def __repr__(self) -> str:
        return f"BackupUnavailable(status={self.status.value!r}, code={self.code!r})"

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True, slots=True)
class BackupFailure:
    """Value-free failure outcome for save or decrypt."""

    status: CapabilityStatus
    code: str
    guidance_only: bool
    written_paths: tuple[Path, ...]

    def __repr__(self) -> str:
        return f"BackupFailure(status={self.status.value!r}, code={self.code!r})"

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True, slots=True)
class BackupDecrypted:
    """In-memory plaintext result; repr and str never contain the plaintext."""

    plaintext: bytes
    status: CapabilityStatus
    code: str
    guidance_only: bool
    written_paths: tuple[Path, ...]

    def __repr__(self) -> str:
        return f"BackupDecrypted(status={self.status.value!r}, code={self.code!r})"

    def __str__(self) -> str:
        return self.__repr__()


BackupResult: TypeAlias = BackupSaved | BackupUnavailable | BackupFailure | BackupDecrypted


@runtime_checkable
class PersistWriter(Protocol):
    """Task 4 persistence gateway shape accepted by the backup service."""

    def __call__(
        self,
        request: PersistRequest,
        context: LeakContext,
        injector: FaultInjector | None = None,
    ) -> PersistResult: ...
