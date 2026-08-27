from __future__ import annotations

import base64
import json
import shlex
from urllib.parse import quote, quote_plus

import pytest

from panopticon.util.leak_check import (
    LeakContext,
    LeakError,
    LeakReason,
    assert_clean,
    find_leaks,
    find_leaks_chunks,
)

SECRET = "REAL/SECRET+VALUE=="
HOME = "/home/alice"
CURRENT_PROJECT_TOKEN = "sk-proj-abcdefghijklmnopqrstuvwxyz1234"
CURRENT_PROJECT_TOKEN_URL = "".join(
    f"%{byte:02X}" for byte in CURRENT_PROJECT_TOKEN.encode("ascii")
)
CURRENT_PROJECT_TOKEN_BASE64 = base64.b64encode(CURRENT_PROJECT_TOKEN.encode()).decode()
CURRENT_PROJECT_TOKEN_BASE64_URLSAFE = base64.urlsafe_b64encode(
    CURRENT_PROJECT_TOKEN.encode()
).decode()
NATIVE_WINDOWS_PATH = r"Z:\Users\alice\key"
NATIVE_WINDOWS_PATH_BASE64 = base64.b64encode(NATIVE_WINDOWS_PATH.encode()).decode()
NATIVE_WINDOWS_PATH_BASE64_URLSAFE = base64.urlsafe_b64encode(NATIVE_WINDOWS_PATH.encode()).decode()
VARIANTS = (
    SECRET,
    json.dumps(SECRET)[1:-1],
    shlex.quote(SECRET),
    quote(SECRET, safe=""),
    quote_plus(SECRET, safe=""),
    base64.b64encode(SECRET.encode()).decode(),
    base64.b64encode(SECRET.encode()).decode().rstrip("="),
    base64.urlsafe_b64encode(SECRET.encode()).decode(),
    base64.urlsafe_b64encode(SECRET.encode()).decode().rstrip("="),
    HOME,
    "/Users/alice",
    "C:/Users/alice",
    r"C:\Users\alice",
    r"\\server\share\Users\alice\secret",
    "/mnt/d/users/ALICE/secret",
    r"d:\users\ALICE\secret",
    r"\\wsl.localhost\Debian\home\alice\secret",
    quote(HOME, safe=""),
    quote_plus(HOME, safe=""),
    base64.b64encode(HOME.encode()).decode(),
    base64.urlsafe_b64encode(HOME.encode()).decode().rstrip("="),
)


@pytest.mark.parametrize("variant", VARIANTS)
def test_direct_encoded_and_native_variants_are_rejected(variant: str) -> None:
    # Given: a known value represented in one supported direct, encoded, or native form.
    context = LeakContext(home_paths=(HOME,), secrets=(SECRET,))

    # When / Then: matching rejects without exposing the value in diagnostics.
    with pytest.raises(LeakError) as captured:
        assert_clean(f"prefix:{variant}:suffix", context=context)
    assert SECRET not in str(captured.value)
    assert "alice" not in str(captured.value)


@pytest.mark.parametrize(
    "variant",
    (
        "REAL%2fSECRET%2bVALUE%3d%3d",
        "REAL%2FSECRET%2bVALUE%3D%3d",
    ),
)
def test_lowercase_and_mixed_percent_escapes_are_rejected(variant: str) -> None:
    # Given: a registered value encoded with non-canonical percent-escape casing.
    context = LeakContext(secrets=(SECRET,))

    # When / Then: case-equivalent URL encodings remain value-free rejection.
    with pytest.raises(LeakError) as captured:
        assert_clean(variant, context)
    assert SECRET not in str(captured.value)


@pytest.mark.parametrize(
    "variant",
    (
        r"\\server\share\Users\alice\secret",
        r"\\wsl.localhost\Debian\home\alice\secret",
    ),
)
def test_nested_rendered_native_paths_are_rejected(variant: str) -> None:
    # Given: a native home transformed by a JSON render layer.
    rendered = json.dumps({"path": variant})

    # When / Then: each intermediate escape depth remains detectable.
    assert find_leaks(rendered, LeakContext(home_paths=(HOME,)))


def test_modern_project_credential_signature_is_rejected_value_free() -> None:
    # Given: a current project-scoped credential shape not registered in context.
    credential = "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890"

    # When: built-in credential signatures scan it.
    hits = find_leaks(credential)

    # Then: it is classified without retaining the credential value.
    assert hits
    assert credential not in str(LeakError(hits))


@pytest.mark.parametrize(
    "clean",
    (
        r"\\server\share\Users\alicia\secret",
        r"\\wsl.localhost\Debian\home\alicia\secret",
        "sk-project-documentation",
        "REAL%20PUBLIC%20VALUE",
    ),
)
def test_native_and_encoded_clean_controls_do_not_overmatch(clean: str) -> None:
    # Given: similar but unregistered path and text controls.
    context = LeakContext(home_paths=(HOME,), secrets=(SECRET,))

    # When / Then: matching stays scoped to registered values and credential signatures.
    assert find_leaks(clean, context) == ()


