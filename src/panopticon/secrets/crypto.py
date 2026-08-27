"""Versioned AES-256-GCM envelope encoding and authenticated decoding."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Final, TypeAlias

from cryptography.exceptions import InvalidTag as CryptographyInvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import JsonValue, TypeAdapter, ValidationError

from panopticon.models.common import NonEmptyStr, StrictModel
from panopticon.secrets.contracts import BackupMetadata
from panopticon.util.canonicalize import canonical_json_bytes

ENVELOPE_VERSION: Final = "0.1"
ENVELOPE_ALGORITHM: Final = "AES-GCM"
AES_KEY_BYTES: Final = 32
GCM_NONCE_BYTES: Final = 12
GCM_TAG_BYTES: Final = 16
_JSON_VALUE: Final[TypeAdapter[JsonValue]] = TypeAdapter(JsonValue)


@dataclass(frozen=True, slots=True)
class EnvelopeError(ValueError):
    """Typed parse or encoding rejection without retaining input bytes."""

    code: str

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class InvalidTagError(RuntimeError):
    """Authenticated decryption rejected the ciphertext or associated data."""

    def __str__(self) -> str:
        return "AUTHENTICATION_FAILED"


InvalidTag: TypeAlias = InvalidTagError


@dataclass(frozen=True, slots=True)
class EncryptionRequest:
    """Typed in-memory input for one envelope encryption operation."""

    plaintext: bytes
    nonce: bytes
    key_id: str
    metadata: BackupMetadata

    def __repr__(self) -> str:
        return "EncryptionRequest(<redacted>)"

    def __str__(self) -> str:
        return self.__repr__()


class EncryptedBackupEnvelope(StrictModel):
    """Closed persisted shape for an encrypted backup."""

    version: NonEmptyStr
    algorithm: NonEmptyStr
    key_id: NonEmptyStr
    nonce: NonEmptyStr
    ciphertext: NonEmptyStr
    metadata: BackupMetadata


class _BackupAad(StrictModel):
    """Canonical authenticated header; never persisted independently."""

    version: NonEmptyStr
    algorithm: NonEmptyStr
    key_id: NonEmptyStr
    nonce: NonEmptyStr
    metadata: BackupMetadata


def _aad(envelope: EncryptedBackupEnvelope) -> bytes:
    header = _BackupAad(
        version=envelope.version,
        algorithm=envelope.algorithm,
        key_id=envelope.key_id,
        nonce=envelope.nonce,
        metadata=envelope.metadata,
    )
    return canonical_json_bytes(header)


def encode_envelope(envelope: EncryptedBackupEnvelope) -> bytes:
    """Serialize an already-validated envelope through canonical JSON."""
    return canonical_json_bytes(envelope)


def parse_envelope(payload: bytes) -> EncryptedBackupEnvelope:
    """Parse one strict envelope and classify malformed versus truncated JSON."""
    if not payload.strip():
        raise EnvelopeError("MALFORMED_ENVELOPE")
    try:
        value = _JSON_VALUE.validate_json(payload)
    except ValidationError as error:
        stripped = payload.strip()
        truncated = stripped[:1] in {b"{", b"["} and stripped[-1:] not in {b"}", b"]"}
        if truncated:
            raise EnvelopeError("TRUNCATED_ENVELOPE") from error
        raise EnvelopeError("MALFORMED_ENVELOPE") from error
    try:
        envelope = EncryptedBackupEnvelope.model_validate(value)
    except ValidationError as error:
        raise EnvelopeError("MALFORMED_ENVELOPE") from error
    if envelope.version != ENVELOPE_VERSION:
        raise EnvelopeError("UNKNOWN_ENVELOPE_VERSION")
    if envelope.algorithm != ENVELOPE_ALGORITHM:
        raise EnvelopeError("UNKNOWN_ENVELOPE_ALGORITHM")
    return envelope


def _decode_field(value: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise EnvelopeError("AUTHENTICATION_FAILED") from error
    if not value or base64.b64encode(decoded).decode("ascii") != value:
        raise EnvelopeError("AUTHENTICATION_FAILED")
    return decoded


def encrypt_envelope(request: EncryptionRequest, key: bytes) -> EncryptedBackupEnvelope:
    """Encrypt exact plaintext bytes with a validated AES-256-GCM key and nonce."""
    if len(key) != AES_KEY_BYTES:
        raise EnvelopeError("INVALID_KEY")
    if len(request.nonce) != GCM_NONCE_BYTES:
        raise EnvelopeError("INVALID_NONCE")
    nonce_text = base64.b64encode(request.nonce).decode("ascii")
    header = _BackupAad(
        version=ENVELOPE_VERSION,
        algorithm=ENVELOPE_ALGORITHM,
        key_id=request.key_id,
        nonce=nonce_text,
        metadata=request.metadata,
    )
    ciphertext = AESGCM(key).encrypt(
        request.nonce,
        request.plaintext,
        canonical_json_bytes(header),
    )
    return EncryptedBackupEnvelope(
        version=ENVELOPE_VERSION,
        algorithm=ENVELOPE_ALGORITHM,
        key_id=request.key_id,
        nonce=nonce_text,
        ciphertext=base64.b64encode(ciphertext).decode("ascii"),
        metadata=request.metadata,
    )


def decrypt_envelope(envelope: EncryptedBackupEnvelope, key: bytes) -> bytes:
    """Authenticate and decrypt one parsed envelope without returning partial plaintext."""
    if len(key) != AES_KEY_BYTES:
        raise EnvelopeError("AUTHENTICATION_FAILED")
    nonce = _decode_field(envelope.nonce)
    ciphertext = _decode_field(envelope.ciphertext)
    if len(nonce) != GCM_NONCE_BYTES or len(ciphertext) < GCM_TAG_BYTES:
        raise EnvelopeError("AUTHENTICATION_FAILED")
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, _aad(envelope))
    except CryptographyInvalidTag as error:
        raise InvalidTagError from error
