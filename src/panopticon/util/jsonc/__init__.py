"""Public syntax-preserving JSONC parsing, patching, and transaction contracts."""

from .parser import JsoncParseError, JsonValue, SourceDocument, SourceSpan, parse_document
from .patch import JsoncPatch, JsoncPatchError, PatchOperation, patch_document
from .tokenizer import Token, TokenizeError, TokenKind, tokenize
from .transaction import PatchReason, PatchRequest, PatchResult, PatchStatus, apply_patches

Document = SourceDocument
Span = SourceSpan

__all__ = [
    "Document",
    "JsonValue",
    "JsoncParseError",
    "JsoncPatch",
    "JsoncPatchError",
    "PatchOperation",
    "PatchReason",
    "PatchRequest",
    "PatchResult",
    "PatchStatus",
    "SourceDocument",
    "SourceSpan",
    "Span",
    "Token",
    "TokenKind",
    "TokenizeError",
    "apply_patches",
    "parse_document",
    "patch_document",
    "tokenize",
]
