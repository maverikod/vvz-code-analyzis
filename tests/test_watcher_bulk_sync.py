"""
Tests for watcher bulk sync program builder.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from code_analysis.core.file_watcher_pkg.watcher_bulk_sync import (
    TEMP_DISK_RAW,
    TEMP_SYNC,
    build_watcher_bulk_sync_program,
)
from code_analysis.core.file_watcher_pkg.watcher_disk_manifest import WatcherDiskFileRow


class _PgDatabase:
    _driver_type = "postgres"


def test_build_watcher_bulk_sync_program_three_batches() -> None:
    db = _PgDatabase()
    rows = [
        WatcherDiskFileRow(
            relative_path="src/a.py",
            last_modified=100.0,
            lines=10,
            has_docstring=True,
            tree_checksum="abc",
        )
    ]
    program = build_watcher_bulk_sync_program("proj-1", "wd-1", rows, db)
    assert program["operation_name"] == "watcher_bulk_project_sync"
    assert program["project_id"] == "proj-1"
    assert len(program["batches"]) == 3
    batch_a, batch_b, batch_c = program["batches"]
    assert any(TEMP_DISK_RAW in sql for sql, _ in batch_a)
    assert any(f"CREATE INDEX idx_watcher_disk_raw_path" in sql for sql, _ in batch_a)
    assert any(f"CREATE TEMP TABLE {TEMP_SYNC}" in sql for sql, _ in batch_b)
    assert any("idx_watcher_sync_action" in sql for sql, _ in batch_b)
    assert (
        len([1 for sql, _ in batch_c if sql.strip().upper().startswith("INSERT")]) >= 1
    )
    assert (
        len([1 for sql, _ in batch_c if sql.strip().upper().startswith("UPDATE")]) >= 1
    )
    assert any("DELETE FROM files" in sql for sql, _ in batch_c)


def test_build_watcher_bulk_sync_requires_postgres() -> None:
    db = SimpleNamespace(_driver_type="sqlite")
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        build_watcher_bulk_sync_program("p", None, [], db)