@pytest.mark.parametrize("boundary", range(1, len(SECRET)))
def test_secret_is_detected_at_every_chunk_boundary(boundary: int) -> None:
    # Given: a representative secret split at one possible streaming boundary.
    chunks = (SECRET[:boundary], SECRET[boundary:])

    # When: the incremental boundary is scanned as one logical artifact.
    hits = find_leaks_chunks(chunks, context=LeakContext(secrets=(SECRET,)))

    # Then: no split evades the matcher.
    assert hits


@pytest.mark.parametrize("boundary", range(1, len(HOME)))
def test_home_is_detected_at_every_chunk_boundary(boundary: int) -> None:
    # Given: a representative home path split at one possible streaming boundary.
    chunks = (HOME[:boundary], HOME[boundary:])

    # When: the incremental boundary is scanned as one logical artifact.
    hits = find_leaks_chunks(chunks, context=LeakContext(home_paths=(HOME,)))

    # Then: no split evades the matcher.
    assert hits


@pytest.mark.parametrize(
    "variant",
    (
        CURRENT_PROJECT_TOKEN_URL,
        CURRENT_PROJECT_TOKEN_BASE64,
        CURRENT_PROJECT_TOKEN_BASE64.rstrip("="),
        CURRENT_PROJECT_TOKEN_BASE64_URLSAFE,
        CURRENT_PROJECT_TOKEN_BASE64_URLSAFE.rstrip("="),
    ),
    ids=(
        "percent-encoded",
        "base64-padded",
        "base64-unpadded",
        "urlsafe-padded",
        "urlsafe-unpadded",
    ),
)
def test_current_project_token_is_rejected_in_encoded_views(variant: str) -> None:
    # Given: a current project-scoped credential represented in one encoded view.
    hits = find_leaks(variant)

    # Then: the credential class is rejected without retaining the token value.
    assert hits
    assert any(hit.reason is LeakReason.CREDENTIAL_PATTERN for hit in hits)
    assert CURRENT_PROJECT_TOKEN not in str(LeakError(hits))


@pytest.mark.parametrize(
    "variant",
    (
        NATIVE_WINDOWS_PATH_BASE64,
        NATIVE_WINDOWS_PATH_BASE64.rstrip("="),
        NATIVE_WINDOWS_PATH_BASE64_URLSAFE,
        NATIVE_WINDOWS_PATH_BASE64_URLSAFE.rstrip("="),
    ),
    ids=("base64-padded", "base64-unpadded", "urlsafe-padded", "urlsafe-unpadded"),
)
def test_base64_native_windows_home_is_rejected_for_registered_posix_home(variant: str) -> None:
    # Given: an arbitrary native Windows home path encoded for a registered POSIX home.
    hits = find_leaks(variant, LeakContext(home_paths=(HOME,)))

    # Then: the native path is rejected without exposing the username in diagnostics.
    assert hits
    assert any(hit.reason is LeakReason.REAL_HOME for hit in hits)
    assert "alice" not in str(LeakError(hits))


def test_embedded_base64_project_token_is_rejected_after_assignment_delimiter() -> None:
    # Given: a base64 credential embedded after a normal key/value delimiter.
    payload = f"credential={CURRENT_PROJECT_TOKEN_BASE64}"

    # Then: the embedded credential is rejected without retaining the token value.
    hits = find_leaks(payload)
    assert hits
    assert any(hit.reason is LeakReason.CREDENTIAL_PATTERN for hit in hits)
    assert CURRENT_PROJECT_TOKEN not in str(LeakError(hits))


@pytest.mark.parametrize(
    "payload",
    (
        "sk-proj-abcdefghijklmnopqrs",
        base64.b64encode(b"sk-proj-abcdefghijklmnopqrs").decode(),
        base64.b64encode(CURRENT_PROJECT_TOKEN[:27].encode()).decode(),
        base64.b64encode(b"sk-proj-").decode(),
        base64.b64encode(rb"Z:\Users\alicia\key").decode(),
        f"{CURRENT_PROJECT_TOKEN_BASE64[:24]}!{CURRENT_PROJECT_TOKEN_BASE64[25:]}",
    ),
    ids=(
        "short-direct",
        "short-base64",
        "bounded-base64",
        "prefix-base64",
        "near-home",
        "invalid-base64",
    ),
)
def test_clean_near_matches_and_invalid_base64_are_not_overmatched(payload: str) -> None:
    # Given: a short credential, a bounded encoding, a near-home path, or invalid base64.
    context = LeakContext(home_paths=(HOME,))

    # Then: no supported leak class is reported for the control value.
    assert find_leaks(payload, context) == ()
