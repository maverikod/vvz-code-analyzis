"""
Optional pagination schema extension for project_cross_search.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any

from code_analysis.commands.project_cross_search_command import (
    get_project_cross_search_schema,
)
from code_analysis.commands.search_session_schema import merge_pagination_schema

__all__ = [
    "document_cross_search_pagination_metadata",
    "get_project_cross_search_schema_with_pagination",
]


def get_project_cross_search_schema_with_pagination() -> dict[str, Any]:
    """Return project_cross_search schema with optional pagination fields."""
    base = get_project_cross_search_schema()
    return merge_pagination_schema(base)


def document_cross_search_pagination_metadata() -> dict[str, str]:
    """Short pagination parameter descriptions for metadata() reuse."""
    return {
        "paginated": "When true, use SearchSession-backed paginated blocks (default false).",
        "job_id": "Existing paginated search session job_id for continuation.",
        "include_job_id": "Include job_id in paginated handoff responses (default true).",
        "block_position": "1-based block position for paginated block fetch.",
    }
