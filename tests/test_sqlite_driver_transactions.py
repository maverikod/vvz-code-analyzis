"""
Tests for SQLite driver transaction support.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import tempfile
import os
from pathlib import Path
import pytest

from code_analysis.core.database.base import CodeDatabase


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    driver_config = {
        "type": "sqlite",
        "config": {"path": str(db_path)},
    }

    # Set environment variable to allow direct SQLite driver
    original_env = os.environ.get("CODE_ANALYSIS_DB_WORKER")
    os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"

    try:
        db = CodeDatabase(driver_config)
        yield db
        db.close()
    finally:
        if original_env is None:
            os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
        else:
            os.environ["CODE_ANALYSIS_DB_WORKER"] = original_env

        if db_path.exists():
            db_path.unlink()


def test_sqlite_transaction_commit(temp_db):
    """Test SQLite transaction commit."""
    temp_db.begin_transaction()

    # Insert data
    temp_db._execute(
        "INSERT INTO projects (id, root_path) VALUES (?, ?)",
        ("commit-test", "/commit/path"),
    )

    # Data should not be visible until commit
    # (In SQLite, uncommitted data is visible within the same connection)
    # But we can test that commit works
    temp_db.commit_transaction()

    # Verify data was committed
    result = temp_db._fetchone("SELECT id FROM projects WHERE id = ?", ("commit-test",))
    assert result is not None
    assert result["id"] == "commit-test"


def test_sqlite_transaction_rollback(temp_db):
    """Test SQLite transaction rollback."""
    # Insert data outside transaction
    temp_db._execute(
        "INSERT INTO projects (id, root_path) VALUES (?, ?)",
        ("before-rollback", "/before/path"),
    )
    temp_db._commit()

    temp_db.begin_transaction()

    # Insert data in transaction
    temp_db._execute(
        "INSERT INTO projects (id, root_path) VALUES (?, ?)",
        ("rollback-test", "/rollback/path"),
    )

    temp_db.rollback_transaction()

    # Verify data was rolled back
    result = temp_db._fetchone(
        "SELECT id FROM projects WHERE id = ?", ("rollback-test",)
    )
    assert result is None

    # Verify data before transaction still exists
    result = temp_db._fetchone(
        "SELECT id FROM projects WHERE id = ?", ("before-rollback",)
    )
    assert result is not None


def test_sqlite_no_autocommit_during_transaction(temp_db):
    """Test that SQLite doesn't auto-commit during transaction."""
    temp_db.begin_transaction()

    # Insert data
    temp_db._execute(
        "INSERT INTO projects (id, root_path) VALUES (?, ?)",
        ("no-autocommit", "/no/autocommit"),
    )

    # Don't commit - just rollback
    temp_db.rollback_transaction()

    # Verify data was not committed
    result = temp_db._fetchone(
        "SELECT id FROM projects WHERE id = ?", ("no-autocommit",)
    )
    assert result is None
