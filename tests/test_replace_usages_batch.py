"""Tests for batched per-file usage replace (delete + insert, logical write)."""

from __future__ import annotations

import sqlite3
from unittest.mock import Mock

from code_analysis.core.database import entities as entities_mod
from code_analysis.core.usage_tracker import UsageTracker


def _memory_db_with_usages() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE usages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            line INTEGER,
            usage_type TEXT,
            target_type TEXT,
            target_name TEXT,
            target_class TEXT,
            context TEXT
        )
        """
    )
    conn.commit()
    return conn


class _LogicalWriteDbShim:
    """Minimal DB surface for entities.replace_usages_for_file (logical write path)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _in_transaction(self) -> bool:
        return False

    def execute_logical_write_operation(self, program: dict) -> dict:
        batches = program.get("batches") or []
        for batch_ops in batches:
            for sql, params in batch_ops:
                self._conn.execute(sql, tuple(params) if params else ())
        self._conn.commit()
        return {"success": True, "data": {"batch_results": []}}


class _InTxBatchDbShim:
    """execute_batch only; no nested logical write (simulates outer transaction)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.batch_calls: list = []

    def _in_transaction(self) -> bool:
        return True

    def execute_batch(self, operations: list) -> list:
        self.batch_calls.append(operations)
        for sql, params in operations:
            self._conn.execute(sql, tuple(params) if params else ())
        return [{"affected_rows": 1} for _ in operations]

    def execute_logical_write_operation(self, program: dict) -> dict:
        raise AssertionError("nested logical write must not run inside transaction")


def test_replace_usages_for_file_uses_logical_write_when_available() -> None:
    db = Mock()
    db.execute_logical_write_operation = Mock(
        return_value={"success": True, "data": {"batch_results": []}}
    )
    db._in_transaction = lambda: False
    rows = [
        {
            "line": 1,
            "usage_type": "call",
            "target_type": "function",
            "target_name": "foo",
            "target_class": None,
            "context": None,
        }
    ]
    n = entities_mod.replace_usages_for_file(db, 7, rows)
    assert n == 1
    db.execute_logical_write_operation.assert_called_once()
    prog = db.execute_logical_write_operation.call_args[0][0]
    assert len(prog["batches"]) == 2
    assert prog["batches"][0][0][0].startswith("DELETE FROM usages")


def test_replace_usages_for_file_idempotent_on_reindex() -> None:
    """Re-running replace for the same file does not duplicate usage rows."""
    conn = _memory_db_with_usages()
    db = _LogicalWriteDbShim(conn)
    rows = [
        {
            "line": 4,
            "usage_type": "call",
            "target_type": "function",
            "target_name": "foo",
            "target_class": None,
            "context": "function:bar",
        }
    ]
    n1 = entities_mod.replace_usages_for_file(db, 1, rows)
    assert n1 == 1
    c1 = conn.execute("SELECT COUNT(*) FROM usages WHERE file_id = 1").fetchone()[0]
    assert c1 == 1

    n2 = entities_mod.replace_usages_for_file(db, 1, rows)
    assert n2 == 1
    c2 = conn.execute("SELECT COUNT(*) FROM usages WHERE file_id = 1").fetchone()[0]
    assert c2 == 1


def test_replace_usages_for_file_in_transaction_uses_execute_batch_not_nested_logical() -> (
    None
):
    conn = _memory_db_with_usages()
    db = _InTxBatchDbShim(conn)
    entities_mod.replace_usages_for_file(
        db,
        2,
        [
            {
                "line": 1,
                "usage_type": "call",
                "target_type": "function",
                "target_name": "int",
                "target_class": None,
                "context": None,
            }
        ],
    )
    assert len(db.batch_calls) == 1
    assert len(db.batch_calls[0]) == 2
    assert db.batch_calls[0][0][0].startswith("DELETE FROM usages")
    n = conn.execute("SELECT COUNT(*) FROM usages WHERE file_id = 2").fetchone()[0]
    assert n == 1


def test_usage_tracker_no_callback_collects_only() -> None:
    import ast

    tree = ast.parse("def f():\n    len([])\n", filename="c.py")
    ut = UsageTracker()
    ut.visit(tree)
    got = ut.get_usages()
    assert len(got) >= 1


def test_replace_usages_fallback_execute_batch_when_no_logical_write() -> None:
    """Without execute_logical_write_operation, falls back to sequential execute_batch."""
    conn = _memory_db_with_usages()

    class FallbackDb:
        def _in_transaction(self) -> bool:
            return False

        def execute_batch(self, operations: list) -> list:
            for sql, params in operations:
                conn.execute(sql, tuple(params) if params else ())
            conn.commit()
            return [{"affected_rows": 1} for _ in operations]

    db = FallbackDb()
    rows = [
        {
            "line": 1,
            "usage_type": "call",
            "target_type": "function",
            "target_name": "z",
            "target_class": None,
            "context": None,
        }
    ]
    n = entities_mod.replace_usages_for_file(db, 3, rows)
    assert n == 1
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM usages WHERE file_id = 3",
        ).fetchone()[0]
        == 1
    )
