from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import pytest

from panopticon.store import persist

from ._support import (
    CONFIG_DIGEST,
    CONFIG_PATH,
    KEY_BYTES,
    NONCE,
    ROTATED_KEY_BYTES,
    SECRET_CONFIG,
    SECRET_TEXT,
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


def test_secret_config_round_trips_through_secret_store(tmp_path: Path) -> None:
    # Given: a deterministic in-memory store and an exact secret-bearing config in memory.
    api = require_secret_api()
    require_symbol(api, "save_encrypted_backup")
    require_symbol(api, "decrypt_backup")
    store = new_store(api)
    target = tmp_path / "config.pano-bak"
    request = make_backup_request(api, target)
    nonce_source = FixedNonceSource(NONCE)

    # When: the backup crosses the Task4 gateway and is decrypted from its persisted envelope.
    save_name = "save_encrypted_backup"
    decrypt_name = "decrypt_backup"
    saved = getattr(api, save_name)(request, store, persist, nonce_source=nonce_source)
    assert_machine_status(saved, "COMPLETE", "BACKUP_PERSISTED")
    restored = getattr(api, decrypt_name)(make_decrypt_request(api, target.read_bytes()), store)

    # Then: only the typed in-memory result contains the exact plaintext.
    assert_machine_status(restored, "COMPLETE", "BACKUP_DECRYPTED")
    assert_no_raw_key_attribute(saved)
    assert_no_raw_key_attribute(restored)
    plaintext_name = "plaintext"
    assert getattr(restored, plaintext_name) == SECRET_CONFIG
    persisted = target.read_bytes()
    envelope = json.loads(persisted)
    assert set(envelope) >= {
        "version",
        "algorithm",
        "key_id",
        "nonce",
        "ciphertext",
        "metadata",
    }
    assert envelope["version"] == "0.1"
    assert envelope["algorithm"] == "AES-GCM"
    assert isinstance(envelope["key_id"], str)
    assert envelope["metadata"] == {
        "source": "fixture",
        "config_path": CONFIG_PATH,
        "config_digest": CONFIG_DIGEST,
    }
    assert SECRET_TEXT.encode() not in persisted
    if os.name != "nt":
        assert target.stat().st_mode & 0o777 == 0o600
    assert_no_sensitive_representation(repr(saved))
    assert_no_sensitive_representation(repr(restored))
    assert_no_sensitive_representation(persisted.decode(errors="replace"))
    assert_no_temp_residue(tmp_path, target)


def test_unavailable_store_returns_guidance_without_files(tmp_path: Path) -> None:
    # Given: a secure backend that reports unavailability before any write.
    api = require_secret_api()
    require_symbol(api, "save_encrypted_backup")
    store = new_store(api, available=False)
    target = tmp_path / "config.pano-bak"

    # When: a secret-bearing backup is requested.
    save_name = "save_encrypted_backup"
    result = getattr(api, save_name)(
        make_backup_request(api, target),
        store,
        persist,
        nonce_source=FixedNonceSource(NONCE),
    )
    # Then: the typed result is guidance-only and no secret-bearing path is created.
    assert_machine_status(result, "UNAVAILABLE", "SECURE_STORE_UNAVAILABLE")
    guidance_name = "guidance_only"
    written_paths_name = "written_paths"
    assert getattr(result, guidance_name) is True
    assert getattr(result, written_paths_name) == ()
    assert not target.exists()
    assert not any(path.suffix in {".env", ".token", ".key"} for path in tmp_path.iterdir())
    assert_no_sensitive_representation(repr(result))
    assert_no_temp_residue(tmp_path, target)


@pytest.mark.parametrize(
    ("field", "replacement", "expected_code"),
    (
        ("version", "9.9", "UNKNOWN_ENVELOPE_VERSION"),
        ("algorithm", "UNSUPPORTED-AEAD", "UNKNOWN_ENVELOPE_ALGORITHM"),
        ("nonce", "A", "AUTHENTICATION_FAILED"),
        ("ciphertext", "A", "AUTHENTICATION_FAILED"),
        ("metadata", "sha256:tampered", "AUTHENTICATION_FAILED"),
    ),
)
def test_envelope_tamper_is_rejected_without_plaintext(
    field: str, replacement: str, expected_code: str, tmp_path: Path
) -> None:
    # Given: one valid persisted envelope represented by the Task4 canonical JSON bytes.
    api = require_secret_api()
    require_symbol(api, "save_encrypted_backup")
    require_symbol(api, "decrypt_backup")
    store = new_store(api)
    target = tmp_path / "valid.pano-bak"
    save_name = "save_encrypted_backup"
    saved = getattr(api, save_name)(
        make_backup_request(api, target),
        store,
        persist,
        nonce_source=FixedNonceSource(NONCE),
    )
    assert_machine_status(saved, "COMPLETE", "BACKUP_PERSISTED")
    envelope = json.loads(target.read_bytes())

    # When: one authenticated envelope field is replaced before decryption.
    if field == "metadata":
        envelope[field]["config_digest"] = replacement
    else:
        envelope[field] = replacement
    tampered = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    decrypt_name = "decrypt_backup"
    result = getattr(api, decrypt_name)(make_decrypt_request(api, tampered), store)

    # Then: the failure is typed and never exposes the original plaintext.
    assert_machine_status(result, "FAILED", expected_code)
    plaintext_name = "plaintext"
    assert not hasattr(result, plaintext_name) or getattr(result, plaintext_name) is None
    assert_no_sensitive_representation(repr(result))
    assert_no_temp_residue(tmp_path, target)


def test_valid_base64_ciphertext_bit_flip_fails_authentication(tmp_path: Path) -> None:
    # Given: one valid encrypted envelope with a valid-base64 ciphertext.
    api = require_secret_api()
    require_symbol(api, "save_encrypted_backup")
    require_symbol(api, "decrypt_backup")
    store = new_store(api)
    target = tmp_path / "valid-bit-flip.pano-bak"
    save_name = "save_encrypted_backup"
    saved = getattr(api, save_name)(
        make_backup_request(api, target),
        store,
        persist,
        nonce_source=FixedNonceSource(NONCE),
    )
    assert_machine_status(saved, "COMPLETE", "BACKUP_PERSISTED")
    envelope = json.loads(target.read_bytes())
    ciphertext_name = "ciphertext"
    encoded_ciphertext = envelope[ciphertext_name]
    assert isinstance(encoded_ciphertext, str)
    ciphertext = base64.b64decode(encoded_ciphertext, validate=True)
    assert ciphertext

    # When: one ciphertext bit changes while its base64 encoding remains valid.
    flipped_ciphertext = bytes((ciphertext[0] ^ 1,)) + ciphertext[1:]
    envelope[ciphertext_name] = base64.b64encode(flipped_ciphertext).decode("ascii")
    tampered = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    decrypt_name = "decrypt_backup"
    result = getattr(api, decrypt_name)(make_decrypt_request(api, tampered), store)

    # Then: authenticated decryption rejects the bit flip without plaintext.
    assert base64.b64decode(envelope[ciphertext_name], validate=True) == flipped_ciphertext
    assert_machine_status(result, "FAILED", "AUTHENTICATION_FAILED")
    plaintext_name = "plaintext"
    assert not hasattr(result, plaintext_name) or getattr(result, plaintext_name) is None
    assert_no_raw_key_attribute(result)
    assert_no_sensitive_representation(repr(result))
    assert_no_temp_residue(tmp_path, target)


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    ((b"", "MALFORMED_ENVELOPE"), (b'{"version":"0.1"', "TRUNCATED_ENVELOPE")),
)
def test_malformed_or_truncated_envelope_is_typed_rejection(
    payload: bytes, expected_code: str, tmp_path: Path
) -> None:
    # Given: bytes that cannot represent a complete supported envelope.
    api = require_secret_api()
    require_symbol(api, "decrypt_backup")
    store = new_store(api)

    # When: malformed bytes cross the decrypt boundary.
    decrypt_name = "decrypt_backup"
    result = getattr(api, decrypt_name)(make_decrypt_request(api, payload), store)

    # Then: parsing fails before any plaintext result exists.
    assert_machine_status(result, "FAILED", expected_code)
    plaintext_name = "plaintext"
    assert not hasattr(result, plaintext_name) or getattr(result, plaintext_name) is None
    assert_no_sensitive_representation(repr(result))
    assert tuple(tmp_path.iterdir()) == ()


