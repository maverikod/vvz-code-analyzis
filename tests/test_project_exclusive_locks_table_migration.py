"""
Unit tests for the ``project_exclusive_locks`` table migration (bugs 88f06abc,
5da73265), precedent-matched to ``test_files_content_stale_column_migration.py``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from code_analysis.core.database.migrations.project_exclusive_locks_table import (
    migrate_project_exclusive_locks_table,
)


class _FakeDb:
    """Minimal db-like stub matching the migration module's driver surface."""

    def __init__(self, *, raise_on_execute: bool = False) -> None:
        """Initialize the instance.

        Args:
            raise_on_execute: When True, ``_execute`` raises instead of
                recording the statement, to exercise the try/except-and-log
                error path.
        """
        self._raise_on_execute = raise_on_execute
        self.executed: List[str] = []
        self.committed = 0

    def _execute(self, sql: str, params: Optional[tuple] = None) -> None:
        """Return execute."""
        if self._raise_on_execute:
            raise RuntimeError("boom")
        self.executed.append(sql)

    def _commit(self) -> None:
        """Return commit."""
        self.committed += 1

    def _fetchone(self, sql: str, params: Optional[tuple] = None) -> Any:
        """Return fetchone (unused by this migration; kept for surface parity)."""
        return None

    def _get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """Return get table info (unused by this migration; surface parity only)."""
        return []


def test_migrate_creates_table_with_all_four_columns() -> None:
    """A single CREATE TABLE IF NOT EXISTS statement with all 4 columns runs."""
    db = _FakeDb()

    migrate_project_exclusive_locks_table(db)

    assert len(db.executed) == 1
    sql = db.executed[0]
    assert "CREATE TABLE IF NOT EXISTS project_exclusive_locks" in sql
    assert "project_id TEXT PRIMARY KEY" in sql
    assert "locked_at REAL NOT NULL" in sql
    assert "owner TEXT NOT NULL" in sql
    assert "reason TEXT" in sql
    assert db.committed == 1


def test_migrate_is_idempotent_by_sql_not_by_guard() -> None:
    """Calling twice does not raise; each call re-issues CREATE TABLE IF NOT EXISTS."""
    db = _FakeDb()

    migrate_project_exclusive_locks_table(db)
    migrate_project_exclusive_locks_table(db)

    assert len(db.executed) == 2
    assert all("CREATE TABLE IF NOT EXISTS project_exclusive_locks" in s for s in db.executed)


def test_migrate_swallows_execute_error() -> None:
    """An _execute failure is caught and logged, never propagated."""
    db = _FakeDb(raise_on_execute=True)

    migrate_project_exclusive_locks_table(db)  # must not raise

    assert db.executed == []
    assert db.committed == 0
