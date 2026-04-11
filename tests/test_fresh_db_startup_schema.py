"""
Fresh DB: skip driver migrations before base tables; catalog probe without noisy SELECT.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from code_analysis.commands.base_mcp_command_open_db import _sqlite_master_has_table
from code_analysis.core.database_driver_pkg.drivers.sqlite_migrations import (
    _sqlite_table_exists,
    run_all_ensure,
)
from code_analysis.core.database_driver_pkg.drivers.sqlite_schema import (
    SQLiteSchemaManager,
)
from code_analysis.core.database.schema_creation_migrate import run_migrate_schema


def test_sqlite_table_exists_false_on_empty_db() -> None:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "e.db"
        conn = sqlite3.connect(str(p))
        try:
            assert _sqlite_table_exists(conn, "projects") is False
        finally:
            conn.close()


def test_run_all_ensure_noop_when_no_projects_table() -> None:
    """Must not create side tables or run ALTERs on a completely empty file."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "e.db"
        conn = sqlite3.connect(str(p))
        conn.row_factory = sqlite3.Row
        try:
            sm = SQLiteSchemaManager(conn)
            run_all_ensure(conn, sm, p)
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
            names = [r[0] for r in cur.fetchall()]
            assert "projects" not in names
            assert "indexing_errors" not in names
        finally:
            conn.close()


def test_run_migrate_schema_noop_when_no_projects() -> None:
    db = MagicMock()
    db._fetchone.return_value = None
    db._get_table_info = MagicMock()
    run_migrate_schema(db)
    db._get_table_info.assert_not_called()


def test_sqlite_master_has_table_uses_execute_data_shape() -> None:
    db = MagicMock()
    db.execute.return_value = {"data": [{"ok": 1}]}
    assert _sqlite_master_has_table(db, "projects") is True
    db.execute.return_value = {"data": []}
    assert _sqlite_master_has_table(db, "projects") is False
