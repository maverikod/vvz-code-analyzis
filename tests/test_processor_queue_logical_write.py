"""ProcessorQueueOps DB batch helpers delegate to the database."""

from __future__ import annotations

from unittest.mock import Mock

from code_analysis.core.file_watcher_pkg.processor_queue import ProcessorQueueOps
from code_analysis.core.worker_db_rpc_priority import BACKGROUND_WORKER_DB_RPC_PRIORITY


def test_db_execute_batch_uses_database_execute_batch_when_available() -> None:
    """Verify test db execute batch uses database execute batch when available."""
    db = Mock()
    db.execute_batch = Mock(return_value=[{"affected_rows": 1, "lastrowid": None}])
    q = ProcessorQueueOps(db, watch_dirs_resolved=[])
    ops = [("INSERT INTO files VALUES (?)", ("a",))]
    out = q._db_execute_batch(ops)
    db.execute_batch.assert_called_once_with(
        ops, priority=BACKGROUND_WORKER_DB_RPC_PRIORITY
    )
    assert len(out) == 1
