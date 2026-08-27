from __future__ import annotations

import pytest

from ._support import (
    KEY_NAME,
    SECRET_TEXT,
    DeterministicPlatformBackend,
    PlatformBackendLike,
    SecretStoreLike,
    assert_machine_status,
    assert_no_raw_key_attribute,
    assert_no_sensitive_representation,
    require_secret_api,
    require_symbol,
)

ADAPTERS = (
    "MacOSKeychainAdapter",
    "LinuxSecretServiceAdapter",
    "WindowsCredentialAdapter",
)


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_platform_adapter_complete_probe_uses_injected_backend(adapter_name: str) -> None:
    # Given: one platform adapter wired to a deterministic fake backend.
    api = require_secret_api()
    for symbol in ("CapabilityStatus", "PlatformBackend", adapter_name):
        require_symbol(api, symbol)
    status_type_name = "CapabilityStatus"
    status = getattr(api, status_type_name).COMPLETE
    backend = DeterministicPlatformBackend(
        status=status,
        code="BACKEND_AVAILABLE",
        detail="fixture",
    )
    adapter_factory = getattr(api, adapter_name)
    adapter = adapter_factory(backend=backend)

    # When: the adapter probes its injected boundary.
    result = adapter.probe()

    # Then: the capability is complete and exactly one fake call occurred.
    assert_machine_status(result, "COMPLETE", "BACKEND_AVAILABLE")
    assert backend.calls == 1
    assert_no_raw_key_attribute(result)
    assert_no_sensitive_representation(repr(result))
    assert_no_sensitive_representation(str(result))


@pytest.mark.parametrize("adapter_name", ADAPTERS)
@pytest.mark.parametrize(
    ("status_name", "code"),
    (("UNAVAILABLE", "BACKEND_UNAVAILABLE"), ("FAILED", "BACKEND_FAILED")),
)
def test_platform_adapter_reports_typed_unavailable_or_failed_state(
    adapter_name: str, status_name: str, code: str
) -> None:
    # Given: a fake backend returning one documented non-complete capability state.
    api = require_secret_api()
    for symbol in ("CapabilityStatus", "PlatformBackend", adapter_name):
        require_symbol(api, symbol)
    status_type_name = "CapabilityStatus"
    status = getattr(api, status_type_name)[status_name]
    raw_detail = f"{SECRET_TEXT}: backend detail must not escape"
    backend = DeterministicPlatformBackend(
        status=status,
        code=code,
        detail=raw_detail,
    )
    adapter_factory = getattr(api, adapter_name)
    adapter = adapter_factory(backend=backend)

    # When: the platform adapter probes the fake boundary.
    result = adapter.probe()

    # Then: state and code are preserved while the raw detail is sanitized.
    assert_machine_status(result, status_name, code)
    assert backend.calls == 1
    assert SECRET_TEXT not in repr(result)
    assert SECRET_TEXT not in str(result)
    assert raw_detail not in repr(result)
    assert raw_detail not in str(result)
    assert_no_raw_key_attribute(result)


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_platform_adapter_implements_typed_key_lifecycle(adapter_name: str) -> None:
    # Given: one platform adapter and its deterministic injected backend.
    api = require_secret_api()
    for symbol in ("CapabilityStatus", "PlatformBackend", "SecretStore", adapter_name):
        require_symbol(api, symbol)
    status_type_name = "CapabilityStatus"
    status = getattr(api, status_type_name).COMPLETE
    backend = DeterministicPlatformBackend(
        status=status,
        code="BACKEND_AVAILABLE",
        detail="fixture",
    )
    assert isinstance(backend, PlatformBackendLike)
    platform_protocol_name = "PlatformBackend"
    platform_protocol = getattr(api, platform_protocol_name)
    protocol_marker_name = "_is_protocol"
    assert getattr(platform_protocol, protocol_marker_name, False) is True
    adapter_factory = getattr(api, adapter_name)
    adapter = adapter_factory(backend=backend)
    assert isinstance(adapter, SecretStoreLike)

    # When: capability, get-or-create, read, rotate, and delete cross the adapter.
    capability = adapter.capability()
    created = adapter.create_key(KEY_NAME)
    fetched = adapter.get_key(created.key_id or "")
    rotated = adapter.rotate_key(KEY_NAME)
    current = adapter.get_key(rotated.key_id or "")
    deleted = adapter.delete_key(created.key_id or "")
    old_after_delete = adapter.get_key(created.key_id or "")

    # Then: every adapter routes the typed lifecycle and preserves opaque identifiers.
    assert_machine_status(capability, "COMPLETE", "BACKEND_AVAILABLE")
    assert_machine_status(created, "COMPLETE", "KEY_CREATED")
    assert_machine_status(fetched, "COMPLETE", "KEY_AVAILABLE")
    assert_machine_status(rotated, "COMPLETE", "KEY_ROTATED")
    assert_machine_status(current, "COMPLETE", "KEY_AVAILABLE")
    assert_machine_status(deleted, "COMPLETE", "KEY_DELETED")
    assert_machine_status(old_after_delete, "UNAVAILABLE", "KEY_NOT_FOUND")
    assert created.key_id
    assert fetched.key_id == created.key_id
    assert rotated.key_id
    assert rotated.key_id != created.key_id
    assert current.key_id == rotated.key_id
    for result in (capability, created, fetched, rotated, current, deleted, old_after_delete):
        assert_no_raw_key_attribute(result)
        assert_no_sensitive_representation(repr(result))
        assert_no_sensitive_representation(str(result))
    assert backend.operations == (
        "probe",
        "get_or_create",
        "read",
        "rotate",
        "read",
        "delete",
        "read",
    )


@pytest.mark.parametrize("adapter_name", ADAPTERS)
@pytest.mark.parametrize(
    ("status_name", "code"),
    (("UNAVAILABLE", "BACKEND_UNAVAILABLE"), ("FAILED", "BACKEND_FAILED")),
)
def test_platform_adapter_lifecycle_propagates_typed_backend_failure(
    adapter_name: str, status_name: str, code: str
) -> None:
    # Given: a platform adapter whose injected backend returns one typed failure state.
    api = require_secret_api()
    for symbol in ("CapabilityStatus", "PlatformBackend", "SecretStore", adapter_name):
        require_symbol(api, symbol)
    status_type_name = "CapabilityStatus"
    status = getattr(api, status_type_name)[status_name]
    raw_detail = f"{SECRET_TEXT}: backend detail must not escape"
    backend = DeterministicPlatformBackend(
        status=status,
        code=code,
        detail=raw_detail,
    )
    assert isinstance(backend, PlatformBackendLike)
    adapter_factory = getattr(api, adapter_name)
    adapter = adapter_factory(backend=backend)
    assert isinstance(adapter, SecretStoreLike)

    # When: every SecretStore lifecycle operation crosses the failing backend.
    results = (
        adapter.capability(),
        adapter.create_key(KEY_NAME),
        adapter.get_key("missing-key-id"),
        adapter.rotate_key(KEY_NAME),
        adapter.delete_key("missing-key-id"),
    )

    # Then: each typed result preserves state/code but sanitizes diagnostics.
    for result in results:
        assert_machine_status(result, status_name, code)
        assert_no_raw_key_attribute(result)
        assert_no_sensitive_representation(repr(result))
        assert_no_sensitive_representation(str(result))
        assert raw_detail not in repr(result)
        assert raw_detail not in str(result)
    assert backend.operations == ("probe", "get_or_create", "read", "rotate", "delete")
