"""Compatibility barrel for focused JSONC test support modules."""

from panopticon.store import AtomicOperation

from ._assertions import (
    as_object,
    assert_exact_spans,
    assert_no_temp_residue,
    machine_value,
    span_for,
)
from ._fixtures import (
    JSONC_SOURCE,
    LOGICAL_PATH,
    DocumentSpec,
    EditInterval,
    PatchSpec,
    WriteSpec,
    write_source,
)
from ._injectors import (
    CleanupFailureInjector,
    ConcurrentReplacementInjector,
    FailingInjector,
    PermissionInjector,
    ReplacementInjector,
)
from ._loaders import (
    apply_patches,
    make_patch,
    parse_document,
    patch_bytes,
    require_jsonc_api,
    require_jsonc_module,
    require_symbol,
    tokenize_source,
)
from ._protocols import (
    DocumentLike,
    JsonValue,
    ParseErrorLike,
    PatchErrorLike,
    PatchLike,
    PatchResultLike,
    SpanLike,
    TokenLike,
    WriteRequestLike,
)

__all__ = [
    "JSONC_SOURCE",
    "LOGICAL_PATH",
    "AtomicOperation",
    "CleanupFailureInjector",
    "ConcurrentReplacementInjector",
    "DocumentLike",
    "DocumentSpec",
    "EditInterval",
    "FailingInjector",
    "JsonValue",
    "ParseErrorLike",
    "PatchErrorLike",
    "PatchLike",
    "PatchResultLike",
    "PatchSpec",
    "PermissionInjector",
    "ReplacementInjector",
    "SpanLike",
    "TokenLike",
    "WriteRequestLike",
    "WriteSpec",
    "apply_patches",
    "as_object",
    "assert_exact_spans",
    "assert_no_temp_residue",
    "machine_value",
    "make_patch",
    "parse_document",
    "patch_bytes",
    "require_jsonc_api",
    "require_jsonc_module",
    "require_symbol",
    "span_for",
    "tokenize_source",
    "write_source",
]
