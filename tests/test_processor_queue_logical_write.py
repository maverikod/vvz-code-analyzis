"""ProcessorQueueOps uses one logical write when the DB supports it."""

from __future__ import annotations

from unittest.mock import Mock

from code_analysis.core.file_watcher_pkg.processor_queue import ProcessorQueueOps


def test_db_submit_logical_write_prefers_execute_logical() -> None:
    db = Mock()
    db.execute_logical_write_operation = Mock(
        return_value={"success": True, "data": {"batch_results": []}}
    )
    q = ProcessorQueueOps(db, watch_dirs_resolved=[])
    b1 = [("INSERT INTO files VALUES (?)", ("a",))]
    b2 = [("UPDATE files SET x=1 WHERE path=?", ("a",))]
    q._db_submit_logical_write([b1, b2])
    db.execute_logical_write_operation.assert_called_once()
    assert db.execute_logical_write_operation.call_args[0][0]["batches"] == [b1, b2]
