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
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple, cast

from .logical_write_program import LogicalWriteProgramV1, SqlParamPair

logger = logging.getLogger(__name__)


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


def execute_all_batches_in_transaction(
    database: Any,
    batches: List[List[Tuple[str, Any]]],
    transaction_id: str,
    *,
    file_path: str,
    file_id: Any,
) -> Optional[Dict[str, Any]]:
    """
    Run batch groups on an existing transaction connection (caller-owned tx).

    Used when an outer scope already called ``begin_transaction`` and holds
    ``files.editing_pid`` on the same connection (e.g. restore backup, compose CST).

    Returns:
        None on success, or an error-shaped dict on the first batch failure.
    """
    try:
        for batch_ops in batches:
            database.execute_batch(batch_ops, transaction_id=transaction_id)
    except Exception as e:
        logger.exception("execute_batch failed for %s", file_path)
        return {
            "success": False,
            "error": str(e),
            "file_path": file_path,
            "file_id": file_id,
        }
    return None


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


def submit_logical_write_program_or_fallback(
    database: Any,
    program: LogicalWriteProgramV1,
) -> Any:
    """
    Submit a full logical-write program, or run its batches via ``execute_batch``.

    Preserves ``operation_name``, ``project_id``, and ``lock_scope`` when the client
    supports ``execute_logical_write_operation``.
    """
    batches = program.get("batches") or []
    inner = _non_empty_batches(batches)
    if not inner:
        return None
    lw = getattr(database, "execute_logical_write_operation", None)
    if callable(lw):
        return lw(program)
    return submit_logical_write_or_fallback(database, inner)
