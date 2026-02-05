"""
Tests for RPC result classes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest

from code_analysis.core.database_client.protocol import (
    DataResult,
    ErrorResult,
    ErrorCode,
    SuccessResult,
)


class TestSuccessResult:
    """Test SuccessResult class."""

    def test_create_result(self):
        """Test creating success result."""
        result = SuccessResult(data={"row_id": 1})
        assert result.data == {"row_id": 1}
        assert result.is_success()
        assert not result.is_error()

    def test_create_result_no_data(self):
        """Test creating success result without data."""
        result = SuccessResult()
        assert result.data is None
        assert result.is_success()
        assert not result.is_error()

    def test_to_dict(self):
        """Test converting to dictionary."""
        result = SuccessResult(data={"row_id": 1})
        data = result.to_dict()
        assert data["success"] is True
        assert data["data"] == {"row_id": 1}

    def test_to_dict_no_data(self):
        """Test converting to dictionary without data."""
        result = SuccessResult()
        data = result.to_dict()
        assert data["success"] is True
        assert "data" not in data

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {"success": True, "data": {"row_id": 1}}
        result = SuccessResult.from_dict(data)
        assert result.data == {"row_id": 1}
        assert result.is_success()

    def test_from_dict_no_data(self):
        """Test creating from dictionary without data."""
        data = {"success": True}
        result = SuccessResult.from_dict(data)
        assert result.data is None
        assert result.is_success()


class TestErrorResult:
    """Test ErrorResult class."""

    def test_create_result(self):
        """Test creating error result."""
        result = ErrorResult(
            error_code=ErrorCode.DATABASE_ERROR,
            description="Database connection failed",
            details={"table": "users"},
        )
        assert result.error_code == ErrorCode.DATABASE_ERROR
        assert result.description == "Database connection failed"
        assert result.details == {"table": "users"}
        assert not result.is_success()
        assert result.is_error()

    def test_create_result_no_details(self):
        """Test creating error result without details."""
        result = ErrorResult(
            error_code=ErrorCode.DATABASE_ERROR,
            description="Database connection failed",
        )
        assert result.details is None
        assert not result.is_success()
        assert result.is_error()

    def test_to_dict(self):
        """Test converting to dictionary."""
        result = ErrorResult(
            error_code=ErrorCode.DATABASE_ERROR,
            description="Database connection failed",
            details={"table": "users"},
        )
        data = result.to_dict()
        assert data["success"] is False
        assert data["error_code"] == ErrorCode.DATABASE_ERROR.value
        assert data["description"] == "Database connection failed"
        assert data["details"] == {"table": "users"}

    def test_to_dict_no_details(self):
        """Test converting to dictionary without details."""
        result = ErrorResult(
            error_code=ErrorCode.DATABASE_ERROR,
            description="Database connection failed",
        )
        data = result.to_dict()
        assert data["success"] is False
        assert "details" not in data

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "success": False,
            "error_code": ErrorCode.DATABASE_ERROR.value,
            "description": "Database connection failed",
            "details": {"table": "users"},
        }
        result = ErrorResult.from_dict(data)
        assert result.error_code == ErrorCode.DATABASE_ERROR
        assert result.description == "Database connection failed"
        assert result.details == {"table": "users"}

    def test_to_rpc_error(self):
        """Test converting to RPCError."""
        result = ErrorResult(
            error_code=ErrorCode.DATABASE_ERROR,
            description="Database connection failed",
            details={"table": "users"},
        )
        rpc_error = result.to_rpc_error()
        assert rpc_error.code == ErrorCode.DATABASE_ERROR
        assert rpc_error.message == "Database connection failed"
        assert rpc_error.data == {"table": "users"}


class TestDataResult:
    """Test DataResult class."""

    def test_create_result(self):
        """Test creating data result."""
        result = DataResult(data=[{"id": 1, "name": "John"}, {"id": 2, "name": "Jane"}])
        assert len(result.data) == 2
        assert result.data[0] == {"id": 1, "name": "John"}
        assert result.is_success()
        assert not result.is_error()

    def test_create_result_empty(self):
        """Test creating data result with empty data."""
        result = DataResult(data=[])
        assert result.data == []
        assert result.is_success()

    def test_to_dict(self):
        """Test converting to dictionary."""
        result = DataResult(data=[{"id": 1, "name": "John"}])
        data = result.to_dict()
        assert data["success"] is True
        assert data["data"] == [{"id": 1, "name": "John"}]

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {"success": True, "data": [{"id": 1, "name": "John"}]}
        result = DataResult.from_dict(data)
        assert result.data == [{"id": 1, "name": "John"}]
        assert result.is_success()

    def test_from_dict_invalid_data(self):
        """Test creating from dictionary with invalid data."""
        data = {"success": True, "data": "invalid"}
        result = DataResult.from_dict(data)
        assert result.data == []
        assert result.is_success()
