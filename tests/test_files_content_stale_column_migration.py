"""
Unit tests for the ``files.content_stale`` / ``content_stale_since`` additive
migration (bug 56c23bd9), precedent-matched to ``watch_dirs_deleted_column``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from code_analysis.core.database.migrations.files_content_stale_column import (
    migrate_files_content_stale_column,
)


class _FakeDb:
    """Minimal db-like stub matching the migration module's driver surface."""

    def __init__(
        self,
        *,
        driver_type: str = "postgres",
        existing_columns: Optional[List[str]] = None,
        settings_has_key: bool = False,
    ) -> None:
        self._driver_type = driver_type
        self._existing_columns = list(existing_columns or [])
        self._settings_has_key = settings_has_key
        self.executed: List[str] = []

    def _execute(self, sql: str, params: Optional[tuple] = None) -> None:
        self.executed.append(sql)
        if "ADD COLUMN content_stale_since" in sql:
            self._existing_columns.append("content_stale_since")
        elif "ADD COLUMN content_stale" in sql:
            self._existing_columns.append("content_stale")
        elif sql.strip().startswith("INSERT INTO db_settings"):
            self._settings_has_key = True

    def _commit(self) -> None:
        return None

    def _fetchone(self, sql: str, params: Optional[tuple] = None) -> Any:
        if self._settings_has_key:
            return {"1": 1}
        return None

    def _get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        return [{"name": name} for name in self._existing_columns]


def test_migrate_adds_both_columns_when_absent() -> None:
    """Fresh files table (no columns) -> both ADD COLUMN statements run."""
    db = _FakeDb(existing_columns=[])

    migrate_files_content_stale_column(db)

    assert any("ADD COLUMN content_stale BOOLEAN" in s for s in db.executed)
    assert any("ADD COLUMN content_stale_since REAL" in s for s in db.executed)
    assert "content_stale" in db._existing_columns
    assert "content_stale_since" in db._existing_columns


def test_migrate_postgres_uses_false_default() -> None:
    """PostgreSQL driver -> DEFAULT FALSE (not the SQLite-style 0 literal)."""
    db = _FakeDb(driver_type="postgres", existing_columns=[])

    migrate_files_content_stale_column(db)

    add_col_sql = next(s for s in db.executed if "ADD COLUMN content_stale BOOLEAN" in s)
    assert "DEFAULT FALSE" in add_col_sql


def test_migrate_is_a_noop_when_columns_already_present_and_marked_done() -> None:
    """Idempotency guard: marked-done + both columns present -> no ALTER TABLE calls."""
    db = _FakeDb(
        existing_columns=["content_stale", "content_stale_since"],
        settings_has_key=True,
    )

    migrate_files_content_stale_column(db)

    assert db.executed == []


def test_migrate_skips_column_already_present_individually() -> None:
    """Only content_stale_since missing -> only that ADD COLUMN runs."""
    db = _FakeDb(existing_columns=["content_stale"], settings_has_key=False)

    migrate_files_content_stale_column(db)

    assert not any("ADD COLUMN content_stale BOOLEAN" in s for s in db.executed)
    assert any("ADD COLUMN content_stale_since REAL" in s for s in db.executed)
