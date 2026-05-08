"""
Ensure database_driver_pkg SQLite connect runs schema_creation_migrate (deleted columns).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

import pytest

from code_analysis.core.database.schema_creation_create import run_create_schema


class _RawSqliteSchemaAdapter:
    """Minimal DB surface (execute/fetch/get_table_info) for run_create_schema + migrations."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._c = conn
        self._c.row_factory = sqlite3.Row

    def _execute(self, sql: str, params: Any = None) -> None:
        if params is not None and params != ():
            self._c.execute(sql, params)
        else:
            self._c.execute(sql)

    def _commit(self) -> None:
        self._c.commit()

    def _get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        cur = self._c.cursor()
        cur.execute(f"PRAGMA table_info({table_name})")
        rows = cur.fetchall()
        cur.close()
        return [{"name": r[1], "type": r[2]} for r in rows]

    def _fetchone(self, sql: str, params: Any = None) -> Optional[Dict[str, Any]]:
        cur = self._c.cursor()
        if params is not None and params != ():
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        row = cur.fetchone()
        cur.close()
        if row is None:
            return None
        return dict(row)

    def _fetchall(self, sql: str, params: Any = None) -> List[Dict[str, Any]]:
        cur = self._c.cursor()
        if params is not None and params != ():
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]


@pytest.mark.skipif(
    sqlite3.sqlite_version_info < (3, 35, 0),
    reason="ALTER TABLE DROP COLUMN requires SQLite 3.35+",
)
def test_sqlite_driver_connect_restores_deleted_columns_after_drop(tmp_path) -> None:
    """Old DBs without soft-delete columns get them on driver connect (run_all_ensure)."""
    db_path = tmp_path / "m.db"
    conn = sqlite3.connect(str(db_path))
    try:
        run_create_schema(_RawSqliteSchemaAdapter(conn))
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path))
    try:
        # Indexes reference deleted; drop them before DROP COLUMN (SQLite 3.35+).
        conn.execute("DROP INDEX IF EXISTS idx_files_deleted")
        conn.execute("DROP INDEX IF EXISTS idx_files_deleted_project_id")
        conn.execute("DROP INDEX IF EXISTS idx_files_needs_indexing")
        conn.execute("DROP INDEX IF EXISTS idx_projects_deleted")
        conn.execute("ALTER TABLE files DROP COLUMN deleted")
        conn.execute("ALTER TABLE projects DROP COLUMN deleted")
        conn.commit()
    finally:
        conn.close()

    from code_analysis.core.database_driver_pkg.driver_factory import create_driver

    driver = create_driver("sqlite", {"path": str(db_path)})
    try:
        files_cols = {r["name"] for r in driver.get_table_info("files")}
        proj_cols = {r["name"] for r in driver.get_table_info("projects")}
        assert "deleted" in files_cols
        assert "deleted" in proj_cols
    finally:
        driver.disconnect()
