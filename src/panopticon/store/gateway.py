"""The sole product persistence gateway."""

from __future__ import annotations

from typing import assert_never

from panopticon.store.atomic import AtomicFailure, AtomicRejected, AtomicSuccess, atomic_replace
from panopticon.store.contracts import (
    BinaryArtifact,
    FaultInjector,
    ModelArtifact,
    PersistFailure,
    PersistRejected,
    PersistRequest,
    PersistResult,
    PersistSuccess,
    RejectionCode,
    RenderedArtifact,
    SinkKind,
)
from panopticon.store.serialization import InvalidArtifact, SerializedArtifact, serialize_artifact
from panopticon.util.leak_check import LeakContext, LeakError, assert_clean


def _kind(request: PersistRequest) -> SinkKind:
    match request.artifact:
        case ModelArtifact(kind=kind) | RenderedArtifact(kind=kind) | BinaryArtifact(kind=kind):
            return kind
        case artifact_unreachable:
            assert_never(artifact_unreachable)


def persist(
    request: PersistRequest,
    context: LeakContext,
    injector: FaultInjector | None = None,
) -> PersistResult:
    """Canonicalize, reject leaks, then atomically replace one artifact."""
    kind = _kind(request)
    serialized = serialize_artifact(request.artifact)
    match serialized:
        case InvalidArtifact(scan_texts=scan_texts):
            try:
                for scan_text in scan_texts:
                    assert_clean(scan_text, context)
            except LeakError as error:
                return PersistRejected(
                    request.target,
                    kind,
                    RejectionCode.LEAK_DETECTED,
                    error.hits,
                )
            return PersistRejected(request.target, kind, RejectionCode.INVALID_ARTIFACT)
        case SerializedArtifact(scan_texts=scan_texts, data=data):
            try:
                for scan_text in scan_texts:
                    assert_clean(scan_text, context)
            except LeakError as error:
                return PersistRejected(
                    request.target,
                    kind,
                    RejectionCode.LEAK_DETECTED,
                    error.hits,
                )
        case serialization_unreachable:
            assert_never(serialization_unreachable)
    atomic_result = atomic_replace(request.target, data, injector)
    match atomic_result:
        case AtomicSuccess(bytes_written=bytes_written, directory_sync=directory_sync):
            return PersistSuccess(request.target, kind, bytes_written, directory_sync)
        case AtomicRejected(code=code):
            return PersistRejected(request.target, kind, code)
        case AtomicFailure(code=code, operation=operation, target_replaced=target_replaced):
            return PersistFailure(request.target, kind, code, operation, target_replaced)
        case atomic_unreachable:
            assert_never(atomic_unreachable)
