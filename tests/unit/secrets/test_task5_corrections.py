from __future__ import annotations

import sys
from pathlib import Path
from typing import Final, TypeAlias

import pytest

from panopticon.models.common import PersistedPath
from panopticon.secrets import (
    BackendResult,
    BackupDecryptRequest,
    BackupMetadata,
    BackupWriteRequest,
    CapabilityStatus,
    KeyringAPI,
    KeyringBridge,
    LazyKeyringAPI,
    LinuxSecretServiceAdapter,
    MacOSKeychainAdapter,
    SecretStore,
    WindowsCredentialAdapter,
    decrypt_backup,
    save_encrypted_backup,
)
from panopticon.secrets.contracts import PlatformBackend
from panopticon.store import LeakContext, persist

from ._support import (
    KEY_NAME,
    NONCE,
    SECRET_CONFIG,
    SECRET_TEXT,
    FixedNonceSource,
    assert_machine_status,
    assert_no_sensitive_representation,
    require_secret_api,
)
from .test_keyring_api_injection import (
    InMemoryKeyringAPI,
    NativeKeyringErrors,
    NativeKeyringModule,
)

AdapterFactory: TypeAlias = (
    type[MacOSKeychainAdapter] | type[LinuxSecretServiceAdapter] | type[WindowsCredentialAdapter]
)
ADAPTERS: Final = (
    ("MacOSKeychainAdapter", MacOSKeychainAdapter),
    ("LinuxSecretServiceAdapter", LinuxSecretServiceAdapter),
    ("WindowsCredentialAdapter", WindowsCredentialAdapter),
)
PLATFORM_CASES: Final = (
    ("darwin", "MacOSKeychainAdapter"),
    ("linux", "LinuxSecretServiceAdapter"),
    ("win32", "WindowsCredentialAdapter"),
)


class FalseyPlatformBackend:
    def __bool__(self) -> bool:
        return False

    def probe(self) -> BackendResult:
        return BackendResult(CapabilityStatus.COMPLETE, "BACKEND_AVAILABLE")

    def get_or_create(self, name: str) -> BackendResult:
        del name
        return BackendResult(CapabilityStatus.COMPLETE, "KEY_CREATED", "fixture-key")

    def read(self, key_id: str) -> BackendResult:
        del key_id
        return BackendResult(CapabilityStatus.COMPLETE, "KEY_AVAILABLE", "fixture-key")

    def rotate(self, name: str) -> BackendResult:
        del name
        return BackendResult(CapabilityStatus.COMPLETE, "KEY_ROTATED", "fixture-key")

    def delete(self, key_id: str) -> BackendResult:
        del key_id
        return BackendResult(CapabilityStatus.COMPLETE, "KEY_DELETED")


def test_invalid_bridge_names_return_typed_failure_without_backend_mutation() -> None:
    # Given: an empty name and a credential API that records every mutation.
    api = InMemoryKeyringAPI()
    bridge = KeyringBridge("task5.invalid", api=api)

    # When: creation and rotation receive the invalid name.
    created = bridge.get_or_create("")
    rotated = bridge.rotate("")

    # Then: both failures are typed and no credential or index was changed.
    assert_machine_status(created, "FAILED", "INVALID_KEY_NAME")
    assert_machine_status(rotated, "FAILED", "INVALID_KEY_NAME")
    assert api.mutations == []
    assert api.usernames("task5.invalid") == ()
    assert_no_sensitive_representation(repr(created))
    assert_no_sensitive_representation(repr(rotated))


def test_index_failure_rolls_back_key_and_leaves_typed_unavailable_result() -> None:
    # Given: an empty index whose next index write fails after credential creation.
    api = InMemoryKeyringAPI()
    api.fail_index_writes = 1
    bridge = KeyringBridge("task5.rollback", api=api)

    # When: the bridge creates a key and cannot persist its index.
    result = bridge.get_or_create(KEY_NAME)

    # Then: the key write is rolled back, the index stays absent, and failure is typed.
    assert_machine_status(result, "UNAVAILABLE", "BACKEND_UNAVAILABLE")
    assert api.usernames("task5.rollback") == ()
    assert api.index_value("task5.rollback") is None
    assert api.operations[-1] == "delete"
    assert_no_sensitive_representation(repr(result))


def test_rollback_failure_is_typed_and_retry_cannot_multiply_orphan_keys() -> None:
    # Given: both index persistence and the first cleanup attempt fail.
    api = InMemoryKeyringAPI()
    api.fail_index_writes = 1
    api.fail_deletes = 1
    bridge = KeyringBridge("task5.rollback-retry", api=api)

    # When: creation is attempted, then retried after the cleanup fault is gone.
    first = bridge.get_or_create(KEY_NAME)
    first_ids = api.usernames("task5.rollback-retry")
    second = bridge.get_or_create(KEY_NAME)
    second_ids = api.usernames("task5.rollback-retry")

    # Then: rollback failure is explicit and retry removes the inaccessible orphan first.
    assert_machine_status(first, "FAILED", "BACKEND_ROLLBACK_FAILED")
    assert len(first_ids) == 1
    assert_machine_status(second, "COMPLETE", "KEY_CREATED")
    assert len(second_ids) == 1
    assert second_ids != first_ids
    assert_no_sensitive_representation(repr(first))
    assert_no_sensitive_representation(repr(second))


