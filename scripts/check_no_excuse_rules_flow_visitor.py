"""Bounded statement traversal for the source-quality checker."""

from __future__ import annotations

import ast
from collections.abc import Iterable
from typing import assert_never

import check_no_excuse_rules_flow as flow
from check_no_excuse_rules_exception_paths import Binding, ExceptionPathCollection, visit_try


class FlowVisitorMixin(ast.NodeVisitor):
    """Traverse statement paths while delegating binding state to the scope visitor."""

    def _bind(self, name: str, binding: Binding | None = None) -> None:
        raise NotImplementedError

    def _invalidate_store_names(self, target: ast.AST) -> None:
        raise NotImplementedError

    def _snapshot(self) -> flow.Scope:
        raise NotImplementedError

    def _replace_scope(self, scope: flow.Scope) -> None:
        raise NotImplementedError

    def _merge_scopes(self, states: tuple[flow.Scope, ...]) -> flow.Scope:
        raise NotImplementedError

    def _exception_paths(self) -> ExceptionPathCollection:
        raise NotImplementedError

    def _visit_nodes(self, nodes: Iterable[ast.AST]) -> flow.FlowStates:
        """Visit a statement list and stop its live path at the first terminator."""
        current: flow.Scope | None = self._snapshot()
        finished: list[flow.FlowStates] = []
        for node in nodes:
            if current is None:
                break
            self._replace_scope(current)
            visited = self.visit(node)
            states = (
                visited if visited is not None else ((flow.FlowOutcome.NORMAL, self._snapshot()),)
            )
            finished.append(
                tuple(
                    (outcome, scope)
                    for outcome, scope in states
                    if outcome is not flow.FlowOutcome.NORMAL
                )
            )
            current = self._scope_for(states, (flow.FlowOutcome.NORMAL,))
        if current is not None:
            finished.append(((flow.FlowOutcome.NORMAL, current),))
        return self._merge_states(finished)

    def _merge_states(self, groups: Iterable[flow.FlowStates]) -> flow.FlowStates:
        scopes: dict[flow.FlowOutcome, list[flow.Scope]] = {}
        for states in groups:
            for outcome, scope in states:
                scopes.setdefault(outcome, []).append(scope)
        return tuple(
            (outcome, self._merge_scopes(tuple(scopes[outcome])))
            for outcome in flow.FlowOutcome
            if outcome in scopes
        )

    def _scope_for(
        self,
        states: flow.FlowStates,
        outcomes: Iterable[flow.FlowOutcome],
    ) -> flow.Scope | None:
        wanted = frozenset(outcomes)
        scopes = tuple(scope for outcome, scope in states if outcome in wanted)
        return self._merge_scopes(scopes) if scopes else None

    def _visit_branch(self, initial: flow.Scope, nodes: Iterable[ast.AST]) -> flow.FlowStates:
        self._replace_scope(initial.copy())
        return self._visit_nodes(nodes)

    def _visit_loop_body(
        self,
        node: ast.For | ast.AsyncFor | ast.While,
        initial: flow.Scope,
    ) -> flow.FlowStates:
        self._replace_scope(initial.copy())
        match node:
            case ast.For(target=target) | ast.AsyncFor(target=target):
                self.visit(target)
                self._invalidate_store_names(target)
            case ast.While():
                pass
            case unreachable:
                assert_never(unreachable)
        return self._visit_nodes(node.body)

    def _merge_loop(
        self,
        node: ast.For | ast.AsyncFor | ast.While,
        before: flow.Scope,
        body: flow.FlowStates,
    ) -> flow.FlowStates:
        facts = flow.loop_reachability(node, (outcome for outcome, _ in body))
        propagated: list[flow.FlowStates] = []
        for outcome in (flow.FlowOutcome.RETURN, flow.FlowOutcome.RAISE):
            state = self._scope_for(body, (outcome,))
            if state is not None:
                propagated.append(((outcome, state),))

        normal_exit_scopes: list[flow.Scope] = []
        break_scope = self._scope_for(body, (flow.FlowOutcome.BREAK,))
        if break_scope is not None:
            normal_exit_scopes.append(break_scope)

        completion_scope = self._scope_for(
            body,
            (flow.FlowOutcome.NORMAL, flow.FlowOutcome.CONTINUE),
        )
        if node.orelse and facts.can_complete_without_break:
            else_inputs = tuple(
                scope
                for scope in (
                    before if facts.can_skip_body else None,
                    completion_scope,
                )
                if scope is not None
            )
            else_initial = self._merge_scopes(else_inputs)
            else_states = self._visit_branch(else_initial, node.orelse)
            else_exit = self._scope_for(
                else_states,
                (flow.FlowOutcome.NORMAL, flow.FlowOutcome.BREAK, flow.FlowOutcome.CONTINUE),
            )
            if else_exit is not None:
                normal_exit_scopes.append(else_exit)
            for outcome in (flow.FlowOutcome.RETURN, flow.FlowOutcome.RAISE):
                state = self._scope_for(else_states, (outcome,))
                if state is not None:
                    propagated.append(((outcome, state),))
        elif not node.orelse and facts.can_complete_without_break:
            if facts.can_skip_body:
                normal_exit_scopes.append(before)
            if completion_scope is not None:
                normal_exit_scopes.append(completion_scope)

        if normal_exit_scopes:
            propagated.append(
                ((flow.FlowOutcome.NORMAL, self._merge_scopes(tuple(normal_exit_scopes))),)
            )
        return self._merge_states(propagated)

    def _visit_loop(self, node: ast.For | ast.AsyncFor | ast.While) -> flow.FlowStates:
        match node:
            case ast.For(iter=iter) | ast.AsyncFor(iter=iter):
                self.visit(iter)
            case ast.While(test=test):
                self.visit(test)
            case unreachable:
                assert_never(unreachable)
        before = self._snapshot()
        facts = flow.loop_reachability(node, ())
        body = self._visit_loop_body(node, before) if facts.enters_body else ()
        return self._merge_loop(node, before, body)

    def _merge_if(self, node: ast.If, before: flow.Scope) -> flow.FlowStates:
        condition = flow.constant_condition(node.test)
        if condition is True:
            return self._visit_branch(before, node.body)
        if condition is False:
            return (
                self._visit_branch(before, node.orelse)
                if node.orelse
                else ((flow.FlowOutcome.NORMAL, before),)
            )
        body = self._visit_branch(before, node.body)
        orelse = (
            self._visit_branch(before, node.orelse)
            if node.orelse
            else ((flow.FlowOutcome.NORMAL, before),)
        )
        return self._merge_states((body, orelse))

    def _visit_try(self, node: ast.Try | ast.TryStar) -> flow.FlowStates:
        return visit_try(self, node)

    def _visit_match_case(self, case: ast.match_case, initial: flow.Scope) -> flow.FlowStates:
        self._replace_scope(initial.copy())
        self.visit(case.pattern)
        for name in flow.match_capture_names(case.pattern):
            self._bind(name)
        if case.guard is not None:
            self.visit(case.guard)
            if flow.constant_condition(case.guard) is False:
                return ()
        return self._visit_nodes(case.body)

    def _visit_with(self, node: ast.With | ast.AsyncWith) -> flow.FlowStates:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                self.visit(item.optional_vars)
                self._invalidate_store_names(item.optional_vars)
        return self._visit_nodes(node.body)

    def visit_Module(self, node: ast.Module) -> flow.FlowStates:
        return self._visit_nodes(node.body)

    def visit_For(self, node: ast.For) -> flow.FlowStates:
        return self._visit_loop(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> flow.FlowStates:
        return self._visit_loop(node)

    def visit_While(self, node: ast.While) -> flow.FlowStates:
        return self._visit_loop(node)

    def visit_With(self, node: ast.With) -> flow.FlowStates:
        return self._visit_with(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> flow.FlowStates:
        return self._visit_with(node)

    def visit_If(self, node: ast.If) -> flow.FlowStates:
        self.visit(node.test)
        return self._merge_if(node, self._snapshot())

    def visit_Try(self, node: ast.Try) -> flow.FlowStates:
        return self._visit_try(node)

    def visit_TryStar(self, node: ast.TryStar) -> flow.FlowStates:
        return self._visit_try(node)

    def visit_Match(self, node: ast.Match) -> flow.FlowStates:
        self.visit(node.subject)
        before = self._snapshot()
        states: list[flow.FlowStates] = []
        for case in node.cases:
            state = self._visit_match_case(case, before)
            if state:
                states.append(state)
            if flow.is_irrefutable_case(case):
                break
        else:
            states.append(((flow.FlowOutcome.NORMAL, before),))
        return self._merge_states(states)

    def visit_Return(self, node: ast.Return) -> flow.FlowStates:
        if node.value is not None:
            self.visit(node.value)
        return ((flow.FlowOutcome.RETURN, self._snapshot()),)

    def visit_Raise(self, node: ast.Raise) -> flow.FlowStates:
        if node.exc is not None:
            self.visit(node.exc)
        if node.cause is not None:
            self.visit(node.cause)
        return ((flow.FlowOutcome.RAISE, self._snapshot()),)

    def visit_Break(self, node: ast.Break) -> flow.FlowStates:
        return ((flow.FlowOutcome.BREAK, self._snapshot()),)

    def visit_Continue(self, node: ast.Continue) -> flow.FlowStates:
        return ((flow.FlowOutcome.CONTINUE, self._snapshot()),)
