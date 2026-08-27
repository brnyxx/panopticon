from __future__ import annotations

import inspect
from pathlib import Path

from panopticon.store import (
    AtomicOperation,
    FailureCode,
    FaultInjector,
    LeakContext,
    ModelArtifact,
    PersistFailure,
    PersistRejected,
    PersistRequest,
    RejectionCode,
    RenderField,
    RenderModel,
    SinkKind,
    persist,
)

from ._support import (
    NONCE,
    OTHER_NONCE,
    SECRET_CONFIG,
    SECRET_TEXT,
    FixedNonceSource,
    NonceSourceLike,
    SequenceNonceSource,
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


def test_encrypted_backup_observables_contain_no_plaintext_or_key_material(
    tmp_path: Path,
) -> None:
    # Given: an encrypted backup written from memory-only secret material.
    api = require_secret_api()
    require_symbol(api, "save_encrypted_backup")
    store = new_store(api)
    target = tmp_path / "metadata.pano-bak"

    # When: the typed backup result and persisted bytes are observed.
    save_name = "save_encrypted_backup"
    result = getattr(api, save_name)(
        make_backup_request(api, target),
        store,
        persist,
        nonce_source=FixedNonceSource(NONCE),
    )
    persisted = target.read_bytes()
    observable = b" ".join(
        (
            persisted,
            target.name.encode(),
            repr(result).encode(),
            str(result).encode(),
            repr(store).encode(),
        )
    )

    # Then: all target, metadata, filename, and representation bytes are value-free.
    assert_machine_status(result, "COMPLETE", "BACKUP_PERSISTED")
    assert_no_raw_key_attribute(result)
    assert SECRET_TEXT.encode() not in observable
    assert SECRET_CONFIG not in observable
    assert_no_sensitive_representation(observable.decode(errors="replace"))
    assert_no_temp_residue(tmp_path, target)


def test_backup_nonce_is_service_dependency_not_request_data(tmp_path: Path) -> None:
    # Given: a request and a deterministic source composed outside the request.
    api = require_secret_api()
    for symbol in ("BackupWriteRequest", "NonceSource", "save_encrypted_backup"):
        require_symbol(api, symbol)
    request = make_backup_request(api, tmp_path / "contract.pano-bak")
    source = FixedNonceSource(NONCE)
    assert isinstance(source, NonceSourceLike)

    # When: public request and service signatures are inspected.
    request_type_name = "BackupWriteRequest"
    request_parameters = inspect.signature(getattr(api, request_type_name)).parameters
    save_name = "save_encrypted_backup"
    save_parameters = inspect.signature(getattr(api, save_name)).parameters
    nonce_name = "nonce"
    nonce_source_name = "nonce_source"
    nonce_type_name = "NonceSource"

    # Then: callers cannot supply a nonce in request data, only through typed composition.
    assert nonce_name not in request_parameters
    assert not hasattr(request, nonce_name)
    assert nonce_source_name in save_parameters
    nonce_source_parameter = save_parameters[nonce_source_name]
    assert nonce_source_parameter.annotation is not inspect.Parameter.empty
    assert nonce_source_parameter.default is not inspect.Parameter.empty
    assert nonce_source_parameter.default is not None
    assert isinstance(nonce_source_parameter.default, NonceSourceLike)
    assert len(nonce_source_parameter.default.next_nonce()) == len(NONCE)
    protocol_marker_name = "_is_protocol"
    assert getattr(getattr(api, nonce_type_name), protocol_marker_name, False) is True


def test_fixed_nonce_source_makes_deterministic_backup_and_round_trips(tmp_path: Path) -> None:
    # Given: one store, identical requests, and separately injected fixed nonce sources.
    api = require_secret_api()
    for symbol in ("save_encrypted_backup", "decrypt_backup"):
        require_symbol(api, symbol)
    store = new_store(api)
    first_target = tmp_path / "first.pano-bak"
    second_target = tmp_path / "second.pano-bak"
    save_name = "save_encrypted_backup"
    decrypt_name = "decrypt_backup"

    # When: the same fixture is encrypted twice with the same injected nonce.
    first = getattr(api, save_name)(
        make_backup_request(api, first_target),
        store,
        persist,
        nonce_source=FixedNonceSource(NONCE),
    )
    second = getattr(api, save_name)(
        make_backup_request(api, second_target),
        store,
        persist,
        nonce_source=FixedNonceSource(NONCE),
    )
    first_bytes = first_target.read_bytes()
    second_bytes = second_target.read_bytes()
    first_restored = getattr(api, decrypt_name)(make_decrypt_request(api, first_bytes), store)
    second_restored = getattr(api, decrypt_name)(make_decrypt_request(api, second_bytes), store)

    # Then: deterministic envelope bytes and exact plaintext round-trip are preserved.
    assert_machine_status(first, "COMPLETE", "BACKUP_PERSISTED")
    assert_machine_status(second, "COMPLETE", "BACKUP_PERSISTED")
    assert first_bytes == second_bytes
    assert_machine_status(first_restored, "COMPLETE", "BACKUP_DECRYPTED")
    assert_machine_status(second_restored, "COMPLETE", "BACKUP_DECRYPTED")
    plaintext_name = "plaintext"
    assert getattr(first_restored, plaintext_name) == SECRET_CONFIG
    assert getattr(second_restored, plaintext_name) == SECRET_CONFIG
    assert_no_sensitive_representation(repr(first))
    assert_no_sensitive_representation(repr(second))
    assert_no_temp_residue(tmp_path, first_target)
    assert_no_temp_residue(tmp_path, second_target)


def test_nonce_sequence_makes_distinct_authenticated_backups_that_both_decrypt(
    tmp_path: Path,
) -> None:
    # Given: one key, one plaintext, and a deterministic two-nonce source.
    api = require_secret_api()
    for symbol in ("save_encrypted_backup", "decrypt_backup"):
        require_symbol(api, symbol)
    store = new_store(api)
    source = SequenceNonceSource((NONCE, OTHER_NONCE))
    first_target = tmp_path / "nonce-a.pano-bak"
    second_target = tmp_path / "nonce-b.pano-bak"
    save_name = "save_encrypted_backup"
    decrypt_name = "decrypt_backup"

    # When: two backups use consecutive nonces under the same key.
    first = getattr(api, save_name)(
        make_backup_request(api, first_target), store, persist, nonce_source=source
    )
    second = getattr(api, save_name)(
        make_backup_request(api, second_target), store, persist, nonce_source=source
    )
    first_bytes = first_target.read_bytes()
    second_bytes = second_target.read_bytes()
    first_restored = getattr(api, decrypt_name)(make_decrypt_request(api, first_bytes), store)
    second_restored = getattr(api, decrypt_name)(make_decrypt_request(api, second_bytes), store)

    # Then: authenticated envelopes differ and both recover the exact plaintext.
    assert_machine_status(first, "COMPLETE", "BACKUP_PERSISTED")
    assert_machine_status(second, "COMPLETE", "BACKUP_PERSISTED")
    assert first_bytes != second_bytes
    assert_machine_status(first_restored, "COMPLETE", "BACKUP_DECRYPTED")
    assert_machine_status(second_restored, "COMPLETE", "BACKUP_DECRYPTED")
    plaintext_name = "plaintext"
    assert getattr(first_restored, plaintext_name) == SECRET_CONFIG
    assert getattr(second_restored, plaintext_name) == SECRET_CONFIG
    assert_no_sensitive_representation(first_bytes.decode(errors="replace"))
    assert_no_sensitive_representation(second_bytes.decode(errors="replace"))
    assert_no_temp_residue(tmp_path, first_target)
    assert_no_temp_residue(tmp_path, second_target)


def test_invalid_nonce_source_returns_typed_rejection_without_files(tmp_path: Path) -> None:
    # Given: a nonce source that violates the AES-GCM nonce length contract.
    api = require_secret_api()
    require_symbol(api, "save_encrypted_backup")
    store = new_store(api)
    target = tmp_path / "invalid-nonce.pano-bak"

    # When: encryption requests the invalid nonce.
    save_name = "save_encrypted_backup"
    result = getattr(api, save_name)(
        make_backup_request(api, target),
        store,
        persist,
        nonce_source=FixedNonceSource(b"x" * 11),
    )

    # Then: typed rejection occurs before target or temporary-file creation.
    assert_machine_status(result, "FAILED", "INVALID_NONCE")
    assert_no_sensitive_representation(repr(result))
    assert not target.exists()
    assert_no_temp_residue(tmp_path, target)


def test_plaintext_backup_path_is_rejected_by_task4_gateway(tmp_path: Path) -> None:
    # Given: a secret-bearing typed model sent to the backup sink without encryption.
    target = tmp_path / "plaintext.pano-bak"
    model = RenderModel(
        schema_version="0.1",
        title="backup",
        fields=(RenderField(name="secret", value=SECRET_TEXT),),
    )

    # When: the existing single persistence gateway scans the attempted plaintext path.
    result = persist(
        PersistRequest(target, ModelArtifact(SinkKind.BACKUP, model)),
        LeakContext(secrets=(SECRET_TEXT,)),
    )

    # Then: the gateway rejects before creating a target or temporary file.
    assert isinstance(result, PersistRejected)
    assert result.code is RejectionCode.LEAK_DETECTED
    assert not target.exists()
    assert_no_temp_residue(tmp_path, target)


def test_failure_diagnostics_are_value_free(tmp_path: Path) -> None:
    # Given: a valid request and a writer that returns a typed Task4 failure.
    api = require_secret_api()
    require_symbol(api, "save_encrypted_backup")
    store = new_store(api)
    target = tmp_path / "failed.pano-bak"

    def failing_writer(
        request: PersistRequest,
        context: LeakContext,
        injector: FaultInjector | None = None,
    ) -> PersistFailure:
        return PersistFailure(
            request.target,
            SinkKind.BACKUP,
            FailureCode.FILESYSTEM_ERROR,
            AtomicOperation.WRITE,
            False,
        )

    # When: persistence fails after encryption but before replacement.
    save_name = "save_encrypted_backup"
    result = getattr(api, save_name)(
        make_backup_request(api, target),
        store,
        failing_writer,
        nonce_source=FixedNonceSource(NONCE),
    )

    # Then: the typed diagnostic and exception surfaces contain no plaintext value.
    assert_machine_status(result, "FAILED", "PERSIST_FAILED")
    assert_no_raw_key_attribute(result)
    assert SECRET_TEXT not in repr(result)
    assert SECRET_TEXT not in str(result)
    assert SECRET_CONFIG not in repr(result).encode()
    assert not target.exists()
    assert_no_temp_residue(tmp_path, target)
