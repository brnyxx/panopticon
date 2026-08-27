# /// script
# requires-python = ">=3.11"
# ///
# ─── How to run ───
# uv run python scripts/check_persistence_boundary.py [paths...]
"""Reject AST-shaped direct product persistence outside approved modules."""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[3]
_WRITE_METHODS: Final[frozenset[str]] = frozenset({"write_text", "write_bytes"})
_PATH_NAME_MARKERS: Final[tuple[str, ...]] = (
    "path",
    "target",
    "source",
    "destination",
    "temporary",
    "file",
)
_TEMP_METHODS: Final[frozenset[str]] = frozenset(
    {"mkstemp", "NamedTemporaryFile", "TemporaryFile", "SpooledTemporaryFile"}
)
_WRITE_FLAG_NAMES: Final[frozenset[str]] = frozenset(
    {"O_WRONLY", "O_RDWR", "O_APPEND", "O_CREAT", "O_TRUNC"}
)
_SUPPORTED_MODULES: Final[tuple[str, ...]] = ("os", "pathlib", "tempfile", "builtins")


@dataclass(frozen=True, slots=True)
class _ImportAliases:
    modules: frozenset[tuple[str, str]]
    names: frozenset[tuple[str, str, str]]

    def module_alias(self, module: str, local_name: str) -> bool:
        return (module, local_name) in self.modules

    def imported_name(self, module: str, local_name: str) -> str | None:
        matches = tuple(
            imported
            for imported_module, imported, local in self.names
            if imported_module == module and local == local_name
        )
        if not matches or len(set(matches)) != 1:
            return None
        return matches[0]


@dataclass(frozen=True, slots=True)
class Violation:
    path: Path
    line: int
    call: str


def _approved(path: Path) -> bool:
    parts = path.resolve().parts
    for index in range(len(parts) - 2):
        if parts[index : index + 2] == ("src", "panopticon"):
            relative = parts[index + 2 :]
            return relative[0] == "store" or relative in {
                ("fix", "config_patch.py"),
                ("install", "config_patch.py"),
            }
    return False


