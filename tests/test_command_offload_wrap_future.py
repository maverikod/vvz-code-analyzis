"""
Regression tests for command_offload's asyncio.wrap_future bridge.

Bug 4d1a2895 / mechanism card 8e6acb34: ``_await_concurrent_future`` used to
poll the worker-thread future every 10ms (``asyncio.sleep(0.01)``) instead of
the ``asyncio.wrap_future`` the module docstring already claimed -- drift
between doc and code, and needless extra loop wakeups under concurrent load.
These tests pin the corrected behavior: real result/exception propagation,
and that the bridge actually delegates to ``asyncio.wrap_future``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio

import pytest

from code_analysis.core import command_offload


def test_await_concurrent_future_propagates_result() -> None:
    """A worker's return value is delivered back through the bridge."""

    async def main() -> None:
        pool = command_offload._get_pool()
        future = pool.submit(lambda: 42)
        result = await command_offload._await_concurrent_future(future)
        assert result == 42

    try:
        asyncio.run(main())
    finally:
        command_offload.shutdown()


def test_await_concurrent_future_propagates_exception() -> None:
    """A worker's exception is re-raised, not swallowed, through the bridge."""

    def boom() -> None:
        raise ValueError("worker exploded")

    async def main() -> None:
        pool = command_offload._get_pool()
        future = pool.submit(boom)
        with pytest.raises(ValueError, match="worker exploded"):
            await command_offload._await_concurrent_future(future)

    try:
        asyncio.run(main())
    finally:
        command_offload.shutdown()


def test_await_concurrent_future_delegates_to_wrap_future(monkeypatch) -> None:
    """The bridge calls asyncio.wrap_future rather than polling on a timer."""
    calls: list[object] = []
    real_wrap_future = asyncio.wrap_future

    def spy_wrap_future(future, *, loop=None):
        calls.append(future)
        return real_wrap_future(future, loop=loop)

    monkeypatch.setattr(command_offload.asyncio, "wrap_future", spy_wrap_future)

    async def main() -> None:
        pool = command_offload._get_pool()
        future = pool.submit(lambda: "ok")
        result = await command_offload._await_concurrent_future(future)
        assert result == "ok"

    try:
        asyncio.run(main())
    finally:
        command_offload.shutdown()

    assert len(calls) == 1
