"""Behavioral contracts for the sandbox boundary."""

import inspect

from panopticon.sandbox.base import Container, ExecResult, StreamResult


def test_stream_result_is_bounded_value() -> None:
    result = StreamResult(b"abc", truncated=True)
    assert result.data == b"abc"
    assert result.truncated


def test_container_exposes_lifecycle_and_archive_operations() -> None:
    required = {
        "exec",
        "logs",
        "copy_in",
        "copy_out",
        "inspect",
        "trace",
        "wait",
        "terminate",
        "kill",
        "rm",
    }
    assert required <= set(Container.__dict__)
    assert inspect.isclass(ExecResult)
