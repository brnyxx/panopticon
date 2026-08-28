from __future__ import annotations

import pytest

from panopticon.sandbox.decoy import (
    DecoyMarker,
    DecoySensitivity,
    DecoySource,
    generate_decoy_home,
    marker_encodings,
)
from panopticon.sandbox.matcher import DecoyMatcher, MatchStatus, match_stream


def test_every_encoding_matches_across_every_chunk_split() -> None:
    marker = generate_decoy_home("seed", "run").markers[0]

    for encoded, variant in marker_encodings(marker):
        for split in range(len(encoded) + 1):
            report = match_stream((encoded[:split], encoded[split:]), (marker,))
            matching = [hit for hit in report.matches if hit.variant == variant]
            assert len(matching) == 1
            assert matching[0].start == 0
            assert matching[0].end == len(encoded)
            assert matching[0].key == marker.key
            assert report.coverage == "COMPLETE"


def test_combined_variants_have_stable_offsets_and_order() -> None:
    marker = generate_decoy_home("seed", "run").markers[0]
    variants = marker_encodings(marker)[:5]
    payload = b"\n".join(encoded for encoded, _ in variants)

    first = match_stream((payload,), (marker,))
    second = match_stream((payload[:7], payload[7:19], payload[19:]), (marker,))

    assert first == second
    assert list(first.matches) == sorted(
        first.matches,
        key=lambda hit: (hit.start, hit.end, hit.marker.key, hit.variant),
    )
    assert {hit.variant for hit in first.matches} >= {variant for _, variant in variants}


def test_overlaps_and_duplicate_markers_are_deterministic() -> None:
    marker = DecoyMarker(
        key="run:overlap",
        value=b"aaa",
        source=DecoySource.CONTENT,
        decoy=True,
        sensitivity=DecoySensitivity.SENSITIVE,
    )
    report = match_stream((b"aaaa",), (marker, marker))

    raw_hits = [hit for hit in report.matches if hit.variant == "RAW"]
    assert [(hit.start, hit.end) for hit in raw_hits] == [(0, 3), (1, 4)]


def test_input_and_match_bounds_report_incomplete_coverage() -> None:
    marker = generate_decoy_home("seed", "run").markers[0]
    encoded = marker.value

    input_limited = match_stream((encoded + b"extra",), (marker,), max_bytes=len(encoded))
    match_limited = match_stream((encoded,), (marker,), max_matches=0)

    assert input_limited.status is MatchStatus.TRUNCATED
    assert input_limited.incomplete
    assert input_limited.retained_bytes == len(encoded)
    assert input_limited.total_bytes == len(encoded) + 5
    assert input_limited.reason_code == "INPUT_LIMIT"
    assert match_limited.incomplete
    assert match_limited.matches == ()


def test_empty_and_invalid_lifecycle_inputs() -> None:
    marker = generate_decoy_home("seed", "run").markers[0]
    matcher = DecoyMatcher((marker,))

    assert matcher.finish().matches == ()
    with pytest.raises(RuntimeError):
        matcher.feed(b"late")
    with pytest.raises(ValueError):
        DecoyMatcher((marker,), max_bytes=-1)
