"""Typed exception paths used by the source-quality checker."""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, TypeAlias

if TYPE_CHECKING:
    import check_no_excuse_rules_flow as flow

Binding: TypeAlias = tuple[str, str | None]
Provenances: TypeAlias = frozenset[Binding]
Scope: TypeAlias = dict[str, Provenances]
ExceptionNames: TypeAlias = frozenset[str] | None


@dataclass(frozen=True, slots=True)
class ExceptionPath:
    """One reachable exception alternative paired with its source-point scope."""

    exception_names: ExceptionNames
    scope: Scope


class ExceptionPathCollection(Protocol):
    """Lifecycle needed by flow traversal for one try body."""

    def close_body(self) -> tuple[ExceptionPath, ...]: ...

    def close_outgoing(self) -> tuple[ExceptionPath, ...]: ...

    def begin_finally(self) -> None: ...

    def finish(self, paths: tuple[ExceptionPath, ...], preserve: bool) -> None: ...


def simple_exception_names(value: ast.expr | None) -> frozenset[str] | None:
    """Return known names from a simple exception name or name tuple."""
    if isinstance(value, ast.Name):
        return frozenset((value.id,))
    if not isinstance(value, ast.Tuple):
        return None
    names: list[str] = []
    for element in value.elts:
        if not isinstance(element, ast.Name):
            return None
        names.append(element.id)
    return frozenset(names)


class _TryVisitor(Protocol):
    """Flow operations needed to analyze one try statement."""

    def _exception_paths(self) -> ExceptionPathCollection: ...

    def _snapshot(self) -> Scope: ...

    def _visit_branch(self, initial: Scope, nodes: Iterable[ast.AST]) -> flow.FlowStates: ...

    def _scope_for(
        self,
        states: flow.FlowStates,
        outcomes: Iterable[flow.FlowOutcome],
    ) -> Scope | None: ...

    def _merge_scopes(self, states: tuple[Scope, ...]) -> Scope: ...

    def _merge_states(self, groups: Iterable[flow.FlowStates]) -> flow.FlowStates: ...


def visit_try(visitor: _TryVisitor, node: ast.Try | ast.TryStar) -> flow.FlowStates:
    """Analyze one reachable try body and compose its finally paths."""
    import check_no_excuse_rules_flow as flow

    exception_paths = visitor._exception_paths()
    before = visitor._snapshot()
    tried = visitor._visit_branch(before, node.body)
    body_paths = exception_paths.close_body()
    tried_normal = visitor._scope_for(tried, (flow.FlowOutcome.NORMAL,))
    normal = (
        visitor._visit_branch(tried_normal, node.orelse)
        if node.orelse and tried_normal is not None
        else ((flow.FlowOutcome.NORMAL, tried_normal),)
        if tried_normal is not None
        else ()
    )
    groups: list[flow.FlowStates] = [normal]
    for outcome in (flow.FlowOutcome.BREAK, flow.FlowOutcome.CONTINUE, flow.FlowOutcome.RETURN):
        state = visitor._scope_for(tried, (outcome,))
        if state is not None:
            groups.append(((outcome, state),))
    exception_flow = flow.analyze_exception_flow(node, body_paths)
    for handler, initial in exception_flow.handler_entries:
        groups.append(visitor._visit_branch(initial, (handler,)))
    outgoing_paths = exception_paths.close_outgoing()
    if outgoing_paths:
        outgoing_scope = visitor._merge_scopes(tuple(path.scope for path in outgoing_paths))
        groups.append(((flow.FlowOutcome.RAISE, outgoing_scope),))
    all_unhandled_paths = exception_flow.unhandled_paths + outgoing_paths
    if not node.finalbody:
        if exception_flow.unhandled_raise_scope is not None:
            groups.append(((flow.FlowOutcome.RAISE, exception_flow.unhandled_raise_scope),))
        merged = visitor._merge_states(groups)
        exception_paths.finish(all_unhandled_paths, True)
        return merged
    merged = visitor._merge_states(
        tuple(
            tuple(state for state in states if state[0] is not flow.FlowOutcome.RAISE)
            for states in groups
        ),
    )
    exception_paths.begin_finally()
    composed: list[flow.FlowStates] = []
    for incoming in merged:
        final = visitor._visit_branch(incoming[1], node.finalbody)
        composed.append(flow.compose_finally(incoming, final))
    preserved_paths: list[ExceptionPath] = []
    for path in all_unhandled_paths:
        final = visitor._visit_branch(path.scope, node.finalbody)
        normal_scope = visitor._scope_for(final, (flow.FlowOutcome.NORMAL,))
        if normal_scope is not None:
            preserved_paths.append(ExceptionPath(path.exception_names, normal_scope))
        composed.append(
            flow.compose_finally((flow.FlowOutcome.RAISE, path.scope), final),
        )
    exception_paths.finish(tuple(preserved_paths), bool(preserved_paths))
    return visitor._merge_states(composed)


class ExceptionPathBuffer:
    """Mutable path buffer whose scope ends when the try body is analyzed."""

    def __init__(self) -> None:
        self._paths: list[ExceptionPath] = []
        self._body_active = True

    @property
    def body_active(self) -> bool:
        """Return whether direct body risks still belong to this try."""
        return self._body_active

    def record(self, path: ExceptionPath) -> None:
        """Record one path at the scope observed by its caller."""
        self._paths.append(path)

    def close_body(self) -> tuple[ExceptionPath, ...]:
        """Freeze direct body paths before handler and finally traversal."""
        self._body_active = False
        return tuple(self._paths)
