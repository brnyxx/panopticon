"""Runtime loaders for the JSONC public contract under test."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType

import pytest

from panopticon.models import JsonPointer
from panopticon.store import FaultInjector

from ._fixtures import DocumentSpec, PatchSpec, WriteSpec
from ._protocols import (
    DocumentLike,
    PatchLike,
    PatchResultLike,
    TokenLike,
    WriteRequestLike,
)


def require_jsonc_api() -> ModuleType:
    """Load the JSONC public API at test time so missing production stays RED."""
    try:
        return import_module("panopticon.util.jsonc")
    except ModuleNotFoundError as error:
        if error.name == "panopticon.util.jsonc":
            pytest.fail("JSONC_CONTRACT_MISSING:panopticon.util.jsonc", pytrace=False)
        raise


def require_jsonc_module(name: str) -> ModuleType:
    """Load one required split JSONC module without collection-time failure."""
    qualified_name = f"panopticon.util.jsonc.{name}"
    try:
        return import_module(qualified_name)
    except ModuleNotFoundError as error:
        if error.name in {qualified_name, "panopticon.util.jsonc"}:
            pytest.fail(f"JSONC_CONTRACT_MISSING:{qualified_name}", pytrace=False)
        raise


def require_symbol(module: ModuleType, name: str) -> None:
    """Require one public contract symbol after the test action begins."""
    assert hasattr(module, name), f"JSONC_CONTRACT_MISSING:{name}"


def parse_document(api: ModuleType, spec: DocumentSpec) -> DocumentLike:
    """Parse one source fixture through the future typed document API."""
    parse_name = "parse_document"
    require_symbol(api, parse_name)
    document = getattr(api, parse_name)(
        spec.source,
        path=spec.path,
        logical_path=spec.logical_path,
    )
    assert isinstance(document, DocumentLike)
    return document


def make_patch(api: ModuleType, spec: PatchSpec) -> PatchLike:
    """Build one typed JSON-pointer patch through the public API."""
    operation_name = "PatchOperation"
    patch_name = "JsoncPatch"
    require_symbol(api, operation_name)
    require_symbol(api, patch_name)
    operation_type = getattr(api, operation_name)
    patch = getattr(api, patch_name)(
        operation=getattr(operation_type, spec.operation),
        pointer=JsonPointer(spec.pointer),
        value=spec.value,
    )
    assert isinstance(patch, PatchLike)
    return patch


def patch_bytes(api: ModuleType, document: DocumentLike, patches: tuple[PatchLike, ...]) -> bytes:
    """Apply pure byte-range patches without crossing the file-write boundary."""
    patch_name = "patch_document"
    require_symbol(api, patch_name)
    result = getattr(api, patch_name)(document, patches)
    assert isinstance(result, bytes)
    return result


def apply_patches(
    api: ModuleType, spec: WriteSpec, injector: FaultInjector | None = None
) -> PatchResultLike:
    """Apply a typed patch request through the filesystem transaction seam."""
    request_name = "PatchRequest"
    apply_name = "apply_patches"
    require_symbol(api, request_name)
    require_symbol(api, apply_name)
    request = getattr(api, request_name)(
        target=spec.target,
        document=spec.document,
        patches=spec.patches,
    )
    assert isinstance(request, WriteRequestLike)
    result = getattr(api, apply_name)(request, injector=injector)
    assert isinstance(result, PatchResultLike)
    return result


def tokenize_source(api: ModuleType, source: bytes) -> tuple[TokenLike, ...]:
    """Tokenize source through the dynamically loaded tokenizer contract."""
    tokenize_name = "tokenize"
    require_symbol(api, tokenize_name)
    tokens = tuple(getattr(api, tokenize_name)(source))
    assert all(isinstance(token, TokenLike) for token in tokens)
    return tokens
