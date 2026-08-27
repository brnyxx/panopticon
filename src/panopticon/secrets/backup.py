"""Encrypted backup service using SecretStore handles and the Task 4 gateway."""

from __future__ import annotations

import os
from typing import Final, assert_never

from panopticon.secrets.contracts import (
    BackupDecrypted,
    BackupDecryptRequest,
    BackupFailure,
    BackupResult,
    BackupSaved,
    BackupUnavailable,
    BackupWriteRequest,
    CapabilityStatus,
    KeyResult,
    NonceSource,
    PersistWriter,
    SecretStore,
    SecretUseError,
)
from panopticon.secrets.crypto import (
    GCM_NONCE_BYTES,
    EncryptionRequest,
    EnvelopeError,
    InvalidTagError,
    decrypt_envelope,
    encrypt_envelope,
    parse_envelope,
)
from panopticon.store.contracts import (
    ModelArtifact,
    PersistFailure,
    PersistRejected,
    PersistRequest,
    PersistSuccess,
    SinkKind,
)

_BACKUP_UNAVAILABLE: Final = "SECURE_STORE_UNAVAILABLE"
_STORE_FAILURE: Final = "STORE_FAILED"


class SecureNonceSource:
    """Cryptographically secure default nonce source for backup composition."""

    __slots__ = ()

    def next_nonce(self) -> bytes:
        """Return one fresh 96-bit AES-GCM nonce."""
        return os.urandom(GCM_NONCE_BYTES)

    def __repr__(self) -> str:
        return "SecureNonceSource()"


_DEFAULT_NONCE_SOURCE: Final[NonceSource] = SecureNonceSource()


def _failure(code: str) -> BackupFailure:
    return BackupFailure(CapabilityStatus.FAILED, code, False, ())


def _unavailable() -> BackupUnavailable:
    return BackupUnavailable(CapabilityStatus.UNAVAILABLE, _BACKUP_UNAVAILABLE, True, ())


def _key_failure(result: KeyResult) -> BackupResult:
    match result.status:
        case CapabilityStatus.COMPLETE:
            return _failure(_STORE_FAILURE)
        case CapabilityStatus.UNAVAILABLE:
            if result.code == "BACKEND_UNAVAILABLE":
                return _unavailable()
            return _failure(result.code)
        case CapabilityStatus.FAILED:
            return _failure(result.code)
        case unreachable:
            assert_never(unreachable)


def save_encrypted_backup(
    request: BackupWriteRequest,
    store: SecretStore,
    persist_writer: PersistWriter,
    *,
    nonce_source: NonceSource = _DEFAULT_NONCE_SOURCE,
) -> BackupResult:
    """Encrypt a secret-bearing request and persist only its authenticated envelope."""
    capability = store.capability()
    match capability.status:
        case CapabilityStatus.COMPLETE:
            key_result = store.create_key(request.key_name)
            match key_result.status:
                case CapabilityStatus.COMPLETE:
                    handle = key_result.handle
                    key_id = key_result.key_id
                    if handle is None or key_id is None:
                        return _failure(_STORE_FAILURE)
                    nonce = nonce_source.next_nonce()
                    if not isinstance(nonce, bytes) or len(nonce) != GCM_NONCE_BYTES:
                        return _failure("INVALID_NONCE")
                    encryption_request = EncryptionRequest(
                        request.plaintext,
                        nonce,
                        key_id,
                        request.metadata,
                    )
                    try:
                        envelope = handle.use(lambda key: encrypt_envelope(encryption_request, key))
                    except SecretUseError as error:
                        code = error.code if error.code == "ENCRYPTION_FAILED" else _STORE_FAILURE
                        return _failure(code)
                    except EnvelopeError as error:
                        code = error.code if error.code == "INVALID_NONCE" else "ENCRYPTION_FAILED"
                        return _failure(code)
                    persisted = persist_writer(
                        PersistRequest(
                            request.target,
                            ModelArtifact(SinkKind.BACKUP, envelope),
                        ),
                        request.leak_context,
                    )
                    match persisted:
                        case PersistSuccess(bytes_written=bytes_written):
                            return BackupSaved(
                                request.target,
                                bytes_written,
                                CapabilityStatus.COMPLETE,
                                "BACKUP_PERSISTED",
                                False,
                                (request.target,),
                            )
                        case PersistRejected() | PersistFailure():
                            return _failure("PERSIST_FAILED")
                        case unreachable:
                            assert_never(unreachable)
                case CapabilityStatus.UNAVAILABLE | CapabilityStatus.FAILED:
                    return _key_failure(key_result)
                case unreachable:
                    assert_never(unreachable)
        case CapabilityStatus.UNAVAILABLE:
            return _unavailable()
        case CapabilityStatus.FAILED:
            return _failure(_STORE_FAILURE)
        case unreachable:
            assert_never(unreachable)


def _decrypt_with_key(request: BackupDecryptRequest, store: SecretStore) -> BackupResult:
    try:
        envelope = parse_envelope(request.envelope)
    except EnvelopeError as error:
        return _failure(error.code)
    key_result = store.get_key(envelope.key_id)
    match key_result.status:
        case CapabilityStatus.COMPLETE:
            if key_result.handle is None:
                return _failure(_STORE_FAILURE)
            try:
                plaintext = key_result.handle.use(lambda key: decrypt_envelope(envelope, key))
            except InvalidTagError:
                return _failure("AUTHENTICATION_FAILED")
            except EnvelopeError as error:
                return _failure(error.code)
            except SecretUseError as error:
                return _failure(error.code)
            return BackupDecrypted(
                plaintext,
                CapabilityStatus.COMPLETE,
                "BACKUP_DECRYPTED",
                False,
                (),
            )
        case CapabilityStatus.UNAVAILABLE | CapabilityStatus.FAILED:
            if key_result.code == "KEY_NOT_FOUND" and key_result.key_id is not None:
                return _failure("AUTHENTICATION_FAILED")
            return _key_failure(key_result)
        case unreachable:
            assert_never(unreachable)


def decrypt_backup(request: BackupDecryptRequest, store: SecretStore) -> BackupResult:
    """Authenticate and decrypt an envelope entirely in memory."""
    capability = store.capability()
    match capability.status:
        case CapabilityStatus.COMPLETE:
            return _decrypt_with_key(request, store)
        case CapabilityStatus.UNAVAILABLE:
            return _unavailable()
        case CapabilityStatus.FAILED:
            return _failure(_STORE_FAILURE)
        case unreachable:
            assert_never(unreachable)
