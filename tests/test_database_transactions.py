"""
Tests for database transaction support.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import tempfile
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
    import os

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


def test_begin_transaction(temp_db):
    """Test beginning a transaction."""
    assert not temp_db._in_transaction()
    temp_db.begin_transaction()
    assert temp_db._in_transaction()


def test_commit_transaction(temp_db):
    """Test committing a transaction."""
    temp_db.begin_transaction()
    assert temp_db._in_transaction()

    # Insert test data
    temp_db._execute(
        "INSERT INTO projects (id, root_path) VALUES (?, ?)", ("test-id", "/test/path")
    )

    temp_db.commit_transaction()
    assert not temp_db._in_transaction()

    # Verify data was committed
    result = temp_db._fetchone("SELECT id FROM projects WHERE id = ?", ("test-id",))
    assert result is not None
    assert result["id"] == "test-id"


def test_rollback_transaction(temp_db):
    """Test rolling back a transaction."""
    temp_db.begin_transaction()
    assert temp_db._in_transaction()

    # Insert test data
    temp_db._execute(
        "INSERT INTO projects (id, root_path) VALUES (?, ?)",
        ("rollback-id", "/rollback/path"),
    )

    temp_db.rollback_transaction()
    assert not temp_db._in_transaction()

    # Verify data was rolled back
    result = temp_db._fetchone("SELECT id FROM projects WHERE id = ?", ("rollback-id",))
    assert result is None


def test_nested_transactions(temp_db):
    """Test that nested transactions raise an error."""
    temp_db.begin_transaction()
    assert temp_db._in_transaction()

    with pytest.raises(RuntimeError, match="Transaction already active"):
        temp_db.begin_transaction()


def test_commit_without_transaction(temp_db):
    """Test that committing without active transaction raises an error."""
    assert not temp_db._in_transaction()

    with pytest.raises(RuntimeError, match="No active transaction"):
        temp_db.commit_transaction()


def test_rollback_without_transaction(temp_db):
    """Test that rolling back without active transaction raises an error."""
    assert not temp_db._in_transaction()

    with pytest.raises(RuntimeError, match="No active transaction"):
        temp_db.rollback_transaction()


def test_transaction_isolation(temp_db):
    """Test that transactions provide isolation."""
    # Insert data outside transaction
    temp_db._execute(
        "INSERT INTO projects (id, root_path) VALUES (?, ?)",
        ("outside-id", "/outside/path"),
    )
    temp_db._commit()

    # Start transaction and insert more data
    temp_db.begin_transaction()
    temp_db._execute(
        "INSERT INTO projects (id, root_path) VALUES (?, ?)",
        ("inside-id", "/inside/path"),
    )

    # Data inside transaction should be visible
    inside_result = temp_db._fetchone(
        "SELECT id FROM projects WHERE id = ?", ("inside-id",)
    )
    assert inside_result is not None

    # Rollback transaction
    temp_db.rollback_transaction()

    # Data inside transaction should be gone
    inside_result = temp_db._fetchone(
        "SELECT id FROM projects WHERE id = ?", ("inside-id",)
    )
    assert inside_result is None

    # Data outside transaction should still be there
    outside_result = temp_db._fetchone(
        "SELECT id FROM projects WHERE id = ?", ("outside-id",)
    )
    assert outside_result is not None


def test_in_transaction(temp_db):
    """Test _in_transaction() method."""
    assert not temp_db._in_transaction()

    temp_db.begin_transaction()
    assert temp_db._in_transaction()

    temp_db.commit_transaction()
    assert not temp_db._in_transaction()

    temp_db.begin_transaction()
    assert temp_db._in_transaction()

    temp_db.rollback_transaction()
    assert not temp_db._in_transaction()
