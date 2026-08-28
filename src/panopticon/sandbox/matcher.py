"""Bounded Aho-Corasick matching of synthetic decoy markers."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
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
    def status(self) -> MatchStatus:
        return MatchStatus.TRUNCATED if self.truncated else MatchStatus.COMPLETE

    @property
    def reason_code(self) -> str:
        return "INPUT_LIMIT" if self.truncated else "NONE"


@dataclass(slots=True)
class _Node:
    edges: dict[int, int] = field(default_factory=dict)
    failure: int = 0
    outputs: list[int] = field(default_factory=list)


class _Automaton:
    def __init__(self, patterns: tuple[bytes, ...]) -> None:
        self.patterns = patterns
        self.nodes = [_Node()]
        for index, pattern in enumerate(patterns):
            state = 0
            for byte in pattern:
                target = self.nodes[state].edges.get(byte)
                if target is None:
                    target = self._new_node()
                    self.nodes[state].edges[byte] = target
                state = target
            self.nodes[state].outputs.append(index)
        self._failures()

    def _new_node(self) -> int:
        self.nodes.append(_Node())
        return len(self.nodes) - 1

    def _failures(self) -> None:
        pending: deque[int] = deque()
        for state in self.nodes[0].edges.values():
            pending.append(state)
        while pending:
            current = pending.popleft()
            for byte, target in self.nodes[current].edges.items():
                pending.append(target)
                failure = self.nodes[current].failure
                while failure and byte not in self.nodes[failure].edges:
                    failure = self.nodes[failure].failure
                self.nodes[target].failure = self.nodes[failure].edges.get(byte, 0)
                self.nodes[target].outputs.extend(self.nodes[self.nodes[target].failure].outputs)

    def find(self, data: bytes) -> Iterable[tuple[int, int]]:
        state = 0
        for offset, byte in enumerate(data):
            while state and byte not in self.nodes[state].edges:
                state = self.nodes[state].failure
            state = self.nodes[state].edges.get(byte, 0)
            for pattern_index in self.nodes[state].outputs:
                yield offset + 1, pattern_index


class DecoyMatcher:
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
        patterns: list[bytes] = []
        identities: list[tuple[DecoyMarker, str]] = []
        for marker in markers:
            for encoded, variant in marker_encodings(marker):
                if encoded:
                    patterns.append(encoded)
                    identities.append((marker, variant))
        self._patterns = tuple(patterns)
        self._identities = tuple(identities)
        self._automaton = _Automaton(self._patterns)
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
        for end, pattern_index in self._automaton.find(data):
            marker, variant = self._identities[pattern_index]
            start = end - len(self._patterns[pattern_index])
            key = (marker.key, variant, start)
            if key in seen:
                continue
            seen.add(key)
            found.append(DecoyMatch(marker, variant, start, end))
            if len(found) > self._max_matches:
                self._truncated = True
                break
        found.sort(key=lambda item: (item.start, item.end, item.marker.key, item.variant))
        retained = tuple(found[: self._max_matches])
        return MatchReport(retained, self._truncated, self._truncated, len(data), self._total)

    def match(self, chunks: Iterable[bytes]) -> MatchReport:
        for chunk in chunks:
            self.feed(chunk)
        return self.finish()


DecoyHit = DecoyMatch


class DecoyRegistry(DecoyMatcher):
    def match(self, chunks: Iterable[bytes] | bytes) -> MatchReport:
        return super().match((chunks,) if isinstance(chunks, bytes) else chunks)


def match_stream(
    chunks: Iterable[bytes],
    markers: Iterable[DecoyMarker] | DecoyManifest,
    *,
    max_bytes: int = 1_048_576,
    max_matches: int = 10_000,
) -> MatchReport:
    return DecoyMatcher(markers, max_bytes=max_bytes, max_matches=max_matches).match(chunks)
