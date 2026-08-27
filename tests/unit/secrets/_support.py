from __future__ import annotations

import base64
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Final, NamedTuple, Protocol, runtime_checkable

import pytest

from panopticon.store import LeakContext

SECRET_TEXT: Final = "memory-only-config-secret-7f9b"
SECRET_CONFIG: Final = (
    b'{"mcpServers":{"fixture":{"env":{"TOKEN":"memory-only-config-secret-7f9b"}}}}\n'
)
KEY_NAME: Final = "panopticon/fixture/config-backup"
KEY_BYTES: Final = b"k" * 32
ROTATED_KEY_BYTES: Final = b"r" * 32
NONCE: Final = b"n" * 12
OTHER_NONCE: Final = b"o" * 12
CONFIG_PATH: Final = "~/.config/fixture/client.json"
CONFIG_DIGEST: Final = "sha256:fixture-config"


@runtime_checkable
class OutcomeLike(Protocol):
    @property
    def status(self) -> str: ...

    @property
    def code(self) -> str: ...


@runtime_checkable
class KeyResultLike(OutcomeLike, Protocol):
    @property
    def key_id(self) -> str | None: ...


@runtime_checkable
class SecretStoreLike(Protocol):
    def capability(self) -> OutcomeLike: ...

    def create_key(self, name: str) -> KeyResultLike: ...

    def get_key(self, key_id: str) -> KeyResultLike: ...

    def rotate_key(self, name: str) -> KeyResultLike: ...

    def delete_key(self, key_id: str) -> OutcomeLike: ...


@runtime_checkable
class PlatformBackendLike(Protocol):
    def probe(self) -> OutcomeLike: ...

    def get_or_create(self, name: str) -> KeyResultLike: ...

    def read(self, key_id: str) -> KeyResultLike: ...

    def rotate(self, name: str) -> KeyResultLike: ...

    def delete(self, key_id: str) -> OutcomeLike: ...


class BackendResult(NamedTuple):
    status: str
    code: str
    key_id: str | None = None
    detail: str = ""

    def __repr__(self) -> str:
        return f"BackendResult(status={self.status!r}, code={self.code!r}, key_id={self.key_id!r})"


BackendRecord = tuple[str, str]


class DeterministicPlatformBackend:
    __slots__ = ("_code", "_detail", "_operations", "_records", "_sequence", "_status")

    def __init__(self, status: str, code: str, detail: str) -> None:
        status_value_name = "value"
        status_value = getattr(status, status_value_name, status)
        self._status = status_value if isinstance(status_value, str) else str(status_value)
        self._code = code
        self._detail = detail
        self._operations: list[str] = []
        self._records: list[BackendRecord] = []
        self._sequence = 0

    @property
    def calls(self) -> int:
        return len(self._operations)

    @property
    def operations(self) -> tuple[str, ...]:
        return tuple(self._operations)

    def __repr__(self) -> str:
        return (
            f"DeterministicPlatformBackend(status={self._status!r}, "
            f"code={self._code!r}, calls={self.calls})"
        )

    def _failed(self, key_id: str | None = None) -> BackendResult:
        return BackendResult(self._status, self._code, key_id, self._detail)

    def _new_record(self, name: str) -> BackendRecord:
        self._sequence += 1
        record = (name, f"{name}:key-{self._sequence}")
        self._records.append(record)
        return record

    def probe(self) -> BackendResult:
        self._operations.append("probe")
        return self._failed()

    def get_or_create(self, name: str) -> BackendResult:
        self._operations.append("get_or_create")
        if self._status != "COMPLETE":
            return self._failed()
        for record in self._records:
            if record[0] == name:
                return BackendResult(self._status, "KEY_AVAILABLE", record[1])
        return BackendResult(self._status, "KEY_CREATED", self._new_record(name)[1])

    def read(self, key_id: str) -> BackendResult:
        self._operations.append("read")
        if self._status != "COMPLETE":
            return self._failed()
        for record in self._records:
            if record[1] == key_id:
                return BackendResult(self._status, "KEY_AVAILABLE", record[1])
        return BackendResult("UNAVAILABLE", "KEY_NOT_FOUND")

    def rotate(self, name: str) -> BackendResult:
        self._operations.append("rotate")
        if self._status != "COMPLETE":
            return self._failed()
        return BackendResult(self._status, "KEY_ROTATED", self._new_record(name)[1])

    def delete(self, key_id: str) -> BackendResult:
        self._operations.append("delete")
        if self._status != "COMPLETE":
            return self._failed()
        for index, record in enumerate(self._records):
            if record[1] == key_id:
                del self._records[index]
                return BackendResult(self._status, "KEY_DELETED")
        return BackendResult("UNAVAILABLE", "KEY_NOT_FOUND")


@runtime_checkable
class MetadataLike(Protocol):
    @property
    def source(self) -> str: ...

    @property
    def config_path(self) -> str: ...

    @property
    def config_digest(self) -> str: ...


