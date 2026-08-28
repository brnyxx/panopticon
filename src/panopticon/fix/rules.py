"""Pure metadata and exact-pointer patches for configuration remediations."""

from __future__ import annotations

import re
from dataclasses import dataclass

from panopticon.models.ids import JsonPointer
from panopticon.util.jsonc.document import JsonValue
from panopticon.util.jsonc.patch import JsoncPatch, PatchOperation


@dataclass(frozen=True, slots=True)
class FixRule:
    fix_id: str
    findings: tuple[str, ...]
    requires_choice: bool = False


RULES: tuple[FixRule, ...] = (
    FixRule("FIX-001", ("CFG-001", "CFG-007", "CFG-011")),
    FixRule("FIX-002", ("CFG-002",), True),
    FixRule("FIX-004", ("CFG-004",), True),
    FixRule("FIX-005", ("CFG-005",), True),
    FixRule("FIX-008", ("CFG-008",)),
    FixRule("FIX-010", ("CFG-009",), True),
)
RULE_BY_ID = {item.fix_id: item for item in RULES}
_EXACT_VERSION = re.compile(r"^(?:v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?|[0-9a-f]{7,64})$")
_ENV_KEY = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")


def replace_value(pointer: str, value: JsonValue) -> JsoncPatch:
    return JsoncPatch(PatchOperation.REPLACE, JsonPointer(pointer), value)


def remove_value(pointer: str) -> JsoncPatch:
    return JsoncPatch(PatchOperation.REMOVE, JsonPointer(pointer))


def secret_reference(pointer: str, key: str) -> JsoncPatch:
    """Replace only the selected secret value with a non-secret reference."""
    if _ENV_KEY.fullmatch(key) is None:
        raise ValueError("INVALID_ENV_KEY")
    return replace_value(pointer, f"${{{key}}}")


def pin_version(pointer: str, version: str) -> JsoncPatch:
    suffix = version.rsplit("@", 1)[-1]
    if _EXACT_VERSION.fullmatch(suffix) is None:
        raise ValueError("INVALID_VERSION")
    return replace_value(pointer, version)


def pinned_package_spec(package: str, version: str) -> str:
    if _EXACT_VERSION.fullmatch(version) is None:
        raise ValueError("INVALID_VERSION")
    if package.startswith("@"):
        separator = package.rfind("@")
        name = package if separator == 0 else package[:separator]
    else:
        name = package.rsplit("@", 1)[0]
    if not name or ("/" in name and not name.startswith("@")):
        raise ValueError("INVALID_PACKAGE")
    return f"{name}@{version}"


def narrow_path(pointer: str, path: str) -> JsoncPatch:
    normalized = re.sub(r"\\", "/", path).rstrip("/")
    if (
        not normalized
        or normalized in {"~", "$HOME"}
        or re.fullmatch(r"(?:[A-Za-z]:)?/", normalized)
        or "/../" in f"/{normalized}/"
    ):
        raise ValueError("INVALID_NARROW_PATH")
    return replace_value(pointer, normalized)


def unify_version(pointer: str, version: str) -> JsoncPatch:
    return pin_version(pointer, version)


def upgrade_https(pointer: str, checked_url: str) -> JsoncPatch:
    if not checked_url.startswith("https://"):
        raise ValueError("HTTPS_NOT_VERIFIED")
    return replace_value(pointer, checked_url)


def remove_disabled(pointer: str) -> JsoncPatch:
    return remove_value(pointer)


__all__ = [
    "RULES",
    "RULE_BY_ID",
    "FixRule",
    "narrow_path",
    "pin_version",
    "pinned_package_spec",
    "remove_disabled",
    "remove_value",
    "replace_value",
    "secret_reference",
    "unify_version",
    "upgrade_https",
]