def test_rotated_key_keeps_old_backup_readable_until_old_key_delete(tmp_path: Path) -> None:
    # Given: an old encrypted backup and a deterministic key sequence for rotation.
    api = require_secret_api()
    for symbol in ("save_encrypted_backup", "decrypt_backup"):
        require_symbol(api, symbol)
    materials = iter((KEY_BYTES, ROTATED_KEY_BYTES))

    def next_key(_: str) -> bytes:
        return next(materials)

    store = new_store(api, key_factory=next_key)
    old_target = tmp_path / "old.pano-bak"
    original = store.create_key("panopticon/fixture/config-backup")
    old_key_id = original.key_id
    assert old_key_id
    save_name = "save_encrypted_backup"
    decrypt_name = "decrypt_backup"
    saved = getattr(api, save_name)(
        make_backup_request(api, old_target),
        store,
        persist,
        nonce_source=FixedNonceSource(NONCE),
    )
    assert_machine_status(saved, "COMPLETE", "BACKUP_PERSISTED")
    rotated = store.rotate_key("panopticon/fixture/config-backup")
    assert_machine_status(rotated, "COMPLETE", "KEY_ROTATED")

    # When: the old envelope is read after rotation and after explicit old-key deletion.
    before_delete = getattr(api, decrypt_name)(
        make_decrypt_request(api, old_target.read_bytes()), store
    )
    deleted = store.delete_key(old_key_id)
    after_delete = getattr(api, decrypt_name)(
        make_decrypt_request(api, old_target.read_bytes()), store
    )

    # Then: old-key retention works until deletion, which becomes a typed failure.
    assert_machine_status(before_delete, "COMPLETE", "BACKUP_DECRYPTED")
    plaintext_name = "plaintext"
    assert getattr(before_delete, plaintext_name) == SECRET_CONFIG
    assert_machine_status(deleted, "COMPLETE", "KEY_DELETED")
    assert_machine_status(after_delete, "FAILED", "KEY_NOT_FOUND")
    assert not hasattr(after_delete, plaintext_name)
    assert_no_sensitive_representation(repr(after_delete))
    assert_no_temp_residue(tmp_path, old_target)
