"""Pure planning and deterministic redacted diff rendering."""

from __future__ import annotations

import difflib
import hashlib
import re
from pathlib import Path

from panopticon.models.ids import ConfigPath
from panopticon.util.jsonc.document import SourceDocument
from panopticon.util.jsonc.parser import parse_document
from panopticon.util.jsonc.patch import JsoncPatch, patch_document

from .model import FixPlan, FixPrompt

_SECRET = re.compile(
    r"(?i)(token|secret|password|api[_-]?key)([\"']?\s*[:=]\s*[\"']?)([^,\"'\s}]+)"
)


def make_plan(
    target: Path,
    document: SourceDocument,
    patches: tuple[JsoncPatch, ...] = (),
    prompts: tuple[FixPrompt, ...] = (),
    mode: int | None = None,
) -> FixPlan:
    return FixPlan(target, document.original_bytes, tuple(patches), tuple(prompts), mode)


def plan_hash(plan: FixPlan) -> str:
    payload = repr(
        tuple((p.operation.value, str(p.pointer), p.value) for p in plan.patches)
    ).encode()
    return hashlib.sha256(plan.original + payload).hexdigest()


def apply_bytes(plan: FixPlan) -> bytes:
    document = parse_document(
        plan.original,
        path=plan.target,
        logical_path=ConfigPath(f"~/{plan.target.name}"),
    )
    return patch_document(document, plan.patches)


def _redact(text: str) -> str:
    return _SECRET.sub(lambda m: m.group(1) + m.group(2) + "<redacted>", text)


def unified_diff(plan: FixPlan, patched: bytes | None = None) -> str:
    updated = patched if patched is not None else apply_bytes(plan)
    old = _redact(plan.original.decode("utf-8", "replace")).splitlines(keepends=True)
    new = _redact(updated.decode("utf-8", "replace")).splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(old, new, fromfile=str(plan.target), tofile=str(plan.target))
    )
