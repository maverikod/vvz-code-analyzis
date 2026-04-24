"""CodeDatabase + database_driver_pkg: transaction_id=local defers commit until driver.commit()."""

import os
from pathlib import Path
from unittest.mock import MagicMock

from code_analysis.core.database.base import LOCAL_DRIVER_TRANSACTION_ID
from code_analysis.core.database_driver_pkg.drivers.sqlite_run import run_execute


def test_sqlite_run_execute_skips_commit_when_transaction_id_local() -> None:
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    cursor.rowcount = 1
    cursor.lastrowid = 0
    cursor.fetchall.return_value = []

    run_execute(conn, "SELECT 1", None, LOCAL_DRIVER_TRANSACTION_ID, None)

    conn.commit.assert_not_called()
    cursor.execute.assert_called()


def test_code_database_begin_transaction_sets_active_before_begin(
    tmp_path: Path,
) -> None:
    os.environ["CODE_ANALYSIS_DB_DRIVER"] = "1"
    try:
        from code_analysis.core.database import CodeDatabase
        from code_analysis.core.database_driver_pkg.driver_factory import create_driver

        db_path = tmp_path / "t.db"
        driver = create_driver("sqlite", {"path": str(db_path)})
        db = CodeDatabase.from_existing_driver(driver)

        db.begin_transaction()
        assert db._transaction_active is True
        db._execute("CREATE TABLE IF NOT EXISTS ttx (id INTEGER PRIMARY KEY, v INTEGER)")
        db._execute("INSERT INTO ttx (v) VALUES (1)")
        db.commit_transaction()

        row = db._fetchone("SELECT COUNT(*) AS c FROM ttx", ())
        assert row is not None and row.get("c") == 1
        driver.disconnect()
    finally:
        os.environ.pop("CODE_ANALYSIS_DB_DRIVER", None)