def _collect_import_aliases(tree: ast.AST) -> _ImportAliases:
    modules: set[tuple[str, str]] = set()
    names: set[tuple[str, str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _SUPPORTED_MODULES:
                    modules.add((alias.name, alias.asname or alias.name))
        if isinstance(node, ast.ImportFrom) and node.module in _SUPPORTED_MODULES:
            for alias in node.names:
                names.add((node.module, alias.name, alias.asname or alias.name))
    return _ImportAliases(frozenset(modules), frozenset(names))


def _attribute_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _mode_is_write(call: ast.Call) -> bool:
    mode_node: ast.expr | None = None
    if len(call.args) >= 2:
        mode_node = call.args[1]
    for keyword in call.keywords:
        if keyword.arg == "mode":
            mode_node = keyword.value
    if mode_node is None:
        return False
    if isinstance(mode_node, ast.Constant) and isinstance(mode_node.value, str):
        return any(marker in mode_node.value for marker in "wax+")
    return True


def _has_write_flags(call: ast.Call) -> bool:
    if len(call.args) < 2:
        return True
    return any(
        isinstance(node, ast.Attribute | ast.Name) and _attribute_name(node) in _WRITE_FLAG_NAMES
        for node in ast.walk(call.args[1])
    )


def _looks_path_receiver(node: ast.expr, aliases: _ImportAliases) -> bool:
    if isinstance(node, ast.Name):
        return (
            any(marker in node.id.casefold() for marker in _PATH_NAME_MARKERS)
            or aliases.imported_name("pathlib", node.id) == "Path"
            or node.id == "Path"
        )
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            is_path_alias = aliases.imported_name("pathlib", node.func.id) == "Path"
            return is_path_alias or node.func.id == "Path"
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            return node.func.attr == "Path" and aliases.module_alias("pathlib", node.func.value.id)
    if isinstance(node, ast.Attribute):
        return _looks_path_receiver(node.value, aliases)
    return False


def _is_open_call(call: ast.Call, aliases: _ImportAliases) -> bool:
    name = _attribute_name(call.func)
    if isinstance(call.func, ast.Name):
        return name == "open" or aliases.imported_name("builtins", call.func.id) == "open"
    if name != "open" or not isinstance(call.func, ast.Attribute):
        return False
    receiver = call.func.value
    if _looks_path_receiver(receiver, aliases):
        return True
    return isinstance(receiver, ast.Name) and aliases.module_alias("builtins", receiver.id)


def _persistence_call(
    call: ast.Call, file_handles: frozenset[str], aliases: _ImportAliases
) -> str | None:
    name = _attribute_name(call.func)
    if name is None:
        return None
    imported_module: str | None = None
    if isinstance(call.func, ast.Name):
        for module in _SUPPORTED_MODULES:
            if aliases.imported_name(module, name) is not None:
                imported_module = module
                break
        if imported_module is not None:
            name = aliases.imported_name(imported_module, name) or name
    if name in _WRITE_METHODS:
        return name
    if name in {"write", "writelines"} and isinstance(call.func, ast.Attribute):
        receiver = call.func.value
        if isinstance(receiver, ast.Name) and receiver.id in file_handles | {"file", "file_handle"}:
            return f"file-{name}"
    if name in {"replace", "rename"}:
        if imported_module == "os" and isinstance(call.func, ast.Name):
            return f"os.{name}"
        if isinstance(call.func, ast.Attribute):
            receiver = call.func.value
            if isinstance(receiver, ast.Name) and aliases.module_alias("os", receiver.id):
                return f"os.{name}"
            return name if _looks_path_receiver(receiver, aliases) else None
    if name == "open":
        if (
            isinstance(call.func, ast.Name)
            and imported_module in {None, "builtins"}
            and _mode_is_write(call)
        ):
            return "open-write-mode"
        if isinstance(call.func, ast.Attribute):
            receiver = call.func.value
            if _looks_path_receiver(receiver, aliases) and call.args:
                mode_node = call.args[0]
                if (
                    isinstance(mode_node, ast.Constant)
                    and isinstance(mode_node.value, str)
                    and any(marker in mode_node.value for marker in "wax+")
                ):
                    return "path-open-write-mode"
            if isinstance(receiver, ast.Name) and aliases.module_alias("os", receiver.id):
                return "os.open-write-flags" if _has_write_flags(call) else None
            if isinstance(receiver, ast.Name) and aliases.module_alias("builtins", receiver.id):
                return "open-write-mode" if _mode_is_write(call) else None
        if imported_module == "os" and isinstance(call.func, ast.Name):
            return "os.open-write-flags" if _has_write_flags(call) else None
    if name in _TEMP_METHODS:
        return name
    return None


def _opened_file_handles(tree: ast.AST, aliases: _ImportAliases) -> frozenset[str]:
    handles: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            for item in node.items:
                if (
                    isinstance(item.context_expr, ast.Call)
                    and _is_open_call(item.context_expr, aliases)
                    and isinstance(item.optional_vars, ast.Name)
                ):
                    handles.add(item.optional_vars.id)
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and (_is_open_call(node.value, aliases) or _attribute_name(node.value.func) == "fdopen")
        ):
            handles.update(target.id for target in node.targets if isinstance(target, ast.Name))
    return frozenset(handles)


def check_file(path: Path) -> tuple[Violation, ...]:
    """Return direct-persistence calls in one non-approved Python source file."""
    if _approved(path):
        return ()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    aliases = _collect_import_aliases(tree)
    file_handles = _opened_file_handles(tree, aliases)
    violations: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call = _persistence_call(node, file_handles, aliases)
            if call is not None:
                violations.append(Violation(path, node.lineno, call))
    return tuple(sorted(violations, key=lambda item: (str(item.path), item.line, item.call)))


def _python_files(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    files: set[Path] = set()
    for path in paths:
        if path.is_dir():
            files.update(path.rglob("*.py"))
        elif path.suffix == ".py":
            files.add(path)
    return tuple(sorted(files))


def scan(arguments: tuple[str, ...] | None = None) -> tuple[Violation, ...]:
    """Scan explicit paths or repository product source without rendering output."""
    selected = arguments if arguments is not None else tuple(sys.argv[1:])
    paths = tuple(Path(value) for value in selected) if selected else (ROOT / "src",)
    return tuple(violation for path in _python_files(paths) for violation in check_file(path))


def main(arguments: tuple[str, ...] | None = None) -> int:
    """Return the machine-consumed checker exit status."""
    return 1 if scan(arguments) else 0
