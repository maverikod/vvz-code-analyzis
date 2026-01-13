"""
Serialization utilities for RPC communication.

Handles serialization and deserialization of RPC messages, including
special types (datetime, Path, etc.) and circular references.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class RPCEncoder(json.JSONEncoder):
    """Custom JSON encoder for RPC messages.

    Handles special types:
    - datetime objects
    - Path objects
    - Other custom types
    """

    def default(self, obj: Any) -> Any:
        """Convert special types to JSON-serializable format."""
        if isinstance(obj, datetime):
            return {"__type__": "datetime", "value": obj.isoformat()}
        if isinstance(obj, Path):
            return {"__type__": "path", "value": str(obj)}
        return super().default(obj)


def serialize_request(request: Any) -> str:
    """Serialize RPC request to JSON string.

    Args:
        request: Request object with to_dict() method

    Returns:
        JSON string representation
    """
    if hasattr(request, "to_dict"):
        data = request.to_dict()
    else:
        data = request
    return json.dumps(data, cls=RPCEncoder)


def deserialize_request(data: str, request_class: type) -> Any:
    """Deserialize JSON string to RPC request.

    Args:
        data: JSON string
        request_class: Request class with from_dict() method

    Returns:
        Request instance
    """
    obj = json.loads(data)
    if hasattr(request_class, "from_dict"):
        return request_class.from_dict(obj)
    return obj


def serialize_response(response: Any) -> str:
    """Serialize RPC response to JSON string.

    Args:
        response: Response object with to_dict() method

    Returns:
        JSON string representation
    """
    if hasattr(response, "to_dict"):
        data = response.to_dict()
    else:
        data = response
    return json.dumps(data, cls=RPCEncoder)


def deserialize_response(data: str, response_class: type) -> Any:
    """Deserialize JSON string to RPC response.

    Args:
        data: JSON string
        response_class: Response class with from_dict() method

    Returns:
        Response instance
    """
    obj = json.loads(data)
    if hasattr(response_class, "from_dict"):
        return response_class.from_dict(obj)
    return obj


def deserialize_special_types(obj: Dict[str, Any]) -> Any:
    """Deserialize special types from dictionary.

    Handles datetime and Path objects that were serialized with __type__ markers.

    Args:
        obj: Dictionary with __type__ marker

    Returns:
        Deserialized object
    """
    if isinstance(obj, dict) and "__type__" in obj:
        type_name = obj["__type__"]
        value = obj["value"]
        if type_name == "datetime":
            return datetime.fromisoformat(value)
        if type_name == "path":
            return Path(value)
    return obj


def serialize_to_dict(obj: Any) -> Dict[str, Any]:
    """Serialize object to dictionary.

    Args:
        obj: Object to serialize

    Returns:
        Dictionary representation
    """
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return obj
    return {"value": obj}


def deserialize_from_dict(
    data: Dict[str, Any], target_class: Optional[type] = None
) -> Any:
    """Deserialize dictionary to object.

    Args:
        data: Dictionary to deserialize
        target_class: Optional target class with from_dict() method

    Returns:
        Deserialized object
    """
    if target_class is not None and hasattr(target_class, "from_dict"):
        return target_class.from_dict(data)
    return deserialize_special_types(data)
