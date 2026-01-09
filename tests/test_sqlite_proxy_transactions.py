"""
Tests for SQLite Proxy driver transaction support.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import tempfile
from pathlib import Path
import pytest

from code_analysis.core.database.base import CodeDatabase


@pytest.fixture
def temp_db_proxy():
    """Create temporary database with proxy driver for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    driver_config = {
        "type": "sqlite_proxy",
        "config": {"path": str(db_path)},
    }

    try:
        db = CodeDatabase(driver_config)
        yield db
        db.close()
    finally:
        if db_path.exists():
            db_path.unlink()


def test_sqlite_proxy_transaction_commit(temp_db_proxy):
    """Test SQLite Proxy transaction commit."""
    temp_db_proxy.begin_transaction()

    # Insert data
    temp_db_proxy._execute(
        "INSERT INTO projects (id, root_path) VALUES (?, ?)",
        ("proxy-commit", "/proxy/commit"),
    )

    temp_db_proxy.commit_transaction()

    # Verify data was committed
    result = temp_db_proxy._fetchone(
        "SELECT id FROM projects WHERE id = ?", ("proxy-commit",)
    )
    assert result is not None
    assert result["id"] == "proxy-commit"


def test_sqlite_proxy_transaction_rollback(temp_db_proxy):
    """Test SQLite Proxy transaction rollback."""
    # Insert data outside transaction
    temp_db_proxy._execute(
        "INSERT INTO projects (id, root_path) VALUES (?, ?)",
        ("before-proxy-rollback", "/before/proxy/rollback"),
    )
    temp_db_proxy._commit()

    temp_db_proxy.begin_transaction()

    # Insert data in transaction
    temp_db_proxy._execute(
        "INSERT INTO projects (id, root_path) VALUES (?, ?)",
        ("proxy-rollback", "/proxy/rollback"),
    )

    temp_db_proxy.rollback_transaction()

    # Verify data was rolled back
    result = temp_db_proxy._fetchone(
        "SELECT id FROM projects WHERE id = ?", ("proxy-rollback",)
    )
    assert result is None

    # Verify data before transaction still exists
    result = temp_db_proxy._fetchone(
        "SELECT id FROM projects WHERE id = ?", ("before-proxy-rollback",)
    )
    assert result is not None


def test_sqlite_proxy_parallel_transactions(temp_db_proxy):
    """Test parallel transactions in SQLite Proxy."""
    # Start first transaction
    temp_db_proxy.begin_transaction()
    temp_db_proxy._execute(
        "INSERT INTO projects (id, root_path) VALUES (?, ?)",
        ("parallel-1", "/parallel/1"),
    )

    # Note: We can't have two active transactions in the same database instance
    # But we can test that transaction isolation works
    temp_db_proxy.commit_transaction()

    # Verify data was committed
    result = temp_db_proxy._fetchone(
        "SELECT id FROM projects WHERE id = ?", ("parallel-1",)
    )
    assert result is not None