@runtime_checkable
class BackupRequestLike(Protocol):
    @property
    def target(self) -> Path: ...

    @property
    def plaintext(self) -> bytes: ...


@runtime_checkable
class DecryptRequestLike(Protocol):
    @property
    def envelope(self) -> bytes: ...


@runtime_checkable
class NonceSourceLike(Protocol):
    def next_nonce(self) -> bytes: ...


class FixedNonceSource:
    __slots__ = ("_nonce",)

    def __init__(self, nonce: bytes) -> None:
        self._nonce = nonce

    def next_nonce(self) -> bytes:
        return self._nonce


class SequenceNonceSource:
    __slots__ = ("_index", "_nonces")

    def __init__(self, nonces: tuple[bytes, ...]) -> None:
        self._index = 0
        self._nonces = nonces

    def next_nonce(self) -> bytes:
        nonce = self._nonces[self._index]
        self._index += 1
        return nonce


def require_secret_api() -> ModuleType:
    try:
        return import_module("panopticon.secrets")
    except ModuleNotFoundError as error:
        if error.name == "panopticon.secrets":
            pytest.fail("SECRET_CONTRACT_MISSING:panopticon.secrets", pytrace=False)
        raise


def require_symbol(api: ModuleType, name: str) -> None:
    assert hasattr(api, name), f"SECRET_CONTRACT_MISSING:{name}"


def fixed_key(_: str) -> bytes:
    return KEY_BYTES


def other_key(_: str) -> bytes:
    return b"z" * 32


def new_store(
    api: ModuleType,
    *,
    available: bool = True,
    failure: str | None = None,
    key_factory: Callable[[str], bytes] | None = None,
) -> SecretStoreLike:
    require_symbol(api, "InMemorySecretStore")
    store_name = "InMemorySecretStore"
    store = getattr(api, store_name)(
        key_factory=key_factory or fixed_key,
        available=available,
        failure=failure,
    )
    assert isinstance(store, SecretStoreLike)
    return store


def make_backup_request(
    api: ModuleType,
    target: Path,
    plaintext: bytes = SECRET_CONFIG,
) -> BackupRequestLike:
    require_symbol(api, "BackupMetadata")
    require_symbol(api, "BackupWriteRequest")
    metadata_name = "BackupMetadata"
    metadata = getattr(api, metadata_name)(
        source="fixture",
        config_path=CONFIG_PATH,
        config_digest=CONFIG_DIGEST,
    )
    assert isinstance(metadata, MetadataLike)
    request_name = "BackupWriteRequest"
    request = getattr(api, request_name)(
        target=target,
        plaintext=plaintext,
        key_name=KEY_NAME,
        metadata=metadata,
        leak_context=LeakContext(secrets=(SECRET_TEXT,)),
    )
    assert isinstance(request, BackupRequestLike)
    return request


def make_decrypt_request(api: ModuleType, envelope: bytes) -> DecryptRequestLike:
    require_symbol(api, "BackupDecryptRequest")
    request_name = "BackupDecryptRequest"
    request = getattr(api, request_name)(envelope=envelope)
    assert isinstance(request, DecryptRequestLike)
    return request


def assert_machine_status(result: OutcomeLike, status: str, code: str) -> None:
    raw_status = result.status
    status_value = getattr(raw_status, "value", raw_status)
    assert isinstance(status_value, str)
    assert status_value == status
    assert result.code == code


def assert_no_sensitive_representation(value: str) -> None:
    assert SECRET_TEXT not in value
    assert SECRET_CONFIG.decode() not in value
    assert KEY_BYTES not in value.encode()
    assert ROTATED_KEY_BYTES not in value.encode()
    assert other_key("") not in value.encode()
    assert KEY_BYTES.hex() not in value
    assert ROTATED_KEY_BYTES.hex() not in value
    assert other_key("").hex() not in value
    assert base64.b64encode(KEY_BYTES).decode() not in value
    assert base64.b64encode(ROTATED_KEY_BYTES).decode() not in value
    assert base64.b64encode(other_key("")).decode() not in value


def assert_no_raw_key_attribute(value: OutcomeLike) -> None:
    for attribute_name in (
        "key",
        "key_bytes",
        "raw_key",
        "key_material",
        "secret",
        "secret_bytes",
        "secret_value",
        "material",
        "raw_value",
        "value",
    ):
        if not hasattr(value, attribute_name):
            continue
        attribute = getattr(value, attribute_name)
        assert not isinstance(attribute, (bytes, bytearray, memoryview, str))
        assert_no_sensitive_representation(repr(attribute))


def assert_no_temp_residue(tmp_path: Path, target: Path) -> None:
    assert not any(path.name.startswith(f".{target.name}.") for path in tmp_path.iterdir())
    assert all(SECRET_TEXT not in path.name for path in tmp_path.iterdir())
