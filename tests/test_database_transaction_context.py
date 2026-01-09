"""
Tests for database transaction context manager.

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


def test_transaction_context_manager_success(temp_db):
    """Test successful transaction via context manager."""
    with temp_db.transaction():
        temp_db._execute(
            "INSERT INTO projects (id, root_path) VALUES (?, ?)",
            ("context-success", "/context/success"),
        )

    # Verify data was committed
    result = temp_db._fetchone(
        "SELECT id FROM projects WHERE id = ?", ("context-success",)
    )
    assert result is not None
    assert result["id"] == "context-success"


def test_transaction_context_manager_rollback_on_error(temp_db):
    """Test transaction rollback on exception via context manager."""
    with pytest.raises(ValueError):
        with temp_db.transaction():
            temp_db._execute(
                "INSERT INTO projects (id, root_path) VALUES (?, ?)",
                ("context-error", "/context/error"),
            )
            raise ValueError("Test error")

    # Verify data was rolled back
    result = temp_db._fetchone(
        "SELECT id FROM projects WHERE id = ?", ("context-error",)
    )
    assert result is None


def test_transaction_context_manager_nested_error(temp_db):
    """Test transaction context manager with nested exception."""
    try:
        with temp_db.transaction():
            temp_db._execute(
                "INSERT INTO projects (id, root_path) VALUES (?, ?)",
                ("nested-error", "/nested/error"),
            )
            # Simulate nested error
            raise RuntimeError("Nested error")
    except RuntimeError:
        pass

    # Verify data was rolled back
    result = temp_db._fetchone(
        "SELECT id FROM projects WHERE id = ?", ("nested-error",)
    )
    assert result is None


def test_transaction_context_manager_multiple_operations(temp_db):
    """Test transaction context manager with multiple operations."""
    with temp_db.transaction():
        temp_db._execute(
            "INSERT INTO projects (id, root_path) VALUES (?, ?)",
            ("multi-1", "/multi/1"),
        )
        temp_db._execute(
            "INSERT INTO projects (id, root_path) VALUES (?, ?)",
            ("multi-2", "/multi/2"),
        )

    # Verify both were committed
    result1 = temp_db._fetchone("SELECT id FROM projects WHERE id = ?", ("multi-1",))
    result2 = temp_db._fetchone("SELECT id FROM projects WHERE id = ?", ("multi-2",))
    assert result1 is not None
    assert result2 is not None
