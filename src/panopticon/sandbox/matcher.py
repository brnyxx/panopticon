"""Bounded streaming matching of synthetic decoy markers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from .decoy import DecoyManifest, DecoyMarker, marker_encodings


class MatchStatus(StrEnum):
    COMPLETE = "COMPLETE"
    TRUNCATED = "TRUNCATED"


@dataclass(frozen=True, slots=True)
class DecoyMatch:
    marker: DecoyMarker
    variant: str
    start: int
    end: int

    @property
    def key(self) -> str:
        return self.marker.key


@dataclass(frozen=True, slots=True)
class MatchReport:
    matches: tuple[DecoyMatch, ...]
    truncated: bool
    incomplete: bool
    retained_bytes: int
    total_bytes: int

    @property
    def coverage(self) -> str:
        return "INCOMPLETE" if self.incomplete else "COMPLETE"

    @property
    def status(self) -> str:
        return MatchStatus.TRUNCATED if self.truncated else MatchStatus.COMPLETE

    @property
    def reason_code(self) -> str:
        return "INPUT_LIMIT" if self.truncated else "NONE"


class DecoyMatcher:
    """Collect chunks up to a hard bound and search all marker encodings.

    Matching is deferred until finish, making boundaries and overlap deterministic while
    retaining offsets in the original byte stream. No input is written to disk.
    """

    def __init__(
        self,
        markers: Iterable[DecoyMarker] | DecoyManifest,
        *,
        max_bytes: int = 1_048_576,
        max_matches: int = 10_000,
    ) -> None:
        if isinstance(markers, DecoyManifest):
            markers = markers.markers
        if max_bytes < 0 or max_matches < 0:
            raise ValueError("bounds must be non-negative")
        self._markers = tuple(markers)
        self._max_bytes = max_bytes
        self._max_matches = max_matches
        self._data = bytearray()
        self._total = 0
        self._truncated = False
        self._done = False

    def feed(self, chunk: bytes | bytearray | memoryview) -> None:
        if self._done:
            raise RuntimeError("matcher already finished")
        raw = bytes(chunk)
        self._total += len(raw)
        remaining = self._max_bytes - len(self._data)
        if remaining > 0:
            self._data.extend(raw[:remaining])
        if len(raw) > max(0, remaining):
            self._truncated = True

    update = feed

    def finish(self) -> MatchReport:
        if self._done:
            raise RuntimeError("matcher already finished")
        self._done = True
        found: list[DecoyMatch] = []
        seen: set[tuple[str, str, int]] = set()
        data = bytes(self._data)
        for marker in self._markers:
            for encoded, variant in marker_encodings(marker):
                if not encoded:
                    continue
                start = data.find(encoded)
                while start >= 0:
                    key = (marker.key, variant, start)
                    if key not in seen:
                        if len(found) >= self._max_matches:
                            self._truncated = True
                            break
                        seen.add(key)
                        found.append(DecoyMatch(marker, variant, start, start + len(encoded)))
                    start = data.find(encoded, start + 1)
                if len(found) >= self._max_matches:
                    break
            if len(found) >= self._max_matches:
                break
        found.sort(key=lambda item: (item.start, item.end, item.marker.key, item.variant))
        return MatchReport(tuple(found), self._truncated, self._truncated, len(data), self._total)

    def match(self, chunks: Iterable[bytes]) -> MatchReport:
        for chunk in chunks:
            self.feed(chunk)
        return self.finish()


DecoyHit = DecoyMatch


class DecoyRegistry(DecoyMatcher):
    """Compatibility name for the registry boundary described by the sandbox API."""

    def match(self, chunks: Iterable[bytes] | bytes) -> MatchReport:
        if isinstance(chunks, bytes):
            chunks = (chunks,)
        return super().match(chunks)


def match_stream(
    chunks: Iterable[bytes],
    markers: Iterable[DecoyMarker] | DecoyManifest,
    *,
    max_bytes: int = 1_048_576,
    max_matches: int = 10_000,
) -> MatchReport:
    return DecoyMatcher(markers, max_bytes=max_bytes, max_matches=max_matches).match(chunks)
