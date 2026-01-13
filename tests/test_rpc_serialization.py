"""
Tests for RPC serialization utilities.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from code_analysis.core.database_driver_pkg.request import InsertRequest
from code_analysis.core.database_driver_pkg.result import SuccessResult
from code_analysis.core.database_driver_pkg.rpc_protocol import RPCRequest, RPCResponse
from code_analysis.core.database_driver_pkg.serialization import (
    RPCEncoder,
    deserialize_from_dict,
    deserialize_request,
    deserialize_response,
    deserialize_special_types,
    serialize_request,
    serialize_response,
    serialize_to_dict,
)


class TestRPCEncoder:
    """Test RPCEncoder class."""

    def test_encode_datetime(self):
        """Test encoding datetime objects."""
        dt = datetime(2024, 1, 1, 12, 0, 0)
        encoder = RPCEncoder()
        result = encoder.default(dt)
        assert result["__type__"] == "datetime"
        assert result["value"] == dt.isoformat()

    def test_encode_path(self):
        """Test encoding Path objects."""
        path = Path("/tmp/test.txt")
        encoder = RPCEncoder()
        result = encoder.default(path)
        assert result["__type__"] == "path"
        assert result["value"] == str(path)

    def test_encode_regular_type(self):
        """Test encoding regular types."""
        encoder = RPCEncoder()
        with pytest.raises(TypeError):
            encoder.default(object())


class TestSerializeRequest:
    """Test serialize_request function."""

    def test_serialize_request_object(self):
        """Test serializing request object."""
        request = InsertRequest(
            table_name="users",
            data={"name": "John"},
        )
        result = serialize_request(request)
        data = json.loads(result)
        assert data["table_name"] == "users"
        assert data["data"] == {"name": "John"}

    def test_serialize_request_dict(self):
        """Test serializing request dictionary."""
        request_dict = {
            "table_name": "users",
            "data": {"name": "John"},
        }
        result = serialize_request(request_dict)
        data = json.loads(result)
        assert data == request_dict


class TestDeserializeRequest:
    """Test deserialize_request function."""

    def test_deserialize_request(self):
        """Test deserializing request."""
        data = json.dumps({
            "table_name": "users",
            "data": {"name": "John"},
        })
        request = deserialize_request(data, InsertRequest)
        assert isinstance(request, InsertRequest)
        assert request.table_name == "users"
        assert request.data == {"name": "John"}


class TestSerializeResponse:
    """Test serialize_response function."""

    def test_serialize_response_object(self):
        """Test serializing response object."""
        response = SuccessResult(data={"row_id": 1})
        result = serialize_response(response)
        data = json.loads(result)
        assert data["success"] is True
        assert data["data"] == {"row_id": 1}

    def test_serialize_response_dict(self):
        """Test serializing response dictionary."""
        response_dict = {"success": True, "data": {"row_id": 1}}
        result = serialize_response(response_dict)
        data = json.loads(result)
        assert data == response_dict


class TestDeserializeResponse:
    """Test deserialize_response function."""

    def test_deserialize_response(self):
        """Test deserializing response."""
        data = json.dumps({
            "success": True,
            "data": {"row_id": 1},
        })
        response = deserialize_response(data, SuccessResult)
        assert isinstance(response, SuccessResult)
        assert response.data == {"row_id": 1}


class TestDeserializeSpecialTypes:
    """Test deserialize_special_types function."""

    def test_deserialize_datetime(self):
        """Test deserializing datetime."""
        obj = {
            "__type__": "datetime",
            "value": "2024-01-01T12:00:00",
        }
        result = deserialize_special_types(obj)
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 1

    def test_deserialize_path(self):
        """Test deserializing Path."""
        obj = {
            "__type__": "path",
            "value": "/tmp/test.txt",
        }
        result = deserialize_special_types(obj)
        assert isinstance(result, Path)
        assert str(result) == "/tmp/test.txt"

    def test_deserialize_regular_dict(self):
        """Test deserializing regular dictionary."""
        obj = {"key": "value"}
        result = deserialize_special_types(obj)
        assert result == obj


class TestSerializeToDict:
    """Test serialize_to_dict function."""

    def test_serialize_object_with_to_dict(self):
        """Test serializing object with to_dict method."""
        request = InsertRequest(
            table_name="users",
            data={"name": "John"},
        )
        result = serialize_to_dict(request)
        assert result["table_name"] == "users"
        assert result["data"] == {"name": "John"}

    def test_serialize_dict(self):
        """Test serializing dictionary."""
        obj = {"key": "value"}
        result = serialize_to_dict(obj)
        assert result == obj

    def test_serialize_regular_object(self):
        """Test serializing regular object."""
        obj = "test"
        result = serialize_to_dict(obj)
        assert result == {"value": "test"}


class TestDeserializeFromDict:
    """Test deserialize_from_dict function."""

    def test_deserialize_with_class(self):
        """Test deserializing with target class."""
        data = {
            "table_name": "users",
            "data": {"name": "John"},
        }
        result = deserialize_from_dict(data, InsertRequest)
        assert isinstance(result, InsertRequest)
        assert result.table_name == "users"

    def test_deserialize_without_class(self):
        """Test deserializing without target class."""
        data = {
            "__type__": "datetime",
            "value": "2024-01-01T12:00:00",
        }
        result = deserialize_from_dict(data)
        assert isinstance(result, datetime)
