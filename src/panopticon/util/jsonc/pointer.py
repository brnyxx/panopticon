"""RFC-6901 pointer traversal for parsed JSONC values."""

from __future__ import annotations

from typing import NoReturn

from panopticon.models import JsonPointer

from .document import JsonValue


def fail_pointer(code: str, detail: str = "") -> NoReturn:
    """Raise the patch error type without coupling pointer logic to patch rendering."""
    from .patch import JsoncPatchError

    raise JsoncPatchError(code, detail)


def decode_pointer(pointer: JsonPointer) -> tuple[str, ...]:
    """Decode one RFC-6901 pointer and reject malformed escape sequences."""
    text = str(pointer)
    if text == "":
        return ()
    if not text.startswith("/"):
        fail_pointer("INVALID_POINTER", text)
    parts: list[str] = []
    for part in text[1:].split("/"):
        decoded: list[str] = []
        index = 0
        while index < len(part):
            if part[index] != "~":
                decoded.append(part[index])
                index += 1
                continue
            if index + 1 >= len(part) or part[index + 1] not in "01":
                fail_pointer("INVALID_POINTER", text)
            decoded.append("/" if part[index + 1] == "1" else "~")
            index += 2
        parts.append("".join(decoded))
    return tuple(parts)


def encode_pointer(parts: tuple[str, ...]) -> str:
    """Encode decoded pointer components using RFC-6901 escape ordering."""
    if not parts:
        return ""
    encoded = (part.replace("~", "~0").replace("/", "~1") for part in parts)
    return "/" + "/".join(encoded)


def array_index(part: str, length: int, *, allow_end: bool = False) -> int:
    """Parse a canonical JSON array index within the requested bounds."""
    if not part or any(char < "0" or char > "9" for char in part):
        fail_pointer("INVALID_INDEX", part)
    if len(part) > 1 and part.startswith("0"):
        fail_pointer("INVALID_INDEX", part)
    try:
        index = int(part)
    except ValueError as error:
        fail_pointer("INVALID_INDEX", part)
        raise AssertionError("unreachable index") from error
    upper_bound = length if allow_end else length - 1
    if index < 0 or index > upper_bound:
        fail_pointer("INVALID_INDEX", part)
    return index


def value_at(value: JsonValue, parts: tuple[str, ...]) -> JsonValue:
    """Resolve a decoded pointer against a parsed JSON value."""
    current = value
    for part in parts:
        match current:
            case dict() as mapping:
                if part not in mapping:
                    fail_pointer("INVALID_POINTER", encode_pointer(parts))
                current = mapping[part]
            case list() as sequence:
                current = sequence[array_index(part, len(sequence))]
            case _:
                fail_pointer("INVALID_POINTER", encode_pointer(parts))
    return current
