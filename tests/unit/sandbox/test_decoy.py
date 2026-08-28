from __future__ import annotations

import pytest

from panopticon.sandbox.decoy import (
    DecoySensitivity,
    DecoySource,
    generate_decoy_home,
    marker_encodings,
)


def test_same_seed_and_identity_are_byte_deterministic() -> None:
    first = generate_decoy_home("seed", "installation-a")
    second = generate_decoy_home("seed", "installation-a")

    assert first == second
    assert first.bytes == second.bytes
    assert tuple(first.files) == tuple(sorted(first.files))
    assert all(marker.decoy for marker in first.markers)
    assert all(marker.sensitivity is DecoySensitivity.SENSITIVE for marker in first.markers)
    assert {marker.source for marker in first.markers} == {
        DecoySource.FILE,
        DecoySource.CONTENT,
        DecoySource.ENVIRONMENT,
    }


def test_seed_and_identity_namespace_every_marker_value() -> None:
    baseline = generate_decoy_home("seed-a", "installation-a")
    other_seed = generate_decoy_home("seed-b", "installation-a")
    other_identity = generate_decoy_home("seed-a", "installation-b")

    baseline_values = {marker.value for marker in baseline.markers}
    assert baseline_values.isdisjoint(marker.value for marker in other_seed.markers)
    assert baseline_values.isdisjoint(marker.value for marker in other_identity.markers)
    assert all(marker.key.startswith("installation-a:") for marker in baseline.markers)
    assert all(value.startswith("PANO_DECOY_") for value in baseline.env.values())


def test_wire_encodings_are_synthetic_and_distinguishable() -> None:
    marker = generate_decoy_home("seed", "run").markers[0]
    encodings = {variant: encoded for encoded, variant in marker_encodings(marker)}

    assert encodings["RAW"] == marker.value
    assert encodings["JSON_ESCAPED"] != encodings["RAW"]
    assert encodings["URL_ENCODED"] != encodings["FORM_ENCODED"]
    assert encodings["BASE64"] != encodings["RAW"]
    assert set(encodings) == {
        "RAW",
        "JSON_ESCAPED",
        "URL_ENCODED",
        "FORM_ENCODED",
        "BASE64",
        "BASE64_URLSAFE",
    }


def test_generation_bounds_and_rejects_invalid_identity() -> None:
    empty = generate_decoy_home("seed", max_bytes=0)

    assert empty.files == {}
    assert empty.bytes == b""
    assert len(empty.markers) == 1
    with pytest.raises(ValueError):
        generate_decoy_home("")
    with pytest.raises(ValueError):
        generate_decoy_home("seed", "../escape")
    with pytest.raises(ValueError):
        generate_decoy_home("seed", max_bytes=-1)
