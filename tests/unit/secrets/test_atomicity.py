from __future__ import annotations

import importlib
from pathlib import Path

from panopticon.store import (
    AtomicOperation,
    FailureCode,
    FaultInjector,
    LeakContext,
    PersistFailure,
    PersistRequest,
    PersistResult,
    SinkKind,
    persist,
)

from ._support import (
    NONCE,
    SECRET_CONFIG,
    FixedNonceSource,
    assert_machine_status,
    assert_no_raw_key_attribute,
    assert_no_sensitive_representation,
    assert_no_temp_residue,
    make_backup_request,
    make_decrypt_request,
    new_store,
    require_secret_api,
    require_symbol,
)


def test_encryption_failure_preserves_prior_encrypted_backup(tmp_path: Path) -> None:
    # Given: the required secrets test package has been imported by pytest.
    importlib.import_module("secrets")
    # Given: a complete encrypted backup already present at the target.
    api = require_secret_api()
    require_symbol(api, "save_encrypted_backup")
    store = new_store(api)
    target = tmp_path / "prior.pano-bak"
    save_name = "save_encrypted_backup"
    first = getattr(api, save_name)(
        make_backup_request(api, target), store, persist, nonce_source=FixedNonceSource(NONCE)
    )
    assert_machine_status(first, "COMPLETE", "BACKUP_PERSISTED")
    prior = target.read_bytes()

    # When: a subsequent encryption operation fails before persistence.
    failed_store = new_store(api, failure="ENCRYPTION")
    result = getattr(api, save_name)(
        make_backup_request(api, target),
        failed_store,
        persist,
        nonce_source=FixedNonceSource(NONCE),
    )

    # Then: the prior complete bytes and restrictive target remain intact.
    assert_machine_status(result, "FAILED", "ENCRYPTION_FAILED")
    assert_no_raw_key_attribute(result)
    assert target.read_bytes() == prior
    assert target.stat().st_mode & 0o777 == 0o600
    assert_no_sensitive_representation(repr(result))
    assert_no_temp_residue(tmp_path, target)


def test_store_failure_preserves_prior_encrypted_backup(tmp_path: Path) -> None:
    # Given: a prior encrypted target and a store that fails key retrieval.
    api = require_secret_api()
    require_symbol(api, "save_encrypted_backup")
    target = tmp_path / "prior.pano-bak"
    first_store = new_store(api)
    save_name = "save_encrypted_backup"
    first = getattr(api, save_name)(
        make_backup_request(api, target),
        first_store,
        persist,
        nonce_source=FixedNonceSource(NONCE),
    )
    assert_machine_status(first, "COMPLETE", "BACKUP_PERSISTED")
    prior = target.read_bytes()
    failed_store = new_store(api, failure="STORE")

    # When: the next write reaches the failing credential-store boundary.
    result = getattr(api, save_name)(
        make_backup_request(api, target),
        failed_store,
        persist,
        nonce_source=FixedNonceSource(NONCE),
    )

    # Then: the previous envelope is preserved and no temp residue remains.
    assert_machine_status(result, "FAILED", "STORE_FAILED")
    assert_no_raw_key_attribute(result)
    assert target.read_bytes() == prior
    assert_no_sensitive_representation(repr(result))
    assert_no_temp_residue(tmp_path, target)


def test_persist_failure_preserves_prior_encrypted_backup(tmp_path: Path) -> None:
    # Given: a prior encrypted target and an injected Task4 persistence failure.
    api = require_secret_api()
    require_symbol(api, "save_encrypted_backup")
    target = tmp_path / "prior.pano-bak"
    store = new_store(api)
    save_name = "save_encrypted_backup"
    first = getattr(api, save_name)(
        make_backup_request(api, target), store, persist, nonce_source=FixedNonceSource(NONCE)
    )
    assert_machine_status(first, "COMPLETE", "BACKUP_PERSISTED")
    prior = target.read_bytes()

    def failing_writer(
        request: PersistRequest,
        context: LeakContext,
        injector: FaultInjector | None = None,
    ) -> PersistResult:
        return PersistFailure(
            request.target,
            SinkKind.BACKUP,
            FailureCode.FILESYSTEM_ERROR,
            AtomicOperation.WRITE,
            False,
        )

    # When: the replacement gateway reports failure.
    result = getattr(api, save_name)(
        make_backup_request(api, target),
        store,
        failing_writer,
        nonce_source=FixedNonceSource(NONCE),
    )

    # Then: the prior bytes remain and the failure is value-free.
    assert_machine_status(result, "FAILED", "PERSIST_FAILED")
    assert_no_raw_key_attribute(result)
    assert target.read_bytes() == prior
    assert_no_sensitive_representation(repr(result))
    assert_no_temp_residue(tmp_path, target)


def test_two_install_keys_do_not_cross_decrypt(tmp_path: Path) -> None:
    # Given: two independent stores with different deterministic key material.
    api = require_secret_api()
    require_symbol(api, "save_encrypted_backup")
    require_symbol(api, "decrypt_backup")
    store_a = new_store(api)
    store_b = new_store(api, key_factory=lambda _: b"z" * 32)
    target = tmp_path / "install-a.pano-bak"
    save_name = "save_encrypted_backup"
    saved = getattr(api, save_name)(
        make_backup_request(api, target),
        store_a,
        persist,
        nonce_source=FixedNonceSource(NONCE),
    )
    assert_machine_status(saved, "COMPLETE", "BACKUP_PERSISTED")

    # When: the second install attempts to decrypt the first install's envelope.
    decrypt_name = "decrypt_backup"
    result = getattr(api, decrypt_name)(make_decrypt_request(api, target.read_bytes()), store_b)

    # Then: cross-install decryption fails without returning any plaintext.
    assert_machine_status(result, "FAILED", "AUTHENTICATION_FAILED")
    assert_no_raw_key_attribute(result)
    plaintext_name = "plaintext"
    assert not hasattr(result, plaintext_name) or getattr(result, plaintext_name) is None
    assert SECRET_CONFIG not in repr(result).encode()
    assert_no_temp_residue(tmp_path, target)
