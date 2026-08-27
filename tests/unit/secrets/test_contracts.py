from __future__ import annotations

from ._support import (
    KEY_NAME,
    SECRET_CONFIG,
    SECRET_TEXT,
    assert_machine_status,
    assert_no_raw_key_attribute,
    assert_no_sensitive_representation,
    new_store,
    require_secret_api,
    require_symbol,
)


def test_secret_store_protocol_and_fake_keep_key_material_out_of_results() -> None:
    # Given: the typed protocol and its deterministic in-memory implementation.
    api = require_secret_api()
    require_symbol(api, "SecretStore")
    require_symbol(api, "InMemorySecretStore")
    protocol_name = "SecretStore"
    protocol = getattr(api, protocol_name)
    store = new_store(api)

    # When: capability, create, and get operations run through the fake.
    capability = store.capability()
    created = store.create_key(KEY_NAME)
    fetched = store.get_key(created.key_id or "")

    # Then: each result is typed, stable, and value-free.
    protocol_marker_name = "_is_protocol"
    assert getattr(protocol, protocol_marker_name, False) is True
    assert_machine_status(capability, "COMPLETE", "BACKEND_AVAILABLE")
    assert_machine_status(created, "COMPLETE", "KEY_CREATED")
    assert_machine_status(fetched, "COMPLETE", "KEY_AVAILABLE")
    assert_no_raw_key_attribute(capability)
    assert_no_raw_key_attribute(created)
    assert_no_raw_key_attribute(fetched)
    assert created.key_id
    assert fetched.key_id == created.key_id
    for value in (store, capability, created, fetched):
        assert not isinstance(value, dict)
        assert_no_sensitive_representation(repr(value))
        assert_no_sensitive_representation(str(value))


def test_secret_store_unavailable_capability_is_typed() -> None:
    # Given: a deterministic store whose secure backend is unavailable.
    api = require_secret_api()
    store = new_store(api, available=False)

    # When: the capability boundary is queried.
    result = store.capability()

    # Then: the result is unavailable without exposing values.
    assert_machine_status(result, "UNAVAILABLE", "BACKEND_UNAVAILABLE")
    assert_no_raw_key_attribute(result)
    assert_no_sensitive_representation(repr(result))
    assert_no_sensitive_representation(str(result))


def test_key_rotation_preserves_old_key_until_explicit_delete() -> None:
    # Given: one store with a stable key name and an existing key identifier.
    api = require_secret_api()
    store = new_store(api)
    original = store.create_key(KEY_NAME)
    original_id = original.key_id
    assert original_id

    # When: the key is rotated, then the old identifier is deleted explicitly.
    rotated = store.rotate_key(KEY_NAME)
    old_after_rotation = store.get_key(original_id)
    deleted = store.delete_key(original_id)
    after_delete = store.get_key(original_id)

    # Then: rotation yields a new identifier and deletion has a typed result.
    assert_machine_status(rotated, "COMPLETE", "KEY_ROTATED")
    assert rotated.key_id
    assert rotated.key_id != original_id
    assert_machine_status(deleted, "COMPLETE", "KEY_DELETED")
    assert_machine_status(old_after_rotation, "COMPLETE", "KEY_AVAILABLE")
    assert_machine_status(after_delete, "UNAVAILABLE", "KEY_NOT_FOUND")
    for result in (rotated, old_after_rotation, deleted, after_delete):
        assert_no_raw_key_attribute(result)
        assert_no_sensitive_representation(repr(result))
        assert_no_sensitive_representation(str(result))


def test_secret_store_results_do_not_use_raw_mapping_or_secret_diagnostics() -> None:
    # Given: a store result and values that must remain memory-only.
    api = require_secret_api()
    store = new_store(api)
    result = store.create_key(KEY_NAME)

    # When: diagnostics and representations are materialized.
    rendered = " ".join((repr(store), repr(result), str(result)))

    # Then: no raw mapping or secret-bearing value crosses the diagnostic surface.
    assert not isinstance(result, dict)
    assert SECRET_TEXT not in rendered
    assert SECRET_CONFIG not in rendered.encode()
    assert_no_sensitive_representation(rendered)
