"""
Shared optional pagination schema helpers for search commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import copy
from typing import Any

OPTIONAL_PAGINATION_PROPERTIES: dict[str, dict[str, Any]] = {
    "paginated": {
        "type": "boolean",
        "default": False,
        "description": (
            "When true, route execution through SearchSession-backed paginated "
            "result blocks instead of returning one unbounded payload."
        ),
    },
    "include_job_id": {
        "type": "boolean",
        "default": True,
        "description": (
            "When paginated is true, include job_id in the handoff response."
        ),
    },
    "job_id": {
        "type": "string",
        "description": (
            "Existing search session job_id for continuation or block fetch."
        ),
    },
    "block_position": {
        "type": "integer",
        "minimum": 1,
        "description": "1-based result block position for paginated retrieval.",
    },
}


def merge_pagination_schema(
    base_schema: dict[str, Any],
    *,
    include_job_id_default: bool = True,
) -> dict[str, Any]:
    """Return a copy of ``base_schema`` with optional pagination properties added."""
    merged = copy.deepcopy(base_schema)
    properties = dict(merged.get("properties") or {})
    pagination_props = copy.deepcopy(OPTIONAL_PAGINATION_PROPERTIES)
    if not include_job_id_default:
        pagination_props["include_job_id"] = {
            **pagination_props["include_job_id"],
            "default": False,
        }
    properties.update(pagination_props)
    merged["properties"] = properties
    required = list(merged.get("required") or [])
    merged["required"] = required
    merged.setdefault("additionalProperties", False)
    return merged
