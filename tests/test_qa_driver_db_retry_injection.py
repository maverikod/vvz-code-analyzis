"""Driver-level QA synthetic transient injection (SQLite file DB)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from code_analysis.core.database_driver_pkg.driver_factory import create_driver


def test_sqlite_qa_inject_emits_db_retry_on_retry(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    p = tmp_path / "db.sqlite"
    d = create_driver("sqlite", {"path": str(p)})
    try:
        d.execute(
            "CREATE TABLE IF NOT EXISTS _qa_inj(x INTEGER)",
            None,
            transaction_id=None,
        )
        d.qa_set_db_retry_injections(1)
        with caplog.at_level(
            logging.INFO,
            logger="code_analysis.core.database_driver_pkg.drivers.sqlite",
        ):
            d.execute("INSERT INTO _qa_inj VALUES (1)", None, transaction_id=None)
        assert "[DB_RETRY]" in caplog.text
    finally:
        d.disconnect()
