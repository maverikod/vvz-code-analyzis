"""
Edge case tests for SQLite transactions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import tempfile
from pathlib import Path

from code_analysis.core.database_driver_pkg.drivers.sqlite_transactions import (
    SQLiteTransactionManager,
)
from code_analysis.core.database_driver_pkg.exceptions import TransactionError


@pytest.fixture
def temp_db_path(tmp_path):
    """Create temporary database path."""
    return tmp_path / "test.db"


@pytest.fixture
def transaction_manager(temp_db_path):
    """Create transaction manager instance."""
    return SQLiteTransactionManager(temp_db_path)


class TestSQLiteTransactionManager:
    """Test SQLite transaction manager."""

    def test_begin_transaction(self, transaction_manager):
        """Test beginning transaction."""
        transaction_id = transaction_manager.begin_transaction()
        assert transaction_id is not None
        assert isinstance(transaction_id, str)

    def test_commit_transaction(self, transaction_manager):
        """Test committing transaction."""
        transaction_id = transaction_manager.begin_transaction()
        result = transaction_manager.commit_transaction(transaction_id)
        assert result is True

    def test_rollback_transaction(self, transaction_manager):
        """Test rolling back transaction."""
        transaction_id = transaction_manager.begin_transaction()
        result = transaction_manager.rollback_transaction(transaction_id)
        assert result is True

    def test_commit_nonexistent_transaction(self, transaction_manager):
        """Test committing non-existent transaction."""
        with pytest.raises(TransactionError, match="not found"):
            transaction_manager.commit_transaction("nonexistent")

    def test_rollback_nonexistent_transaction(self, transaction_manager):
        """Test rolling back non-existent transaction."""
        with pytest.raises(TransactionError, match="not found"):
            transaction_manager.rollback_transaction("nonexistent")

    def test_close_all(self, transaction_manager):
        """Test closing all transactions."""
        transaction_id1 = transaction_manager.begin_transaction()
        transaction_id2 = transaction_manager.begin_transaction()

        transaction_manager.close_all()
        # Transactions should be closed
        with pytest.raises(TransactionError):
            transaction_manager.commit_transaction(transaction_id1)
