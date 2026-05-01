"""
Tests for RPC protocol definitions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any

import pytest

from code_analysis.core.database_client.protocol import (
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

    def test_request_priority_round_trip_nonzero(self):
        """to_dict/from_dict preserves non-default priority."""
        original = RPCRequest(
            method="insert",
            params={"k": "v"},
            priority=7,
            request_id="req-1",
        )
        restored = RPCRequest.from_dict(original.to_dict())
        assert restored.method == original.method
        assert restored.params == original.params
        assert restored.priority == 7
        assert restored.request_id == original.request_id

    def test_request_from_dict_priority_key_absent(self):
        """Missing priority in payload defaults to 0."""
        data = {
            "jsonrpc": "2.0",
            "method": "ping",
            "params": {},
        }
        request = RPCRequest.from_dict(data)
        assert request.priority == 0

    def test_request_to_dict_omits_priority_when_zero(self):
        """Default and explicit priority=0 must not add a wire key (step 1 contract)."""
        req_default = RPCRequest(method="m", params={})
        assert "priority" not in req_default.to_dict()
        req_explicit = RPCRequest(method="m", params={}, priority=0)
        assert "priority" not in req_explicit.to_dict()

    def test_request_round_trip_priority_explicit_zero(self):
        """Explicit priority:0 in JSON round-trips without bloating minimal to_dict."""
        data = {
            "jsonrpc": "2.0",
            "method": "ping",
            "params": {},
            "priority": 0,
        }
        request = RPCRequest.from_dict(data)
        assert request.priority == 0
        out = request.to_dict()
        assert "priority" not in out

    def test_request_from_dict_priority_non_numeric_raises(self):
        """Invalid priority payload should fail fast (wire misuse)."""
        data: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": "ping",
            "params": {},
            "priority": "not-int",
        }
        with pytest.raises(ValueError):
            RPCRequest.from_dict(data)

    def test_request_to_dict_negative_priority_serialized(self):
        """Non-zero negative priorities are preserved on the wire (if ever used)."""
        original = RPCRequest(method="m", params={}, priority=-3, request_id="x")
        restored = RPCRequest.from_dict(original.to_dict())
        assert restored.priority == -3


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

    def test_response_to_dict_no_result_no_error(self):
        """Test converting response with no result and no error."""
        response = RPCResponse(request_id="123")
        data = response.to_dict()
        assert data["jsonrpc"] == "2.0"
        assert data["result"] is None
        assert "error" not in data
        assert data["id"] == "123"

    def test_response_from_dict_no_id(self):
        """Test creating response from dictionary without ID."""
        data = {
            "jsonrpc": "2.0",
            "result": {"row_id": 1},
        }
        response = RPCResponse.from_dict(data)
        assert response.result == {"row_id": 1}
        assert response.request_id is None

    def test_error_from_dict_defaults(self):
        """Test creating error from dictionary with defaults."""
        data: dict[str, Any] = {}
        error = RPCError.from_dict(data)
        assert error.code == ErrorCode.INTERNAL_ERROR
        assert error.message == "Unknown error"
        assert error.data is None
