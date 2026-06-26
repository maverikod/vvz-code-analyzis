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
    """Represent PgDatabase."""

    _driver_type = "postgres"


def test_build_watcher_bulk_sync_program_three_batches() -> None:
    """Verify test build watcher bulk sync program three batches."""
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


def test_disk_raw_inserts_use_boolean_has_docstring() -> None:
    """Verify test disk raw inserts use boolean has docstring."""
    db = _PgDatabase()
    rows = [
        WatcherDiskFileRow(
            relative_path="src/a.py",
            last_modified=100.0,
            lines=10,
            has_docstring=True,
            tree_checksum="abc",
        ),
        WatcherDiskFileRow(
            relative_path="src/b.py",
            last_modified=101.0,
            lines=5,
            has_docstring=False,
            tree_checksum="def",
        ),
    ]
    program = build_watcher_bulk_sync_program("proj-1", "wd-1", rows, db)
    insert_ops = [
        params
        for sql, params in program["batches"][0]
        if f"INSERT INTO {TEMP_DISK_RAW}" in sql
    ]
    assert len(insert_ops) == 1
    bound = insert_ops[0]
    assert bound[3] is True and isinstance(bound[3], bool)
    assert bound[8] is False and isinstance(bound[8], bool)


def test_build_watcher_bulk_sync_requires_postgres() -> None:
    """Verify test build watcher bulk sync requires postgres."""
    db = SimpleNamespace(_driver_type="sqlite")
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        build_watcher_bulk_sync_program("p", None, [], db)


def test_build_watcher_bulk_sync_avoids_full_outer_join() -> None:
    """Verify test build watcher bulk sync avoids full outer join."""
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
    batch_b = program["batches"][1]
    sync_sql = next(
        sql for sql, _ in batch_b if f"CREATE TEMP TABLE {TEMP_SYNC}" in sql
    )
    upper = sync_sql.upper()
    assert "FULL OUTER JOIN" not in upper
    assert "FULL JOIN" not in upper
    assert "LEFT JOIN" in upper
    assert "UNION ALL" in upper
    assert "NOT EXISTS" in upper
