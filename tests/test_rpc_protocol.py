"""
Tests for RPC protocol definitions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest

from code_analysis.core.database_driver_pkg.rpc_protocol import (
    ErrorCode,
    RPCError,
    RPCRequest,
    RPCResponse,
)


class TestErrorCode:
    """Test ErrorCode enum."""

    def test_error_code_values(self):
        """Test error code values."""
        assert ErrorCode.SUCCESS == 0
        assert ErrorCode.INVALID_REQUEST == 1
        assert ErrorCode.DATABASE_ERROR == 2
        assert ErrorCode.NOT_FOUND == 3
        assert ErrorCode.VALIDATION_ERROR == 4


class TestRPCError:
    """Test RPCError class."""

    def test_create_error(self):
        """Test creating RPC error."""
        error = RPCError(
            code=ErrorCode.DATABASE_ERROR,
            message="Database connection failed",
            data={"table": "users"},
        )
        assert error.code == ErrorCode.DATABASE_ERROR
        assert error.message == "Database connection failed"
        assert error.data == {"table": "users"}

    def test_error_to_dict(self):
        """Test converting error to dictionary."""
        error = RPCError(
            code=ErrorCode.DATABASE_ERROR,
            message="Database connection failed",
            data={"table": "users"},
        )
        data = error.to_dict()
        assert data["code"] == ErrorCode.DATABASE_ERROR.value
        assert data["message"] == "Database connection failed"
        assert data["data"] == {"table": "users"}

    def test_error_to_dict_no_data(self):
        """Test converting error to dictionary without data."""
        error = RPCError(
            code=ErrorCode.DATABASE_ERROR,
            message="Database connection failed",
        )
        data = error.to_dict()
        assert data["code"] == ErrorCode.DATABASE_ERROR.value
        assert data["message"] == "Database connection failed"
        assert "data" not in data

    def test_error_from_dict(self):
        """Test creating error from dictionary."""
        data = {
            "code": ErrorCode.DATABASE_ERROR.value,
            "message": "Database connection failed",
            "data": {"table": "users"},
        }
        error = RPCError.from_dict(data)
        assert error.code == ErrorCode.DATABASE_ERROR
        assert error.message == "Database connection failed"
        assert error.data == {"table": "users"}

    def test_error_from_dict_no_data(self):
        """Test creating error from dictionary without data."""
        data = {
            "code": ErrorCode.DATABASE_ERROR.value,
            "message": "Database connection failed",
        }
        error = RPCError.from_dict(data)
        assert error.code == ErrorCode.DATABASE_ERROR
        assert error.message == "Database connection failed"
        assert error.data is None


class TestRPCRequest:
    """Test RPCRequest class."""

    def test_create_request(self):
        """Test creating RPC request."""
        request = RPCRequest(
            method="insert",
            params={"table_name": "users", "data": {"name": "John"}},
            request_id="123",
        )
        assert request.method == "insert"
        assert request.params == {"table_name": "users", "data": {"name": "John"}}
        assert request.request_id == "123"

    def test_request_to_dict(self):
        """Test converting request to dictionary."""
        request = RPCRequest(
            method="insert",
            params={"table_name": "users"},
            request_id="123",
        )
        data = request.to_dict()
        assert data["jsonrpc"] == "2.0"
        assert data["method"] == "insert"
        assert data["params"] == {"table_name": "users"}
        assert data["id"] == "123"

    def test_request_to_dict_no_id(self):
        """Test converting request to dictionary without ID."""
        request = RPCRequest(method="insert", params={"table_name": "users"})
        data = request.to_dict()
        assert data["jsonrpc"] == "2.0"
        assert data["method"] == "insert"
        assert data["params"] == {"table_name": "users"}
        assert "id" not in data

    def test_request_from_dict(self):
        """Test creating request from dictionary."""
        data = {
            "jsonrpc": "2.0",
            "method": "insert",
            "params": {"table_name": "users"},
            "id": "123",
        }
        request = RPCRequest.from_dict(data)
        assert request.method == "insert"
        assert request.params == {"table_name": "users"}
        assert request.request_id == "123"

    def test_request_from_dict_no_id(self):
        """Test creating request from dictionary without ID."""
        data = {
            "jsonrpc": "2.0",
            "method": "insert",
            "params": {"table_name": "users"},
        }
        request = RPCRequest.from_dict(data)
        assert request.method == "insert"
        assert request.params == {"table_name": "users"}
        assert request.request_id is None


class TestRPCResponse:
    """Test RPCResponse class."""

    def test_create_success_response(self):
        """Test creating successful RPC response."""
        response = RPCResponse(
            result={"row_id": 1},
            request_id="123",
        )
        assert response.result == {"row_id": 1}
        assert response.error is None
        assert response.request_id == "123"
        assert response.is_success()
        assert not response.is_error()

    def test_create_error_response(self):
        """Test creating error RPC response."""
        error = RPCError(
            code=ErrorCode.DATABASE_ERROR,
            message="Database connection failed",
        )
        response = RPCResponse(
            error=error,
            request_id="123",
        )
        assert response.result is None
        assert response.error == error
        assert response.request_id == "123"
        assert not response.is_success()
        assert response.is_error()

    def test_response_to_dict_success(self):
        """Test converting successful response to dictionary."""
        response = RPCResponse(
            result={"row_id": 1},
            request_id="123",
        )
        data = response.to_dict()
        assert data["jsonrpc"] == "2.0"
        assert data["result"] == {"row_id": 1}
        assert data["id"] == "123"
        assert "error" not in data

    def test_response_to_dict_error(self):
        """Test converting error response to dictionary."""
        error = RPCError(
            code=ErrorCode.DATABASE_ERROR,
            message="Database connection failed",
        )
        response = RPCResponse(
            error=error,
            request_id="123",
        )
        data = response.to_dict()
        assert data["jsonrpc"] == "2.0"
        assert "error" in data
        assert data["error"]["code"] == ErrorCode.DATABASE_ERROR.value
        assert data["error"]["message"] == "Database connection failed"
        assert data["id"] == "123"
        assert "result" not in data

    def test_response_from_dict_success(self):
        """Test creating response from dictionary (success)."""
        data = {
            "jsonrpc": "2.0",
            "result": {"row_id": 1},
            "id": "123",
        }
        response = RPCResponse.from_dict(data)
        assert response.result == {"row_id": 1}
        assert response.error is None
        assert response.request_id == "123"

    def test_response_from_dict_error(self):
        """Test creating response from dictionary (error)."""
        data = {
            "jsonrpc": "2.0",
            "error": {
                "code": ErrorCode.DATABASE_ERROR.value,
                "message": "Database connection failed",
            },
            "id": "123",
        }
        response = RPCResponse.from_dict(data)
        assert response.result is None
        assert response.error is not None
        assert response.error.code == ErrorCode.DATABASE_ERROR
        assert response.error.message == "Database connection failed"
        assert response.request_id == "123"
