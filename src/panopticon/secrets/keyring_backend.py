"""Lazy, injectable bridge to OS credential stores through keyring."""

from __future__ import annotations

import base64
import binascii
import os
from typing import Final, Literal

from pydantic import ValidationError

from panopticon.models.common import NonEmptyStr, StrictModel
from panopticon.secrets.contracts import (
    BackendResult,
    CapabilityStatus,
    KeyringAPI,
    KeyringDataError,
    KeyringUnavailableError,
    SecretUseError,
)

_INDEX_USERNAME: Final = "__panopticon_secret_index_v1__"
_KEY_ID_PREFIX: Final = "credential-key-"


class LazyKeyringAPI:
    """Import and invoke keyring only when a credential operation is requested."""

    def get_password(self, service: str, username: str) -> str | None:
        """Read one credential value from the selected OS backend."""
        try:
            import keyring
            from keyring.errors import KeyringError
        except ImportError as error:
            raise KeyringUnavailableError from error
        try:
            return keyring.get_password(service, username)
        except KeyringError as error:
            raise KeyringUnavailableError from error

    def set_password(self, service: str, username: str, password: str) -> None:
        """Write one credential value to the selected OS backend."""
        try:
            import keyring
            from keyring.errors import KeyringError
        except ImportError as error:
            raise KeyringUnavailableError from error
        try:
            keyring.set_password(service, username, password)
        except KeyringError as error:
            raise KeyringUnavailableError from error

    def delete_password(self, service: str, username: str) -> None:
        """Delete one credential value from the selected OS backend."""
        try:
            import keyring
            from keyring.errors import KeyringError
        except ImportError as error:
            raise KeyringUnavailableError from error
        try:
            keyring.delete_password(service, username)
        except KeyringError as error:
            raise KeyringUnavailableError from error


class _IndexEntry(StrictModel):
    name: NonEmptyStr
    key_id: NonEmptyStr


class _KeyIndex(StrictModel):
    version: Literal["1"]
    entries: tuple[_IndexEntry, ...]


