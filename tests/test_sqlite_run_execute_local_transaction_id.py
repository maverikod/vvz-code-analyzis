"""sqlite_run.execute with ``transaction_id='local'`` skips per-statement commit.

Covers defer-commit semantics used when a facade marks an active transaction
with :data:`~code_analysis.core.database.base.LOCAL_DRIVER_TRANSACTION_ID`.
End-to-end :class:`~code_analysis.core.database_client.client.DatabaseClient`
transaction persistence is exercised in ``test_database_transactions`` and
``test_sqlite_driver_transactions``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

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
