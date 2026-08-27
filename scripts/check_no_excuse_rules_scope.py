"""Source-order binding analysis for the source-quality checker."""

from __future__ import annotations

import ast
from typing import Literal, assert_never

import check_no_excuse_rules_flow as flow
import check_no_excuse_rules_flow_visitor as flow_visitor
from check_no_excuse_rules_exception_paths import (
    Binding,
    ExceptionPath,
    ExceptionPathBuffer,
    ExceptionPathCollection,
    Provenances,
    simple_exception_names,
)


class _TryExceptionPaths:
    """Route exception paths according to the active stage of one try statement."""

    def __init__(self, stack: list[_TryExceptionPaths | None]) -> None:
        self._stack = stack
        self._buffer = ExceptionPathBuffer()
        self._outgoing_paths: list[ExceptionPath] = []
        self._phase: Literal["body", "outgoing", "finally"] = "body"
        stack.append(self)

    def record(self, path: ExceptionPath) -> bool:
        """Record a path here, or return false so a finally path can move outward."""
        match self._phase:
            case "body":
                self._buffer.record(path)
                return True
            case "outgoing":
                self._outgoing_paths.append(path)
                return True
            case "finally":
                return False
            case unreachable:
                assert_never(unreachable)

    def close_body(self) -> tuple[ExceptionPath, ...]:
        """Close body collection before handlers and the else block are visited."""
        self._phase = "outgoing"
        return self._buffer.close_body()

    def close_outgoing(self) -> tuple[ExceptionPath, ...]:
        """Return exceptions raised by handlers or else without routing them again."""
        return tuple(self._outgoing_paths)

    def begin_finally(self) -> None:
        """Forward finally risks to an enclosing try instead of this try's handlers."""
        self._phase = "finally"

    def finish(self, paths: tuple[ExceptionPath, ...], preserve: bool) -> None:
        """Remove this context and propagate surviving paths to its parent."""
        self._stack.pop()
        if preserve:
            for path in paths:
                self._record_in_parent(path)

    def _record_in_parent(self, path: ExceptionPath) -> None:
        for context in reversed(self._stack):
            if context is None:
                return
            if context.record(path):
                return


class _CallProvenanceVisitor(flow_visitor.FlowVisitorMixin, ast.NodeVisitor):
    """Find prohibited calls while preserving possible lexical provenance."""

    def __init__(self, module: str, function: str) -> None:
        self._module = module
        self._function = function
        self._scopes: list[tuple[bool, flow.Scope]] = [(False, {})]
        self._exception_path_stack: list[_TryExceptionPaths | None] = []
        self.found = False

    def _exception_paths(self) -> ExceptionPathCollection:
        return _TryExceptionPaths(self._exception_path_stack)

    def _record_exception_path(self, exception_names: frozenset[str] | None) -> None:
        path = ExceptionPath(exception_names, self._snapshot())
        for context in reversed(self._exception_path_stack):
            if context is None:
                return
            if context.record(path):
                return

    def _visit_deferred_body(self, nodes: list[ast.stmt]) -> None:
        self._exception_path_stack.append(None)
        try:
            self._visit_nodes(nodes)
        finally:
            self._exception_path_stack.pop()

    def _bind(self, name: str, binding: Binding | None = None) -> None:
        self._scopes[-1][1][name] = frozenset((binding,)) if binding is not None else frozenset()

    def _lookup(self, name: str) -> Provenances:
        current_is_class = self._scopes[-1][0]
        included_class = False
        for is_class, scope in reversed(self._scopes):
            if is_class:
                if not current_is_class or included_class:
                    continue
                included_class = True
            if name in scope:
                return scope[name]
        return frozenset()

    def _invalidate_store_names(self, target: ast.AST) -> None:
        for node in ast.walk(target):
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                self._bind(node.id)

    def _snapshot(self) -> flow.Scope:
        return self._scopes[-1][1].copy()

    def _merge_scopes(self, states: tuple[flow.Scope, ...]) -> flow.Scope:
        return flow.merge_scopes(states)

    def _replace_scope(self, scope: flow.Scope) -> None:
        self._scopes[-1] = (self._scopes[-1][0], scope)

    def _visit_arguments(self, arguments: ast.arguments) -> None:
        for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs):
            if argument.annotation is not None:
                self.visit(argument.annotation)
        for optional_argument in (arguments.vararg, arguments.kwarg):
            if optional_argument is not None and optional_argument.annotation is not None:
                self.visit(optional_argument.annotation)
        for default in arguments.defaults:
            self.visit(default)
        for optional_default in arguments.kw_defaults:
            if optional_default is not None:
                self.visit(optional_default)

    def _bind_arguments(self, arguments: ast.arguments) -> None:
        for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs):
            self._bind(argument.arg)
        for optional_argument in (arguments.vararg, arguments.kwarg):
            if optional_argument is not None:
                self._bind(optional_argument.arg)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        self._visit_arguments(node.args)
        if node.returns is not None:
            self.visit(node.returns)
        self._bind(node.name)
        self._scopes.append((False, {}))
        self._bind_arguments(node.args)
        self._visit_deferred_body(node.body)
        self._scopes.pop()

    def visit_Import(self, node: ast.Import) -> None:
        self._record_exception_path(None)
        for alias in node.names:
            local_name = alias.asname or alias.name.split(".", maxsplit=1)[0]
            self._bind(local_name, (alias.name, None))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self._record_exception_path(None)
        for alias in node.names:
            if alias.name == "*":
                continue
            local_name = alias.asname or alias.name
            binding = (
                (node.module, alias.name) if node.level == 0 and node.module is not None else None
            )
            self._bind(local_name, binding)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        for target in node.targets:
            self.visit(target)
            self._invalidate_store_names(target)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self.visit(node.value)
        self.visit(node.target)
        self._invalidate_store_names(node.target)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.visit(node.target)
        self.visit(node.value)
        self._invalidate_store_names(node.target)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        self.visit(node.target)
        self._invalidate_store_names(node.target)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            self.visit(target)
            self._invalidate_store_names(target)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> flow.FlowStates:
        if node.type is not None:
            self.visit(node.type)
        if node.name is not None:
            self._bind(node.name)
        return self._visit_nodes(node.body)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._visit_arguments(node.args)
        self._scopes.append((False, {}))
        self._bind_arguments(node.args)
        self._exception_path_stack.append(None)
        try:
            self.visit(node.body)
        finally:
            self._exception_path_stack.pop()
        self._scopes.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword.value)
        self._bind(node.name)
        self._scopes.append((True, {}))
        self._visit_nodes(node.body)
        self._scopes.pop()

    def visit_Raise(self, node: ast.Raise) -> flow.FlowStates:
        self._record_exception_path(simple_exception_names(node.exc))
        return super().visit_Raise(node)

    def visit_Call(self, node: ast.Call) -> None:
        self._record_exception_path(None)
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            bindings = self._lookup(node.func.value.id)
            if (self._module, None) in bindings and node.func.attr == self._function:
                self.found = True
        if isinstance(node.func, ast.Name) and (self._module, self._function) in self._lookup(
            node.func.id
        ):
            self.found = True
        self.generic_visit(node)


def has_call(tree: ast.AST, module: str, function: str) -> bool:
    """Return whether a prohibited call provenance is possible in an AST."""
    visitor = _CallProvenanceVisitor(module, function)
    visitor.visit(tree)
    return visitor.found