class KeyringBridge:
    """Platform-neutral keyring bridge retaining only opaque identifiers in its index."""

    __slots__ = ("_api", "_pending_cleanup_key_id", "_service")

    def __init__(self, service: str, api: KeyringAPI | None = None) -> None:
        self._service = service
        self._api = api if api is not None else LazyKeyringAPI()
        self._pending_cleanup_key_id: str | None = None

    def __repr__(self) -> str:
        return "KeyringBridge(<redacted>)"

    def __str__(self) -> str:
        return self.__repr__()

    def _empty_index(self) -> _KeyIndex:
        return _KeyIndex(version="1", entries=())

    def _load_index(self) -> _KeyIndex:
        value = self._api.get_password(self._service, _INDEX_USERNAME)
        if value is None:
            return self._empty_index()
        try:
            return _KeyIndex.model_validate_json(value)
        except ValidationError as error:
            raise KeyringDataError from error

    def _save_index(self, index: _KeyIndex) -> None:
        self._api.set_password(
            self._service,
            _INDEX_USERNAME,
            index.model_dump_json(exclude_none=False),
        )

    @staticmethod
    def _entry(index: _KeyIndex, name: str) -> _IndexEntry | None:
        for entry in index.entries:
            if entry.name == name:
                return entry
        return None

    @staticmethod
    def _with_entry(index: _KeyIndex, name: str, key_id: str) -> _KeyIndex:
        return _KeyIndex(
            version="1",
            entries=(
                *tuple(entry for entry in index.entries if entry.name != name),
                _IndexEntry(name=name, key_id=key_id),
            ),
        )

    @staticmethod
    def _without_key(index: _KeyIndex, key_id: str) -> _KeyIndex:
        return _KeyIndex(
            version="1",
            entries=tuple(entry for entry in index.entries if entry.key_id != key_id),
        )

    def _new_key(self, index: _KeyIndex, name: str, result_code: str) -> BackendResult:
        try:
            _IndexEntry(name=name, key_id=_KEY_ID_PREFIX)
        except ValidationError:
            return BackendResult(CapabilityStatus.FAILED, "INVALID_KEY_NAME")

        pending_key_id = self._pending_cleanup_key_id
        if pending_key_id is not None:
            try:
                self._api.delete_password(self._service, pending_key_id)
            except KeyringUnavailableError:
                return BackendResult(CapabilityStatus.FAILED, "BACKEND_ROLLBACK_FAILED")
            self._pending_cleanup_key_id = None

        key_id = f"{_KEY_ID_PREFIX}{os.urandom(16).hex()}"
        material = os.urandom(32)
        encoded = base64.b64encode(material).decode("ascii")
        self._api.set_password(self._service, key_id, encoded)
        try:
            self._save_index(self._with_entry(index, name, key_id))
        except KeyringUnavailableError:
            try:
                self._api.delete_password(self._service, key_id)
            except KeyringUnavailableError:
                self._pending_cleanup_key_id = key_id
                return BackendResult(CapabilityStatus.FAILED, "BACKEND_ROLLBACK_FAILED")
            return BackendResult(CapabilityStatus.UNAVAILABLE, "BACKEND_UNAVAILABLE")
        return BackendResult(CapabilityStatus.COMPLETE, result_code, key_id)

    def probe(self) -> BackendResult:
        """Probe keyring availability without creating or changing credentials."""
        try:
            self._api.get_password(self._service, _INDEX_USERNAME)
        except KeyringUnavailableError:
            return BackendResult(CapabilityStatus.UNAVAILABLE, "BACKEND_UNAVAILABLE")
        return BackendResult(CapabilityStatus.COMPLETE, "BACKEND_AVAILABLE")

    def get_or_create(self, name: str) -> BackendResult:
        """Return the current named key, creating an opaque credential when absent."""
        try:
            index = self._load_index()
            entry = self._entry(index, name)
            if entry is not None:
                try:
                    self.read_material(entry.key_id)
                except SecretUseError as error:
                    if error.code != "KEY_NOT_FOUND":
                        return BackendResult(CapabilityStatus.FAILED, "BACKEND_FAILED")
                else:
                    return BackendResult(CapabilityStatus.COMPLETE, "KEY_AVAILABLE", entry.key_id)
            return self._new_key(index, name, "KEY_CREATED")
        except KeyringUnavailableError:
            return BackendResult(CapabilityStatus.UNAVAILABLE, "BACKEND_UNAVAILABLE")
        except KeyringDataError:
            return BackendResult(CapabilityStatus.FAILED, "BACKEND_FAILED")

    def read(self, key_id: str) -> BackendResult:
        """Check one opaque credential identifier without returning its material."""
        try:
            self.read_material(key_id)
        except SecretUseError as error:
            status = (
                CapabilityStatus.UNAVAILABLE
                if error.code == "KEY_NOT_FOUND"
                else CapabilityStatus.FAILED
            )
            missing_key_id = key_id if error.code == "KEY_NOT_FOUND" else None
            return BackendResult(status, error.code, missing_key_id)
        except KeyringUnavailableError:
            return BackendResult(CapabilityStatus.UNAVAILABLE, "BACKEND_UNAVAILABLE")
        return BackendResult(CapabilityStatus.COMPLETE, "KEY_AVAILABLE", key_id)

    def rotate(self, name: str) -> BackendResult:
        """Create a new current credential while retaining old credentials."""
        try:
            index = self._load_index()
            return self._new_key(index, name, "KEY_ROTATED")
        except KeyringUnavailableError:
            return BackendResult(CapabilityStatus.UNAVAILABLE, "BACKEND_UNAVAILABLE")
        except KeyringDataError:
            return BackendResult(CapabilityStatus.FAILED, "BACKEND_FAILED")

    def delete(self, key_id: str) -> BackendResult:
        """Delete one credential and remove only its index entry."""
        try:
            self._api.delete_password(self._service, key_id)
            index = self._load_index()
            self._save_index(self._without_key(index, key_id))
        except KeyringUnavailableError:
            return BackendResult(CapabilityStatus.UNAVAILABLE, "BACKEND_UNAVAILABLE")
        except KeyringDataError:
            return BackendResult(CapabilityStatus.FAILED, "BACKEND_FAILED")
        return BackendResult(CapabilityStatus.COMPLETE, "KEY_DELETED")

    def read_material(self, key_id: str) -> bytes:
        """Load one key only for a surrounding opaque-handle callback."""
        value = self._api.get_password(self._service, key_id)
        if value is None:
            raise SecretUseError("KEY_NOT_FOUND")
        try:
            material = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as error:
            raise SecretUseError("BACKEND_FAILED") from error
        if not value or base64.b64encode(material).decode("ascii") != value or len(material) != 32:
            raise SecretUseError("BACKEND_FAILED")
        return material
