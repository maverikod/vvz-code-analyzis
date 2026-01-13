"""
Tests for RPC handlers.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
from unittest.mock import Mock, MagicMock

from code_analysis.core.database_driver_pkg.rpc_handlers import RPCHandlers
from code_analysis.core.database_driver_pkg.drivers.base import BaseDatabaseDriver


@pytest.fixture
def mock_driver():
    """Create mock driver."""
    driver = Mock(spec=BaseDatabaseDriver)
    return driver


@pytest.fixture
def handlers(mock_driver):
    """Create RPC handlers instance."""
    return RPCHandlers(mock_driver)


class TestRPCHandlersTableOperations:
    """Test RPC handlers for table operations."""

    def test_handle_create_table(self, handlers, mock_driver):
        """Test create_table handler."""
        mock_driver.create_table.return_value = True
        params = {
            "schema": {
                "name": "users",
                "columns": [{"name": "id", "type": "INTEGER"}],
            }
        }
        result = handlers.handle_create_table(params)
        assert result == {"success": True}
        mock_driver.create_table.assert_called_once()

    def test_handle_create_table_missing_schema(self, handlers):
        """Test create_table with missing schema."""
        with pytest.raises(ValueError, match="schema"):
            handlers.handle_create_table({})

    def test_handle_drop_table(self, handlers, mock_driver):
        """Test drop_table handler."""
        mock_driver.drop_table.return_value = True
        params = {"table_name": "users"}
        result = handlers.handle_drop_table(params)
        assert result == {"success": True}
        mock_driver.drop_table.assert_called_once_with("users")

    def test_handle_drop_table_missing_name(self, handlers):
        """Test drop_table with missing table_name."""
        with pytest.raises(ValueError, match="table_name"):
            handlers.handle_drop_table({})


class TestRPCHandlersCRUD:
    """Test RPC handlers for CRUD operations."""

    def test_handle_insert(self, handlers, mock_driver):
        """Test insert handler."""
        mock_driver.insert.return_value = 123
        params = {"table_name": "users", "data": {"name": "John"}}
        result = handlers.handle_insert(params)
        assert result == {"row_id": 123}
        mock_driver.insert.assert_called_once_with("users", {"name": "John"})

    def test_handle_insert_missing_params(self, handlers):
        """Test insert with missing parameters."""
        with pytest.raises(ValueError):
            handlers.handle_insert({"table_name": "users"})
        with pytest.raises(ValueError):
            handlers.handle_insert({"data": {"name": "John"}})

    def test_handle_update(self, handlers, mock_driver):
        """Test update handler."""
        mock_driver.update.return_value = 1
        params = {
            "table_name": "users",
            "where": {"id": 1},
            "data": {"name": "Jane"},
        }
        result = handlers.handle_update(params)
        assert result == {"affected_rows": 1}
        mock_driver.update.assert_called_once_with(
            "users", {"id": 1}, {"name": "Jane"}
        )

    def test_handle_delete(self, handlers, mock_driver):
        """Test delete handler."""
        mock_driver.delete.return_value = 1
        params = {"table_name": "users", "where": {"id": 1}}
        result = handlers.handle_delete(params)
        assert result == {"affected_rows": 1}
        mock_driver.delete.assert_called_once_with("users", {"id": 1})

    def test_handle_select(self, handlers, mock_driver):
        """Test select handler."""
        mock_driver.select.return_value = [{"id": 1, "name": "John"}]
        params = {
            "table_name": "users",
            "where": {"id": 1},
            "columns": ["id", "name"],
            "limit": 10,
            "offset": 0,
            "order_by": ["id"],
        }
        result = handlers.handle_select(params)
        assert result == {"data": [{"id": 1, "name": "John"}]}
        mock_driver.select.assert_called_once_with(
            "users", {"id": 1}, ["id", "name"], 10, 0, ["id"]
        )

    def test_handle_select_minimal(self, handlers, mock_driver):
        """Test select with minimal parameters."""
        mock_driver.select.return_value = []
        params = {"table_name": "users"}
        result = handlers.handle_select(params)
        assert result == {"data": []}
        mock_driver.select.assert_called_once_with(
            "users", None, None, None, None, None
        )


class TestRPCHandlersTransactions:
    """Test RPC handlers for transactions."""

    def test_handle_begin_transaction(self, handlers, mock_driver):
        """Test begin_transaction handler."""
        mock_driver.begin_transaction.return_value = "trans_123"
        result = handlers.handle_begin_transaction({})
        assert result == {"transaction_id": "trans_123"}
        mock_driver.begin_transaction.assert_called_once()

    def test_handle_commit_transaction(self, handlers, mock_driver):
        """Test commit_transaction handler."""
        mock_driver.commit_transaction.return_value = True
        params = {"transaction_id": "trans_123"}
        result = handlers.handle_commit_transaction(params)
        assert result == {"success": True}
        mock_driver.commit_transaction.assert_called_once_with("trans_123")

    def test_handle_commit_missing_id(self, handlers):
        """Test commit_transaction with missing transaction_id."""
        with pytest.raises(ValueError, match="transaction_id"):
            handlers.handle_commit_transaction({})

    def test_handle_rollback_transaction(self, handlers, mock_driver):
        """Test rollback_transaction handler."""
        mock_driver.rollback_transaction.return_value = True
        params = {"transaction_id": "trans_123"}
        result = handlers.handle_rollback_transaction(params)
        assert result == {"success": True}
        mock_driver.rollback_transaction.assert_called_once_with("trans_123")


class TestRPCHandlersSchema:
    """Test RPC handlers for schema operations."""

    def test_handle_get_table_info(self, handlers, mock_driver):
        """Test get_table_info handler."""
        mock_driver.get_table_info.return_value = [
            {"name": "id", "type": "INTEGER", "primary_key": True}
        ]
        params = {"table_name": "users"}
        result = handlers.handle_get_table_info(params)
        assert "info" in result
        mock_driver.get_table_info.assert_called_once_with("users")

    def test_handle_sync_schema(self, handlers, mock_driver):
        """Test sync_schema handler."""
        mock_driver.sync_schema.return_value = {
            "created_tables": ["users"],
            "modified_tables": [],
        }
        params = {
            "schema_definition": {"tables": []},
            "backup_dir": "/tmp/backup",
        }
        result = handlers.handle_sync_schema(params)
        assert "created_tables" in result
        mock_driver.sync_schema.assert_called_once()

    def test_handle_sync_schema_missing_definition(self, handlers):
        """Test sync_schema with missing schema_definition."""
        with pytest.raises(ValueError, match="schema_definition"):
            handlers.handle_sync_schema({})


class TestRPCHandlersExecute:
    """Test RPC handlers for execute operation."""

    def test_handle_execute(self, handlers, mock_driver):
        """Test execute handler."""
        mock_driver.execute.return_value = {
            "affected_rows": 1,
            "lastrowid": 123,
        }
        params = {"sql": "INSERT INTO users (name) VALUES (?)", "params": ("John",)}
        result = handlers.handle_execute(params)
        assert result["affected_rows"] == 1
        mock_driver.execute.assert_called_once_with(
            "INSERT INTO users (name) VALUES (?)", ("John",)
        )

    def test_handle_execute_missing_sql(self, handlers):
        """Test execute with missing sql."""
        with pytest.raises(ValueError, match="sql"):
            handlers.handle_execute({})
