"""
Tests for client-side Result class.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest

from code_analysis.core.database_client.result import Result
from code_analysis.core.database_driver_pkg.rpc_protocol import ErrorCode


class TestResult:
    """Test Result class."""

    def test_create_success(self):
        """Test creating successful result."""
        result = Result.success(data={"node_id": "123"})
        assert result.success is True
        assert result.data == {"node_id": "123"}
        assert result.is_success()
        assert not result.is_error()

    def test_create_success_no_data(self):
        """Test creating successful result without data."""
        result = Result.success()
        assert result.success is True
        assert result.data is None
        assert result.is_success()

    def test_create_error(self):
        """Test creating error result."""
        result = Result.error(
            error_code=ErrorCode.NOT_FOUND,
            description="Node not found",
            details={"node_id": "123"},
        )
        assert result.success is False
        assert result.error_code == ErrorCode.NOT_FOUND
        assert result.error_description == "Node not found"
        assert result.error_details == {"node_id": "123"}
        assert not result.is_success()
        assert result.is_error()

    def test_create_error_no_details(self):
        """Test creating error result without details."""
        result = Result.error(
            error_code=ErrorCode.NOT_FOUND,
            description="Node not found",
        )
        assert result.error_details is None

    def test_to_dict_success(self):
        """Test converting successful result to dictionary."""
        result = Result.success(data={"node_id": "123"})
        data = result.to_dict()
        assert data["success"] is True
        assert data["data"] == {"node_id": "123"}
        assert "error_code" not in data

    def test_to_dict_error(self):
        """Test converting error result to dictionary."""
        result = Result.error(
            error_code=ErrorCode.NOT_FOUND,
            description="Node not found",
            details={"node_id": "123"},
        )
        data = result.to_dict()
        assert data["success"] is False
        assert data["error_code"] == ErrorCode.NOT_FOUND.value
        assert data["error_description"] == "Node not found"
        assert data["error_details"] == {"node_id": "123"}

    def test_from_dict_success(self):
        """Test creating result from dictionary (success)."""
        data = {"success": True, "data": {"node_id": "123"}}
        result = Result.from_dict(data)
        assert result.success is True
        assert result.data == {"node_id": "123"}
        assert result.error_code is None

    def test_from_dict_error(self):
        """Test creating result from dictionary (error)."""
        data = {
            "success": False,
            "error_code": ErrorCode.NOT_FOUND.value,
            "error_description": "Node not found",
            "error_details": {"node_id": "123"},
        }
        result = Result.from_dict(data)
        assert result.success is False
        assert result.error_code == ErrorCode.NOT_FOUND
        assert result.error_description == "Node not found"
        assert result.error_details == {"node_id": "123"}

    def test_round_trip_serialization(self):
        """Test round-trip serialization."""
        original = Result.success(data={"node_id": "123", "name": "test"})
        data = original.to_dict()
        restored = Result.from_dict(data)
        assert restored.success == original.success
        assert restored.data == original.data

    def test_round_trip_serialization_error(self):
        """Test round-trip serialization for error."""
        original = Result.error(
            error_code=ErrorCode.NOT_FOUND,
            description="Node not found",
            details={"node_id": "123"},
        )
        data = original.to_dict()
        restored = Result.from_dict(data)
        assert restored.success == original.success
        assert restored.error_code == original.error_code
        assert restored.error_description == original.error_description
        assert restored.error_details == original.error_details
