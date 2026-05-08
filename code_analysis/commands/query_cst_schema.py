"""
JSON schema for query_cst command.

Assembled from ``query_cst_metadata_descr_params.get_parameters()`` so schema and
structured metadata stay aligned.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict

from .query_cst_metadata_descr_params import get_parameters


def get_query_cst_schema() -> Dict[str, Any]:
    """Return JSON Schema for query_cst command parameters."""
    meta = get_parameters()
    properties: Dict[str, Any] = {}
    required: list[str] = []

    for name, spec in meta.items():
        if spec.get("required") is True:
            required.append(name)
        prop: Dict[str, Any] = {
            "type": spec["type"],
            "description": spec["description"],
        }
        if "default" in spec:
            prop["default"] = spec["default"]
        if spec.get("type") == "array" and "items" in spec:
            prop["items"] = spec["items"]
        properties[name] = prop

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
