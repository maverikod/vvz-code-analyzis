"""
Helpers to submit logical write programs with execute_batch fallback.

When ``database.execute_logical_write_operation`` exists, uses one composite
operation (one RPC / one transaction on the driver). Otherwise runs each inner
batch via ``execute_batch`` in order (legacy behavior).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
from typing import Any, List, Sequence, Tuple, cast

from .logical_write_program import LogicalWriteProgramV1, SqlParamPair


def _non_empty_batches(
    batches: Sequence[Sequence[Tuple[str, Any]]],
) -> List[List[SqlParamPair]]:
    return [cast(List[SqlParamPair], list(b)) for b in batches if b]


def submit_logical_write_or_fallback(
    database: Any,
    batches: Sequence[Sequence[Tuple[str, Any]]],
) -> Any:
    """
    Run ``execute_logical_write_operation`` when available; else sequential ``execute_batch``.

    Inner batches are preserved (ordering). Empty inner batches are skipped.
    """
    inner = _non_empty_batches(batches)
    if not inner:
        return None
    lw = getattr(database, "execute_logical_write_operation", None)
    if callable(lw):
        program: LogicalWriteProgramV1 = {"batches": inner}
        return lw(program)
    last: Any = None
    for batch_ops in inner:
        last = database.execute_batch(batch_ops)
    return last


async def submit_logical_write_or_fallback_async(
    database: Any,
    batches: Sequence[Sequence[Tuple[str, Any]]],
) -> Any:
    """Async variant for callers that already use ``asyncio.to_thread`` around DB writes."""
    inner = _non_empty_batches(batches)
    if not inner:
        return None
    lw = getattr(database, "execute_logical_write_operation", None)
    if callable(lw):
        program: LogicalWriteProgramV1 = {"batches": inner}
        if asyncio.iscoroutinefunction(lw):
            return await lw(program)
        return await asyncio.to_thread(lw, program)
    execute_batch = database.execute_batch
    last: Any = None
    for batch_ops in inner:
        if asyncio.iscoroutinefunction(execute_batch):
            last = await execute_batch(batch_ops)
        else:
            last = await asyncio.to_thread(execute_batch, batch_ops)
    return last
