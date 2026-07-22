"""ProcessorQueueOps DB batch helpers delegate to the database.

Regression coverage: the driver-direct ``execute``/``execute_batch`` signatures
(``code_analysis.core.database_driver_pkg.drivers.base``) do NOT accept a
``priority`` keyword (that was a ``DatabaseClient`` RPC-era param, deleted in
stage 2). A permissive ``Mock()`` here would silently swallow a stray
``priority=`` kwarg and never catch the regression, so this test uses a
signature-strict stub instead (no ``**kwargs``, exact base-driver signature).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from code_analysis.core.file_watcher_pkg.processor_queue import ProcessorQueueOps


class _StrictDriverStub:
    """Minimal stand-in with EXACTLY the base-driver ``execute_batch`` signature."""

    def __init__(self) -> None:
        """Initialize the instance."""
        self.calls: List[Tuple[List[Tuple[str, Optional[tuple]]], Optional[str]]] = []

    def execute_batch(
        self,
        operations: List[Tuple[str, Optional[tuple]]],
        transaction_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Record the call and return a fixed batch result."""
        self.calls.append((operations, transaction_id))
        return [{"affected_rows": 1, "lastrowid": None}]


def test_db_execute_batch_uses_database_execute_batch_when_available() -> None:
    """Verify test db execute batch uses database execute batch when available."""
    db = _StrictDriverStub()
    q = ProcessorQueueOps(db, watch_dirs_resolved=[])
    ops = [("INSERT INTO files VALUES (?)", ("a",))]
    out = q._db_execute_batch(ops)
    assert db.calls == [(ops, None)]
    assert len(out) == 1
