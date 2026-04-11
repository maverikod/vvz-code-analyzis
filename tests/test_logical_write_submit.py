"""Tests for logical_write_submit helpers."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from code_analysis.core.database.logical_write_submit import (
    submit_logical_write_or_fallback,
    submit_logical_write_or_fallback_async,
)


def test_submit_logical_write_uses_execute_logical_when_present() -> None:
    db = Mock()
    db.execute_logical_write_operation = Mock(
        return_value={"success": True, "data": {"batch_results": []}}
    )
    b1 = [("INSERT INTO t VALUES (?)", (1,))]
    b2 = [("UPDATE t SET x=?", (2,))]
    submit_logical_write_or_fallback(db, [b1, b2])
    db.execute_logical_write_operation.assert_called_once()
    prog = db.execute_logical_write_operation.call_args[0][0]
    assert prog["batches"] == [b1, b2]
    db.execute_batch.assert_not_called()


def test_submit_logical_write_fallback_sequential_execute_batch() -> None:
    db = Mock(spec=["execute_batch"])
    db.execute_batch = Mock(
        side_effect=[
            [{"affected_rows": 1}],
            [{"affected_rows": 1}],
        ]
    )
    b1 = [("SQL1", (1,))]
    b2 = [("SQL2", (2,))]
    submit_logical_write_or_fallback(db, [b1, b2])
    assert db.execute_batch.call_count == 2
    db.execute_batch.assert_any_call(b1)
    db.execute_batch.assert_any_call(b2)


@pytest.mark.asyncio
async def test_submit_logical_write_async_uses_logical_when_present() -> None:
    db = Mock()
    db.execute_logical_write_operation = Mock(
        return_value={"success": True, "data": {"batch_results": []}}
    )
    b1 = [("INSERT INTO t VALUES (?)", (1,))]
    await submit_logical_write_or_fallback_async(db, [b1])
    db.execute_logical_write_operation.assert_called_once()
    db.execute_batch.assert_not_called()


@pytest.mark.asyncio
async def test_submit_logical_write_async_fallback_execute_batch() -> None:
    db = Mock(spec=["execute_batch"])
    db.execute_batch = Mock(return_value=[{"affected_rows": 1}])
    b1 = [("SQL1", (1,))]
    await submit_logical_write_or_fallback_async(db, [b1])
    db.execute_batch.assert_called_once_with(b1)


def test_submit_skips_empty_inner_batches() -> None:
    db = Mock()
    db.execute_logical_write_operation = Mock(
        return_value={"success": True, "data": {"batch_results": []}}
    )
    b1 = [("SQL1", (1,))]
    submit_logical_write_or_fallback(db, [b1, []])
    prog = db.execute_logical_write_operation.call_args[0][0]
    assert prog["batches"] == [b1]
