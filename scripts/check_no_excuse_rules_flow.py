"""Bounded control-flow facts used by the source-quality checker."""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias, assert_never

from check_no_excuse_rules_exception_paths import ExceptionPath, simple_exception_names
from check_no_excuse_rules_exception_paths import Scope as Scope


class FlowOutcome(StrEnum):
    """Possible results of visiting one statement sequence."""

    NORMAL = "normal"
    BREAK = "break"
    CONTINUE = "continue"
    RETURN = "return"
    RAISE = "raise"


FlowState: TypeAlias = tuple[FlowOutcome, Scope]
FlowStates: TypeAlias = tuple[FlowState, ...]


@dataclass(frozen=True, slots=True)
class ExceptionFlow:
    """Handler entries and unhandled paths for one analyzed try statement."""

    handler_entries: tuple[tuple[ast.ExceptHandler, Scope], ...]
    unhandled_paths: tuple[ExceptionPath, ...]
    unhandled_raise_scope: Scope | None


def merge_scopes(states: Iterable[Scope]) -> Scope:
    """Conservatively union possible bindings from multiple scopes."""
    materialized = tuple(states)
    return {
        name: frozenset(binding for state in materialized for binding in state.get(name, ()))
        for name in sorted({name for state in materialized for name in state})
    }


def _handler_match(handler: ast.ExceptHandler, exception_name: str) -> bool | None:
    if handler.type is None:
        return True
    names = simple_exception_names(handler.type)
    if names is None:
        return None
    return exception_name in names or bool(names & {"BaseException", "Exception"})


def _route_known_name(
    handlers: list[ast.ExceptHandler],
    exception_name: str,
) -> tuple[tuple[int, ...], bool]:
    indices: list[int] = []
    for index, handler in enumerate(handlers):
        match = _handler_match(handler, exception_name)
        if match is not False:
            indices.append(index)
        if match is True:
            return tuple(indices), False
    return tuple(indices), True


def _route_exception_path(
    handlers: list[ast.ExceptHandler],
    path: ExceptionPath,
) -> tuple[tuple[int, ...], bool]:
    """Return possible first-handler routes and whether the path propagates."""
    if path.exception_names is None:
        possible_indices: list[int] = []
        for index, handler in enumerate(handlers):
            possible_indices.append(index)
            names = simple_exception_names(handler.type)
            if handler.type is None or (
                names is not None and bool(names & {"BaseException", "Exception"})
            ):
                return tuple(possible_indices), False
        return tuple(possible_indices), True
    indices: set[int] = set()
    propagates = False
    for exception_name in path.exception_names:
        routed, path_propagates = _route_known_name(handlers, exception_name)
        indices.update(routed)
        propagates = propagates or path_propagates
    return tuple(sorted(indices)), propagates


def analyze_exception_flow(
    node: ast.Try | ast.TryStar,
    paths: tuple[ExceptionPath, ...],
) -> ExceptionFlow:
    """Route each reachable exception path through ordered handlers."""
    handler_scopes: list[list[Scope]] = [[] for _ in node.handlers]
    unhandled_paths: list[ExceptionPath] = []
    for path in paths:
        indices, propagates = _route_exception_path(node.handlers, path)
        for index in indices:
            handler_scopes[index].append(path.scope)
        if propagates:
            unhandled_paths.append(path)
    entries = tuple(
        (handler, merge_scopes(tuple(scopes)))
        for handler, scopes in zip(node.handlers, handler_scopes, strict=True)
        if scopes
    )
    unhandled = tuple(unhandled_paths)
    unhandled_scope = merge_scopes(path.scope for path in unhandled) if unhandled else None
    return ExceptionFlow(entries, unhandled, unhandled_scope)


def compose_finally(incoming: FlowState, final: FlowStates) -> FlowStates:
    """Apply finally outcomes to one incoming control-flow state."""
    incoming_outcome = incoming[0]
    composed: list[FlowState] = []
    for final_outcome, scope in final:
        match final_outcome:
            case FlowOutcome.NORMAL:
                outcome = incoming_outcome
            case FlowOutcome.BREAK | FlowOutcome.CONTINUE | FlowOutcome.RETURN | FlowOutcome.RAISE:
                outcome = final_outcome
            case unreachable:
                assert_never(unreachable)
        composed.append((outcome, scope))
    return tuple(composed)


@dataclass(frozen=True, slots=True)
class LoopReachability:
    """Known loop paths needed to decide whether a loop else can run."""

    enters_body: bool
    can_skip_body: bool
    can_complete_without_break: bool


def constant_condition(test: ast.expr) -> bool | None:
    """Return a boolean literal's value, or None for a non-literal condition."""
    if isinstance(test, ast.Constant) and type(test.value) is bool:
        return test.value
    return None


def is_empty_literal(value: ast.expr) -> bool:
    """Return whether an iterable expression is a statically empty literal."""
    if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
        return not value.elts
    if isinstance(value, ast.Dict):
        return not value.keys and not value.values
    return isinstance(value, ast.Constant) and type(value.value) in (str, bytes) and not value.value


def is_nonempty_literal(value: ast.expr) -> bool:
    """Return whether an iterable expression is a statically nonempty literal."""
    if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
        return bool(value.elts)
    if isinstance(value, ast.Dict):
        return bool(value.keys or value.values)
    return (
        isinstance(value, ast.Constant) and type(value.value) in (str, bytes) and bool(value.value)
    )


def is_irrefutable_pattern(pattern: ast.pattern) -> bool:
    """Return whether a simple wildcard or capture pattern can match any subject."""
    if not isinstance(pattern, ast.MatchAs):
        return False
    return pattern.pattern is None or is_irrefutable_pattern(pattern.pattern)


def is_irrefutable_case(case: ast.match_case) -> bool:
    """Return whether a match case cannot fall through to a later case."""
    guard = case.guard
    return is_irrefutable_pattern(case.pattern) and (
        guard is None or constant_condition(guard) is True
    )


def match_capture_names(pattern: ast.pattern) -> tuple[str, ...]:
    """Return capture names bound while a pattern matches, excluding wildcards."""
    names: list[str] = []
    for node in ast.walk(pattern):
        if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name is not None:
            names.append(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest is not None:
            names.append(node.rest)
    return tuple(names)


def loop_reachability(
    node: ast.For | ast.AsyncFor | ast.While,
    body_outcomes: Iterable[FlowOutcome],
) -> LoopReachability:
    """Classify only loop facts needed by the bounded visitor."""
    outcomes = frozenset(body_outcomes)
    can_exhaust_without_break = FlowOutcome.NORMAL in outcomes or FlowOutcome.CONTINUE in outcomes
    match node:
        case ast.While(test=test):
            condition = constant_condition(test)
            if condition is False:
                return LoopReachability(False, True, True)
            if condition is True:
                return LoopReachability(True, False, False)
            return LoopReachability(True, True, True)
        case ast.For(iter=iter) | ast.AsyncFor(iter=iter):
            if is_empty_literal(iter):
                return LoopReachability(False, True, True)
            if is_nonempty_literal(iter):
                return LoopReachability(True, False, can_exhaust_without_break)
            return LoopReachability(True, True, True)
        case unreachable:
            assert_never(unreachable)
