"""
Tests for RPC request classes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest

from code_analysis.core.database_client.protocol import (
    DeleteRequest,
    InsertRequest,
    SelectRequest,
    TableOperationRequest,
    TransactionRequest,
    UpdateRequest,
)


class TestTableOperationRequest:
    """Test TableOperationRequest class."""

    def test_create_request(self):
        """Test creating table operation request."""
        request = TableOperationRequest(table_name="users")
        assert request.table_name == "users"

    def test_validate_success(self):
        """Test successful validation."""
        request = TableOperationRequest(table_name="users")
        request.validate()  # Should not raise

    def test_validate_empty_table_name(self):
        """Test validation with empty table name."""
        request = TableOperationRequest(table_name="")
        with pytest.raises(ValueError, match="table_name must be a non-empty string"):
            request.validate()

    def test_to_dict(self):
        """Test converting to dictionary."""
        request = TableOperationRequest(table_name="users")
        data = request.to_dict()
        assert data == {"table_name": "users"}

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {"table_name": "users"}
        request = TableOperationRequest.from_dict(data)
        assert request.table_name == "users"


class TestInsertRequest:
    """Test InsertRequest class."""

    def test_create_request(self):
        """Test creating insert request."""
        request = InsertRequest(
            table_name="users",
            data={"name": "John", "age": 30},
        )
        assert request.table_name == "users"
        assert request.data == {"name": "John", "age": 30}

    def test_validate_success(self):
        """Test successful validation."""
        request = InsertRequest(
            table_name="users",
            data={"name": "John"},
        )
        request.validate()  # Should not raise

    def test_validate_empty_data(self):
        """Test validation with empty data."""
        request = InsertRequest(table_name="users", data={})
        with pytest.raises(ValueError, match="data cannot be empty"):
            request.validate()

    def test_validate_invalid_data_type(self):
        """Test validation with invalid data type."""
        request = InsertRequest(table_name="users", data="invalid")
        with pytest.raises(ValueError, match="data must be a dictionary"):
            request.validate()

    def test_to_dict(self):
        """Test converting to dictionary."""
        request = InsertRequest(
            table_name="users",
            data={"name": "John"},
        )
        data = request.to_dict()
        assert data["table_name"] == "users"
        assert data["data"] == {"name": "John"}

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "table_name": "users",
            "data": {"name": "John"},
        }
        request = InsertRequest.from_dict(data)
        assert request.table_name == "users"
        assert request.data == {"name": "John"}


class TestSelectRequest:
    """Test SelectRequest class."""

    def test_create_request(self):
        """Test creating select request."""
        request = SelectRequest(
            table_name="users",
            where={"age": 30},
            columns=["name", "age"],
            limit=10,
            offset=0,
            order_by=["name"],
        )
        assert request.table_name == "users"
        assert request.where == {"age": 30}
        assert request.columns == ["name", "age"]
        assert request.limit == 10
        assert request.offset == 0
        assert request.order_by == ["name"]

    def test_create_request_minimal(self):
        """Test creating minimal select request."""
        request = SelectRequest(table_name="users")
        assert request.table_name == "users"
        assert request.where is None
        assert request.columns is None
        assert request.limit is None
        assert request.offset is None
        assert request.order_by is None

    def test_validate_success(self):
        """Test successful validation."""
        request = SelectRequest(table_name="users")
        request.validate()  # Should not raise

    def test_validate_invalid_where(self):
        """Test validation with invalid where."""
        request = SelectRequest(table_name="users", where="invalid")
        with pytest.raises(ValueError, match="where must be a dictionary or None"):
            request.validate()

    def test_validate_invalid_limit(self):
        """Test validation with invalid limit."""
        request = SelectRequest(table_name="users", limit=-1)
        with pytest.raises(ValueError, match="limit must be a non-negative integer"):
            request.validate()

    def test_validate_invalid_columns(self):
        """Test validation with invalid columns."""
        request = SelectRequest(table_name="users", columns="invalid")
        with pytest.raises(ValueError, match="columns must be a list or None"):
            request.validate()

    def test_validate_invalid_offset(self):
        """Test validation with invalid offset."""
        request = SelectRequest(table_name="users", offset=-1)
        with pytest.raises(ValueError, match="offset must be a non-negative integer"):
            request.validate()

    def test_validate_invalid_order_by(self):
        """Test validation with invalid order_by."""
        request = SelectRequest(table_name="users", order_by="invalid")
        with pytest.raises(ValueError, match="order_by must be a list or None"):
            request.validate()

    def test_to_dict_all_fields(self):
        """Test converting to dictionary with all fields."""
        request = SelectRequest(
            table_name="users",
            where={"age": 30},
            columns=["name", "age"],
            limit=10,
            offset=5,
            order_by=["name"],
        )
        data = request.to_dict()
        assert data["table_name"] == "users"
        assert data["where"] == {"age": 30}
        assert data["columns"] == ["name", "age"]
        assert data["limit"] == 10
        assert data["offset"] == 5
        assert data["order_by"] == ["name"]

    def test_to_dict(self):
        """Test converting to dictionary."""
        request = SelectRequest(
            table_name="users",
            where={"age": 30},
            limit=10,
        )
        data = request.to_dict()
        assert data["table_name"] == "users"
        assert data["where"] == {"age": 30}
        assert data["limit"] == 10
        assert "columns" not in data
        assert "offset" not in data

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "table_name": "users",
            "where": {"age": 30},
            "limit": 10,
        }
        request = SelectRequest.from_dict(data)
        assert request.table_name == "users"
        assert request.where == {"age": 30}
        assert request.limit == 10


class TestUpdateRequest:
    """Test UpdateRequest class."""

    def test_create_request(self):
        """Test creating update request."""
        request = UpdateRequest(
            table_name="users",
            where={"id": 1},
            data={"name": "John Updated"},
        )
        assert request.table_name == "users"
        assert request.where == {"id": 1}
        assert request.data == {"name": "John Updated"}

    def test_validate_success(self):
        """Test successful validation."""
        request = UpdateRequest(
            table_name="users",
            where={"id": 1},
            data={"name": "John"},
        )
        request.validate()  # Should not raise

    def test_validate_empty_where(self):
        """Test validation with empty where."""
        request = UpdateRequest(
            table_name="users",
            where={},
            data={"name": "John"},
        )
        with pytest.raises(ValueError, match="where cannot be empty"):
            request.validate()

    def test_to_dict(self):
        """Test converting to dictionary."""
        request = UpdateRequest(
            table_name="users",
            where={"id": 1},
            data={"name": "John"},
        )
        data = request.to_dict()
        assert data["table_name"] == "users"
        assert data["where"] == {"id": 1}
        assert data["data"] == {"name": "John"}

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "table_name": "users",
            "where": {"id": 1},
            "data": {"name": "John"},
        }
        request = UpdateRequest.from_dict(data)
        assert request.table_name == "users"
        assert request.where == {"id": 1}
        assert request.data == {"name": "John"}


class TestDeleteRequest:
    """Test DeleteRequest class."""

    def test_create_request(self):
        """Test creating delete request."""
        request = DeleteRequest(
            table_name="users",
            where={"id": 1},
        )
        assert request.table_name == "users"
        assert request.where == {"id": 1}

    def test_validate_success(self):
        """Test successful validation."""
        request = DeleteRequest(
            table_name="users",
            where={"id": 1},
        )
        request.validate()  # Should not raise

    def test_validate_empty_where(self):
        """Test validation with empty where."""
        request = DeleteRequest(table_name="users", where={})
        with pytest.raises(ValueError, match="where cannot be empty"):
            request.validate()

    def test_to_dict(self):
        """Test converting to dictionary."""
        request = DeleteRequest(
            table_name="users",
            where={"id": 1},
        )
        data = request.to_dict()
        assert data["table_name"] == "users"
        assert data["where"] == {"id": 1}

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "table_name": "users",
            "where": {"id": 1},
        }
        request = DeleteRequest.from_dict(data)
        assert request.table_name == "users"
        assert request.where == {"id": 1}


class TestTransactionRequest:
    """Test TransactionRequest class."""

    def test_create_request_begin(self):
        """Test creating begin transaction request."""
        request = TransactionRequest(
            transaction_id="tx123",
            operation="begin",
        )
        assert request.transaction_id == "tx123"
        assert request.operation == "begin"

    def test_create_request_commit(self):
        """Test creating commit transaction request."""
        request = TransactionRequest(
            transaction_id="tx123",
            operation="commit",
        )
        assert request.operation == "commit"

    def test_create_request_rollback(self):
        """Test creating rollback transaction request."""
        request = TransactionRequest(
            transaction_id="tx123",
            operation="rollback",
        )
        assert request.operation == "rollback"

    def test_validate_success(self):
        """Test successful validation."""
        request = TransactionRequest(
            transaction_id="tx123",
            operation="begin",
        )
        request.validate()  # Should not raise

    def test_validate_invalid_operation(self):
        """Test validation with invalid operation."""
        request = TransactionRequest(
            transaction_id="tx123",
            operation="invalid",
        )
        with pytest.raises(ValueError, match="operation must be"):
            request.validate()

    def test_to_dict(self):
        """Test converting to dictionary."""
        request = TransactionRequest(
            transaction_id="tx123",
            operation="begin",
        )
        data = request.to_dict()
        assert data["transaction_id"] == "tx123"
        assert data["operation"] == "begin"

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "transaction_id": "tx123",
            "operation": "begin",
        }
        request = TransactionRequest.from_dict(data)
        assert request.transaction_id == "tx123"
        assert request.operation == "begin"
