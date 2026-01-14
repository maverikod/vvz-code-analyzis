"""
Tests for RPC handlers.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
from unittest.mock import Mock

from code_analysis.core.database_driver_pkg.rpc_handlers import RPCHandlers
from code_analysis.core.database_driver_pkg.drivers.base import BaseDatabaseDriver
from code_analysis.core.database_driver_pkg.result import (
    DataResult,
    ErrorResult,
    SuccessResult,
)
from code_analysis.core.database_driver_pkg.request import (
    DeleteRequest,
    InsertRequest,
    SelectRequest,
    UpdateRequest,
)


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
        assert isinstance(result, SuccessResult)
        assert result.is_success()
        assert result.data == {"success": True}
        mock_driver.create_table.assert_called_once()

    def test_handle_create_table_missing_schema(self, handlers):
        """Test create_table with missing schema."""
        result = handlers.handle_create_table({})
        assert isinstance(result, ErrorResult)
        assert result.is_error()
        assert "schema" in result.description.lower()

    def test_handle_drop_table(self, handlers, mock_driver):
        """Test drop_table handler."""
        mock_driver.drop_table.return_value = True
        params = {"table_name": "users"}
        result = handlers.handle_drop_table(params)
        assert isinstance(result, SuccessResult)
        assert result.is_success()
        assert result.data == {"success": True}
        mock_driver.drop_table.assert_called_once_with("users")

    def test_handle_drop_table_missing_name(self, handlers):
        """Test drop_table with missing table_name."""
        result = handlers.handle_drop_table({})
        assert isinstance(result, ErrorResult)
        assert result.is_error()
        assert "table_name" in result.description.lower()


class TestRPCHandlersCRUD:
    """Test RPC handlers for CRUD operations."""

    def test_handle_insert(self, handlers, mock_driver):
        """Test insert handler."""
        mock_driver.insert.return_value = 123
        request = InsertRequest(table_name="users", data={"name": "John"})
        result = handlers.handle_insert(request)
        assert isinstance(result, SuccessResult)
        assert result.is_success()
        assert result.data == {"row_id": 123}
        mock_driver.insert.assert_called_once_with("users", {"name": "John"})

    def test_handle_insert_missing_params(self, handlers):
        """Test insert with missing parameters."""
        # Test with missing table_name
        request = InsertRequest(table_name="", data={"name": "John"})
        result = handlers.handle_insert(request)
        assert isinstance(result, ErrorResult)
        assert result.is_error()

        # Test with missing data
        request = InsertRequest(table_name="users", data={})
        result = handlers.handle_insert(request)
        assert isinstance(result, ErrorResult)
        assert result.is_error()

    def test_handle_update(self, handlers, mock_driver):
        """Test update handler."""
        mock_driver.update.return_value = 1
        request = UpdateRequest(
            table_name="users", where={"id": 1}, data={"name": "Jane"}
        )
        result = handlers.handle_update(request)
        assert isinstance(result, SuccessResult)
        assert result.is_success()
        assert result.data == {"affected_rows": 1}
        mock_driver.update.assert_called_once_with("users", {"id": 1}, {"name": "Jane"})

    def test_handle_delete(self, handlers, mock_driver):
        """Test delete handler."""
        mock_driver.delete.return_value = 1
        request = DeleteRequest(table_name="users", where={"id": 1})
        result = handlers.handle_delete(request)
        assert isinstance(result, SuccessResult)
        assert result.is_success()
        assert result.data == {"affected_rows": 1}
        mock_driver.delete.assert_called_once_with("users", {"id": 1})

    def test_handle_select(self, handlers, mock_driver):
        """Test select handler."""
        mock_driver.select.return_value = [{"id": 1, "name": "John"}]
        request = SelectRequest(
            table_name="users",
            where={"id": 1},
            columns=["id", "name"],
            limit=10,
            offset=0,
            order_by=["id"],
        )
        result = handlers.handle_select(request)
        assert isinstance(result, DataResult)
        assert result.is_success()
        assert result.data == [{"id": 1, "name": "John"}]
        mock_driver.select.assert_called_once_with(
            table_name="users",
            where={"id": 1},
            columns=["id", "name"],
            limit=10,
            offset=0,
            order_by=["id"],
        )

    def test_handle_select_minimal(self, handlers, mock_driver):
        """Test select with minimal parameters."""
        mock_driver.select.return_value = []
        request = SelectRequest(table_name="users")
        result = handlers.handle_select(request)
        assert isinstance(result, DataResult)
        assert result.is_success()
        assert result.data == []
        mock_driver.select.assert_called_once_with(
            table_name="users",
            where=None,
            columns=None,
            limit=None,
            offset=None,
            order_by=None,
        )


class TestRPCHandlersTransactions:
    """Test RPC handlers for transactions."""

    def test_handle_begin_transaction(self, handlers, mock_driver):
        """Test begin_transaction handler."""
        mock_driver.begin_transaction.return_value = "trans_123"
        result = handlers.handle_begin_transaction({})
        assert isinstance(result, SuccessResult)
        assert result.is_success()
        assert result.data == {"transaction_id": "trans_123"}
        mock_driver.begin_transaction.assert_called_once()

    def test_handle_commit_transaction(self, handlers, mock_driver):
        """Test commit_transaction handler."""
        mock_driver.commit_transaction.return_value = True
        params = {"transaction_id": "trans_123"}
        result = handlers.handle_commit_transaction(params)
        assert isinstance(result, SuccessResult)
        assert result.is_success()
        assert result.data == {"success": True}
        mock_driver.commit_transaction.assert_called_once_with("trans_123")

    def test_handle_commit_missing_id(self, handlers):
        """Test commit_transaction with missing transaction_id."""
        result = handlers.handle_commit_transaction({})
        assert isinstance(result, ErrorResult)
        assert result.is_error()
        assert "transaction_id" in result.description.lower()

    def test_handle_rollback_transaction(self, handlers, mock_driver):
        """Test rollback_transaction handler."""
        mock_driver.rollback_transaction.return_value = True
        params = {"transaction_id": "trans_123"}
        result = handlers.handle_rollback_transaction(params)
        assert isinstance(result, SuccessResult)
        assert result.is_success()
        assert result.data == {"success": True}
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
        assert isinstance(result, DataResult)
        assert result.is_success()
        assert len(result.data) == 1
        assert result.data[0]["name"] == "id"
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
        assert isinstance(result, SuccessResult)
        assert result.is_success()
        assert "created_tables" in result.data
        assert result.data["created_tables"] == ["users"]
        mock_driver.sync_schema.assert_called_once()

    def test_handle_sync_schema_missing_definition(self, handlers):
        """Test sync_schema with missing schema_definition."""
        result = handlers.handle_sync_schema({})
        assert isinstance(result, ErrorResult)
        assert result.is_error()
        assert "schema_definition" in result.description.lower()


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
        assert isinstance(result, SuccessResult)
        assert result.is_success()
        assert result.data["affected_rows"] == 1
        assert result.data["lastrowid"] == 123
        mock_driver.execute.assert_called_once_with(
            "INSERT INTO users (name) VALUES (?)", ("John",)
        )

    def test_handle_execute_missing_sql(self, handlers):
        """Test execute with missing sql."""
        result = handlers.handle_execute({})
        assert isinstance(result, ErrorResult)
        assert result.is_error()
        assert "sql" in result.description.lower()
