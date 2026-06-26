"""Tests for logical_write_submit helpers."""

from __future__ import annotations

from unittest.mock import Mock

from typing import Any

import pytest

from code_analysis.core.database.logical_write_submit import (
    submit_logical_write_or_fallback,
    submit_logical_write_or_fallback_async,
    submit_logical_write_program_or_fallback,
)


def test_submit_logical_write_uses_execute_logical_when_present() -> None:
    """Verify test submit logical write uses execute logical when present."""
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
    """Verify test submit logical write fallback sequential execute batch."""
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
    """Verify test submit logical write async uses logical when present."""
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
    """Verify test submit logical write async fallback execute batch."""
    db = Mock(spec=["execute_batch"])
    db.execute_batch = Mock(return_value=[{"affected_rows": 1}])
    b1 = [("SQL1", (1,))]
    await submit_logical_write_or_fallback_async(db, [b1])
    db.execute_batch.assert_called_once_with(b1)


def test_submit_logical_write_program_or_fallback_uses_full_program() -> None:
    """Verify test submit logical write program or fallback uses full program."""
    calls: list[Any] = []

    class _Db:
        """Represent Db."""

        def execute_logical_write_operation(self, program: dict) -> dict:
            """Return execute logical write operation."""
            calls.append(("lw", program))
            return {"success": True}

        def execute_batch(self, batch: list) -> None:
            """Return execute batch."""
            calls.append(("batch", batch))

    db = _Db()
    program = {
        "batches": [[("DELETE FROM files WHERE id = ?", ("x",))]],
        "operation_name": "test_purge",
        "project_id": "p1",
        "lock_scope": "project_write",
    }
    submit_logical_write_program_or_fallback(db, program)
    assert len(calls) == 1
    assert calls[0][0] == "lw"
    assert calls[0][1]["operation_name"] == "test_purge"


def test_submit_logical_write_program_or_fallback_batches_when_no_lw() -> None:
    """Verify test submit logical write program or fallback batches when no lw."""
    calls: list[Any] = []

    class _Db:
        """Represent Db."""

        def execute_batch(self, batch: list) -> None:
            """Return execute batch."""
            calls.append(batch)

    program = {
        "batches": [[("DELETE FROM files WHERE id = ?", ("x",))]],
        "operation_name": "test_purge",
    }
    submit_logical_write_program_or_fallback(_Db(), program)
    assert len(calls) == 1


def test_submit_skips_empty_inner_batches() -> None:
    """Verify test submit skips empty inner batches."""
    db = Mock()
    db.execute_logical_write_operation = Mock(
        return_value={"success": True, "data": {"batch_results": []}}
    )
    b1 = [("SQL1", (1,))]
    submit_logical_write_or_fallback(db, [b1, []])
    prog = db.execute_logical_write_operation.call_args[0][0]
    assert prog["batches"] == [b1]
