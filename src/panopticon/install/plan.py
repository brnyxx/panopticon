"""Pure reversible stdio wrapper planning."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from panopticon.discovery.base import RawServerEntry
from panopticon.models import JsonPointer
from panopticon.util.jsonc.patch import JsoncPatch, PatchOperation

from .model import InstallPlan

_ORIGINAL = "_pano_original"


def _original(raw: Mapping[str, object]) -> tuple[str, tuple[str, ...]] | None:
    value = raw.get(_ORIGINAL)
    if not isinstance(value, Mapping):
        return None
    command = value.get("command", value.get("original_command"))
    args = value.get("args", value.get("original_args", ()))
    if (
        not isinstance(command, str)
        or not isinstance(args, (list, tuple))
        or not all(isinstance(x, str) for x in args)
    ):
        return None
    return command, tuple(args)


def _unsafe(command: str) -> bool:
    name = Path(command).name.lower()
    return (
        name in {"open", "osascript", "xdg-open", "explorer", "start"}
        or ".app/" in command.lower()
        or command.lower().endswith(".app")
    )


def plan_entry(
    entry: RawServerEntry, *, pano_command: str = "pano", uninstall: bool = False
) -> InstallPlan:
    raw = entry.raw
    ptr = str(entry.json_pointer)
    command = raw.get("command")
    args = raw.get("args", ())
    if uninstall:
        original = _original(raw)
        if original is None:
            raise ValueError("NOT_WRAPPED")
        patches = (
            JsoncPatch(PatchOperation.REPLACE, JsonPointer(ptr + "/command"), original[0]),
            JsoncPatch(PatchOperation.REPLACE, JsonPointer(ptr + "/args"), list(original[1])),
            JsoncPatch(PatchOperation.REMOVE, JsonPointer(ptr + "/_pano_original")),
        )
        return InstallPlan(
            entry.config_path,
            entry.json_pointer,
            patches,
            entry.name,
            "Restart the client.",
            "UNINSTALL_PLANNED",
        )
    if _ORIGINAL in raw:
        if _original(raw) is not None and raw[_ORIGINAL].get("version", 1) == 0:  # type: ignore[union-attr]
            raise ValueError("ALREADY_WRAPPED")
        raise ValueError("ALREADY_WRAPPED")
    if (
        not isinstance(command, str)
        or not isinstance(args, (list, tuple))
        or not all(isinstance(x, str) for x in args)
    ):
        raise ValueError("UNSUPPORTED_STDIO")
    if "url" in raw or raw.get("transport") in {"http", "sse"}:
        raise ValueError("REMOTE_NOT_TARGET")
    if raw.get("disabled") is True:
        raise ValueError("DISABLED")
    if raw.get("running") is True or raw.get("concurrent") is True:
        raise ValueError("CONCURRENT")
    if _unsafe(command):
        raise ValueError("UNSAFE_GUI_EXECUTABLE")
    metadata = {"version": 1, "command": command, "args": list(args)}
    wrapped_args = ["wrap", "--", command, *args]
    patches = (
        JsoncPatch(PatchOperation.REPLACE, JsonPointer(ptr + "/command"), pano_command),
        JsoncPatch(PatchOperation.REPLACE, JsonPointer(ptr + "/args"), wrapped_args),
        JsoncPatch(PatchOperation.ADD, JsonPointer(ptr + "/_pano_original"), metadata),
    )
    return InstallPlan(
        entry.config_path, entry.json_pointer, patches, entry.name, "Restart the client."
    )


make_plan = plan_entry

__all__ = ["make_plan", "plan_entry"]