def test_memory_store_rejects_unknown_future_deleted_and_cross_store_handles() -> None:
    # Given: one created key, an unrelated store, and syntactically valid unknown IDs.
    api = require_secret_api()
    store_factory = api.InMemorySecretStore
    first_store = store_factory(key_factory=lambda _: b"a" * 32)
    other_store = store_factory(key_factory=lambda _: b"b" * 32)
    created = first_store.create_key(KEY_NAME)
    assert created.key_id is not None

    # When: handles are looked up before creation, across stores, and after deletion.
    future = first_store.get_key("memory-key-999")
    cross_store = other_store.get_key(created.key_id)
    deleted = first_store.delete_key(created.key_id)
    after_delete = first_store.get_key(created.key_id)

    # Then: only the originally created key was readable, and all others are typed misses.
    for result in (future, cross_store, after_delete):
        assert_machine_status(result, "UNAVAILABLE", "KEY_NOT_FOUND")
    assert_machine_status(deleted, "COMPLETE", "KEY_DELETED")


@pytest.mark.parametrize(("adapter_name", "adapter_type"), ADAPTERS)
def test_adapter_retains_falsey_injected_backend(
    adapter_name: str, adapter_type: AdapterFactory
) -> None:
    # Given: a valid platform backend whose truth value is false.
    del adapter_name
    backend: PlatformBackend = FalseyPlatformBackend()

    # When: the named adapter is composed with that backend.
    adapter = adapter_type(backend=backend)

    # Then: identity is retained instead of constructing a real bridge.
    assert adapter._backend is backend


@pytest.mark.parametrize(("platform_name", "matching_adapter"), PLATFORM_CASES)
def test_wrong_platform_defaults_are_unavailable_without_native_store_access(
    platform_name: str,
    matching_adapter: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a simulated host and a native keyring module that records access.
    native = NativeKeyringModule()
    errors = NativeKeyringErrors("keyring.errors")
    monkeypatch.setattr(sys, "platform", platform_name)
    monkeypatch.setitem(sys.modules, "keyring", native)
    monkeypatch.setitem(sys.modules, "keyring.errors", errors)

    # When: every named adapter probes its default composition.
    results = tuple((name, adapter_type().capability()) for name, adapter_type in ADAPTERS)

    # Then: only the matching platform can select keyring, and mismatches never import/use it.
    for name, result in results:
        if name == matching_adapter:
            assert_machine_status(result, "COMPLETE", "BACKEND_AVAILABLE")
        else:
            assert_machine_status(result, "UNAVAILABLE", "BACKEND_UNAVAILABLE")
    assert native.calls == ["get"]


def test_lazy_keyring_api_constructs_without_importing_keyring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: no keyring modules in the interpreter module table.
    monkeypatch.delitem(sys.modules, "keyring", raising=False)
    monkeypatch.delitem(sys.modules, "keyring.errors", raising=False)

    # When: the lazy API object is composed without calling an operation.
    LazyKeyringAPI()

    # Then: importing the bridge layer did not import or touch the native package.
    assert "keyring" not in sys.modules


@pytest.mark.parametrize(("adapter_name", "adapter_type"), ADAPTERS)
def test_real_bridge_lifecycle_and_backup_use_injected_api_only(
    adapter_name: str,
    adapter_type: AdapterFactory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a real KeyringBridge, a named adapter, and a test-only keyring API/module.
    native = NativeKeyringModule()
    errors = NativeKeyringErrors("keyring.errors")
    monkeypatch.setitem(sys.modules, "keyring", native)
    monkeypatch.setitem(sys.modules, "keyring.errors", errors)
    api = InMemoryKeyringAPI()
    assert isinstance(api, KeyringAPI)
    bridge = KeyringBridge(f"task5.{adapter_name}", api=api)
    adapter: SecretStore = adapter_type(backend=bridge)
    target = tmp_path / f"{adapter_name}.pano-bak"

    # When: lifecycle calls and encrypted backup roundtrip cross the real bridge and adapter.
    created = adapter.create_key(KEY_NAME)
    fetched = adapter.get_key(created.key_id or "")
    rotated = adapter.rotate_key(KEY_NAME)
    deleted = adapter.delete_key(created.key_id or "")
    saved = save_encrypted_backup(
        BackupWriteRequest(
            target=target,
            plaintext=SECRET_CONFIG,
            key_name=KEY_NAME,
            metadata=BackupMetadata(
                source="fixture",
                config_path=PersistedPath("~/.config/fixture/client.json"),
                config_digest="sha256:fixture-config",
            ),
            leak_context=LeakContext(secrets=(SECRET_TEXT,)),
        ),
        adapter,
        persist,
        nonce_source=FixedNonceSource(NONCE),
    )
    restored = decrypt_backup(BackupDecryptRequest(envelope=target.read_bytes()), adapter)

    # Then: all operations work through the injected API and never touch the native module.
    assert_machine_status(created, "COMPLETE", "KEY_CREATED")
    assert_machine_status(fetched, "COMPLETE", "KEY_AVAILABLE")
    assert_machine_status(rotated, "COMPLETE", "KEY_ROTATED")
    assert_machine_status(deleted, "COMPLETE", "KEY_DELETED")
    assert_machine_status(saved, "COMPLETE", "BACKUP_PERSISTED")
    assert_machine_status(restored, "COMPLETE", "BACKUP_DECRYPTED")
    assert api.operations
    assert native.calls == []
    assert_no_sensitive_representation(repr(saved))
    assert_no_sensitive_representation(repr(restored))
