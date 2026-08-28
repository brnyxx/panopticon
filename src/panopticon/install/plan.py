"""Pure reversible stdio-wrapper planning over exact JSONC pointers."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from panopticon.discovery.base import RawServerEntry
from panopticon.fix.plan import make_plan
from panopticon.inventory.normalize import normalize_entry
from panopticon.models.ids import JsonPointer
from panopticon.util.jsonc.document import JsonValue, SourceDocument
from panopticon.util.jsonc.patch import JsoncPatch, PatchOperation
from panopticon.util.jsonc.pointer import decode_pointer, encode_pointer

from .model import InstallAction, InstallPlan, InstallSelection

_ORIGINAL = "_pano_original"


def _child(pointer: JsonPointer, name: str) -> JsonPointer:
    return JsonPointer(encode_pointer((*decode_pointer(pointer), name)))


def _original(
    raw: Mapping[str, JsonValue],
) -> tuple[str, tuple[str, ...], str | None] | None:
    value = raw.get(_ORIGINAL)
    if not isinstance(value, Mapping):
        return None
    version = value.get("v", value.get("version"))
    command = value.get("command", value.get("original_command"))
    args = value.get("args", value.get("original_args", []))
    transaction_id = value.get("transaction_id")
    if (
        version not in {0, 1}
        or not isinstance(command, str)
        or not isinstance(args, list)
        or not all(isinstance(argument, str) for argument in args)
    ):
        return None
    return (
        command,
        tuple(argument for argument in args if isinstance(argument, str)),
        transaction_id if isinstance(transaction_id, str) else None,
    )


def _replace_or_add(entry: RawServerEntry, field: str, value: JsonValue) -> JsoncPatch:
    operation = PatchOperation.REPLACE if field in entry.raw else PatchOperation.ADD
    return JsoncPatch(operation, _child(entry.json_pointer, field), value)


def _pano_executable(value: str | None) -> str:
    if value is None:
        raise ValueError("PANO_EXECUTABLE_REQUIRED")
    path = Path(value)
    if not path.is_absolute() or not path.exists() or not path.is_file():
        raise ValueError("PANO_EXECUTABLE_UNAVAILABLE")
    return str(path)


def plan_entry(
    entry: RawServerEntry,
    document: SourceDocument,
    *,
    client: str,
    home: Path,
    pano_command: str | None,
    action: InstallAction,
) -> InstallPlan:
    raw = entry.raw
    command = raw.get("command")
    args = raw.get("args", [])
    restore_transaction_id: str | None = None
    if action is InstallAction.UNINSTALL:
        original = _original(raw)
        if original is None:
            raise ValueError("NOT_WRAPPED")
        patches = (
            _replace_or_add(entry, "command", original[0]),
            _replace_or_add(entry, "args", list(original[1])),
            JsoncPatch(PatchOperation.REMOVE, _child(entry.json_pointer, _ORIGINAL)),
        )
        restore_transaction_id = original[2]
        reason = "UNINSTALL_PLANNED"
    else:
        if _ORIGINAL in raw or (
            command is not None
            and isinstance(args, list)
            and any(argument == "wrap" for argument in args[:2])
        ):
            raise ValueError("ALREADY_WRAPPED")
        transport = raw.get("transport")
        if "url" in raw or (isinstance(transport, str) and transport.casefold() in {"http", "sse"}):
            raise ValueError("REMOTE_NOT_TARGET")
        if raw.get("disabled") is True or raw.get("enabled") is False:
            raise ValueError("DISABLED")
        if (
            not isinstance(command, str)
            or not isinstance(args, list)
            or not all(isinstance(argument, str) for argument in args)
        ):
            raise ValueError("UNSUPPORTED_STDIO")
        executable = _pano_executable(pano_command)
        installed = normalize_entry(entry, client=client, home=str(home))
        metadata: dict[str, JsonValue] = {
            "v": 1,
            "command": command,
            "args": list(args),
            "transaction_id": "__PENDING__",
        }
        wrapped_args = [
            "wrap",
            "--server-id",
            str(installed.server_id),
            "--installation-id",
            str(installed.installation_id),
            "--",
            command,
            *args,
        ]
        patches = (
            _replace_or_add(entry, "command", executable),
            _replace_or_add(entry, "args", wrapped_args),
            JsoncPatch(PatchOperation.ADD, _child(entry.json_pointer, _ORIGINAL), metadata),
        )
        reason = "INSTALL_PLANNED"
    fix_plan = make_plan(entry.config_path, document, patches)
    metadata_pointer = _child(entry.json_pointer, _ORIGINAL)
    selection = InstallSelection(
        "INSTALL" if action is InstallAction.INSTALL else "UNINSTALL",
        entry.config_path,
        entry.json_pointer,
        value=restore_transaction_id,
        transaction_pointer=metadata_pointer if action is InstallAction.INSTALL else None,
    )
    return InstallPlan(fix_plan, selection, entry.name, "CLIENT_RESTART_REQUIRED", reason)


__all__ = ["plan_entry"]
