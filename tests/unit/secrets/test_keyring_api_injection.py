from __future__ import annotations

import sys
from types import ModuleType
from typing import Final

import pytest

import panopticon.secrets.keyring_backend as keyring_backend
from panopticon.secrets import KeyringAPI, KeyringBridge
from panopticon.secrets.contracts import KeyringUnavailableError

from ._support import KEY_NAME, assert_machine_status

_INDEX_USERNAME: Final = "__panopticon_secret_index_v1__"


class InMemoryKeyringAPI:
    """Test-only credential API with observable mutation boundaries."""

    def __init__(self) -> None:
        self.entries: dict[tuple[str, str], str] = {}
        self.operations: list[str] = []
        self.mutations: list[str] = []
        self.fail_index_writes = 0
        self.fail_deletes = 0

    def get_password(self, service: str, username: str) -> str | None:
        self.operations.append("get")
        return self.entries.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.operations.append("set")
        if username == _INDEX_USERNAME and self.fail_index_writes:
            self.fail_index_writes -= 1
            raise KeyringUnavailableError
        self.entries[(service, username)] = password
        self.mutations.append(f"set:{username}")

    def delete_password(self, service: str, username: str) -> None:
        self.operations.append("delete")
        if self.fail_deletes:
            self.fail_deletes -= 1
            raise KeyringUnavailableError
        self.entries.pop((service, username), None)
        self.mutations.append(f"delete:{username}")

    def usernames(self, service: str) -> tuple[str, ...]:
        return tuple(
            sorted(
                username
                for current_service, username in self.entries
                if current_service == service and username != _INDEX_USERNAME
            )
        )

    def index_value(self, service: str) -> str | None:
        return self.entries.get((service, _INDEX_USERNAME))


class FalseyKeyringAPI(InMemoryKeyringAPI):
    def __bool__(self) -> bool:
        return False


class NativeKeyringModule(ModuleType):
    """Test-only native-module sentinel; any call represents forbidden store access."""

    def __init__(self) -> None:
        super().__init__("keyring")
        self.calls: list[str] = []

    def get_password(self, service: str, username: str) -> None:
        del service, username
        self.calls.append("get")

    def set_password(self, service: str, username: str, password: str) -> None:
        del service, username, password
        self.calls.append("set")

    def delete_password(self, service: str, username: str) -> None:
        del service, username
        self.calls.append("delete")


class NativeKeyringErrors(ModuleType):
    KeyringError: type[KeyringUnavailableError] = KeyringUnavailableError


def test_falsey_injected_keyring_api_is_retained_for_probe_and_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a valid falsey API plus sentinels for lazy and native keyring access.
    native = NativeKeyringModule()
    errors = NativeKeyringErrors("keyring.errors")
    monkeypatch.setitem(sys.modules, "keyring", native)
    monkeypatch.setitem(sys.modules, "keyring.errors", errors)
    lazy_calls: list[str] = []

    def lazy_keyring_sentinel() -> KeyringAPI:
        lazy_calls.append("construct")
        return InMemoryKeyringAPI()

    monkeypatch.setattr(keyring_backend, "LazyKeyringAPI", lazy_keyring_sentinel)
    api = FalseyKeyringAPI()
    assert isinstance(api, KeyringAPI)
    bridge = KeyringBridge("task5.falsey-api", api=api)

    # When: the bridge is probed and a complete credential lifecycle is executed.
    probed = bridge.probe()
    created = bridge.get_or_create(KEY_NAME)
    key_id = created.key_id
    assert key_id is not None
    fetched = bridge.read(key_id)
    deleted = bridge.delete(key_id)

    # Then: every call uses the injected API and neither fallback boundary is touched.
    assert bridge._api is api
    assert_machine_status(probed, "COMPLETE", "BACKEND_AVAILABLE")
    assert_machine_status(created, "COMPLETE", "KEY_CREATED")
    assert_machine_status(fetched, "COMPLETE", "KEY_AVAILABLE")
    assert_machine_status(deleted, "COMPLETE", "KEY_DELETED")
    assert api.operations == ["get", "get", "set", "set", "get", "delete", "get", "set"]
    assert lazy_calls == []
    assert native.calls == []
