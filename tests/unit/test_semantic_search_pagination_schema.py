"""Tests for semantic_search pagination schema extension (T-003/A-004)."""
from __future__ import annotations

from code_analysis.commands.semantic_search_pagination_schema import (
    document_semantic_search_pagination_metadata,
    get_semantic_search_schema_with_pagination,
)


def test_schema_includes_optional_pagination_properties() -> None:
    schema = get_semantic_search_schema_with_pagination()
    props = schema["properties"]
    assert "paginated" in props
    assert "job_id" in props
    assert "include_job_id" in props
    assert "block_position" in props


def test_required_list_unchanged() -> None:
    schema = get_semantic_search_schema_with_pagination()
    required = set(schema.get("required") or [])
    for field in ("paginated", "job_id", "include_job_id", "block_position"):
        assert field not in required


def test_metadata_documents_all_four_pagination_fields() -> None:
    meta = document_semantic_search_pagination_metadata()
    for key in ("paginated", "job_id", "include_job_id", "block_position"):
        assert key in meta
